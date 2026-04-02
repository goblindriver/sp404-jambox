#!/usr/bin/env python3
"""
Fetch samples for the SP-404 based on bank_config.yaml.
1. Search local library TAG DATABASE for matches (not just filenames)
2. Fall back to Freesound.org for missing sounds
3. Download to library, convert, and stage for SD card

Usage:
    python scripts/fetch_samples.py              # all banks
    python scripts/fetch_samples.py --bank b     # single bank
    python scripts/fetch_samples.py --bank b --pad 1  # single pad
"""
import os, sys, glob, re, json, yaml, argparse, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from wav_utils import convert_and_tag, build_sp404_wav
import freesound_client as fs

LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
FREESOUND_DIR = os.path.join(LIBRARY, "Freesound")
TAGS_FILE = os.path.join(LIBRARY, "_tags.json")
CONFIG_PATH = os.path.join(REPO_DIR, "bank_config.yaml")
STAGING = os.path.join(REPO_DIR, "_CARD_STAGING")
SMPL_DIR = os.path.join(REPO_DIR, "sd-card-template", "ROLAND", "SP-404SX", "SMPL")

# ═══════════════════════════════════════════════════════════
# Tag database scoring
# ═══════════════════════════════════════════════════════════

# Type codes recognized from pad descriptions
TYPE_CODES = {
    "KIK", "SNR", "HAT", "CLP", "CYM", "RIM", "PRC", "BRK", "DRM",
    "BAS", "GTR", "KEY", "SYN", "PAD", "STR", "BRS", "PLK", "WND", "VOX", "SMP",
    "FX", "SFX", "AMB", "FLY", "TPE", "RSR",
}

# Playability keywords
PLAYABILITY_KEYWORDS = {"one-shot", "loop", "chop-ready", "chromatic", "layer", "transition"}

# Words to ignore in scoring
STOP_WORDS = {"a", "an", "the", "or", "and", "in", "for", "not", "but", "with", "style", "of"}


def parse_pad_query(query):
    """Parse a pad description into structured search terms.

    Returns dict with:
      type_code: str or None
      playability: str or None
      bpm: int or None
      key: str or None
      keywords: set of remaining search words
    """
    words = query.strip().split()
    result = {
        "type_code": None,
        "playability": None,
        "bpm": None,
        "key": None,
        "keywords": set(),
    }

    for word in words:
        upper = word.upper()
        lower = word.lower()

        # Type code (always uppercase in pad descriptions)
        if upper in TYPE_CODES and not result["type_code"]:
            result["type_code"] = upper
            continue

        # Playability
        if lower in PLAYABILITY_KEYWORDS:
            result["playability"] = lower
            continue

        # BPM (e.g., "112bpm" or "120")
        bpm_match = re.match(r"^(\d{2,3})(?:bpm)?$", lower)
        if bpm_match:
            val = int(bpm_match.group(1))
            if 50 <= val <= 250:
                result["bpm"] = val
                continue

        # Musical key (e.g., "Am", "Dm", "F", "Fs")
        key_match = re.match(r"^([A-G][bs]?m?)$", word)
        if key_match and lower not in STOP_WORDS:
            result["key"] = word
            continue

        # Regular keyword
        if lower not in STOP_WORDS and len(lower) >= 2:
            result["keywords"].add(lower)

    return result


def score_from_tags(entry, parsed_query, bank_config):
    """Score a library entry against a parsed pad query using the tag database.

    Scoring weights:
      Type code match:     +10 (critical — wrong type = wrong sound)
      Playability match:   +5  (one-shot vs loop matters a lot)
      BPM within ±5:       +4
      BPM within ±15:      +2
      Key match:           +3
      Keyword in tags:     +3  (vibe, texture, genre from tag DB)
      Keyword in filename: +1  (fallback for untagged dimensions)

    Penalties:
      Type code MISMATCH:  -8  (asking for KIK, got PAD = bad)
      Playability mismatch:-4  (asking for one-shot, got loop = bad)
      Duration mismatch:   -3  (one-shot pad but file > 10s)
    """
    score = 0
    q = parsed_query

    # --- Type code (most important) ---
    entry_tc = entry.get("type_code", "")
    if q["type_code"]:
        if entry_tc == q["type_code"]:
            score += 10
        else:
            # Partial credit for related types
            related = {
                "KIK": {"DRM"}, "SNR": {"DRM"}, "HAT": {"DRM"}, "CLP": {"DRM", "SNR"},
                "CYM": {"HAT"}, "RIM": {"PRC", "SNR"}, "PRC": {"DRM"},
                "BRK": {"DRM", "SMP"}, "SMP": {"BRK"},
                "SYN": {"PAD", "KEY"}, "PAD": {"SYN", "AMB"}, "KEY": {"SYN"},
                "FX": {"SFX", "RSR"}, "SFX": {"FX"}, "RSR": {"FX"},
                "AMB": {"PAD", "TPE"}, "TPE": {"AMB"},
            }
            if entry_tc in related.get(q["type_code"], set()):
                score += 3  # related but not exact
            else:
                score -= 8  # wrong category entirely

    # --- Playability ---
    entry_play = entry.get("playability", "")
    if q["playability"]:
        if entry_play == q["playability"]:
            score += 5
        elif q["playability"] == "one-shot" and entry_play == "loop":
            score -= 4  # definitely wrong
        elif q["playability"] == "loop" and entry_play == "one-shot":
            score -= 4

    # --- BPM ---
    entry_bpm = entry.get("bpm")
    target_bpm = q["bpm"] or bank_config.get("bpm")
    if target_bpm and entry_bpm:
        diff = abs(entry_bpm - target_bpm)
        if diff <= 5:
            score += 4
        elif diff <= 15:
            score += 2
        elif diff > 30:
            score -= 2

    # --- Key ---
    entry_key = entry.get("key")
    if q["key"] and entry_key:
        if entry_key.lower() == q["key"].lower():
            score += 3
        # Relative major/minor get partial credit
        elif _keys_compatible(q["key"], entry_key):
            score += 1

    # --- Keywords vs tag dimensions ---
    entry_tags = set(t.lower() for t in entry.get("tags", []))
    entry_vibes = set(v.lower() for v in entry.get("vibe", []))
    entry_textures = set(t.lower() for t in entry.get("texture", []))
    entry_genres = set(g.lower() for g in entry.get("genre", []))

    for kw in q["keywords"]:
        if kw in entry_vibes or kw in entry_textures or kw in entry_genres:
            score += 3  # dimension match — high confidence
        elif kw in entry_tags:
            score += 2  # flat tag match
        elif kw in os.path.basename(entry.get("path", "")).lower():
            score += 1  # filename fallback

    # --- Duration penalty for one-shots ---
    duration = entry.get("duration", 0)
    if q["playability"] == "one-shot" and duration > 10:
        score -= 3
    if q["playability"] == "loop" and duration < 1:
        score -= 3

    # --- Plex metadata bonuses ---
    # Stems from personal library with Plex moods get a small bonus
    # because the vibes are machine-tagged (more reliable than filename inference)
    if entry.get("plex_moods"):
        score += 1  # Plex-tagged = higher confidence metadata
    # Samples from tracks with play history rank higher (user actually listens to these)
    if entry.get("plex_play_count", 0) > 0:
        score += 2

    return score


# Relative major/minor key compatibility
_KEY_RELATIVES = {
    "Am": "C", "C": "Am", "Dm": "F", "F": "Dm",
    "Em": "G", "G": "Em", "Bm": "D", "D": "Bm",
    "Fm": "Ab", "Ab": "Fm", "Gm": "Bb", "Bb": "Gm",
    "Cm": "Eb", "Eb": "Cm", "Fsm": "A", "A": "Fsm",
    "Bbm": "Db", "Db": "Bbm",
}


def _keys_compatible(key_a, key_b):
    """Check if two keys are relative major/minor."""
    return _KEY_RELATIVES.get(key_a) == key_b or _KEY_RELATIVES.get(key_b) == key_a


# ═══════════════════════════════════════════════════════════
# Local library search (tag-database-powered)
# ═══════════════════════════════════════════════════════════

def load_tag_db():
    """Load the tag database."""
    try:
        with open(TAGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("  WARNING: No tag database found. Run: python scripts/tag_library.py")
        return {}


def search_local(query, bank_config, tag_db, used_files, min_score=8):
    """Search the local library using the tag database.

    Args:
        query: pad description string
        bank_config: bank-level config (bpm, key, etc.)
        tag_db: the loaded _tags.json database
        used_files: set of file paths already assigned (for deduplication)
        min_score: minimum score to accept a match

    Returns (filepath, score) or (None, 0).
    """
    parsed = parse_pad_query(query)
    best_path = None
    best_score = 0

    for rel_path, entry in tag_db.items():
        # Skip already-used files
        full_path = os.path.join(LIBRARY, rel_path)
        if full_path in used_files:
            continue

        score = score_from_tags(entry, parsed, bank_config)
        if score > best_score:
            best_score = score
            best_path = full_path

    if best_score >= min_score:
        return best_path, best_score
    return None, 0


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def fetch_pad(bank_letter, pad_number, pad_query, bank_config, tag_db, used_files):
    """Fetch a sample for one pad. Returns the path to the staged file or None."""
    bank_name = bank_config.get('name', bank_letter)
    sp404_name = f"{bank_letter.upper()}{pad_number:07d}.WAV"
    staged_path = os.path.join(STAGING, sp404_name)

    # 1. Search local library via tag database
    local_path, score = search_local(pad_query, bank_config, tag_db, used_files)
    if local_path:
        print(f"    LOCAL (score={score}): {os.path.relpath(local_path, LIBRARY)}")
        if convert_and_tag(local_path, staged_path, bank_letter.upper(), pad_number):
            used_files.add(local_path)  # mark as used
            return staged_path
        print(f"    Conversion failed, trying Freesound...")

    # 2. Search Freesound
    parsed = parse_pad_query(pad_query)
    is_oneshot = parsed["playability"] == "one-shot" or pad_number <= 4
    dur_min = 0.1 if is_oneshot else 1.0
    dur_max = 10.0 if is_oneshot else 60.0

    # Build a focused search query (type + top keywords)
    search_words = []
    if parsed["type_code"]:
        # Map type code to a search-friendly word
        tc_search = {
            "KIK": "kick", "SNR": "snare", "HAT": "hihat", "CLP": "clap",
            "CYM": "cymbal", "RIM": "rimshot", "PRC": "percussion",
            "BRK": "drum loop break", "BAS": "bass", "GTR": "guitar",
            "KEY": "piano keys", "SYN": "synth", "PAD": "pad ambient",
            "STR": "strings", "BRS": "brass horn", "PLK": "pluck",
            "WND": "woodwind", "VOX": "vocal voice", "SMP": "sample loop",
            "FX": "sound effect", "SFX": "stab hit impact", "RSR": "riser sweep",
            "AMB": "ambient atmosphere", "FLY": "foley", "TPE": "tape vinyl",
        }.get(parsed["type_code"], "")
        search_words.append(tc_search)
    search_words.extend(list(parsed["keywords"])[:4])
    search_query = " ".join(search_words)

    print(f"    FREESOUND: searching '{search_query}'...")
    time.sleep(0.3)

    dl_dir = os.path.join(FREESOUND_DIR, re.sub(r'[^\w\-]', '_', bank_name))
    os.makedirs(dl_dir, exist_ok=True)
    dl_base = re.sub(r'[^\w\-]', '_', pad_query)[:60]
    dl_path = os.path.join(dl_dir, f"{bank_letter}{pad_number}_{dl_base}")

    downloaded, sound_info = fs.search_and_download(
        search_query, dl_path, duration_min=dur_min, duration_max=dur_max,
    )

    if not downloaded:
        # Try simpler query
        simple_words = search_query.split()[:3]
        simple_query = ' '.join(simple_words)
        print(f"    FREESOUND: retrying '{simple_query}'...")
        time.sleep(0.3)
        downloaded, sound_info = fs.search_and_download(
            simple_query, dl_path, duration_min=dur_min, duration_max=dur_max,
        )

    if downloaded and sound_info:
        print(f"    FOUND: '{sound_info['name']}' by {sound_info['username']} ({sound_info['duration']:.1f}s)")

        attr_path = dl_path + '.attribution.txt'
        with open(attr_path, 'w') as f:
            f.write(f"Sound: {sound_info['name']}\n")
            f.write(f"Author: {sound_info['username']}\n")
            f.write(f"License: {sound_info['license']}\n")
            f.write(f"URL: https://freesound.org/people/{sound_info['username']}/sounds/{sound_info['id']}/\n")

        if convert_and_tag(downloaded, staged_path, bank_letter.upper(), pad_number):
            used_files.add(downloaded)
            return staged_path
        print(f"    Conversion failed for {downloaded}")
    else:
        print(f"    NO MATCH found on Freesound")

    return None


def fetch_bank(bank_letter, bank_config, tag_db, used_files):
    """Fetch all samples for one bank."""
    name = bank_config.get('name', bank_letter)
    pads = bank_config.get('pads', {})
    if not pads:
        return 0

    print(f"\n=== Bank {bank_letter.upper()}: {name} ===")
    bpm = bank_config.get('bpm', '')
    key = bank_config.get('key', '')
    if bpm or key:
        print(f"    Target: {bpm} BPM, Key: {key}")

    fetched = 0
    for pad_num, pad_query in pads.items():
        pad_num = int(pad_num)
        print(f"  Pad {pad_num}: {pad_query}")
        result = fetch_pad(bank_letter, pad_num, pad_query, bank_config, tag_db, used_files)
        if result:
            fetched += 1
    print(f"  → {fetched}/{len(pads)} pads filled")
    return fetched


def main():
    parser = argparse.ArgumentParser(description='Fetch samples for SP-404 banks')
    parser.add_argument('--bank', '-b', help='Single bank letter to fetch (e.g., b)')
    parser.add_argument('--pad', '-p', type=int, help='Single pad number (use with --bank)')
    parser.add_argument('--freesound-only', action='store_true', help='Skip local library search')
    args = parser.parse_args()

    config = load_config()
    os.makedirs(STAGING, exist_ok=True)
    os.makedirs(FREESOUND_DIR, exist_ok=True)

    # Load tag database once
    tag_db = load_tag_db()
    if not tag_db:
        print("WARNING: Tag database is empty. Local matching will be limited.")
        print("Run: python scripts/tag_library.py")

    # Global deduplication set — no file used twice across any bank
    used_files = set()

    total_fetched = 0
    total_pads = 0

    for key, bank_config in config.items():
        if not key.startswith('bank_') or not bank_config:
            continue
        bank_letter = key.split('_')[1]

        if args.bank and bank_letter.lower() != args.bank.lower():
            continue

        pads = bank_config.get('pads', {})
        if not pads:
            continue

        if args.pad:
            pad_query = pads.get(args.pad) or pads.get(str(args.pad))
            if pad_query:
                print(f"\n=== Bank {bank_letter.upper()} Pad {args.pad} ===")
                print(f"  {pad_query}")
                result = fetch_pad(bank_letter, args.pad, pad_query, bank_config, tag_db, used_files)
                if result:
                    total_fetched += 1
                total_pads += 1
        else:
            fetched = fetch_bank(bank_letter, bank_config, tag_db, used_files)
            total_fetched += fetched
            total_pads += len(pads)

    print(f"\n{'='*50}")
    print(f"Total: {total_fetched}/{total_pads} pads filled")
    print(f"Staged in: {STAGING}")

    if total_fetched > 0:
        os.makedirs(SMPL_DIR, exist_ok=True)
        import shutil
        for f in glob.glob(os.path.join(STAGING, "*.WAV")):
            shutil.copy2(f, SMPL_DIR)
        print(f"Copied to: {SMPL_DIR}")


if __name__ == '__main__':
    main()
