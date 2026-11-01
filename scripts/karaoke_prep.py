#!/usr/bin/env python3
"""Karaoke prep ("the kitchen"): turn songs into ready-to-sing packages.

Per song: Demucs pulls the vocal out, librosa finds tempo + first downbeat,
lyrics come from a ``.lrc`` sidecar or LRCLIB, choruses are located from the
repeated lyric blocks, and a drop sheet is drafted for the SP-404A. Output
lives OUTSIDE the sample library (see ``KARAOKE_DIR`` / ``SP404_KARAOKE_DIR``)::

    Karaoke/
      _index.json
      Artist - Title/
        song.json      # bpm, key, beat offset, lyrics source, choruses, drops[], preset
        backing.flac   # no_vocals, stereo 44.1k
        guide.flac     # vocals stem (guide-vocal mode)
        lyrics.lrc  lyrics.ass
        cover.jpg      # if the file/folder has art

Usage::

    python scripts/karaoke_prep.py --playlist Karaoke
    python scripts/karaoke_prep.py --track 123456 --model htdemucs_ft
    python scripts/karaoke_prep.py --file ~/song.flac --artist "Home Front" --title "..."
    python scripts/karaoke_prep.py --playlist Karaoke --refresh   # lyrics + drops only, keep stems
    python scripts/karaoke_prep.py --list                          # what's prepped

Hand edits to ``drops`` survive re-runs: set ``"drops_locked": true`` in song.json.
"""
import argparse
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
import karaoke_drops  # noqa: E402
import karaoke_lyrics  # noqa: E402

SETTINGS = load_settings_for_script(__file__)
KARAOKE_DIR = SETTINGS["KARAOKE_DIR"]
FFMPEG = SETTINGS["FFMPEG_BIN"]
FFPROBE = SETTINGS["FFPROBE_BIN"]

SCHEMA_VERSION = 1

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


def prep_song(meta, *, out_root=None, model="htdemucs", refresh=False, force=False,
              online=True, separator=None, log=print):
    """Prepare one song. ``meta`` needs ``file_path``; artist/title/album,
    duration (ms, Plex style) or duration_s, moods, styles, genres, id are optional.

    ``refresh``: keep existing stems, redo analysis/lyrics/drops.
    ``separator``: injectable for tests (defaults to Demucs).
    Returns the song.json dict.
    """
    out_root = out_root or KARAOKE_DIR
    audio_path = meta.get("file_path")
    if not audio_path or not os.path.isfile(audio_path):
        raise FileNotFoundError(f"audio not found: {audio_path}")
    artist, title = meta.get("artist"), meta.get("title")
    if not title:
        title = os.path.splitext(os.path.basename(audio_path))[0]
    song_dir = os.path.join(out_root, safe_dirname(artist, title))
    os.makedirs(song_dir, exist_ok=True)
    existing = load_song_json(song_dir) or {}
    backing = os.path.join(song_dir, "backing.flac")

    label = f"{artist or '?'} - {title}"
    if os.path.isfile(backing) and not force:
        if not refresh:
            log(f"  = {label} (already prepped; --refresh to redo lyrics/drops, --force to re-split)")
            return existing
        log(f"  ~ {label}: refreshing lyrics + drops")
    else:
        log(f"  + {label}: separating vocals ({model})...")
        t0 = time.time()
        (separator or separate)(audio_path, song_dir, model)
        log(f"    stems done in {time.time() - t0:.0f}s")

    # Analyse the backing (drums intact, no vocal smear) — falls back to the source.
    info = analyze(backing if os.path.isfile(backing) else audio_path)
    if meta.get("duration_s"):
        info["duration_s"] = info["duration_s"] or meta["duration_s"]
    elif meta.get("duration"):
        info["duration_s"] = info["duration_s"] or round(meta["duration"] / 1000.0, 3)
    duration_s = info["duration_s"]

    lines, lyrics_source, plain = karaoke_lyrics.find_lyrics(
        audio_path, artist, title, meta.get("album"), duration_s, online=online)
    display = f"{artist} - {title}" if artist else title
    if lines:
        with open(os.path.join(song_dir, "lyrics.lrc"), "w", encoding="utf-8") as fh:
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

    song = {
        "schema": SCHEMA_VERSION,
        "artist": artist,
        "title": title,
        "album": meta.get("album"),
        "plex_id": meta.get("id"),
        "source_path": audio_path,
        "duration_s": duration_s,
        "bpm": info["bpm"],
        "key": info["key"],
        "beat_offset_s": info["first_beat_s"],
        "energy": energy,
        "moods": meta.get("moods") or [],
        "styles": meta.get("styles") or [],
        "demucs_model": existing.get("demucs_model") if (refresh and not force and existing) else model,
        "lyrics_source": lyrics_source,
        "has_lyrics": bool(lines),
        "choruses": [list(c) for c in choruses],
        "preset": existing.get("preset") or suggest_preset(meta.get("styles"), meta.get("genres")),
        "drops": drops,
        "drops_locked": bool(existing.get("drops_locked")),
        "prepped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    write_json(os.path.join(song_dir, "song.json"), song)
    log(f"    bpm={song['bpm']} key={song['key']} lyrics={lyrics_source} "
        f"choruses={len(choruses)} drops={len(drops)} preset={song['preset']}")
    return song


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
                "preset": data.get("preset"),
                "drops": len(data.get("drops") or []),
            })
    os.makedirs(out_root, exist_ok=True)
    write_json(os.path.join(out_root, "_index.json"),
               {"schema": SCHEMA_VERSION, "count": len(songs), "songs": songs})
    return songs


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
    ap.add_argument("--model", default="htdemucs", help="htdemucs (fast) or htdemucs_ft (cleaner, ~4x slower)")
    ap.add_argument("--refresh", action="store_true", help="Keep stems; redo analysis, lyrics, drops")
    ap.add_argument("--force", action="store_true", help="Re-split even if backing exists")
    ap.add_argument("--offline", action="store_true", help="Skip LRCLIB lookups")
    ap.add_argument("--out", default=None, help=f"Output root (default {KARAOKE_DIR})")
    args = ap.parse_args(argv)
    out_root = os.path.expanduser(args.out) if args.out else KARAOKE_DIR

    if args.list:
        for s in rebuild_index(out_root):
            lyr = "lyrics" if s["has_lyrics"] else "no lyrics"
            print(f"{s['artist']} - {s['title']}  [{s['bpm']} bpm {s['key']}, {lyr}, {s['drops']} drops]")
        return 0
    if not (args.playlist or args.track or args.file):
        ap.error("pick a source: --playlist, --track or --file")

    tracks = resolve_tracks(args)
    print(f"Karaoke prep → {out_root} ({len(tracks)} song{'s' if len(tracks) != 1 else ''})")
    failures = 0
    for meta in tracks:
        try:
            prep_song(meta, out_root=out_root, model=args.model, refresh=args.refresh,
                      force=args.force, online=not args.offline)
        except Exception as exc:  # keep going; one bad file shouldn't kill a batch
            failures += 1
            print(f"  ! {meta.get('artist')} - {meta.get('title')}: {exc}")
    songs = rebuild_index(out_root)
    print(f"Done. {len(songs)} songs ready, {failures} failed. Index: {os.path.join(out_root, '_index.json')}")
    return 1 if failures and not songs else 0


if __name__ == "__main__":
    sys.exit(main())
