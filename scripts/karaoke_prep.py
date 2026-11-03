#!/usr/bin/env python3
"""Karaoke prep ("the kitchen"): turn songs into ready-to-sing packages.

Per song: the vocal comes out (Demucs by default — it ships with this repo;
karaoke-gen when ``SP404_KARAOKE_BACKEND=karaoke-gen``, or when the web probe
sees that binary or a remote lane), librosa finds tempo + first downbeat, choruses are located from
the repeated lyric blocks, and a drop sheet is drafted for the SP-404A. Output
lives OUTSIDE the sample library (see ``KARAOKE_DIR`` / ``SP404_KARAOKE_DIR``)::

    Karaoke/
      _index.json
      Artist - Title/
        song.json        # bpm, key, beat offset, lyrics source, choruses, drops[], preset
        backing.flac     # instrumental, stereo 44.1k
        backing_bv.flac  # instrumental with the backing vocals kept (karaoke-gen)
        guide.flac       # vocals stem (guide-vocal mode)
        lyrics.lrc  lyrics.ass       # word-timed with karaoke-gen
        lyrics_corrections.json      # karaoke-gen's correction data, for a later review pass
        stems/           # 6-stem split, only with --keep-stems
        cover.jpg        # if the file/folder has art
        video.mp4        # music video for the deck's second screen, only with --videos

karaoke-gen runs as its own install (``SP404_KARAOKE_GEN``, default ``karaoke-gen``
on PATH; models in ``SP404_KARAOKE_GEN_MODELS``). Set ``GENIUS_API_TOKEN`` to add
Genius to the lyrics it corrects against.

Usage::

    python scripts/karaoke_prep.py --playlist Karaoke
    python scripts/karaoke_prep.py --track 123456 --backend demucs --model htdemucs_ft
    python scripts/karaoke_prep.py --file ~/song.flac --artist "Home Front" --title "..."
    python scripts/karaoke_prep.py --playlist Karaoke --refresh   # lyrics + drops only, keep stems
    python scripts/karaoke_prep.py --playlist Karaoke --videos    # + a music video per song (yt-dlp)
    python scripts/karaoke_prep.py --list                          # what's prepped

Hand edits to ``drops`` survive re-runs: set ``"drops_locked": true`` in song.json.
"""
import argparse
import collections
import contextlib
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from queue import SimpleQueue

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings_for_script  # noqa: E402
import karaoke_drops  # noqa: E402
import karaoke_lyrics  # noqa: E402
import karaoke_video  # noqa: E402

SETTINGS = load_settings_for_script(__file__)
KARAOKE_DIR = SETTINGS["KARAOKE_DIR"]
KARAOKE_BACKEND = SETTINGS["KARAOKE_BACKEND"]
KARAOKE_GEN = SETTINGS["KARAOKE_GEN_BIN"]
KARAOKE_GEN_MODELS = SETTINGS["KARAOKE_GEN_MODELS"]
KARAOKE_REMOTE_HOST = SETTINGS["KARAOKE_REMOTE_HOST"]
KARAOKE_REMOTE_LANE = SETTINGS["KARAOKE_REMOTE_LANE"]
KARAOKE_REMOTE_WORK = SETTINGS["KARAOKE_REMOTE_WORK"]
FFMPEG = SETTINGS["FFMPEG_BIN"]
FFPROBE = SETTINGS["FFPROBE_BIN"]
BACKENDS = ("karaoke-gen", "demucs")

SCHEMA_VERSION = 1
# A karaoke-gen transcription further than this from the reference lyrics (word
# error rate), or one that skips more reference words in a row than this, loses
# to hand-synced reference lines. Clean songs: WER ~0.07, runs of 2-4 words.
MAX_TRANSCRIPT_WER = 0.25
MAX_MISSED_WORDS = 10
# The remote lane exits 75 when it gave the GPU back to a game: re-queue the song.
LANE_YIELDED = 75
# The local lane (~15-19 min a song on an M3) only takes a song while the remote
# one (~2 min on GOBLINDRIVER's RTX) is free if this many are still queued.
LOCAL_TAKES_AT = 8
# A song the remote lane can't finish this many times (yields to a game aside) is left to the local lane.
REMOTE_TRIES = 2

HIGH_MOODS = {"aggressive", "energetic", "intense", "fiery", "rousing", "boisterous",
              "volatile", "hostile", "rowdy", "raucous", "exuberant", "anthemic", "celebratory"}
LOW_MOODS = {"mellow", "calm", "peaceful", "serene", "gentle", "meditative",
             "melancholy", "wistful", "tender", "intimate"}

# Plex style/genre keyword → genre preset for banks D-J on karaoke night.
# First match wins, so more specific keywords come first.
STYLE_TO_PRESET = [
    ("riot grrrl", "genre/riot-mode"),
    ("synth-punk", "genre/synth-punk-pogo"),
    ("synthpunk", "genre/synth-punk-pogo"),
    ("synth punk", "genre/synth-punk-pogo"),
    ("coldwave", "genre/synth-punk-pogo"),
    ("new wave", "genre/synth-punk-pogo"),
    ("post-punk", "genre/synth-punk-pogo"),
    ("dance-punk", "genre/electro-sweat"),
    ("pop punk", "genre/pop-punk-nostalgia"),
    ("pop-punk", "genre/pop-punk-nostalgia"),
    ("ska", "genre/riot-mode"),
    ("punk", "genre/riot-mode"),
    ("power metal", "genre/karaoke-metal"),
    ("metal", "genre/karaoke-metal"),
    ("disco", "genre/disco-inferno"),
    ("funk", "genre/funk-muscle"),
    ("soul", "genre/soul-kitchen"),
    ("synth-pop", "genre/synth-pop-dreams"),
    ("synthpop", "genre/synth-pop-dreams"),
    ("electroclash", "genre/electroclash"),
    ("house", "genre/french-filter-house"),
    ("big beat", "genre/big-beat-blowout"),
    ("hip hop", "genre/boom-bap-cipher"),
    ("hip-hop", "genre/boom-bap-cipher"),
    ("rap", "genre/boom-bap-cipher"),
    ("reggae", "genre/dub-cooldown"),
    ("dub", "genre/dub-cooldown"),
    ("dancehall", "genre/caribbean-heat"),
    ("country", "genre/outlaw-country-kitchen"),
    ("americana", "genre/outlaw-country-kitchen"),
    ("pop", "genre/brat-mode"),
]


# ── Small helpers ────────────────────────────────────────────────────

def safe_dirname(artist, title):
    name = f"{artist or 'Unknown'} - {title or 'Untitled'}"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)  # Windows-safe too (robocopy target)
    return name.strip(" .")[:120] or "Untitled"


def infer_energy(moods):
    lower = {str(m).lower() for m in (moods or [])}
    if lower & HIGH_MOODS:
        return "high"
    if lower & LOW_MOODS:
        return "low"
    return "mid"


def suggest_preset(styles=(), genres=()):
    haystack = " | ".join(str(s).lower() for s in list(styles or []) + list(genres or []))
    for needle, preset in STYLE_TO_PRESET:
        if needle in haystack:
            return preset
    return None


def probe_duration(path):
    try:
        out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path],
                             capture_output=True, text=True, timeout=30)
        return round(float(out.stdout.strip()), 3)
    except Exception:
        return None


def to_flac(src, dst):
    """Stereo 44.1k FLAC. SP-404 mono rule is for the SD card only, not this."""
    result = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", src, "-ar", "44100", "-ac", "2",
                             "-c:a", "flac", dst], capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg flac failed: {result.stderr[:200]}")


def extract_cover(audio_path, dst):
    """Folder art (cover/folder.jpg) or embedded art. Returns True if written."""
    folder = os.path.dirname(audio_path)
    for name in ("cover.jpg", "folder.jpg", "Cover.jpg", "Folder.jpg", "cover.png", "folder.png"):
        cand = os.path.join(folder, name)
        if os.path.isfile(cand):
            shutil.copyfile(cand, dst)
            return True
    try:
        res = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", audio_path, "-an",
                              "-frames:v", "1", dst], capture_output=True, timeout=30)
        return res.returncode == 0 and os.path.isfile(dst) and os.path.getsize(dst) > 0
    except Exception:
        return False


def analyze(path):
    """BPM, first downbeat, key, duration. librosa optional; degrades to ffprobe."""
    info = {"bpm": None, "first_beat_s": None, "key": None, "duration_s": None}
    try:
        import audio_analysis
        if audio_analysis.is_available():
            import librosa
            y, sr = librosa.load(path, sr=22050, mono=True)
            grid = audio_analysis.detect_beat_grid(y, sr)
            info.update(bpm=grid["bpm"], first_beat_s=grid["first_beat_s"],
                        key=audio_analysis.detect_key(y, sr),
                        duration_s=round(len(y) / sr, 3))
    except Exception as exc:
        print(f"    analysis skipped: {exc}")
    if not info["duration_s"]:
        info["duration_s"] = probe_duration(path)
    return info


# ── Core ─────────────────────────────────────────────────────────────

def _source_kind(meta):
    """``upload``, ``plex``, or ``file``. A missing value follows plex_id."""
    kind = meta.get("source_kind")
    if kind in ("file", "upload", "plex"):
        return kind
    return "plex" if meta.get("id") else "file"


def load_song_json(song_dir):
    path = os.path.join(song_dir, "song.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def separate(audio_path, song_dir, model):
    """Demucs two-stem split → backing.flac + guide.flac."""
    from stem_split import run_demucs
    with tempfile.TemporaryDirectory(prefix="karaoke_") as tmp:
        stems = dict(run_demucs(audio_path, tmp, model=model, two_stems="vocals", timeout=1800))
        if "no_vocals" not in stems:
            raise RuntimeError("Demucs produced no backing track (is demucs installed?)")
        to_flac(stems["no_vocals"], os.path.join(song_dir, "backing.flac"))
        if "vocals" in stems:
            to_flac(stems["vocals"], os.path.join(song_dir, "guide.flac"))


def _karaoke_gen_files(track_dir):
    """Find karaoke-gen's outputs in one track folder.

    The clean instrumental is named after its model; the guide is that same
    model's vocal stem, not the 6-stem or lead/backing split's.
    """
    root = glob.escape(track_dir)

    def first(pattern):
        hits = sorted(glob.glob(os.path.join(root, pattern)))
        return hits[0] if hits else None

    clean = next((p for p in sorted(glob.glob(os.path.join(root, "*(Instrumental *).flac")))
                  if "(Instrumental +BV" not in p), None)
    model = re.search(r"\(Instrumental (.+)\)\.flac$", clean).group(1) if clean else None
    return {
        "clean": clean,
        "model": model,
        "backing_vocals": first("*(Instrumental +BV*).flac"),
        "guide": first(os.path.join("stems", f"*(Vocals {glob.escape(model)}).flac")) if model else None,
        "lrc": first(os.path.join("lyrics", "*(Karaoke).lrc")),
        "corrections": first(os.path.join("lyrics", "*(Lyrics Corrections).json")),
        "stems": sorted(glob.glob(os.path.join(root, "stems", "*.flac"))),
    }


def vocal_presence(path, *, hop_s=0.05, floor_db=15.0):
    """``sung(t0, t1)``: the share of a span where the separated vocal is audible, or None.

    A frame counts as sung when it is within ``floor_db`` of the stem's loud
    end (95th percentile), which still separates singing from the instrumental
    bleed every separated vocal carries.
    """
    if not os.path.isfile(path):
        return None
    try:
        import numpy as np
        import soundfile as sf
        audio, rate = sf.read(path, dtype="float32", always_2d=True)
    except Exception:
        return None
    mono = audio.mean(axis=1)
    hop = max(1, int(rate * hop_s))
    frames = len(mono) // hop
    if not frames:
        return None
    level = 20 * np.log10(np.sqrt((mono[:frames * hop].reshape(frames, hop) ** 2).mean(axis=1)) + 1e-9)
    active = level > np.percentile(level, 95) - floor_db

    def sung(t0, t1):
        a = int(t0 / hop_s)
        span = active[a:max(int(t1 / hop_s), a + 1)]
        return float(span.mean()) if len(span) else 0.0
    return sung


def karaoke_gen_args(audio_path, out_dir, *, artist=None, title=None, lyrics_file=None, lyrics_only=False):
    """karaoke-gen's arguments: prep phase only, unattended, no video, into ``out_dir``."""
    args = ["--lyrics-only" if lyrics_only else "--prep-only", "-y", "--skip_transcription_review",
            "--skip_instrumental_review", "--no-video", "--output_dir", out_dir]
    if lyrics_file:
        args += ["--lyrics_file", lyrics_file]
    args.append(audio_path)
    if artist and title:
        args += [artist, title]
    return args


class LaneUnavailable(RuntimeError):
    """The remote lane couldn't finish this song (unreachable, timed out); it goes back in the queue."""


class LaneYielded(LaneUnavailable):
    """The remote lane gave its GPU back to a game mid-song."""


class RemoteLane:
    """karaoke-gen on another machine's GPU (GOBLINDRIVER), through its ``lane.cmd`` over ssh/scp.

    ``lane.cmd check`` exits 0 while the GPU is free for karaoke (no game,
    stream or other job). ``lane.cmd run <job> <karaoke-gen args>`` runs in
    ``<work>\\<job>\\out`` with its own model folder and exits 75 when it yields
    the GPU to a game. Audio goes up as ``in\\input<ext>`` and the artist/title
    as ``in\\meta.json`` (UTF-8), so names never pass through cmd.exe or file
    names; the lane appends them to karaoke-gen's arguments itself. The job
    folder is removed afterwards. A transport failure (the machine asleep,
    rebooting, off the network) raises ``LaneUnavailable``, and a run that
    didn't come back is stopped so it can't hold the GPU.
    """

    TRANSPORT_ERRORS = (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError)
    SSH_FAILED = 255  # ssh's own exit status when the connection fails

    def __init__(self, host, lane=KARAOKE_REMOTE_LANE, work=KARAOKE_REMOTE_WORK, *, run=subprocess.run):
        self.name = host
        self.host, self.lane, self.work, self._run = host, lane, work.rstrip("\\"), run

    def _ssh(self, command, **kwargs):
        return self._run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "LogLevel=ERROR",
                          self.host, command], stdin=subprocess.DEVNULL, **kwargs)

    def _scp(self, *args, **kwargs):
        return self._run(["scp", "-q", "-o", "BatchMode=yes", "-o", "LogLevel=ERROR", *args],
                         stdin=subprocess.DEVNULL, **kwargs)

    def _path(self, *parts):
        return "\\".join([self.work, *parts])

    def _scp_path(self, *parts):
        return f"{self.host}:" + self._path(*parts).replace("\\", "/")

    def free(self):
        """``(free, reason)`` from ``lane.cmd check``; an unreachable lane is busy."""
        try:
            res = self._ssh(f"{self.lane} check", capture_output=True, text=True, timeout=60)
        except self.TRANSPORT_ERRORS as exc:
            return False, f"unreachable: {exc}"
        return res.returncode == 0, (res.stdout or res.stderr or "").strip()

    def run(self, audio_path, out_dir, *, artist=None, title=None, lyrics_file=None, lyrics_only=False,
            log_fh=None):
        """Run karaoke-gen remotely and copy its output into ``out_dir``. Returns its exit code."""
        job = f"citadel-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{os.urandom(2).hex()}"
        audio_name = "input" + os.path.splitext(audio_path)[1].lower()
        sent = came_back = False
        try:
            try:
                self._upload(job, audio_path, audio_name, lyrics_file, artist, title)
                args = karaoke_gen_args(self._path(job, "in", audio_name), self._path(job, "out"),
                                        lyrics_file=self._path(job, "in", "lyrics.txt") if lyrics_file else None,
                                        lyrics_only=lyrics_only)
                sent = True
                res = self._ssh(f"{self.lane} run {job} " + " ".join(f'"{a}"' for a in args),
                                stdout=log_fh, stderr=subprocess.STDOUT, timeout=3600)
                if res.returncode == self.SSH_FAILED:
                    raise LaneUnavailable(f"{self.name}: connection lost during the run")
                came_back = True
                if res.returncode != LANE_YIELDED:
                    self._fetch(job, out_dir)
                if log_fh is not None:
                    self._append_log(job, log_fh)
            except self.TRANSPORT_ERRORS as exc:
                raise LaneUnavailable(f"{self.name} unavailable: {exc}") from exc
            return res.returncode
        finally:
            # Stop only a run this call sent and lost track of; a failed upload never started
            # one, and stopping then could end another dispatcher's job.
            stop = [f"{self.lane} stop"] if sent and not came_back else []
            for command in stop + [f'rmdir /s /q "{self._path(job)}"']:
                try:
                    self._ssh(command, capture_output=True, timeout=60)
                except self.TRANSPORT_ERRORS:
                    pass

    def _upload(self, job, audio_path, audio_name, lyrics_file, artist, title):
        self._ssh(f'mkdir "{self._path(job, "in")}"', check=True, capture_output=True, timeout=60)
        self._scp(audio_path, self._scp_path(job, "in", audio_name), check=True, timeout=900)
        if lyrics_file:
            self._scp(lyrics_file, self._scp_path(job, "in", "lyrics.txt"), check=True, timeout=120)
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = os.path.join(tmp, "meta.json")
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump({k: v for k, v in (("artist", artist), ("title", title)) if v}, fh, ensure_ascii=False)
            self._scp(meta_path, self._scp_path(job, "in", "meta.json"), check=True, timeout=120)

    def _fetch(self, job, out_dir):
        # Fetch beside out_dir, not into it: the importer expects one track folder there.
        with tempfile.TemporaryDirectory(dir=os.path.dirname(out_dir)) as fetched:
            self._scp("-r", self._scp_path(job, "out"), fetched, check=True, timeout=900)
            remote_out = os.path.join(fetched, "out")
            for name in os.listdir(remote_out) if os.path.isdir(remote_out) else ():
                shutil.move(os.path.join(remote_out, name), os.path.join(out_dir, name))

    def _append_log(self, job, log_fh):
        with tempfile.TemporaryDirectory() as tmp:
            remote_log = os.path.join(tmp, "karaoke-gen.log")
            if self._scp(self._scp_path(job, "karaoke-gen.log"), remote_log, timeout=120).returncode == 0:
                with open(remote_log, encoding="utf-8", errors="replace") as fh:
                    log_fh.write(f"--- {self.name} {job} ---\n{fh.read()}")


def separate_with_karaoke_gen(audio_path, song_dir, *, artist=None, title=None, lyrics_file=None,
                              keep_stems=False, lyrics_only=False, lane=None, runner=subprocess.run):
    """karaoke-gen's prep phase → backing, backing_bv and guide FLACs plus word-timed lyrics.

    karaoke-gen works in a scratch folder inside the song folder that is removed
    afterwards; its log stays as ``karaoke-gen.log``. Auto-correction is on
    (karaoke-gen's default leaves raw Whisper text for a human review step).
    ``lyrics_only`` re-transcribes without separating and leaves the audio alone.
    ``lane`` (a ``RemoteLane``) runs it on another machine's GPU instead.
    Returns ``{"lines", "lyrics_source", "model", "references"}``.
    """
    log_path = os.path.join(song_dir, "karaoke-gen.log")
    with tempfile.TemporaryDirectory(prefix="_karaoke-gen-", dir=song_dir) as work:
        with open(log_path, "w", encoding="utf-8") as log_fh:
            if lane is not None:
                returncode = lane.run(audio_path, work, artist=artist, title=title, lyrics_file=lyrics_file,
                                      lyrics_only=lyrics_only, log_fh=log_fh)
            else:
                if runner is subprocess.run and not shutil.which(KARAOKE_GEN):
                    raise RuntimeError(f"karaoke-gen not found at {KARAOKE_GEN!r}; set SP404_KARAOKE_GEN to it")
                cmd = [KARAOKE_GEN] + karaoke_gen_args(audio_path, work, artist=artist, title=title,
                                                       lyrics_file=lyrics_file, lyrics_only=lyrics_only)
                if KARAOKE_GEN_MODELS:
                    cmd[1:1] = ["--model_file_dir", KARAOKE_GEN_MODELS]
                env = dict(os.environ, SKIP_CORRECTION="false")
                if os.path.dirname(FFMPEG):
                    env["PATH"] = os.pathsep.join([os.path.dirname(FFMPEG), env.get("PATH", "")])
                returncode = runner(cmd, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=log_fh,
                                    stderr=subprocess.STDOUT, timeout=3600).returncode
        if lane is not None and returncode == LANE_YIELDED:
            raise LaneYielded(f"{lane.name} yielded its GPU; see {log_path}")

        tracks = [d for d in glob.glob(os.path.join(glob.escape(work), "*")) if os.path.isdir(d)]
        files = _karaoke_gen_files(tracks[0]) if len(tracks) == 1 else {}
        if lyrics_only:
            if not files.get("lrc"):
                raise RuntimeError(f"karaoke-gen made no lyrics (exit {returncode}); see {log_path}")
        elif not files.get("clean"):
            raise RuntimeError(f"karaoke-gen made no instrumental (exit {returncode}); see {log_path}")
        else:
            to_flac(files["clean"], os.path.join(song_dir, "backing.flac"))
            for key, name in (("backing_vocals", "backing_bv.flac"), ("guide", "guide.flac")):
                if files[key]:
                    to_flac(files[key], os.path.join(song_dir, name))
        if files["corrections"]:
            shutil.copyfile(files["corrections"], os.path.join(song_dir, "lyrics_corrections.json"))
        if keep_stems and files["stems"]:
            os.makedirs(os.path.join(song_dir, "stems"), exist_ok=True)
            for stem in files["stems"]:
                shutil.copyfile(stem, os.path.join(song_dir, "stems", os.path.basename(stem)))
        lines, references = [], []
        if files["lrc"]:
            with open(files["lrc"], encoding="utf-8") as fh:
                lines = karaoke_lyrics.parse_midico(fh.read())
            lines = karaoke_lyrics.tighten_word_gaps(karaoke_lyrics.drop_word_loops(lines),
                                                     sung=vocal_presence(os.path.join(song_dir, "guide.flac")))
        if files["corrections"]:
            with open(files["corrections"], encoding="utf-8") as fh:
                references = sorted((json.load(fh).get("reference_lyrics") or {}).keys())
    return {"lines": lines, "lyrics_source": "karaoke-gen" if lines else None, "model": files["model"],
            "references": references}


_reference_cache = {}
_reference_pending = {}  # key -> Event while one lookup for it is in flight
_reference_lock = threading.Lock()


def _meta_duration(meta):
    return meta.get("duration_s") or (meta["duration"] / 1000.0 if meta.get("duration") else None)


def reference_lyrics(meta, *, online=True):
    """``(lines, source, plain)`` from a ``.lrc`` beside the audio or LRCLIB, looked up once per song.

    LRCLIB answers 503 for minutes at a time, so a lookup retries with backoff;
    the result is kept for an hour (a miss for ten minutes) so karaoke-gen's
    input and the quality check share one lookup, and ``prep_batch`` warms it
    for the whole queue before any GPU lane needs it.
    """
    key = (meta.get("file_path"), meta.get("artist"), meta.get("title"), meta.get("album"), online)
    while True:
        with _reference_lock:
            cached = _reference_cache.get(key)
            if cached and cached[0] > time.time():
                return cached[1]
            pending = _reference_pending.get(key)
            if pending is None:  # nobody is asking yet: this call does
                pending = _reference_pending[key] = threading.Event()
                break
        pending.wait()  # the prefetch and a lane want the same song: wait for its answer
    try:
        found = karaoke_lyrics.find_lyrics(meta.get("file_path"), meta.get("artist"), meta.get("title"),
                                           meta.get("album"), _meta_duration(meta), online=online, retries=4)
        with _reference_lock:
            _reference_cache[key] = (time.time() + (600 if found[1] == "none" else 3600), found)
        return found
    finally:
        with _reference_lock:
            _reference_pending.pop(key, None)
        pending.set()


@contextlib.contextmanager
def reference_lyrics_file(reference):
    """Reference lyrics as a text file for karaoke-gen to correct its transcription against, or None.

    ``reference`` is ``reference_lyrics()``'s result. A hand-placed ``.lrc``
    always goes in. LRCLIB's lyrics go in without a Genius token, when LRCLIB
    is karaoke-gen's only source anyway and they're already fetched; with
    ``GENIUS_API_TOKEN`` set this yields None and karaoke-gen asks LRCLIB and
    Genius itself, which a lyrics file would switch off.
    """
    lines, source, plain = reference
    texts = []
    if source == "sidecar" or (source != "none" and not os.environ.get("GENIUS_API_TOKEN")):
        if plain:
            texts = [row.strip() for row in plain.splitlines() if row.strip()]
        else:
            texts = [ln.text for ln in lines if ln.text.strip()]
    if not texts:
        yield None
        return
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as fh:
        fh.write("\n".join(texts) + "\n")
    try:
        yield fh.name
    finally:
        os.unlink(fh.name)


def choose_lyrics(transcribed, reference_lines, reference_plain, reference_source, *,
                  max_wer=MAX_TRANSCRIPT_WER, max_missed=MAX_MISSED_WORDS):
    """Keep karaoke-gen's word-timed lines unless they stray from the reference lyrics.

    Whisper can loop on one word through a whole verse ("la la la" over "Now
    that I've lost everything to you"), and correction can't restore words it
    never heard. Past ``max_wer`` against the reference, or with more than
    ``max_missed`` reference words skipped in a row, hand-synced reference
    lines (line timing, right words) win; with only plain reference text the
    transcription stays. Returns ``(lines, source, wer)``; ``wer`` is None
    without a reference.
    """
    reference = karaoke_lyrics.lyric_words(reference_plain or " ".join(ln.text for ln in reference_lines))
    if not reference:
        return transcribed, "karaoke-gen", None
    heard = karaoke_lyrics.lyric_words(" ".join(ln.text for ln in transcribed))
    wer = round(karaoke_lyrics.word_error_rate(reference, heard), 3)
    strayed = wer > max_wer or karaoke_lyrics.longest_missed_run(reference, heard) > max_missed
    if strayed and reference_lines:
        return reference_lines, reference_source, wer
    return transcribed, "karaoke-gen", wer


def _separator_for(backend, meta, keep_stems, online, lyrics_only=False, lane=None):
    if backend == "demucs":
        return separate

    def run(audio_path, song_dir, _model):
        with reference_lyrics_file(reference_lyrics(meta, online=online)) as lyrics_file:
            return separate_with_karaoke_gen(audio_path, song_dir, artist=meta.get("artist"),
                                             title=meta.get("title"), lyrics_file=lyrics_file,
                                             keep_stems=keep_stems, lyrics_only=lyrics_only, lane=lane)
    return run


def prep_song(meta, *, out_root=None, model="htdemucs", refresh=False, force=False,
              online=True, separator=None, backend=None, keep_stems=False, relyric=False, lane=None,
              log=print):
    """Prepare one song. ``meta`` needs ``file_path``; artist/title/album,
    duration (ms, Plex style) or duration_s, moods, styles, genres, id are optional.

    ``backend``: ``karaoke-gen`` or ``demucs`` (default ``SP404_KARAOKE_BACKEND``);
    ``model`` only applies to Demucs.
    ``refresh``: keep existing stems, redo analysis/lyrics/drops (karaoke-gen's
    word-timed lyrics are kept too).
    ``relyric``: keep existing stems, re-transcribe the lyrics with karaoke-gen
    (e.g. once LRCLIB is reachable or a Genius token is set).
    ``lane``: a ``RemoteLane`` to run karaoke-gen on (raises ``LaneYielded`` if it gives the GPU back).
    ``separator``: injectable for tests; may return
    ``{"lines", "lyrics_source", "model", "references"}``.
    Returns the song.json dict.
    """
    out_root = out_root or KARAOKE_DIR
    backend = backend or KARAOKE_BACKEND
    if backend not in BACKENDS:
        raise ValueError(f"unknown karaoke backend {backend!r}")
    audio_path = meta.get("file_path")
    if not audio_path:
        raise FileNotFoundError("audio not found: no file_path")
    artist, title = meta.get("artist"), meta.get("title")
    if not title:
        title = os.path.splitext(os.path.basename(audio_path))[0]
    song_dir = os.path.join(out_root, safe_dirname(artist, title))
    existing = load_song_json(song_dir) or {}
    backing = os.path.join(song_dir, "backing.flac")

    label = f"{artist or '?'} - {title}"
    prepped = os.path.isfile(backing) and not force
    if prepped and not relyric and not refresh:  # needs nothing from the source (its drive may be offline)
        log(f"  = {label} (already prepped; --refresh to redo lyrics/drops, --force to re-split)")
        return existing
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"audio not found: {audio_path}")
    os.makedirs(song_dir, exist_ok=True)
    meta = dict(meta, artist=artist, title=title)
    separated = None   # a separation run's result; None keeps the existing stems
    relyriced = None   # a lyrics-only karaoke-gen run's result
    if prepped:
        if relyric:
            log(f"  ~ {label}: re-transcribing lyrics (karaoke-gen)...")
            t0 = time.time()
            transcribe = separator or _separator_for("karaoke-gen", meta, False, online, lyrics_only=True,
                                                     lane=lane)
            relyriced = transcribe(audio_path, song_dir, model) or {}
            log(f"    lyrics done in {time.time() - t0:.0f}s")
        else:
            log(f"  ~ {label}: refreshing lyrics + drops")
    else:
        where = f" on {lane.name}" if lane is not None and backend != "demucs" else ""
        log(f"  + {label}: separating vocals ({model if backend == 'demucs' else backend}{where})...")
        t0 = time.time()
        split = separator or _separator_for(backend, meta, keep_stems, online, lane=lane)
        separated = split(audio_path, song_dir, model) or {}
        log(f"    stems done in {time.time() - t0:.0f}s")

    # Analyse the backing (drums intact, no vocal smear) — falls back to the source.
    info = analyze(backing if os.path.isfile(backing) else audio_path)
    if meta.get("duration_s"):
        info["duration_s"] = info["duration_s"] or meta["duration_s"]
    elif meta.get("duration"):
        info["duration_s"] = info["duration_s"] or round(meta["duration"] / 1000.0, 3)
    duration_s = info["duration_s"]

    lrc_path = os.path.join(song_dir, "lyrics.lrc")
    fresh = separated or relyriced
    lyrics_wer = existing.get("lyrics_wer") if separated is None and relyriced is None else None
    if fresh and fresh.get("lines"):
        ref_lines, ref_source, ref_plain = reference_lyrics(meta, online=online)
        lines, lyrics_source, lyrics_wer = choose_lyrics(fresh["lines"], ref_lines, ref_plain, ref_source)
        plain = None
        if lyrics_source != "karaoke-gen":
            log(f"    transcription strayed from the lyrics (WER {lyrics_wer}); using {lyrics_source}'s sync")
    elif separated is None and existing.get("lyrics_source") == "karaoke-gen" and os.path.isfile(lrc_path):
        with open(lrc_path, encoding="utf-8") as fh:  # a refresh keeps the word-timed lyrics
            lines, lyrics_source, plain = karaoke_lyrics.parse_lrc(fh.read()), "karaoke-gen", None
    else:
        lines, lyrics_source, plain = karaoke_lyrics.find_lyrics(
            audio_path, artist, title, meta.get("album"), duration_s, online=online)
    display = f"{artist} - {title}" if artist else title
    if lines:
        with open(lrc_path, "w", encoding="utf-8") as fh:
            fh.write(karaoke_lyrics.format_lrc(lines, artist=artist, title=title))
        ass = karaoke_lyrics.render_ass(lines, title=display, duration_s=duration_s)
    elif plain:
        with open(os.path.join(song_dir, "lyrics.txt"), "w", encoding="utf-8") as fh:
            fh.write(plain)
        ass = karaoke_lyrics.plain_to_ass(plain, title=display, duration_s=duration_s)
    else:
        ass = karaoke_lyrics.render_ass([karaoke_lyrics.LyricLine(0.0, display)],
                                        title=display, duration_s=duration_s, countdown=False)
    with open(os.path.join(song_dir, "lyrics.ass"), "w", encoding="utf-8") as fh:
        fh.write(ass)

    if not os.path.isfile(os.path.join(song_dir, "cover.jpg")):
        extract_cover(audio_path, os.path.join(song_dir, "cover.jpg"))

    choruses = karaoke_lyrics.find_choruses(lines)
    sung = [ln.t for ln in lines if ln.text.strip()]
    energy = infer_energy(meta.get("moods"))
    if existing.get("drops_locked"):
        drops = karaoke_drops.validate_drops(existing.get("drops"))
    else:
        drops = karaoke_drops.draft_drop_sheet(
            duration_s=duration_s, bpm=info["bpm"], first_beat_s=info["first_beat_s"],
            choruses=choruses, first_vocal_s=sung[0] if sung else None,
            last_vocal_s=sung[-1] if sung else None, energy=energy)

    if separated is not None:
        separator_name = backend
        separation_model = separated.get("model") or model
        references = separated.get("references") or []
    else:
        separator_name = existing.get("separator") or "demucs"
        separation_model = existing.get("separation_model") or existing.get("demucs_model")
        if relyriced is not None:
            references = relyriced.get("references") or []
        else:
            references = existing.get("lyrics_references") or []

    song = {
        "schema": SCHEMA_VERSION,
        "artist": artist,
        "title": title,
        "album": meta.get("album"),
        "plex_id": meta.get("id"),
        "source_path": audio_path,
        "source_kind": _source_kind(meta),
        "duration_s": duration_s,
        "bpm": info["bpm"],
        "key": info["key"],
        "beat_offset_s": info["first_beat_s"],
        "energy": energy,
        "moods": meta.get("moods") or [],
        "styles": meta.get("styles") or [],
        "separator": separator_name,
        "separation_model": separation_model,
        "demucs_model": separation_model if separator_name == "demucs" else None,
        "lyrics_source": lyrics_source,
        # karaoke-gen's transcription was corrected against these (empty = unchecked Whisper; review it)
        "lyrics_references": references if lyrics_source == "karaoke-gen" else [],
        # word error rate of karaoke-gen's transcription against the reference lyrics (None: no reference)
        "lyrics_wer": lyrics_wer,
        "has_lyrics": bool(lines),
        "choruses": [list(c) for c in choruses],
        "preset": existing.get("preset") or suggest_preset(meta.get("styles"), meta.get("genres")),
        "drops": drops,
        "drops_locked": bool(existing.get("drops_locked")),
        "video": existing.get("video"),  # kept: fetched once by prep_video, same song timeline
        "prepped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    write_json(os.path.join(song_dir, "song.json"), song)
    log(f"    bpm={song['bpm']} key={song['key']} lyrics={lyrics_source} "
        f"choruses={len(choruses)} drops={len(drops)} preset={song['preset']}")
    return song


def prep_video(meta, *, out_root=None, refresh=False, log=print, fetch=None):
    """Give a prepped song its music video (``karaoke_video``) and note it in song.json.

    A video already there is kept unless ``refresh``; when nothing better turns
    up the old one stays too. It's aligned against the source track (falling
    back to the backing when the source drive is gone). ``fetch`` is injectable
    for tests. Returns the song's ``video`` entry, or None.
    """
    out_root = out_root or KARAOKE_DIR
    audio_path = meta.get("file_path")
    artist, title = meta.get("artist"), meta.get("title")
    if not title:
        title = os.path.splitext(os.path.basename(audio_path or ""))[0]
    song_dir = os.path.join(out_root, safe_dirname(artist, title))
    song = load_song_json(song_dir)
    if not song:
        raise FileNotFoundError(f"not prepped yet: {artist or '?'} - {title}")
    current = song.get("video")
    if current and os.path.isfile(os.path.join(song_dir, current.get("file") or "")) and not refresh:
        return current
    source = audio_path or song.get("source_path")
    mix = source if source and os.path.isfile(source) else os.path.join(song_dir, "backing.flac")
    log(f"  ▶ {artist or '?'} - {title}: looking for a music video...")
    video = (fetch or karaoke_video.fetch_video)(
        song_dir, mix, source_path=source, artist=artist, title=title,
        duration_s=song.get("duration_s"), log=log)
    if video is None:
        return current
    song = load_song_json(song_dir) or song  # re-read: a drop-sheet save may have landed meanwhile
    song["video"] = video
    write_json(os.path.join(song_dir, "song.json"), song)
    return video


def rebuild_index(out_root=None):
    """Scan song folders and write ``_index.json`` (what the deck's queue reads)."""
    out_root = out_root or KARAOKE_DIR
    songs = []
    if os.path.isdir(out_root):
        for name in sorted(os.listdir(out_root), key=str.lower):
            song_dir = os.path.join(out_root, name)
            data = load_song_json(song_dir) if os.path.isdir(song_dir) else None
            if not data or not os.path.isfile(os.path.join(song_dir, "backing.flac")):
                continue
            songs.append({
                "dir": name,
                "artist": data.get("artist"),
                "title": data.get("title"),
                "bpm": data.get("bpm"),
                "key": data.get("key"),
                "duration_s": data.get("duration_s"),
                "energy": data.get("energy"),
                "has_lyrics": data.get("has_lyrics"),
                "has_guide": os.path.isfile(os.path.join(song_dir, "guide.flac")),
                "has_backing_vocals": os.path.isfile(os.path.join(song_dir, "backing_bv.flac")),
                "has_video": bool(data.get("video")) and os.path.isfile(
                    os.path.join(song_dir, data["video"].get("file") or "")),
                "lyrics_source": data.get("lyrics_source"),
                "lyrics_need_review": data.get("lyrics_source") == "karaoke-gen" and (
                    not data.get("lyrics_references") or data.get("lyrics_wer") is None
                    or data["lyrics_wer"] > MAX_TRANSCRIPT_WER),
                "preset": data.get("preset"),
                "drops": len(data.get("drops") or []),
            })
    os.makedirs(out_root, exist_ok=True)
    write_json(os.path.join(out_root, "_index.json"),
               {"schema": SCHEMA_VERSION, "count": len(songs), "songs": songs})
    return songs


def prep_batch(tracks, *, lane=None, local=True, on_start=None, on_done=None, log=print, poll_s=60,
               videos=False, revideo=False, video_only=False, on_video=None, **prep_kwargs):
    """Prep songs on this machine's GPU and a remote lane at the same time.

    The remote lane takes the next song whenever ``lane.free()`` says its GPU is
    free. The local lane takes one while the remote is busy (a game is running,
    or it is unreachable) or while ``LOCAL_TAKES_AT``+ songs are waiting, since
    one local song takes about as long as eight remote ones. A song the lane
    yields or can't finish goes back to the front of the queue; after
    ``REMOTE_TRIES`` failures (yields to a game don't count) it is left to the
    local lane. The local lane stays until nothing is queued or in flight
    remotely, so a late yield never
    strands a song. ``on_start(meta, where)`` and ``on_done(meta, error)``
    report progress. Returns ``(done, failed)``.

    ``videos``: each song that preps (or was prepped already) then gets a music
    video (``prep_video``; ``revideo`` re-fetches) on a thread of its own, so
    downloads never hold a GPU lane. ``on_video(meta, video, error)`` reports
    each; a missing video doesn't fail the song.

    ``video_only``: the songs are prepped already, so skip prep (and the lanes:
    no ssh, no lyrics lookups) and only fetch their videos; ``on_start`` and
    ``on_done`` then report the video work, and a video that errors fails it.
    """
    seen, unique = set(), []
    for meta in tracks:  # the same file twice would prep one folder on both lanes at once
        key = meta.get("file_path") or id(meta)
        if key not in seen:
            seen.add(key)
            unique.append(meta)
    queue = collections.deque(unique)
    video_todo = SimpleQueue() if videos or revideo or video_only else None
    cond = threading.Condition()
    state = {"done": 0, "failed": 0, "remote_free": lane is not None, "remote_busy": 0}
    remote_tries = collections.Counter()

    def prep(meta, use_lane):
        label = f"{meta.get('artist') or '?'} - {meta.get('title') or '?'}"
        if on_start:
            on_start(meta, use_lane.name if use_lane else "local")
        try:
            prep_song(meta, lane=use_lane, log=log, **prep_kwargs)
            error = None
        except LaneUnavailable as exc:
            log(f"  ↺ {label}: {exc}; back in the queue")
            with cond:
                state["remote_free"] = False
                if not isinstance(exc, LaneYielded):  # a game yield isn't the lane failing
                    remote_tries[id(meta)] += 1
                queue.appendleft(meta)
                cond.notify_all()
            return
        except Exception as exc:  # keep going; one bad file shouldn't kill a batch
            log(f"  ! {label}: {exc}")
            error = exc
        with cond:
            state["failed" if error else "done"] += 1
            cond.notify_all()
        if on_done:
            on_done(meta, error)
        if video_todo is not None and error is None:
            video_todo.put(meta)

    def video_worker():
        while (meta := video_todo.get()) is not None:
            if video_only and on_start:
                on_start(meta, "video")
            try:
                video, error = prep_video(meta, out_root=prep_kwargs.get("out_root"), refresh=revideo,
                                          log=log), None
            except Exception as exc:  # the song is still singable without one
                video, error = None, exc
                log(f"  ! video for {meta.get('artist') or '?'} - {meta.get('title') or '?'}: {exc}")
            if on_video:
                on_video(meta, video, error)
            if video_only:  # nothing else happens to these songs
                with cond:
                    state["failed" if error else "done"] += 1
                if on_done:
                    on_done(meta, error)

    def next_for_remote():
        for meta in queue:
            if remote_tries[id(meta)] < REMOTE_TRIES:
                queue.remove(meta)
                return meta
        return None

    def remote_worker():
        try:
            while True:
                with cond:
                    if not any(remote_tries[id(m)] < REMOTE_TRIES for m in queue):
                        return
                free, why = lane.free()
                with cond:
                    if free != state["remote_free"]:
                        log(f"  {lane.name}: {'free' if free else 'busy (' + why + ')'}")
                    state["remote_free"] = free
                    cond.notify_all()
                    if not free:
                        cond.wait(poll_s)
                        continue
                    meta = next_for_remote()
                    if meta is None:
                        return
                    state["remote_busy"] += 1
                    cond.notify_all()
                try:
                    prep(meta, lane)
                finally:
                    with cond:
                        state["remote_busy"] -= 1
                        cond.notify_all()
        finally:
            with cond:
                state["remote_free"] = False
                cond.notify_all()

    def local_worker():
        while True:
            with cond:
                while (queue and state["remote_free"] and len(queue) < LOCAL_TAKES_AT
                       and any(remote_tries[id(m)] < REMOTE_TRIES for m in queue)) \
                        or (not queue and state["remote_busy"]):
                    cond.wait(poll_s)
                if not queue:
                    return
                meta = queue.popleft()
            prep(meta, None)

    if video_only:
        queue.clear()
        for meta in unique:
            video_todo.put(meta)
    elif (prep_kwargs.get("backend") or KARAOKE_BACKEND) == "karaoke-gen":
        # Look every song's reference lyrics up front, so no GPU lane waits on LRCLIB.
        online = prep_kwargs.get("online", True)
        threading.Thread(target=lambda: [reference_lyrics(m, online=online) for m in unique],
                         name="lyrics-prefetch", daemon=True).start()
    video_thread = None
    if video_todo is not None:
        video_thread = threading.Thread(target=video_worker, name="videos")
        video_thread.start()
    workers = []
    if lane is not None and not video_only:
        workers.append(threading.Thread(target=remote_worker, name=f"lane-{lane.name}"))
    if (local or lane is None) and not video_only:
        workers.append(threading.Thread(target=local_worker, name="lane-local"))
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    if video_thread is not None:
        video_todo.put(None)
        video_thread.join()
    for meta in queue:  # remote-only, and the lane gave up on these
        state["failed"] += 1
        error = LaneUnavailable(f"{lane.name} couldn't finish it after {REMOTE_TRIES} tries")
        log(f"  ! {meta.get('artist') or '?'} - {meta.get('title') or '?'}: {error}")
        if on_done:
            on_done(meta, error)
    return state["done"], state["failed"]


def _plex():
    from plex_client import PlexMusicDB
    return PlexMusicDB()


def resolve_tracks(args):
    if args.file:
        return [{"file_path": os.path.expanduser(args.file), "artist": args.artist,
                 "title": args.title, "album": args.album}]
    plex = _plex()
    if args.track:
        t = plex.track(args.track)
        if not t:
            raise SystemExit(f"Plex track {args.track} not found")
        return [t]
    items = plex.playlist_tracks(args.playlist)
    if items is None:
        names = ", ".join(p["title"] for p in plex.playlists()) or "(none)"
        raise SystemExit(f"No Plex playlist named {args.playlist!r}. Playlists: {names}")
    # Pull full metadata (moods/styles) per track for energy + preset suggestions.
    return [plex.track(it["id"]) or it for it in items]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--playlist", help="Plex playlist title or id")
    src.add_argument("--track", help="Plex track id")
    src.add_argument("--file", help="Any audio file (use --artist/--title for lyrics lookup)")
    src.add_argument("--list", action="store_true", help="List prepped songs")
    ap.add_argument("--artist")
    ap.add_argument("--title")
    ap.add_argument("--album")
    ap.add_argument("--backend", choices=BACKENDS, default=None,
                    help=f"Vocal separation (default {KARAOKE_BACKEND}, from SP404_KARAOKE_BACKEND)")
    ap.add_argument("--model", default="htdemucs",
                    help="Demucs backend only: htdemucs (fast) or htdemucs_ft (cleaner, ~4x slower)")
    ap.add_argument("--keep-stems", action="store_true",
                    help="karaoke-gen backend: also keep its 6-stem split in <song>/stems/")
    ap.add_argument("--relyric", action="store_true",
                    help="Keep stems; re-transcribe lyrics with karaoke-gen (e.g. once LRCLIB/Genius answer)")
    ap.add_argument("--refresh", action="store_true", help="Keep stems; redo analysis, lyrics, drops")
    ap.add_argument("--force", action="store_true", help="Re-split even if backing exists")
    ap.add_argument("--offline", action="store_true", help="Skip LRCLIB lookups")
    ap.add_argument("--videos", action="store_true",
                    help="Also fetch a music video per song (yt-dlp, SP404_YTDLP) for the deck's second screen")
    ap.add_argument("--revideo", action="store_true", help="Re-fetch music videos even where one exists")
    ap.add_argument("--video-only", action="store_true",
                    help="Songs already prepped: only fetch videos (no separation, no GPU lanes)")
    ap.add_argument("--out", default=None, help=f"Output root (default {KARAOKE_DIR})")
    lanes = ap.add_mutually_exclusive_group()
    lanes.add_argument("--local-only", action="store_true",
                       help="Don't use the remote GPU lane (SP404_KARAOKE_REMOTE)")
    lanes.add_argument("--remote-only", action="store_true",
                       help="Only use the remote GPU lane; wait while it is busy")
    args = ap.parse_args(argv)
    out_root = os.path.expanduser(args.out) if args.out else KARAOKE_DIR

    if args.list:
        for s in rebuild_index(out_root):
            lyr = "lyrics" if s["has_lyrics"] else "no lyrics"
            vid = ", video" if s["has_video"] else ""
            print(f"{s['artist']} - {s['title']}  [{s['bpm']} bpm {s['key']}, {lyr}, {s['drops']} drops{vid}]")
        return 0
    if not (args.playlist or args.track or args.file):
        ap.error("pick a source: --playlist, --track or --file")

    tracks = resolve_tracks(args)
    lane = None
    if KARAOKE_REMOTE_HOST and not args.local_only and not args.video_only \
            and (args.backend or KARAOKE_BACKEND) == "karaoke-gen":
        lane = RemoteLane(KARAOKE_REMOTE_HOST)
    elif args.remote_only:
        ap.error("--remote-only needs SP404_KARAOKE_REMOTE and the karaoke-gen backend")
    lanes_note = f", lanes: {lane.name}{'' if args.remote_only else ' + local'}" if lane else ""
    print(f"Karaoke prep → {out_root} ({len(tracks)} song{'s' if len(tracks) != 1 else ''}{lanes_note})")
    _done, failures = prep_batch(
        tracks, lane=lane, local=not args.remote_only, out_root=out_root, model=args.model,
        refresh=args.refresh, force=args.force, online=not args.offline, backend=args.backend,
        keep_stems=args.keep_stems, relyric=args.relyric, videos=args.videos, revideo=args.revideo,
        video_only=args.video_only)
    songs = rebuild_index(out_root)
    print(f"Done. {len(songs)} songs ready, {failures} failed. Index: {os.path.join(out_root, '_index.json')}")
    return 1 if failures and not songs else 0


if __name__ == "__main__":
    sys.exit(main())
