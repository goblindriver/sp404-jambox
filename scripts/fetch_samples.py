#!/usr/bin/env python3
"""
Fetch samples for the SP-404 based on bank_config.yaml.
Search local library TAG DATABASE for matches and stage for SD card.

Usage:
    python scripts/fetch_samples.py              # all banks
    python scripts/fetch_samples.py --bank b     # single bank
    python scripts/fetch_samples.py --bank b --pad 1  # single pad
"""
import os, sys, re, json, argparse, hashlib, random, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from jambox_config import is_excluded_rel_path, load_bank_config, load_settings_for_script
from jambox_cache import load_score_cache, save_score_cache, score_cache_key, tags_freshness_marker
from jambox_tuning import SCORE_VERSION, load_scoring_config
from wav_utils import convert_and_tag
from tag_vocab import (
    TYPE_CODES as _VOCAB_TYPE_CODES,
    PLAYABILITIES as _VOCAB_PLAYABILITIES,
    GENRE_ALIASES, TEXTURE_ALIASES, VIBE_ALIASES,
)

SETTINGS = load_settings_for_script(__file__)
SCORING_CONFIG = load_scoring_config()
SCORING_WEIGHTS = SCORING_CONFIG["weights"]
SCORING_VERSION = SCORE_VERSION
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
CONFIG_PATH = SETTINGS["CONFIG_PATH"]
STAGING = SETTINGS["STAGING_DIR"]
SMPL_DIR = SETTINGS["SMPL_DIR"]
FETCH_HISTORY_FILE = SETTINGS.get("FETCH_HISTORY_FILE", os.path.join(REPO_DIR, "data", "fetch_history.json"))
FETCH_TOP_N = int(SETTINGS.get("FETCH_DIVERSITY_TOP_N", 8) or 8)
FETCH_DETERMINISTIC = str(SETTINGS.get("FETCH_DETERMINISTIC", "0")).strip().lower() in ("1", "true", "yes", "on")
FETCH_COOLDOWN_SECONDS = int(SETTINGS.get("FETCH_DIVERSITY_COOLDOWN_SECONDS", 6 * 3600) or 21600)

# ═══════════════════════════════════════════════════════════
# Tag database scoring
# ═══════════════════════════════════════════════════════════

TYPE_CODES = _VOCAB_TYPE_CODES
PLAYABILITY_KEYWORDS = _VOCAB_PLAYABILITIES

STOP_WORDS = {"a", "an", "the", "or", "and", "in", "for", "not", "but", "with", "style", "of"}

_ALL_ALIASES = {**GENRE_ALIASES, **TEXTURE_ALIASES, **VIBE_ALIASES}

_WEIGHTS_HASH = hashlib.md5(json.dumps(SCORING_WEIGHTS, sort_keys=True).encode()).hexdigest()[:8]

_RELATED_TYPE_CODES_RAW = {
    "KIK": {"DRM"}, "SNR": {"DRM"}, "HAT": {"DRM"}, "CLP": {"DRM", "SNR"},
    "CYM": {"HAT"}, "RIM": {"PRC", "SNR"}, "PRC": {"DRM"},
    "BRK": {"DRM", "SMP"}, "SMP": {"BRK"},
    "SYN": {"PAD", "KEY"}, "PAD": {"SYN", "AMB"}, "KEY": {"SYN"},
    "FX": {"SFX", "RSR"}, "SFX": {"FX"}, "RSR": {"FX"},
    "AMB": {"PAD", "TPE"}, "TPE": {"AMB"},
    "HRN": {"BRS"}, "BRS": {"HRN"},
    "DRM": {"KIK", "SNR", "HAT", "BRK", "PRC"},
}
# Ensure bidirectional: if A relates to B, B relates to A
_RELATED_TYPE_CODES = {}
for tc, relatives in _RELATED_TYPE_CODES_RAW.items():
    _RELATED_TYPE_CODES.setdefault(tc, set()).update(relatives)
    for rel in relatives:
        _RELATED_TYPE_CODES.setdefault(rel, set()).add(tc)


def parse_pad_query(query):
    """Parse a pad description into structured search terms.

    Returns dict with:
      type_code: str or None
      playability: str or None
      bpm: int or None
      key: str or None
      keywords: set of remaining search words
    """
    query = "" if query is None else str(query)
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

    result["keywords"] = {_ALL_ALIASES.get(kw, kw) for kw in result["keywords"]}

    result["energy"] = None
    for kw in result["keywords"]:
        if kw in ("low", "mid", "high"):
            result["energy"] = kw
            result["keywords"].discard(kw)
            break

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
    weights = SCORING_WEIGHTS
    q = parsed_query

    # --- Type code (most important) ---
    entry_tc = entry.get("type_code", "")
    if q["type_code"]:
        if entry_tc == q["type_code"]:
            score += weights["type_exact"]
        elif not entry_tc:
            pass
        elif entry_tc in _RELATED_TYPE_CODES.get(q["type_code"], set()):
            score += weights["type_related"]
        else:
            score += weights["type_mismatch"]

    # --- Playability ---
    entry_play = entry.get("playability", "")
    if q["playability"]:
        if entry_play == q["playability"]:
            score += weights["playability_exact"]
        elif q["playability"] == "one-shot" and entry_play == "loop":
            score += weights["playability_mismatch"]  # definitely wrong
        elif q["playability"] == "loop" and entry_play == "one-shot":
            score += weights["playability_mismatch"]

    # --- BPM ---
    entry_bpm = entry.get("bpm")
    target_bpm = q["bpm"] or bank_config.get("bpm")
    if target_bpm and entry_bpm:
        try:
            diff = abs(float(entry_bpm) - float(target_bpm))
        except (TypeError, ValueError):
            diff = 999
        if diff <= 5:
            score += weights["bpm_close"]
        elif diff <= 15:
            score += weights["bpm_near"]
        elif diff <= 30:
            score += weights.get("bpm_distant", -1)
        else:
            score += weights["bpm_far"]

    # --- Key ---
    entry_key = entry.get("key")
    target_key = q["key"] or bank_config.get("key")
    if target_key and target_key.upper() != "XX" and entry_key:
        norm_entry = _normalize_key(entry_key)
        norm_target = _normalize_key(target_key)
        if norm_entry.lower() == norm_target.lower():
            score += weights["key_exact"]
        elif _keys_compatible(target_key, entry_key):
            score += weights["key_compatible"]

    # --- Keywords vs tag dimensions ---
    entry_tags = set(t.lower() for t in entry.get("tags", []))
    entry_vibes = set(v.lower() for v in entry.get("vibe", []))
    entry_textures = set(t.lower() for t in entry.get("texture", []))
    entry_genres = set(g.lower() for g in entry.get("genre", []))
    fname_lower = os.path.basename(entry.get("path", "")).lower()

    for kw in q["keywords"]:
        if kw in entry_vibes or kw in entry_textures or kw in entry_genres:
            score += weights["keyword_dimension"]
        elif kw in entry_tags:
            score += weights["keyword_tag"]
        elif kw in fname_lower:
            score += weights["keyword_filename"]

    # --- Duration penalty for one-shots ---
    duration = entry.get("duration", 0)
    if q["playability"] == "one-shot" and duration > 10:
        score += weights["oneshot_long_penalty"]
    if q["playability"] == "loop" and duration < 1:
        score += weights["loop_short_penalty"]

    # --- Energy dimension ---
    entry_energy = (entry.get("energy") or "").lower()
    if entry_energy and q["energy"]:
        if entry_energy == q["energy"]:
            score += weights.get("energy_match", 0)
        else:
            score += weights.get("energy_mismatch", 0)

    # --- Instrument hint ---
    hint = (entry.get("instrument_hint") or "").lower().strip()
    if hint and q["keywords"]:
        hint_tokens = set(hint.split())
        if hint_tokens & q["keywords"]:
            score += weights.get("instrument_hint_match", 0)

    # --- Quality score tiebreaker ---
    qs = entry.get("quality_score")
    if isinstance(qs, (int, float)) and 1 <= qs <= 5:
        score += qs * weights.get("quality_tiebreaker", 0)

    # --- Plex metadata bonuses ---
    if entry.get("plex_moods"):
        score += weights["plex_moods_bonus"]
    if entry.get("plex_play_count", 0) > 0:
        score += weights["plex_play_count_bonus"]

    return score


# Normalize sharp/flat enharmonic spellings to a canonical form
_ENHARMONIC = {
    "Gs": "Ab", "As": "Bb", "Cs": "Db", "Ds": "Eb", "Fs": "Gb",
    "Gsm": "Abm", "Asm": "Bbm", "Csm": "Dbm", "Dsm": "Ebm", "Fsm": "Gbm",
    "G#": "Ab", "A#": "Bb", "C#": "Db", "D#": "Eb", "F#": "Gb",
    "G#m": "Abm", "A#m": "Bbm", "C#m": "Dbm", "D#m": "Ebm", "F#m": "Gbm",
}

def _normalize_key(key):
    """Normalize sharp-notation keys to flat equivalents for consistent lookup."""
    if not key:
        return key
    return _ENHARMONIC.get(key, key)

_KEY_RELATIVES = {
    "Am": "C", "C": "Am", "Dm": "F", "F": "Dm",
    "Em": "G", "G": "Em", "Bm": "D", "D": "Bm",
    "Abm": "B", "B": "Abm", "Bbm": "Db", "Db": "Bbm",
    "Dbm": "E", "E": "Dbm", "Ebm": "Gb", "Gb": "Ebm",
    "Gbm": "A", "A": "Gbm",
    "Fm": "Ab", "Ab": "Fm", "Gm": "Bb", "Bb": "Gm",
    "Cm": "Eb", "Eb": "Cm",
}


def _keys_compatible(key_a, key_b):
    """Check if two keys are relative major/minor (enharmonic-aware)."""
    a = _normalize_key(key_a)
    b = _normalize_key(key_b)
    return _KEY_RELATIVES.get(a) == b or _KEY_RELATIVES.get(b) == a


# ═══════════════════════════════════════════════════════════
# Local library search (tag-database-powered)
# ═══════════════════════════════════════════════════════════

def load_tag_db():
    """Load the tag database."""
    from jambox_config import load_tag_db as _load
    db = _load(TAGS_FILE)
    if not db:
        print("  WARNING: No tag database found. Run: python scripts/tag_library.py")
    return db


def search_local(query, bank_config, tag_db, used_files, min_score=8, cache_entries=None):
    """Search the local library using the tag database.

    Args:
        query: pad description string
        bank_config: bank-level config (bpm, key, etc.)
        tag_db: the loaded _tags.json database
        used_files: set of file paths already assigned (for deduplication)
        min_score: minimum score to accept a match
        cache_entries: optional in-memory score cache (avoids disk I/O per pad)

    Returns (filepath, score) or (None, 0).
    """
    matches = rank_library_matches(
        query,
        bank_config=bank_config,
        tag_db=tag_db,
        used_files=used_files,
        limit=max(2, FETCH_TOP_N),
        min_score=min_score,
        cache_entries=cache_entries,
    )
    if matches:
        picked = choose_diverse_match(matches, deterministic=FETCH_DETERMINISTIC)
        return picked["path"], picked["score"]
    return None, 0


def rank_library_matches(query, bank_config=None, tag_db=None, used_files=None, limit=12, min_score=0, cache_entries=None):
    """Return ranked library matches for a natural-language-derived query.

    When cache_entries is provided, uses it as the in-memory cache and skips
    disk I/O. The caller is responsible for calling save_score_cache once at
    session end. When None, loads/saves per call (backward compatible).
    """
    parsed = parse_pad_query(query)
    bank_config = bank_config or {}
    tag_db = tag_db if tag_db is not None else load_tag_db()
    tag_db = tag_db if isinstance(tag_db, dict) else {}
    used_files = used_files or set()

    owns_cache = cache_entries is None
    if owns_cache:
        cache_entries = load_score_cache(LIBRARY)

    cache_key = score_cache_key(
        parsed,
        bank_config,
        score_version=SCORING_VERSION,
        tags_marker=tags_freshness_marker(TAGS_FILE),
        weights_hash=_WEIGHTS_HASH,
    )
    cached_results = cache_entries.get(cache_key)

    if not isinstance(cached_results, list):
        cached_results = []
        for rel_path, entry in tag_db.items():
            if is_excluded_rel_path(rel_path):
                continue
            full_path = os.path.join(LIBRARY, rel_path)
            score = score_from_tags(entry, parsed, bank_config)
            cached_results.append({
                "path": full_path,
                "rel_path": rel_path,
                "score": score,
                "type_code": entry.get("type_code"),
                "playability": entry.get("playability"),
                "bpm": entry.get("bpm"),
                "key": entry.get("key"),
                "tags": entry.get("tags", []),
                "vibe": entry.get("vibe", []),
                "genre": entry.get("genre", []),
                "texture": entry.get("texture", []),
                "duration": entry.get("duration"),
            })
        cached_results.sort(key=lambda item: item["score"], reverse=True)
        cached_results = cached_results[:500]
        cache_entries[cache_key] = cached_results
        if owns_cache:
            save_score_cache(LIBRARY, cache_entries)

    filtered = [
        item for item in cached_results
        if item["path"] not in used_files and item["score"] >= min_score
    ]
    return filtered[:limit]


def _load_fetch_history():
    try:
        with open(FETCH_HISTORY_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"last_used": {}}
    if not isinstance(data, dict):
        return {"last_used": {}}
    last_used = data.get("last_used")
    if not isinstance(last_used, dict):
        last_used = {}
    return {"last_used": last_used}


def _save_fetch_history(history):
    try:
        os.makedirs(os.path.dirname(FETCH_HISTORY_FILE), exist_ok=True)
        with open(FETCH_HISTORY_FILE, "w", encoding="utf-8") as handle:
            json.dump(history, handle, indent=2, sort_keys=True)
    except OSError:
        pass


def choose_diverse_match(matches, deterministic=False):
    """Pick from top-N with recency penalties to reduce repetition."""
    if not matches:
        return None
    top = matches[:max(1, FETCH_TOP_N)]
    if deterministic:
        return top[0]

    now = int(time.time())
    history = _load_fetch_history()
    last_used = history.get("last_used", {})
    weighted = []
    for item in top:
        base = max(float(item.get("score", 0)), 0.1)
        path = item.get("path")
        last_ts = int(last_used.get(path, 0) or 0)
        age = now - last_ts
        cooldown_factor = 1.0 if age >= FETCH_COOLDOWN_SECONDS else max(0.1, age / max(FETCH_COOLDOWN_SECONDS, 1))
        weight = max(0.001, base * cooldown_factor)
        weighted.append((item, weight))

    total_weight = sum(weight for _, weight in weighted)
    if total_weight <= 0:
        return top[0]
    roll = random.uniform(0, total_weight)
    cursor = 0.0
    chosen = top[0]
    for item, weight in weighted:
        cursor += weight
        if roll <= cursor:
            chosen = item
            break

    chosen_path = chosen.get("path")
    if chosen_path:
        last_used[chosen_path] = now
        history["last_used"] = last_used
        _save_fetch_history(history)
    return chosen


def load_config():
    return load_bank_config(CONFIG_PATH, strict=True)


def clear_staging_wavs(bank=None, pad=None):
    """Remove staged WAV outputs for the targeted scope.

    bank=None, pad=None → wipe all WAVs (full fetch).
    bank='b', pad=None → wipe only Bank B WAVs.
    bank='b', pad=3    → wipe only B0000003.WAV.
    """
    if not os.path.isdir(STAGING):
        return

    if bank and pad:
        target = f"{bank.upper()}{int(pad):07d}.WAV"
        path = os.path.join(STAGING, target)
        if os.path.isfile(path):
            os.remove(path)
        return

    prefix = bank.upper() if bank else None
    for name in os.listdir(STAGING):
        if not name.upper().endswith('.WAV'):
            continue
        if prefix and not name.upper().startswith(prefix):
            continue
        os.remove(os.path.join(STAGING, name))


def fetch_pad(bank_letter, pad_number, pad_query, bank_config, tag_db, used_files, cache_entries=None):
    """Fetch a sample for one pad. Returns the path to the staged file or None."""
    sp404_name = f"{bank_letter.upper()}{pad_number:07d}.WAV"
    staged_path = os.path.join(STAGING, sp404_name)

    local_path, score = search_local(pad_query, bank_config, tag_db, used_files, cache_entries=cache_entries)
    if local_path:
        print(f"    LOCAL (score={score}): {os.path.relpath(local_path, LIBRARY)}")
        if convert_and_tag(local_path, staged_path, bank_letter.upper(), pad_number):
            used_files.add(local_path)  # mark as used
            return staged_path
        print(f"    Conversion failed")

    print(f"    NO MATCH found in local library")
    return None


def main():
    parser = argparse.ArgumentParser(description='Fetch samples for SP-404 banks')
    parser.add_argument('--bank', '-b', help='Single bank letter to fetch (e.g., b)')
    parser.add_argument('--pad', '-p', type=int, help='Single pad number (use with --bank)')
    args = parser.parse_args()
    if args.pad is not None and not args.bank:
        parser.error('--pad requires --bank')
    if args.pad is not None and not 1 <= args.pad <= 12:
        parser.error('--pad must be between 1 and 12')

    config = load_config()
    os.makedirs(STAGING, exist_ok=True)
    clear_staging_wavs(bank=args.bank, pad=args.pad)

    # Load tag database once
    tag_db = load_tag_db()
    if not tag_db:
        print("WARNING: Tag database is empty. Local matching will be limited.")
        print("Run: python scripts/tag_library.py")

    used_files = set()
    score_cache = load_score_cache(LIBRARY)

    total_fetched = 0
    total_pads = 0
    generated_files = []

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
                result = fetch_pad(bank_letter, args.pad, pad_query, bank_config, tag_db, used_files, cache_entries=score_cache)
                if result:
                    total_fetched += 1
                    generated_files.append(result)
                total_pads += 1
        else:
            print(f"\n=== Bank {bank_letter.upper()}: {bank_config.get('name', bank_letter)} ===")
            bank_bpm = bank_config.get('bpm', '')
            bank_key = bank_config.get('key', '')
            if bank_bpm or bank_key:
                print(f"    Target: {bank_bpm} BPM, Key: {bank_key}")

            fetched = 0
            valid_pads = 0
            for pad_num, pad_query in pads.items():
                try:
                    pad_num = int(pad_num)
                except (TypeError, ValueError):
                    continue
                valid_pads += 1
                print(f"  Pad {pad_num}: {pad_query}")
                result = fetch_pad(bank_letter, pad_num, pad_query, bank_config, tag_db, used_files, cache_entries=score_cache)
                if result:
                    fetched += 1
                    generated_files.append(result)
            print(f"  → {fetched}/{valid_pads} pads filled")
            total_fetched += fetched
            total_pads += valid_pads

    save_score_cache(LIBRARY, score_cache)

    print(f"\n{'='*50}")
    print(f"Total: {total_fetched}/{total_pads} pads filled")
    print(f"Staged in: {STAGING}")

    if total_fetched > 0:
        os.makedirs(SMPL_DIR, exist_ok=True)
        import shutil
        for f in generated_files:
            shutil.copy2(f, SMPL_DIR)
        print(f"Copied to: {SMPL_DIR}")


if __name__ == '__main__':
    main()
