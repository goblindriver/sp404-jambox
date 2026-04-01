#!/usr/bin/env python3
"""Auto-tag the SP-404 sample library.

Walks ~/Music/SP404-Sample-Library/, extracts tags from directory structure,
filenames, and audio duration, then saves a JSON tag database.

Usage:
    python scripts/tag_library.py            # full scan
    python scripts/tag_library.py --update   # only new/changed files
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
TAGS_FILE = os.path.join(LIBRARY, "_tags.json")
AUDIO_EXTS = {".wav", ".aif", ".aiff"}
FFPROBE = "/opt/homebrew/bin/ffprobe"
SKIP_DIRS = {"_RAW-DOWNLOADS", "_GOLD"}

# --- Directory-to-instrument mapping ---

DIR_INSTRUMENT_MAP = {
    "kicks": "kick",
    "kick": "kick",
    "snares": "snare",
    "snare": "snare",
    "snares-claps": "snare",
    "claps": "clap",
    "clap": "clap",
    "hi-hats": "hihat",
    "hihats": "hihat",
    "hihat": "hihat",
    "hats": "hihat",
    "percussion": "percussion",
    "perc": "percussion",
    "drum-loops": "drum-loop",
    "drum loops": "drum-loop",
    "bass": "bass",
    "guitar": "guitar",
    "keys-piano": "keys",
    "keys": "keys",
    "piano": "keys",
    "synths-pads": "synth",
    "synths": "synth",
    "synth": "synth",
    "pads": "pad",
    "pad": "pad",
    "instrument-loops": "loop",
    "stabs-hits": "stab",
    "stabs": "stab",
    "hits": "stab",
    "chops": "vocal",
    "vocals": "vocal",
    "vocal": "vocal",
    "atmospheres": "ambient",
    "ambient-textural": "ambient",
    "ambient": "ambient",
    "fx": "fx",
    "sfx": "fx",
}

# Category tags from top-level dirs
DIR_CATEGORY_MAP = {
    "drums": "drums",
    "melodic": "melodic",
    "loops": "loop",
    "sfx": "fx",
    "vocals": "vocal",
    "ambient-textural": "ambient",
    "freesound": "freesound",
}

# --- Genre detection from pack prefixes / path segments ---

GENRE_PATTERNS = [
    (r"funk", "funk"),
    (r"lo-?fi", "lofi"),
    (r"lofi", "lofi"),
    (r"hip-?hop", "hiphop"),
    (r"hiphop", "hiphop"),
    (r"idm", "idm"),
    (r"witch[\s_-]?house", "witch-house"),
    (r"nu[\s_-]?rave", "nu-rave"),
    (r"electro[\s_-]?clash", "electroclash"),
    (r"electro", "electro"),
    (r"synth[\s_-]?wave", "synthwave"),
    (r"synthwave", "synthwave"),
    (r"80s[\s_-]?synth", "80s-synth"),
    (r"soul", "soul"),
    (r"jazz", "jazz"),
    (r"house", "house"),
    (r"techno", "techno"),
    (r"ambient", "ambient"),
    (r"cinematic", "cinematic"),
    (r"trap", "trap"),
    (r"dnb|drum[\s_-]?(?:and|n|&)[\s_-]?bass", "dnb"),
    (r"dub[\s_-]?step", "dubstep"),
    (r"reggae", "reggae"),
    (r"r&b|rnb", "rnb"),
    (r"pop", "pop"),
    (r"rock", "rock"),
    (r"metal", "metal"),
    (r"world", "world"),
    (r"tribal", "tribal"),
    (r"garage", "garage"),
    (r"breakbeat", "breakbeat"),
    (r"glitch", "glitch"),
    (r"industrial", "industrial"),
    (r"minimal", "minimal"),
    (r"disco", "disco"),
]

# Character keywords to detect in filenames
CHARACTER_KEYWORDS = [
    "acoustic", "electric", "analog", "digital", "distorted", "clean",
    "warm", "cold", "dark", "bright", "deep", "crispy", "soft", "hard",
    "heavy", "light", "dry", "wet", "reverb", "compressed", "vintage",
    "modern", "lo-fi", "glitch", "tribal", "ambient", "cinematic",
    "tight", "punchy", "muted", "open", "closed", "saturated", "filtered",
    "choppy", "smooth", "gritty", "lush", "sparse", "dense", "metallic",
]

# Filename patterns for instrument detection (supplements directory)
FILENAME_INSTRUMENT_PATTERNS = [
    (r"\bkick\b|\bbd\b|\bbass[\s_-]?drum\b", "kick"),
    (r"\bsnare\b|\bsd\b|\bsnr\b", "snare"),
    (r"\bclap\b|\bcp\b", "clap"),
    (r"\bh(?:i[\s_-]?)?hat\b|\bhh\b|\boh\b|\bch\b", "hihat"),
    (r"\bperc\b|\bconga\b|\bbongo\b|\btom\b|\bshaker\b|\btambourine\b|\brimshot\b|\bcowbell\b", "percussion"),
    (r"\bbass\b", "bass"),
    (r"\bguitar\b|\bgtr\b", "guitar"),
    (r"\bkeys?\b|\bpiano\b|\borgan\b|\brhodes\b|\bwurlitzer\b", "keys"),
    (r"\bsynth\b|\blead\b|\barp\b", "synth"),
    (r"\bpad\b|\batmosphere\b|\batmos\b", "pad"),
    (r"\bvox\b|\bvocal\b|\bvoice\b", "vocal"),
    (r"\bfx\b|\bsfx\b|\briser\b|\bsweep\b|\bimpact\b|\btransition\b", "fx"),
    (r"\bstab\b|\bhit\b|\bchord\b", "stab"),
]

# BPM extraction patterns
BPM_PATTERNS = [
    re.compile(r"(\d{2,3})\s*bpm", re.IGNORECASE),
    re.compile(r"bpm\s*(\d{2,3})", re.IGNORECASE),
    re.compile(r"[\-_](\d{2,3})[\-_]", re.IGNORECASE),
    re.compile(r"\((\d{2,3})\)"),
]

# Key extraction patterns
KEY_PATTERN = re.compile(
    r"[\s_\-]([A-G][#b]?)\s*(?:m(?:in(?:or)?)?|maj(?:or)?)?[\s_\-\.]",
    re.IGNORECASE,
)
KEY_PATTERN_SUFFIX = re.compile(
    r"[\s_\-]([A-G][#b]?(?:m|min|maj)?)\s*\.",
    re.IGNORECASE,
)


def get_duration(filepath: str) -> float:
    """Get audio duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            [
                FFPROBE, "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                filepath,
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, FileNotFoundError):
        pass
    return 0.0


def classify_duration(dur: float) -> str:
    """Classify duration into oneshot/short/medium/long."""
    if dur <= 0:
        return "unknown"
    if dur < 2:
        return "oneshot"
    if dur < 5:
        return "short"
    if dur < 15:
        return "medium"
    return "long"


def extract_bpm(filename, dirpath):
    """Try to extract BPM from filename or directory path."""
    text = filename + " " + dirpath
    for pat in BPM_PATTERNS:
        m = pat.search(text)
        if m:
            bpm = int(m.group(1))
            if 50 <= bpm <= 250:
                return bpm
    return None


def extract_key(filename):
    """Try to extract musical key from filename."""
    for pat in [KEY_PATTERN, KEY_PATTERN_SUFFIX]:
        m = pat.search(filename)
        if m:
            raw = m.group(1).strip()
            # Normalize: uppercase root, keep sharp/flat and minor
            if len(raw) >= 1:
                root = raw[0].upper()
                rest = raw[1:]
                return root + rest
    return None


def extract_instrument_from_dir(rel_path):
    """Get instrument tag from directory structure."""
    parts = rel_path.lower().replace("\\", "/").split("/")
    for part in reversed(parts[:-1]):  # skip filename itself
        if part in DIR_INSTRUMENT_MAP:
            return DIR_INSTRUMENT_MAP[part]
    return None


def extract_instrument_from_filename(filename):
    """Get instrument tag from filename patterns."""
    fname_lower = filename.lower()
    for pattern, instrument in FILENAME_INSTRUMENT_PATTERNS:
        if re.search(pattern, fname_lower):
            return instrument
    return None


def extract_genres(rel_path: str) -> list[str]:
    """Extract genre tags from path and filename."""
    text = rel_path.lower().replace("_", " ").replace("-", " ")
    genres = []
    for pattern, genre in GENRE_PATTERNS:
        if re.search(pattern, text):
            if genre not in genres:
                genres.append(genre)
    return genres


def extract_character(filename: str) -> list[str]:
    """Extract character keywords from filename."""
    fname_lower = filename.lower().replace("-", " ").replace("_", " ")
    found = []
    for kw in CHARACTER_KEYWORDS:
        kw_search = kw.replace("-", " ")
        if kw_search in fname_lower:
            found.append(kw)
    return found


def extract_category_from_dir(rel_path):
    """Get top-level category tag from directory."""
    parts = rel_path.lower().replace("\\", "/").split("/")
    if parts:
        top = parts[0]
        return DIR_CATEGORY_MAP.get(top)
    return None


def tag_file(rel_path: str, full_path: str, get_dur: bool = True) -> dict:
    """Generate all tags for a single file."""
    filename = os.path.basename(rel_path)
    dirpath = os.path.dirname(rel_path)

    # Duration
    duration = get_duration(full_path) if get_dur else 0.0
    dur_type = classify_duration(duration)

    # Instrument
    instrument = extract_instrument_from_dir(rel_path)
    if not instrument:
        instrument = extract_instrument_from_filename(filename)

    # BPM and key
    bpm = extract_bpm(filename, dirpath)
    key = extract_key(filename)

    # Genres
    genres = extract_genres(rel_path)

    # Character
    character = extract_character(filename)

    # Category
    category = extract_category_from_dir(rel_path)

    # Build tag set
    tags = set()
    if instrument:
        tags.add(instrument)
    if category:
        tags.add(category)
    if dur_type != "unknown":
        tags.add(dur_type)
    for g in genres:
        tags.add(g)
    for c in character:
        tags.add(c)
    if bpm:
        tags.add(f"{bpm}bpm")

    entry = {
        "path": rel_path,
        "tags": sorted(tags),
        "bpm": bpm,
        "key": key,
        "duration": round(duration, 3),
        "type": dur_type,
        "instrument": instrument,
        "genre": genres[0] if genres else None,
        "character": character,
        "mtime": os.path.getmtime(full_path),
    }
    return entry


def walk_library() -> list[tuple[str, str]]:
    """Walk library and return (rel_path, full_path) for all audio files."""
    files = []
    for root, dirs, filenames in os.walk(LIBRARY):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            if f.startswith("."):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in AUDIO_EXTS:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, LIBRARY)
                files.append((rel, full))
    return files


def load_existing_tags() -> dict:
    """Load existing tag database if it exists."""
    if os.path.exists(TAGS_FILE):
        try:
            with open(TAGS_FILE, "r") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_tags(db: dict) -> None:
    """Save tag database to JSON."""
    with open(TAGS_FILE, "w") as fh:
        json.dump(db, fh, indent=1, sort_keys=True)
    print(f"Saved {len(db)} entries to {TAGS_FILE}")


def print_summary(db: dict) -> None:
    """Print tag frequency summary."""
    tag_counts = Counter()
    instrument_counts = Counter()
    genre_counts = Counter()
    type_counts = Counter()

    for entry in db.values():
        for t in entry.get("tags", []):
            tag_counts[t] += 1
        inst = entry.get("instrument")
        if inst:
            instrument_counts[inst] += 1
        genre = entry.get("genre")
        if genre:
            genre_counts[genre] += 1
        dur_type = entry.get("type")
        if dur_type:
            type_counts[dur_type] += 1

    print(f"\n{'='*60}")
    print(f"LIBRARY TAG SUMMARY")
    print(f"{'='*60}")
    print(f"Total files tagged: {len(db)}")

    print(f"\n--- Top 30 Tags ---")
    for tag, count in tag_counts.most_common(30):
        bar = "#" * min(count // 20, 40)
        print(f"  {tag:<20s} {count:>5d}  {bar}")

    print(f"\n--- Instruments ---")
    for inst, count in instrument_counts.most_common(20):
        print(f"  {inst:<20s} {count:>5d}")

    print(f"\n--- Genres ---")
    for genre, count in genre_counts.most_common(15):
        print(f"  {genre:<20s} {count:>5d}")

    print(f"\n--- Duration Types ---")
    for dtype, count in type_counts.most_common():
        print(f"  {dtype:<20s} {count:>5d}")


def main():
    parser = argparse.ArgumentParser(description="Auto-tag the SP-404 sample library")
    parser.add_argument("--update", action="store_true",
                        help="Only tag new or changed files")
    parser.add_argument("--no-duration", action="store_true",
                        help="Skip ffprobe duration detection (faster)")
    args = parser.parse_args()

    print(f"Scanning library: {LIBRARY}")
    files = walk_library()
    print(f"Found {len(files)} audio files")

    # Load existing if updating
    db = load_existing_tags() if args.update else {}
    skipped = 0
    tagged = 0

    t0 = time.time()
    for i, (rel, full) in enumerate(files):
        # Update mode: skip if file hasn't changed
        if args.update and rel in db:
            try:
                mtime = os.path.getmtime(full)
                if db[rel].get("mtime") and mtime <= db[rel]["mtime"]:
                    skipped += 1
                    continue
            except OSError:
                pass

        entry = tag_file(rel, full, get_dur=not args.no_duration)
        db[rel] = entry
        tagged += 1

        # Progress
        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  [{i+1}/{len(files)}] {rate:.0f} files/sec — {rel[:60]}")

    elapsed = time.time() - t0
    print(f"\nTagged {tagged} files in {elapsed:.1f}s", end="")
    if skipped:
        print(f" (skipped {skipped} unchanged)")
    else:
        print()

    # Remove entries for files that no longer exist
    existing_rels = {rel for rel, _ in files}
    removed = [k for k in db if k not in existing_rels]
    for k in removed:
        del db[k]
    if removed:
        print(f"Removed {len(removed)} stale entries")

    save_tags(db)
    print_summary(db)


if __name__ == "__main__":
    main()
