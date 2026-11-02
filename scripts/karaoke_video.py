#!/usr/bin/env python3
"""Karaoke music videos: find one for a song, fetch it, and line it up with the track.

The deck plays the video muted on a second screen. When the video's own audio
matches the track, ``offset_s`` locks it to the song (video_pos = song_pos +
offset_s, mode ``"sync"``); a live take, radio edit or re-cut plays ``"loose"``
in the background instead (``offset_s`` None). Used by ``karaoke_prep.py --videos``::

    video = fetch_video(song_dir, "/music/Le Tigre/01 Deceptacon.mp3", artist="Le Tigre",
                        title="Deceptacon", duration_s=184.6)
    # {"file": "video.mp4", "mode": "sync", "offset_s": 4.21, "confidence": 0.93, ...}

A video file beside the source track (``Song.mp4`` next to ``Song.flac``) is
used as-is (copied, not re-encoded); otherwise yt-dlp searches YouTube (``SP404_YTDLP``; YouTube needs
its JS challenge solver: node on PATH plus the ``yt-dlp-ejs`` package).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings_for_script  # noqa: E402

SETTINGS = load_settings_for_script(__file__)
YTDLP = SETTINGS["YTDLP_BIN"]
FFMPEG = SETTINGS["FFMPEG_BIN"]
FFPROBE = SETTINGS["FFPROBE_BIN"]

VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".m4v")
SEARCH_RESULTS = 8
MAX_DOWNLOADS = 3   # candidates tried before giving up (still images are skipped)
# Never the music video: lyric videos would double the deck's own lyrics, and
# audio uploads are a still image. Ignored when the song's own title has the word.
SKIP_WORDS = ("lyric", "lyrics", "karaoke", "reaction", "cover", "remix", "instrumental", "tutorial",
              "lesson", "slowed", "sped up", "nightcore", "8d", "official audio", "audio only",
              "visualizer", "visualiser", "fan made", "fanmade", "ai")
LIVE_WORDS = ("live", "concert", "session", "sessions", "performance", "tour", "festival")
FEAT_WORDS = ("ft", "feat", "featuring")
# What artists' own channels tack on to their name: LeTigreWorld, ChrisStapletonVEVO.
CHANNEL_SUFFIXES = ("vevo", "official", "music", "tv", "band", "channel", "records", "world")

# Alignment: onset-strength envelopes at 22.05 kHz / 512 hop (~23 ms frames).
SR = 22050
HOP = 512
SYNC_TOLERANCE_S = 0.1   # early, middle and late stretches must agree this closely
# Normalised correlation of the song with the video at the lag. The first five
# songs: the same audio scored 0.86-0.96, other recordings and live takes 0.06.
MIN_MATCH = 0.4
# The lag must beat every other one (>PEAK_EXCLUDE_S away) by this much, or a
# loop-tight track could lock a bar off (drum-machine Deceptacon: 0.86 vs 0.76).
MIN_PEAK_MARGIN = 0.05
PEAK_EXCLUDE_S = 1.0
WINDOW_SHARE = 0.9       # each stretch matches at the song's lag at least this well vs its best
CHECK_WINDOW_S = 20.0
STILL_DIFF = 3.0         # keyframes closer than this (mean abs, 0-255) are one picture


def _norm(text):
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _has_words(haystack, words):
    """Whole-word match of normalised ``words`` inside normalised ``haystack``."""
    return bool(words) and f" {words} " in f" {haystack} "


def clean_title(title):
    """Drop tag-style suffixes Plex titles carry: (Remastered 2011), [Live], - Single Version."""
    title = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", title or "")
    title = re.sub(r"\s+-\s+.*\b(remaster(ed)?|version|edit|mono|stereo|mix)\b.*$", "", title, flags=re.I)
    return title.strip() or (title or "")


# ── Search ───────────────────────────────────────────────────────────

def rank_candidates(entries, artist, title, duration_s=None):
    """Search hits that could be the song's video, best first.

    A hit must name the song, and name the artist in its title or come from the
    artist's channel (no covers). The artist's own channel counts most, over
    anyone else's "official video" label (fan uploads use it too), then a
    length close to the track's. Live takes can't sync, so they rank lower;
    lyric, audio-only, cover and remix uploads, and other artists' features,
    are dropped.

    The artist's channel is their name, alone or with a usual suffix
    (``CHANNEL_SUFFIXES``), or, for names of 5+ letters, a channel that
    contains the name ("Yusuf / Cat Stevens"); a short name like Low or Can
    would otherwise claim "Low Key Covers".
    """
    want_title, want_artist = _norm(clean_title(title)), _norm(artist)
    compact_artist = want_artist.replace(" ", "")
    own_channel = re.compile(re.escape(compact_artist) + "(" + "|".join(CHANNEL_SUFFIXES) + ")?")
    if want_artist.startswith("the "):
        want_artist = want_artist[4:]
    scored, seen = [], set()
    for order, entry in enumerate(entries or []):
        name = _norm(entry.get("title"))
        channel = _norm(entry.get("channel") or entry.get("uploader"))
        if not want_title or not _has_words(name, want_title) or entry.get("id") in seen:
            continue
        if channel.endswith(" topic") or any(
                _has_words(name, w) and not _has_words(want_title, w) for w in map(_norm, SKIP_WORDS)):
            continue
        from_artist = bool(compact_artist) and (
            own_channel.fullmatch(channel.replace(" ", "")) is not None
            or (len(compact_artist) >= 5 and _has_words(channel, want_artist)))
        if not from_artist and not _has_words(name, want_artist):
            continue
        score = 1 + (8 if from_artist else 0)
        if _has_words(name, "official") and (_has_words(name, "video") or _has_words(name, "mv")):
            score += 4
        elif _has_words(name, "video") or _has_words(name, "mv"):
            score += 1
        if any(_has_words(name, w) for w in LIVE_WORDS):
            score -= 3
        if any(_has_words(name, w) and not _has_words(want_artist, w) for w in FEAT_WORDS):
            score -= 2
        length = entry.get("duration")
        if duration_s and length:
            gap = abs(length - duration_s)
            score += 3 if gap <= 5 else 1 if gap <= 20 else 0 if gap <= 60 else -2
        if score > 0:
            seen.add(entry.get("id"))
            scored.append((-score, order, entry))
    return [entry for _score, _order, entry in sorted(scored, key=lambda s: s[:2])]


def search(artist, title, *, run=subprocess.run):
    """YouTube search hits (id, title, channel, duration, url) for the song's video."""
    query = f"ytsearch{SEARCH_RESULTS}:{artist or ''} {clean_title(title)} official music video".strip()
    res = run([YTDLP, "--flat-playlist", "--dump-single-json", "--js-runtimes", "node", query],
              capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        raise RuntimeError(f"yt-dlp search failed: {(res.stderr or '').strip()[-300:]}")
    entries = json.loads(res.stdout or "{}").get("entries") or []
    for entry in entries:
        entry.setdefault("url", f"https://www.youtube.com/watch?v={entry.get('id')}")
    return entries


def download(url, dest, *, run=subprocess.run):
    """Fetch ``url`` to ``dest`` (mp4): 720p at most, H.264 + AAC preferred."""
    cmd = [YTDLP, "--js-runtimes", "node", "-S", "res:720,vcodec:h264,acodec:aac", "--merge-output-format",
           "mp4", "--no-playlist", "--max-filesize", "500M", "-o", dest, url]
    if os.path.dirname(FFMPEG):
        cmd[1:1] = ["--ffmpeg-location", os.path.dirname(FFMPEG)]
    res = run(cmd, capture_output=True, text=True, timeout=900)
    if res.returncode != 0 or not os.path.isfile(dest):
        raise RuntimeError(f"yt-dlp download failed: {(res.stderr or '').strip()[-300:]}")


def is_still(path):
    """True when the video is one picture (an audio upload with cover art).

    Compares the keyframes (only those are decoded, so it's quick) at 32x18 grey.
    Raises ``RuntimeError`` when ffmpeg can't read it.
    """
    import numpy as np
    res = subprocess.run([FFMPEG, "-v", "error", "-skip_frame", "nokey", "-i", path, "-an",
                          "-fps_mode", "passthrough", "-vf", "scale=32:18,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, timeout=300)
    if res.returncode != 0:
        err = (res.stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(f"ffmpeg couldn't read the video: {err[-300:]}")
    frames = np.frombuffer(res.stdout, dtype=np.uint8)
    frames = frames[:len(frames) // 576 * 576].reshape(-1, 576).astype(np.float32)
    if len(frames) < 2:
        return True
    return float(np.abs(np.diff(frames, axis=0)).mean(axis=1).max()) < STILL_DIFF


# ── Alignment ────────────────────────────────────────────────────────

def onset_envelope(path):
    """Z-normalised onset-strength envelope of a file's audio (video or track), or None."""
    import librosa
    import soundfile as sf
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        res = subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), wav],
                             capture_output=True, timeout=300)
        if res.returncode != 0 or not os.path.isfile(wav):
            return None
        y, _sr = sf.read(wav, dtype="float32")
    if len(y) < SR:
        return None
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    return (env - env.mean()) / (env.std() + 1e-9)


def _ncc(song, video):
    """``(lags, scores)``: normalised cross-correlation of ``song`` against ``video``.

    video frame = song frame + lag. Scores are cosine similarities (1 = the
    same envelope), so a loud stretch of the video can't outscore a matching
    one. Only lags where the two overlap by at least half the shorter are kept.
    """
    import numpy as np
    from scipy import signal
    n = len(song)
    padded = np.concatenate([np.zeros(n - 1), video, np.zeros(n - 1)])
    corr = signal.correlate(padded, song, mode="valid", method="fft")
    energy = np.concatenate([[0.0], np.cumsum(padded ** 2)])
    window_energy = np.maximum(energy[n:] - energy[:-n], 1e-12)
    scores = corr / (np.linalg.norm(song) * np.sqrt(window_energy) + 1e-12)
    lags = np.arange(len(corr)) - (n - 1)
    overlap = np.minimum(lags + n, len(video)) - np.maximum(lags, 0)
    keep = overlap >= min(n, len(video)) // 2
    return lags[keep], scores[keep]


def align(song_env, video_env):
    """``(mode, offset_s, confidence)`` for playing the video against the song.

    Locks (``"sync"``) when the whole song matches the video at one clear lag
    (score ``MIN_MATCH``, ``MIN_PEAK_MARGIN`` over any other lag) and three
    stretches of it (early, middle, late) each match the video at that same lag
    (within ``SYNC_TOLERANCE_S``) about as well as anywhere else: same audio,
    same edit. A repeated chorus doesn't spoil it, a cut or a different take
    does: those play loose (``offset_s`` None). ``confidence`` is the
    whole-song match score.
    """
    import numpy as np
    frame_s = HOP / SR
    lags, scores = _ncc(song_env, video_env)
    if not len(scores):
        return "loose", None, 0.0
    peak = int(np.argmax(scores))
    global_lag, score = int(lags[peak]), float(scores[peak])
    near = int(PEAK_EXCLUDE_S / frame_s)
    rest = np.concatenate([scores[:max(0, peak - near)], scores[peak + near + 1:]])
    runner_up = float(rest.max()) if len(rest) else -1.0
    confidence = round(score, 3)
    window = int(CHECK_WINDOW_S / frame_s)
    if len(song_env) < window * 2 or score < MIN_MATCH or score - runner_up < MIN_PEAK_MARGIN:
        return "loose", None, confidence
    tolerance = int(SYNC_TOLERANCE_S / frame_s)
    for frac in (0.15, 0.5, 0.8):
        start = min(int(len(song_env) * frac), len(song_env) - window)
        w_lags, w_scores = _ncc(song_env[start:start + window], video_env)
        at_lag = w_scores[np.abs(w_lags - (start + global_lag)) <= tolerance]
        if not len(at_lag) or at_lag.max() < MIN_MATCH or at_lag.max() < WINDOW_SHARE * w_scores.max():
            return "loose", None, confidence
    return "sync", round(global_lag * frame_s, 3), confidence


def video_duration(path):
    try:
        res = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=30)
        return round(float(res.stdout.strip()), 3)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


# ── One song ─────────────────────────────────────────────────────────

def local_video(source_path):
    """A video file sitting beside the source track with the same name, if any."""
    stem = os.path.splitext(source_path or "")[0]
    for ext in VIDEO_EXTS:
        if stem and os.path.isfile(stem + ext):
            return stem + ext
    return None


def fetch_video(song_dir, audio_path, *, source_path=None, artist=None, title=None, duration_s=None,
                log=print, run=subprocess.run, envelope=onset_envelope, still=is_still):
    """Find, fetch and align one song's video into ``song_dir``; returns song.json's ``video`` or None.

    ``audio_path`` is what the video is aligned against (the song's full mix);
    a video beside ``source_path`` (default ``audio_path``) wins over YouTube.
    Downloads go to the system temp folder, so a half-fetched file never sits
    in a song folder someone is mirroring; the file lands as
    ``song_dir/video.<ext>`` only once it has been checked.
    """
    source_path = source_path or audio_path
    found = local_video(source_path)
    with tempfile.TemporaryDirectory(prefix="jambox-video-") as tmp:
        if found:
            ext = os.path.splitext(found)[1].lower()
            path = os.path.join(tmp, "video" + ext)
            shutil.copyfile(found, path)
            info = {"origin": "local", "source": found, "title": os.path.basename(found), "channel": None}
        else:
            path, info = None, None
            for hit in rank_candidates(search(artist, title, run=run), artist, title, duration_s)[:MAX_DOWNLOADS]:
                dest = os.path.join(tmp, f"{hit.get('id') or 'video'}.mp4")
                try:
                    download(hit["url"], dest, run=run)
                    if still(dest):
                        log(f"    video {hit.get('title')!r} is a still picture; next")
                        continue
                except RuntimeError as exc:
                    log(f"    video {hit.get('title')!r}: {exc}")
                    continue
                path, info = dest, {"origin": "yt-dlp", "source": hit["url"], "title": hit.get("title"),
                                    "channel": hit.get("channel") or hit.get("uploader")}
                break
            if path is None:
                log(f"    no music video found for {artist or '?'} - {title}")
                return None
        song_env, video_env = envelope(audio_path), envelope(path)
        if song_env is None or video_env is None:
            mode, offset_s, confidence = "loose", None, 0.0
        else:
            mode, offset_s, confidence = align(song_env, video_env)
        name = "video" + os.path.splitext(path)[1].lower()
        for old in os.listdir(song_dir):  # a re-fetch may change the extension
            if old.startswith("video.") and os.path.splitext(old)[1].lower() in VIDEO_EXTS:
                os.remove(os.path.join(song_dir, old))
        final = os.path.join(song_dir, name)
        shutil.move(path, final)  # a rename when the temp folder shares the disk
    log(f"    video: {info['title']} ({mode}{'' if offset_s is None else f', offset {offset_s:+.2f}s'})")
    return {"file": name, "mode": mode, "offset_s": offset_s, "confidence": confidence,
            "duration_s": video_duration(final), "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"), **info}
