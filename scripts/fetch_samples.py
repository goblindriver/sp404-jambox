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

from jambox_config import (
    is_excluded_rel_path,
    load_bank_config,
    load_settings_for_script,
    upsert_tag_entries,
)
from jambox_cache import load_score_cache, save_score_cache, score_cache_key, tags_freshness_marker
from jambox_tuning import SCORE_VERSION, load_scoring_config
from wav_utils import convert_and_tag, wav_identity
from tag_vocab import (
    TYPE_CODES as _VOCAB_TYPE_CODES,
    PLAYABILITIES as _VOCAB_PLAYABILITIES,
    GENRE_ALIASES, TEXTURE_ALIASES, VIBE_ALIASES,
)
from clap_engine import EmbeddingStore, embed_text, cosine_similarity
from discogs_fetch_bridge import discogs_keyword_tokens
from scoring_engine import (
    score_sample as _unified_score,
    bpm_score as _bpm_score_smooth,
    normalize_key as _normalize_key_se,
    keys_compatible as _keys_compatible_se,
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

# SD Card Intelligence — performance data for scoring boosts
_PERFORMANCE_PROFILE = None


def _perf_profile_cell(profile, identity):
    """Return mutable stats dict for one WAV content identity (hex sha256)."""
    if not identity:
        return None
    return profile.setdefault(identity, {
        "sessions_seen": 0,
        "bpm_adjustments": [],
        "pattern_hits": 0,
        "avg_velocity": 0.0,
    })


def _parse_pattern_pad_key(key):
    """Pattern keys look like ``E2`` (bank E, pad 2) or ``A10``."""
    if not key or not isinstance(key, str) or len(key) < 2:
        return None, None
    bank = key[0].upper()
    if bank not in "ABCDEFGHIJ":
        return None, None
    try:
        pad_num = int(key[1:])
    except ValueError:
        return None, None
    if not 1 <= pad_num <= 12:
        return None, None
    return bank, pad_num


def _identity_session_bank_pad(banks, bank, pad_num):
    blk = banks.get(bank) or {}
    for p in blk.get("pads", []):
        if int(p.get("pad", -1)) == int(pad_num) and p.get("on_card") and p.get("identity"):
            return p["identity"]
    return None


def _identity_toolkit_pad(toolkit, pad_num):
    for f in toolkit.get("files", []):
        if int(f.get("pad", -1)) == int(pad_num) and f.get("identity"):
            return f["identity"]
    return None


def _identity_bed_pad(bed_context, pad_num):
    name = f"A{int(pad_num):07d}.WAV"
    for f in bed_context.get("files", []):
        if str(f.get("name", "")).upper() == name:
            return f.get("identity")
    return None


def _ingest_card_session(profile, session):
    """Merge one archived card intelligence JSON into ``profile`` keyed by wav identity."""
    sb = session.get("session_banks") or {}
    banks = sb.get("banks") or {}
    toolkit = session.get("toolkit") or {}
    bed = session.get("bed_context") or {}

    # BPM tweaks: C–J from session_banks.adjustments (Bank A omitted — no reliable PAD_INFO).
    for adj in sb.get("adjustments", []):
        bank = str(adj.get("bank", "")).upper()
        try:
            pad_num = int(adj.get("pad", 0))
        except (TypeError, ValueError):
            continue
        if bank == "A":
            continue
        ident = _identity_toolkit_pad(toolkit, pad_num) if bank == "B" else _identity_session_bank_pad(banks, bank, pad_num)
        if adj.get("field") == "bpm" and ident:
            cell = _perf_profile_cell(profile, ident)
            cell["bpm_adjustments"].append({
                "original": adj.get("original"), "user": adj.get("user"),
            })

    # Bank B toolkit adjustments (separate list in session JSON).
    for adj in toolkit.get("adjustments", []):
        if str(adj.get("bank", "")).upper() != "B":
            continue
        try:
            pad_num = int(adj.get("pad", 0))
        except (TypeError, ValueError):
            continue
        ident = _identity_toolkit_pad(toolkit, pad_num)
        if adj.get("field") == "bpm" and ident:
            cell = _perf_profile_cell(profile, ident)
            cell["bpm_adjustments"].append({
                "original": adj.get("original"), "user": adj.get("user"),
            })

    # Pattern favorites: all banks including A (resolve A from bed filenames).
    ptn = sb.get("pattern_usage") or {}
    for item in ptn.get("most_used", []):
        bank, pad_num = _parse_pattern_pad_key(item.get("pad", ""))
        if not bank:
            continue
        if bank == "A":
            ident = _identity_bed_pad(bed, pad_num)
        elif bank == "B":
            ident = _identity_toolkit_pad(toolkit, pad_num)
        else:
            ident = _identity_session_bank_pad(banks, bank, pad_num)
        if not ident:
            continue
        cell = _perf_profile_cell(profile, ident)
        cell["pattern_hits"] += int(item.get("hit_count", 0) or 0)
        cell["avg_velocity"] = max(
            float(cell["avg_velocity"]),
            float(item.get("avg_velocity", 0) or 0),
        )


def _load_performance_profile():
    """Build per-WAV-identity performance profile from ``data/card_sessions/*.json``."""
    global _PERFORMANCE_PROFILE
    if _PERFORMANCE_PROFILE is not None:
        return _PERFORMANCE_PROFILE

    _PERFORMANCE_PROFILE = {}
    sessions_dir = os.path.join(REPO_DIR, "data", "card_sessions")
    if not os.path.isdir(sessions_dir):
        return _PERFORMANCE_PROFILE

    for sess_file in sorted(f for f in os.listdir(sessions_dir) if f.endswith(".json")):
        try:
            with open(os.path.join(sessions_dir, sess_file), encoding="utf-8") as fh:
                session = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        _ingest_card_session(_PERFORMANCE_PROFILE, session)

    return _PERFORMANCE_PROFILE


def _library_rel_path(full_path):
    """Tag DB keys are relative to the sample library root."""
    full_path = os.path.normpath(os.path.abspath(full_path))
    lib = os.path.normpath(os.path.abspath(LIBRARY))
    prefix = lib + os.sep
    if not full_path.startswith(prefix):
        return None
    rel = full_path[len(prefix) :]
    return rel.replace("\\", "/")


def _persist_sp404_wav_identity(tag_db, rel_path, staged_path):
    """Store SP-404 output identity on the tag row after a successful fetch convert.

    Returns True if the tag row was updated (caller may invalidate score cache).
    """
    ident = wav_identity(staged_path)
    if not ident or not rel_path:
        return False
    entry = tag_db.get(rel_path)
    if not isinstance(entry, dict):
        return False
    if entry.get("sp404_wav_identity") == ident:
        return False
    updated = dict(entry)
    updated["sp404_wav_identity"] = ident
    tag_db[rel_path] = updated
    try:
        upsert_tag_entries(TAGS_FILE, {rel_path: updated})
    except Exception:
        return False
    return True

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
    "BRK": {"DRM"},
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
        if upper == "SMP":
            upper = "BRK"
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
    """Score a library entry against a parsed pad query using the unified scoring engine.

    Legacy wrapper — delegates to scoring_engine.score_sample() without CLAP similarity.
    Returns a float score on the legacy 0-30+ scale (converted from unified 0-1 range).
    """
    perf = _load_performance_profile()
    unified, _breakdown = _unified_score(
        entry, parsed_query, bank_config,
        clap_similarity=None,
        performance_profile=perf,
        discogs_tokens_fn=discogs_keyword_tokens,
    )
    # Scale unified 0-1 score to legacy ~0-30 range for backward compatibility
    # with min_score thresholds and cache consumers
    return round(unified * 30, 2)


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


# ---------------------------------------------------------------------------
# CLAP embedding store (lazy singleton)
# ---------------------------------------------------------------------------

_embed_store = None

def _get_embed_store():
    global _embed_store
    if _embed_store is None:
        _embed_store = EmbeddingStore(LIBRARY)
    return _embed_store


def _clap_available():
    """Check if CLAP embeddings exist for this library."""
    store = _get_embed_store()
    return store.count > 0


# ---------------------------------------------------------------------------
# CLAP-powered search and ranking
# ---------------------------------------------------------------------------

import numpy as np


def _build_clap_query_text(parsed, bank_config):
    """Build the text string for CLAP embedding from a parsed pad query.

    Strips out structural tokens (type_code, BPM number, key) and keeps
    the descriptive keywords that carry subjective meaning.
    """
    parts = []
    if parsed["keywords"]:
        parts.extend(sorted(parsed["keywords"]))
    if parsed.get("playability"):
        parts.append(parsed["playability"])
    return " ".join(parts) if parts else "general audio sample"


def rank_library_clap(query, bank_config=None, tag_db=None, used_files=None, limit=12, min_score=0.0):
    """Rank library matches using CLAP embedding similarity.

    Scoring: CLAP cosine similarity (dominant) + BPM/key structural bonuses.
    Type_code and playability act as hard filters when specified in the query.
    Falls back to tag-based scoring if CLAP store is empty.
    """
    parsed = parse_pad_query(query)
    bank_config = bank_config or {}
    tag_db = tag_db if tag_db is not None else load_tag_db()
    tag_db = tag_db if isinstance(tag_db, dict) else {}
    used_files = used_files or set()

    store = _get_embed_store()
    if store.count == 0:
        return rank_library_matches_legacy(
            query, bank_config=bank_config, tag_db=tag_db,
            used_files=used_files, limit=limit, min_score=int(min_score * 30),
        )

    query_text = _build_clap_query_text(parsed, bank_config)
    text_emb = embed_text(query_text)[0]

    matrix = store.load_matrix()
    paths = store.paths_array()
    scores = cosine_similarity(text_emb, matrix)

    perf = _load_performance_profile()

    results = []
    for i, rel_path in enumerate(paths):
        if not rel_path:
            continue
        entry = tag_db.get(rel_path, {})
        if is_excluded_rel_path(rel_path):
            continue

        full_path = os.path.join(LIBRARY, rel_path)
        if full_path in used_files:
            continue

        # Hard filter: type_code (skip completely wrong types before scoring)
        if parsed["type_code"]:
            entry_tc = entry.get("type_code", "")
            if entry_tc != parsed["type_code"]:
                related = _RELATED_TYPE_CODES.get(parsed["type_code"], set())
                if entry_tc not in related:
                    continue

        # Unified scoring — CLAP similarity as primary signal
        final_score, breakdown = _unified_score(
            entry, parsed, bank_config,
            clap_similarity=float(scores[i]),
            performance_profile=perf,
            discogs_tokens_fn=discogs_keyword_tokens,
        )

        if final_score >= min_score:
            results.append({
                "path": full_path,
                "rel_path": rel_path,
                "score": final_score,
                "clap_sim": round(float(scores[i]), 4),
                "type_code": entry.get("type_code"),
                "playability": entry.get("playability", ""),
                "bpm": entry.get("bpm"),
                "key": entry.get("key"),
                "duration": entry.get("duration", 0) or 0,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def search_local(query, bank_config, tag_db, used_files, min_score=8, cache_entries=None):
    """Search the local library using CLAP embeddings (primary) or tag DB (fallback).

    Returns (filepath, score) or (None, 0).
    """
    if _clap_available():
        matches = rank_library_clap(
            query,
            bank_config=bank_config,
            tag_db=tag_db,
            used_files=used_files,
            limit=max(2, FETCH_TOP_N),
            min_score=0.05,
        )
    else:
        matches = rank_library_matches_legacy(
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
    """Public interface — routes to CLAP or legacy scoring."""
    if _clap_available():
        clap_min = min_score / 30.0 if min_score > 1 else min_score
        return rank_library_clap(
            query, bank_config=bank_config, tag_db=tag_db,
            used_files=used_files, limit=limit, min_score=clap_min,
        )
    return rank_library_matches_legacy(
        query, bank_config=bank_config, tag_db=tag_db,
        used_files=used_files, limit=limit, min_score=min_score,
        cache_entries=cache_entries,
    )


def rank_library_matches_legacy(query, bank_config=None, tag_db=None, used_files=None, limit=12, min_score=0, cache_entries=None):
    """Legacy tag-based ranking (fallback when no CLAP embeddings exist)."""
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
            rel = _library_rel_path(local_path)
            if rel:
                if _persist_sp404_wav_identity(tag_db, rel, staged_path) and cache_entries is not None:
                    cache_entries.clear()
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
