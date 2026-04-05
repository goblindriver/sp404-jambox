#!/usr/bin/env python3
"""Split audio files into stems using Demucs (htdemucs).

Optional pipeline step between ingest and tag. Each full track becomes
4-6 individually tagged samples in the library.

Stem channels → type codes:
  drums  → BRK (drum break)
  bass   → BAS (bass)
  vocals → VOX (vocal)
  other  → SMP (sampled phrase)

Stems inherit parent tags (BPM, key, genre, source context) and get
their own type_code based on which channel. Linked back to parent via
source_id in the tag database.

Output: ~/Music/SP404-Sample-Library/Stems/{source-name}/

Usage:
    python scripts/stem_split.py                        # process all unprocessed
    python scripts/stem_split.py path/to/track.wav      # single file
    python scripts/stem_split.py --model htdemucs_6s    # 6-stem mode
    python scripts/stem_split.py --dir ~/Downloads/      # process a directory
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

from jambox_config import LONG_HOLD_DIRNAME, load_settings_for_script

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
STEMS_DIR = SETTINGS["STEMS_DIR"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
FFMPEG = SETTINGS["FFMPEG_BIN"]
FFPROBE = SETTINGS["FFPROBE_BIN"]
PYTHON = sys.executable

# Demucs stem name → type code mapping
STEM_TYPE_MAP = {
    "drums": "BRK",
    "bass": "BAS",
    "vocals": "VOX",
    "other": "SMP",
    # 6-stem mode extras
    "guitar": "GTR",
    "piano": "KEY",
}

# Minimum duration (seconds) to bother splitting
MIN_DURATION = 5.0

# Marker file to track what's been split
SPLIT_MARKER = ".stem-split"


def get_duration(filepath):
    """Get audio duration via ffprobe."""
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_format", filepath],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            import json as _json
            data = _json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except Exception:
        pass
    return 0.0


def source_id(filepath):
    """Generate a stable ID for a source file based on its path."""
    rel = os.path.relpath(filepath, LIBRARY) if filepath.startswith(LIBRARY) else filepath
    return hashlib.md5(rel.encode()).hexdigest()[:12]


def run_demucs(input_path, output_dir, model="htdemucs"):
    """Run demucs on an audio file.

    Returns list of (stem_name, stem_path) tuples on success, or empty list.
    """
    # Demucs outputs to {output_dir}/{model}/{track_name}/{stem}.wav
    try:
        # Pre-convert to clean WAV via ffmpeg (some files have RLND/non-standard chunks
        # that confuse torchaudio)
        import tempfile as _tf
        clean_wav = os.path.join(output_dir, "_input_clean.wav")
        preconvert = subprocess.run([
            FFMPEG, "-y", "-i", input_path,
            "-ar", "44100", "-ac", "2", "-sample_fmt", "s16",
            "-c:a", "pcm_s16le", clean_wav,
        ], capture_output=True, timeout=30)
        if preconvert.returncode != 0:
            print(f"    Pre-convert failed")
            return []

        if not os.path.exists(clean_wav):
            print(f"    Pre-convert failed")
            return []

        cmd = [PYTHON, "-m", "demucs", "-n", model, "-o", output_dir, clean_wav]

        print(f"    Running demucs ({model})...")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
        )

        if result.returncode != 0:
            # Filter out warnings — only show actual errors
            err = result.stderr or ""
            err_lines = [l for l in err.split("\n")
                         if l.strip() and "Warning" not in l and "%" not in l and "UserWarning" not in l]
            if err_lines:
                print(f"    Demucs error: {err_lines[0][:200]}")
            else:
                print(f"    Demucs failed (exit code {result.returncode})")
            return []

        # Find output stems (use clean wav name since that's what demucs saw)
        track_name = "_input_clean"
        stem_dir = os.path.join(output_dir, model, track_name)

        if not os.path.isdir(stem_dir):
            print(f"    No output dir found at {stem_dir}")
            return []

        stems = []
        for f in os.listdir(stem_dir):
            if f.endswith(".wav"):
                stem_name = os.path.splitext(f)[0]
                stem_path = os.path.join(stem_dir, f)
                stems.append((stem_name, stem_path))

        return stems

    except subprocess.TimeoutExpired:
        print(f"    Demucs timed out (10min limit)")
        return []
    except FileNotFoundError as e:
        print(f"    Demucs failed: {e}")
        return []
    except Exception as e:
        print(f"    Demucs failed: {e}")
        return []


def load_tag_db():
    from jambox_config import load_tag_db as _load
    return _load(TAGS_FILE)


def save_tag_db(db):
    from jambox_config import save_tag_db as _save
    _save(TAGS_FILE, db)


def copy_stem_to_library(stem_path, source_name, stem_name):
    """Copy a stem WAV to the Stems directory in the library.

    Returns the destination path (relative to LIBRARY).
    """
    # Clean up source name for directory
    safe_name = re.sub(r'[^\w\-]', '_', source_name)[:60]
    dest_dir = os.path.join(STEMS_DIR, safe_name)
    os.makedirs(dest_dir, exist_ok=True)

    dest = os.path.join(dest_dir, f"{stem_name}.wav")
    shutil.copy2(stem_path, dest)
    return os.path.relpath(dest, LIBRARY)


def tag_stem(rel_path, stem_name, parent_tags, parent_src_id, duration):
    """Create a tag entry for a stem, inheriting parent context."""
    type_code = STEM_TYPE_MAP.get(stem_name, "SMP")

    # Inherit parent's dimensional tags
    vibe = list(parent_tags.get("vibe", []))
    texture = list(parent_tags.get("texture", []))
    genre = list(parent_tags.get("genre", []))
    source = "processed"  # stems are always processed
    bpm = parent_tags.get("bpm")
    key = parent_tags.get("key")

    # Energy from parent
    energy = parent_tags.get("energy", "mid")

    # Playability based on stem type and duration
    if type_code == "BRK":
        playability = "loop" if duration > 2 else "one-shot"
    elif type_code == "VOX":
        playability = "chop-ready" if duration > 3 else "one-shot"
    elif type_code == "BAS":
        playability = "loop" if duration > 2 else "one-shot"
    else:
        playability = "loop" if duration > 4 else "chop-ready"

    # Build flat tags
    tags = set()
    tags.add(type_code)
    tags.update(vibe)
    tags.update(texture)
    tags.update(genre)
    tags.add(source)
    tags.add(energy)
    tags.add(playability)
    if bpm:
        tags.add(f"{bpm}bpm")

    return {
        "path": rel_path,
        "type_code": type_code,
        "vibe": vibe,
        "texture": texture,
        "genre": genre,
        "source": source,
        "energy": energy,
        "playability": playability,
        "bpm": bpm,
        "key": key,
        "duration": round(duration, 3),
        "tags": sorted(tags),
        "source_id": parent_src_id,
        "stem_of": stem_name,
        "mtime": time.time(),
    }


def find_splittable_files(search_dir=None):
    """Find audio files that are long enough and haven't been split yet."""
    db = load_tag_db()
    # Find files already split (have stems linked to them)
    already_split = set()
    for entry in db.values():
        sid = entry.get("source_id")
        if sid:
            already_split.add(sid)

    candidates = []
    scan_dir = search_dir or LIBRARY

    for root, dirs, files in os.walk(scan_dir):
        # Skip utility dirs
        dirs[:] = [d for d in dirs if d not in {
            "_RAW-DOWNLOADS", "_GOLD", "_DUPES", "Stems", LONG_HOLD_DIRNAME,
        } and not d.startswith(".")]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in {".wav", ".mp3", ".flac", ".aif", ".aiff", ".m4a", ".ogg"}:
                continue

            full = os.path.join(root, f)
            # Check if already split
            sid = source_id(full)
            if sid in already_split:
                continue

            # Check duration
            dur = get_duration(full)
            if dur >= MIN_DURATION:
                candidates.append((full, dur, sid))

    return candidates


def process_file(filepath, duration, src_id, model, db, tmp_dir):
    """Split one file and tag its stems. Returns number of stems created."""
    source_name = os.path.splitext(os.path.basename(filepath))[0]

    # Get parent tags if this file is in the tag DB
    rel = os.path.relpath(filepath, LIBRARY) if filepath.startswith(LIBRARY) else ""
    parent_tags = db.get(rel, {})

    # Run demucs
    stems = run_demucs(filepath, tmp_dir, model)
    if not stems:
        return 0

    created = 0
    for stem_name, stem_path in stems:
        # Check if stem has actual content (not just silence)
        stem_dur = get_duration(stem_path)
        if stem_dur < 1.0:
            continue

        # Copy to library
        stem_rel = copy_stem_to_library(stem_path, source_name, stem_name)

        # Tag it
        entry = tag_stem(stem_rel, stem_name, parent_tags, src_id, stem_dur)
        db[stem_rel] = entry
        created += 1

        tc = STEM_TYPE_MAP.get(stem_name, "SMP")
        print(f"    ✓ {stem_name} → {tc} ({stem_dur:.1f}s) → {stem_rel}")

    return created


def main():
    parser = argparse.ArgumentParser(description="Split audio into stems via Demucs")
    parser.add_argument("files", nargs="*", help="Specific files to split")
    parser.add_argument("--model", default="htdemucs",
                        choices=["htdemucs", "htdemucs_6s", "htdemucs_ft"],
                        help="Demucs model (default: htdemucs = 4 stems)")
    parser.add_argument("--dir", help="Process all eligible files in this directory")
    parser.add_argument("--limit", type=int, default=0, help="Max files to process")
    parser.add_argument("--min-duration", type=float, default=5.0,
                        help="Minimum duration in seconds (default: 5)")
    args = parser.parse_args()

    global MIN_DURATION
    MIN_DURATION = args.min_duration

    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="demucs_")

    db = load_tag_db()
    total_stems = 0
    total_files = 0

    try:
        if args.files:
            # Process specific files
            candidates = []
            for f in args.files:
                f = os.path.expanduser(f)
                if os.path.isfile(f):
                    dur = get_duration(f)
                    candidates.append((f, dur, source_id(f)))
                else:
                    print(f"  SKIP: {f} (not found)")
        else:
            # Find all splittable files
            search_dir = args.dir if args.dir else None
            print(f"Scanning for splittable files (>={args.min_duration}s)...")
            candidates = find_splittable_files(search_dir)
            print(f"Found {len(candidates)} candidates")

        if args.limit:
            candidates = candidates[:args.limit]

        t0 = time.time()
        for i, (filepath, duration, src_id) in enumerate(candidates):
            fname = os.path.basename(filepath)
            print(f"\n[{i+1}/{len(candidates)}] {fname} ({duration:.1f}s)")

            n = process_file(filepath, duration, src_id, args.model, db, tmp_dir)
            if n > 0:
                total_stems += n
                total_files += 1

        elapsed = time.time() - t0

        print(f"\n{'='*60}")
        print(f"STEM SPLIT COMPLETE")
        print(f"  Files processed: {total_files}")
        print(f"  Stems created: {total_stems}")
        print(f"  Time: {elapsed:.1f}s")
        print(f"  Output: {STEMS_DIR}")

        if total_stems > 0:
            save_tag_db(db)
            print(f"  Tags saved to: {TAGS_FILE}")

    finally:
        # Clean up demucs temp output
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
