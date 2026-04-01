#!/usr/bin/env python3
"""Auto-tag the SP-404 sample library using the TAGGING_SPEC dimensions.

Walks ~/Music/SP404-Sample-Library/, extracts tags from directory structure,
filenames, and audio duration, then saves a JSON tag database.

Tag dimensions (per TAGGING_SPEC.md):
  type_code  — 3-letter instrument/category code (KIK, SNR, SYN, etc.)
  vibe       — emotional mood (dark, chill, hype, etc.)
  texture    — sonic character (dusty, warm, bright, etc.)
  genre      — aesthetic lineage (boom-bap, house, funk, etc.)
  source     — how obtained (kit, dug, synth, field, etc.)
  energy     — intensity (low, mid, high)
  playability — usage intent (one-shot, loop, chop-ready, etc.)

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

# ═══════════════════════════════════════════════════════════
# Type Code Detection (3-letter codes per TAGGING_SPEC)
# ═══════════════════════════════════════════════════════════

# Directory name → type code
DIR_TYPE_MAP = {
    # Percussive
    "kicks": "KIK", "kick": "KIK",
    "snares": "SNR", "snare": "SNR", "snares-claps": "SNR",
    "claps": "CLP", "clap": "CLP",
    "hi-hats": "HAT", "hihats": "HAT", "hihat": "HAT", "hats": "HAT",
    "cymbals": "CYM", "cymbal": "CYM", "crashes": "CYM",
    "rimshots": "RIM", "rimshot": "RIM",
    "percussion": "PRC", "perc": "PRC",
    "drum-loops": "BRK", "drum loops": "BRK", "breaks": "BRK",
    # Melodic
    "bass": "BAS",
    "guitar": "GTR", "guitars": "GTR",
    "keys-piano": "KEY", "keys": "KEY", "piano": "KEY", "organ": "KEY",
    "synths-pads": "SYN", "synths": "SYN", "synth": "SYN",
    "pads": "PAD", "pad": "PAD",
    "strings": "STR", "orchestral": "STR",
    "brass": "BRS",
    "plucks": "PLK",
    "woodwind": "WND", "flute": "WND", "sax": "WND",
    "vocals": "VOX", "vocal": "VOX", "chops": "VOX",
    # Utility
    "fx": "FX", "sfx": "FX",
    "stabs-hits": "SFX", "stabs": "SFX", "hits": "SFX",
    "ambient-textural": "AMB", "ambient": "AMB", "atmospheres": "AMB",
    "foley": "FLY",
    "risers": "RSR", "sweeps": "RSR",
    "tape": "TPE", "vinyl": "TPE",
    "instrument-loops": "SMP",
}

# Filename patterns → type code
FILENAME_TYPE_PATTERNS = [
    # Percussive
    (r"\bkick\b|\bbd\b|\bbass[\s_-]?drum\b", "KIK"),
    (r"\bsnare\b|\bsd\b|\bsnr\b", "SNR"),
    (r"\bclap\b|\bcp\b|\bsnap\b", "CLP"),
    (r"\bh(?:i[\s_-]?)?hat\b|\bhh\b|\boh\b|\bch\b", "HAT"),
    (r"\bcymbal\b|\bcrash\b|\bride\b", "CYM"),
    (r"\brimshot\b|\brim\b", "RIM"),
    (r"\bperc\b|\bconga\b|\bbongo\b|\btom\b|\bshaker\b|\btambourine\b|\bcowbell\b", "PRC"),
    # Melodic
    (r"\bbass\b|\bsub\b|\b808\b", "BAS"),
    (r"\bguitar\b|\bgtr\b", "GTR"),
    (r"\bkeys?\b|\bpiano\b|\borgan\b|\brhodes\b|\bwurlitzer\b|\bclavinet\b", "KEY"),
    (r"\bsynth\b|\blead\b|\barp\b", "SYN"),
    (r"\bpad\b|\batmosphere\b|\batmos\b", "PAD"),
    (r"\bstring\b|\bviolin\b|\bcello\b|\bviola\b|\borchestra\b", "STR"),
    (r"\bbrass\b|\btrumpet\b|\btrombone\b", "BRS"),
    (r"\bpluck\b|\bpizz\b|\bkalimba\b|\bmbira\b|\bharp\b", "PLK"),
    (r"\bflute\b|\bclarinet\b|\bsax\b|\bsaxophone\b|\boboe\b|\bwoodwind\b", "WND"),
    (r"\bvox\b|\bvocal\b|\bvoice\b|\bchoir\b|\bspoken\b", "VOX"),
    # Utility
    (r"\briser\b|\bsweep\b|\bbuild\b", "RSR"),
    (r"\bfoley\b|\bfootstep\b", "FLY"),
    (r"\btape\b|\bvinyl\b|\bcrackle\b|\bhiss\b", "TPE"),
    (r"\bstab\b|\bhit\b|\bchord\b|\bimpact\b|\bboom\b", "SFX"),
    (r"\bfx\b|\bsfx\b|\btransition\b", "FX"),
    (r"\bsampl\b|\bphrase\b|\bchop\b", "SMP"),
]

# Top-level dir → broad category (for fallback)
DIR_CATEGORY_MAP = {
    "drums": "DRM",
    "melodic": "SYN",
    "loops": "BRK",
    "sfx": "FX",
    "vocals": "VOX",
    "ambient-textural": "AMB",
    "freesound": None,
}

# ═══════════════════════════════════════════════════════════
# Vibe (mood) detection
# ═══════════════════════════════════════════════════════════

VIBE_KEYWORDS = {
    "dark": ["dark", "evil", "occult", "horror", "noir", "sinister"],
    "mellow": ["mellow", "calm", "gentle", "relaxed"],
    "hype": ["hype", "energy", "rave", "party", "anthem"],
    "dreamy": ["dreamy", "dream", "float", "lush"],
    "gritty": ["gritty", "grit", "dirty", "grimy"],
    "nostalgic": ["nostalgic", "vintage", "retro", "old-school", "oldschool"],
    "eerie": ["eerie", "creepy", "spooky", "haunted", "ghostly"],
    "uplifting": ["uplifting", "happy", "positive", "joyful"],
    "melancholic": ["melancholic", "sad", "lonely", "somber"],
    "aggressive": ["aggressive", "hard", "heavy", "industrial", "intense"],
    "playful": ["playful", "fun", "cartoon", "quirky", "weird", "funny"],
    "soulful": ["soulful", "gospel"],
    "ethereal": ["ethereal", "angelic", "heavenly"],
    "tense": ["tense", "suspense", "cinematic", "dramatic", "tension"],
    "chill": ["chill", "smooth", "muted"],
}

# ═══════════════════════════════════════════════════════════
# Texture (sonic character) detection
# ═══════════════════════════════════════════════════════════

TEXTURE_KEYWORDS = {
    "dusty": ["dusty", "dust"],
    "clean": ["clean", "pure", "clear"],
    "lo-fi": ["lo-fi", "lofi", "low-fi"],
    "saturated": ["saturated", "driven", "overdriven"],
    "airy": ["airy", "spacious", "open"],
    "crunchy": ["crunchy", "crunch", "crispy"],
    "warm": ["warm"],
    "glassy": ["glassy", "glass", "crystal", "crystalline"],
    "warbly": ["warbly", "warble", "wobble", "detuned", "woozy"],
    "bitcrushed": ["bitcrushed", "bitcrush", "8-bit", "8bit", "chiptune"],
    "tape-saturated": ["cassette"],
    "bright": ["bright"],
    "muddy": ["muddy", "murky"],
    "thin": ["thin"],
    "thick": ["thick", "fat", "dense"],
    "filtered": ["filtered", "filter", "muffled"],
    "raw": ["raw", "unprocessed"],
}

# ═══════════════════════════════════════════════════════════
# Genre detection
# ═══════════════════════════════════════════════════════════

GENRE_PATTERNS = [
    (r"boom[\s_-]?bap", "boom-bap"),
    (r"lo-?fi[\s_-]?hip[\s_-]?hop", "lo-fi-hiphop"),
    (r"lo-?fi|lofi", "lo-fi-hiphop"),
    (r"hip-?hop|hiphop", "boom-bap"),
    (r"trap", "trap"),
    (r"drill", "drill"),
    (r"funk", "funk"),
    (r"soul", "soul"),
    (r"jazz", "jazz"),
    (r"gospel", "gospel"),
    (r"r&b|rnb", "r&b"),
    (r"house", "house"),
    (r"uk[\s_-]?garage", "uk-garage"),
    (r"garage", "uk-garage"),
    (r"techno", "electronic"),
    (r"electro[\s_-]?clash", "electronic"),
    (r"electro", "electronic"),
    (r"idm", "electronic"),
    (r"witch[\s_-]?house", "electronic"),
    (r"nu[\s_-]?rave", "electronic"),
    (r"synth[\s_-]?wave|synthwave", "electronic"),
    (r"80s[\s_-]?synth", "electronic"),
    (r"dnb|drum[\s_-]?(?:and|n|&)[\s_-]?bass", "electronic"),
    (r"dub[\s_-]?step", "electronic"),
    (r"footwork|juke", "footwork"),
    (r"afrobeat|afro", "afrobeat"),
    (r"city[\s_-]?pop", "city-pop"),
    (r"psychedelic|psych", "psychedelic"),
    (r"dub(?!step)", "dub"),
    (r"disco", "disco"),
    (r"reggae", "reggae"),
    (r"latin|salsa|bossa", "latin"),
    (r"classical|orchestral", "classical"),
    (r"ambient", "ambient"),
    (r"pop", "electronic"),
    (r"rock", "rock"),
    (r"metal", "rock"),
    (r"punk", "rock"),
    (r"breakbeat", "electronic"),
    (r"glitch", "electronic"),
    (r"minimal", "electronic"),
    (r"tribal", "world"),
    (r"world", "world"),
]

# ═══════════════════════════════════════════════════════════
# BPM + Key extraction
# ═══════════════════════════════════════════════════════════

BPM_PATTERNS = [
    re.compile(r"(\d{2,3})\s*bpm", re.IGNORECASE),
    re.compile(r"bpm\s*(\d{2,3})", re.IGNORECASE),
    re.compile(r"[\-_](\d{2,3})[\-_]", re.IGNORECASE),
    re.compile(r"\((\d{2,3})\)"),
]

KEY_PATTERN = re.compile(
    r"[\s_\-]([A-G][#bs]?)\s*(?:m(?:in(?:or)?)?|maj(?:or)?)?[\s_\-\.]",
    re.IGNORECASE,
)
KEY_PATTERN_SUFFIX = re.compile(
    r"[\s_\-]([A-G][#bs]?(?:m|min|maj)?)\s*\.",
    re.IGNORECASE,
)


def get_duration(filepath):
    """Get audio duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", filepath],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, FileNotFoundError):
        pass
    return 0.0


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
    """Try to extract musical key from filename. Normalizes # to s per spec."""
    for pat in [KEY_PATTERN, KEY_PATTERN_SUFFIX]:
        m = pat.search(filename)
        if m:
            raw = m.group(1).strip()
            if len(raw) >= 1:
                root = raw[0].upper()
                rest = raw[1:].replace("#", "s")
                return root + rest
    return None


# ═══════════════════════════════════════════════════════════
# Type code extraction
# ═══════════════════════════════════════════════════════════

def extract_type_code_from_dir(rel_path):
    """Get type code from directory structure."""
    parts = rel_path.lower().replace("\\", "/").split("/")
    for part in reversed(parts[:-1]):
        if part in DIR_TYPE_MAP:
            return DIR_TYPE_MAP[part]
    return None


def extract_type_code_from_filename(filename):
    """Get type code from filename patterns."""
    fname_lower = filename.lower()
    for pattern, code in FILENAME_TYPE_PATTERNS:
        if re.search(pattern, fname_lower):
            return code
    return None


def extract_type_code_from_category(rel_path):
    """Fallback: get type code from top-level directory."""
    parts = rel_path.lower().replace("\\", "/").split("/")
    if parts:
        return DIR_CATEGORY_MAP.get(parts[0])
    return None


def extract_type_code(rel_path, filename):
    """Extract 3-letter type code using all available signals."""
    code = extract_type_code_from_dir(rel_path)
    if not code:
        code = extract_type_code_from_filename(filename)
    if not code:
        code = extract_type_code_from_category(rel_path)
    return code or "FX"  # fallback


# ═══════════════════════════════════════════════════════════
# Vibe + Texture extraction
# ═══════════════════════════════════════════════════════════

def extract_tags_from_keywords(text, keyword_map):
    """Generic: find matching tags from a keyword→tag mapping."""
    text_lower = text.lower().replace("-", " ").replace("_", " ")
    found = []
    for tag, keywords in keyword_map.items():
        for kw in keywords:
            kw_clean = kw.replace("-", " ")
            if kw_clean in text_lower:
                if tag not in found:
                    found.append(tag)
                break
    return found


def extract_vibe(rel_path, filename):
    """Extract vibe/mood tags."""
    text = rel_path + " " + filename
    return extract_tags_from_keywords(text, VIBE_KEYWORDS)


def extract_texture(rel_path, filename):
    """Extract texture/sonic character tags."""
    text = rel_path + " " + filename
    return extract_tags_from_keywords(text, TEXTURE_KEYWORDS)


# ═══════════════════════════════════════════════════════════
# Genre extraction
# ═══════════════════════════════════════════════════════════

def extract_genres(rel_path):
    """Extract genre tags from path and filename."""
    text = rel_path.lower().replace("_", " ").replace("-", " ")
    genres = []
    for pattern, genre in GENRE_PATTERNS:
        if re.search(pattern, text):
            if genre not in genres:
                genres.append(genre)
    return genres


# ═══════════════════════════════════════════════════════════
# Source classification
# ═══════════════════════════════════════════════════════════

def classify_source(rel_path, filename, type_code):
    """Classify sample source: kit, dug, synth, field, generated, processed."""
    text = (rel_path + " " + filename).lower()

    if re.search(r"field[\s_-]?record|foley|nature|outdoor|ambience", text):
        return "field"
    if re.search(r"vinyl[\s_-]?rip|crate|digg?ing|sampled|chop", text):
        return "dug"
    if re.search(r"generated|noise[\s_-]?gen|test[\s_-]?tone|sine|saw[\s_-]?wave", text):
        return "generated"
    if re.search(r"mangled|granular|processed|glitch[\s_-]?fx", text):
        return "processed"

    # Infer from type code
    if type_code in ("SYN", "PAD", "BAS") and re.search(r"synth|analog|digital|fm|wave", text):
        return "synth"
    if type_code in ("AMB", "FLY"):
        return "field"
    if type_code in ("FX", "RSR", "SFX", "TPE"):
        return "processed"
    if type_code in ("VOX",) and re.search(r"speech|spoken|dialogue", text):
        return "dug"

    return "kit"


# ═══════════════════════════════════════════════════════════
# Energy classification
# ═══════════════════════════════════════════════════════════

PERCUSSIVE_CODES = {"KIK", "SNR", "CLP", "HAT", "PRC", "CYM", "RIM", "BRK", "DRM"}
HIGH_ENERGY_GENRES = {"trap", "drill", "house", "electronic", "footwork", "rock"}
LOW_ENERGY_GENRES = {"ambient", "lo-fi-hiphop", "classical", "dub"}


def classify_energy(bpm, type_code, genres, vibes):
    """Classify energy as low/mid/high using a simple scoring model."""
    score = 0

    # BPM
    if bpm:
        if bpm < 80:
            score -= 2
        elif bpm > 130:
            score += 2
        elif bpm > 110:
            score += 1

    # Type code
    if type_code in PERCUSSIVE_CODES:
        score += 1
    if type_code in ("PAD", "AMB", "TPE"):
        score -= 1

    # Genre
    for g in genres:
        if g in HIGH_ENERGY_GENRES:
            score += 1
            break
    for g in genres:
        if g in LOW_ENERGY_GENRES:
            score -= 1
            break

    # Vibe
    for v in vibes:
        if v in ("hype", "aggressive"):
            score += 2
        elif v in ("chill", "mellow", "dreamy"):
            score -= 2
        elif v in ("dark", "tense"):
            score += 1

    if score <= -2:
        return "low"
    elif score >= 2:
        return "high"
    return "mid"


# ═══════════════════════════════════════════════════════════
# Playability classification
# ═══════════════════════════════════════════════════════════

def classify_playability(duration, type_code, filename, bpm):
    """Classify how the sample is intended to be used."""
    fname_lower = filename.lower()

    if duration <= 0:
        return "one-shot"

    # Short samples
    if duration < 2:
        if type_code in PERCUSSIVE_CODES:
            return "one-shot"
        if re.search(r"c[3-5]|d[3-5]|e[3-5]|chromatic", fname_lower):
            return "chromatic"
        if type_code in ("FX", "RSR", "SFX"):
            return "transition"
        return "one-shot"

    # Longer samples
    if "loop" in fname_lower or bpm or type_code == "BRK":
        return "loop"
    if type_code in ("VOX", "SMP") and duration < 10:
        return "chop-ready"
    if type_code in ("PAD", "AMB", "STR", "TPE"):
        return "layer"
    if type_code in ("FX", "RSR"):
        return "transition"
    if duration > 8:
        return "chop-ready"

    return "loop" if duration >= 4 else "one-shot"


# ═══════════════════════════════════════════════════════════
# Main tagging function
# ═══════════════════════════════════════════════════════════

def tag_file(rel_path, full_path, get_dur=True):
    """Generate all tags for a single file using the spec dimensions."""
    filename = os.path.basename(rel_path)
    dirpath = os.path.dirname(rel_path)

    # Duration
    duration = get_duration(full_path) if get_dur else 0.0

    # Core dimensions
    type_code = extract_type_code(rel_path, filename)
    bpm = extract_bpm(filename, dirpath)
    key = extract_key(filename)
    vibe = extract_vibe(rel_path, filename)
    texture = extract_texture(rel_path, filename)
    genres = extract_genres(rel_path)
    source = classify_source(rel_path, filename, type_code)
    energy = classify_energy(bpm, type_code, genres, vibe)
    playability = classify_playability(duration, type_code, filename, bpm)

    # Build flat tag set (union of all dimensions for search)
    tags = set()
    tags.add(type_code)
    for v in vibe:
        tags.add(v)
    for t in texture:
        tags.add(t)
    for g in genres:
        tags.add(g)
    tags.add(source)
    tags.add(energy)
    tags.add(playability)
    if bpm:
        tags.add(f"{bpm}bpm")

    entry = {
        "path": rel_path,
        "type_code": type_code,
        "vibe": vibe,
        "texture": texture,
        "genre": genres,
        "source": source,
        "energy": energy,
        "playability": playability,
        "bpm": bpm,
        "key": key,
        "duration": round(duration, 3),
        "tags": sorted(tags),
        "mtime": os.path.getmtime(full_path),
    }
    return entry


# ═══════════════════════════════════════════════════════════
# Library walker
# ═══════════════════════════════════════════════════════════

def walk_library():
    """Walk library and return (rel_path, full_path) for all audio files."""
    files = []
    for root, dirs, filenames in os.walk(LIBRARY):
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


def load_existing_tags():
    """Load existing tag database if it exists."""
    if os.path.exists(TAGS_FILE):
        try:
            with open(TAGS_FILE, "r") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_tags(db):
    """Save tag database to JSON."""
    with open(TAGS_FILE, "w") as fh:
        json.dump(db, fh, indent=1, sort_keys=True)
    print(f"Saved {len(db)} entries to {TAGS_FILE}")


def print_summary(db):
    """Print tag frequency summary by dimension."""
    type_counts = Counter()
    vibe_counts = Counter()
    texture_counts = Counter()
    genre_counts = Counter()
    source_counts = Counter()
    energy_counts = Counter()
    play_counts = Counter()

    for entry in db.values():
        tc = entry.get("type_code")
        if tc:
            type_counts[tc] += 1
        for v in entry.get("vibe", []):
            vibe_counts[v] += 1
        for t in entry.get("texture", []):
            texture_counts[t] += 1
        for g in entry.get("genre", []):
            genre_counts[g] += 1
        s = entry.get("source")
        if s:
            source_counts[s] += 1
        e = entry.get("energy")
        if e:
            energy_counts[e] += 1
        p = entry.get("playability")
        if p:
            play_counts[p] += 1

    print(f"\n{'='*60}")
    print(f"LIBRARY TAG SUMMARY — {len(db)} files")
    print(f"{'='*60}")

    print(f"\n--- Type Codes ---")
    for code, count in type_counts.most_common():
        bar = "#" * min(count // 20, 40)
        print(f"  {code:<6s} {count:>5d}  {bar}")

    print(f"\n--- Vibe ---")
    for v, count in vibe_counts.most_common(15):
        print(f"  {v:<15s} {count:>5d}")

    print(f"\n--- Texture ---")
    for t, count in texture_counts.most_common(15):
        print(f"  {t:<15s} {count:>5d}")

    print(f"\n--- Genre ---")
    for g, count in genre_counts.most_common(15):
        print(f"  {g:<15s} {count:>5d}")

    print(f"\n--- Source ---")
    for s, count in source_counts.most_common():
        print(f"  {s:<15s} {count:>5d}")

    print(f"\n--- Energy ---")
    for e, count in energy_counts.most_common():
        print(f"  {e:<15s} {count:>5d}")

    print(f"\n--- Playability ---")
    for p, count in play_counts.most_common():
        print(f"  {p:<15s} {count:>5d}")


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

    db = load_existing_tags() if args.update else {}
    skipped = 0
    tagged = 0

    t0 = time.time()
    for i, (rel, full) in enumerate(files):
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

    # Remove stale entries
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
