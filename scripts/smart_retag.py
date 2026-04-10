#!/usr/bin/env python3
"""Smart retag: LLM-powered sample library tagger with audio feature analysis.

Extracts spectral features via librosa, sends them to a local LLM (Ollama),
and writes enriched tags back to _tags.json. Checkpoint/resume for overnight
runs on large libraries. Quarantines low-quality samples.

Usage:
    python scripts/smart_retag.py --validate --limit 100   # validation batch
    python scripts/smart_retag.py --all                     # full library pass
    python scripts/smart_retag.py --resume                  # resume from checkpoint
    python scripts/smart_retag.py --path Drums/Kicks/       # specific directory
    python scripts/smart_retag.py --dry-run --limit 10      # feature extraction only

Env:
    SP404_LLM_MODEL — Ollama model (default: qwen3.5:9b).
    SP404_SMART_RETAG_SKIP_ABOVE_SECONDS — if set, skip LLM entirely when duration >= this (features only).
    SP404_SMART_RETAG_WORKERS — concurrent workers (default 3, max SP404_SMART_RETAG_WORKERS_MAX). Ollama manages model memory; tune workers if the server queues or OOMs.
"""

import argparse
import json
import os
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import (
    LIBRARY_SKIP_DIRS,
    LONG_HOLD_DIRNAME,
    delete_tag_paths,
    is_excluded_rel_path,
    load_settings_for_script,
    upsert_tag_entries,
)
from audio_analysis import extract_features, is_available as librosa_available
from llm_client import LLMError, call_llm_chat

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
LLM_ENDPOINT = SETTINGS.get("LLM_ENDPOINT", "")
# Default to qwen3.5:9b — newer MoE arch, faster inference than qwen3:32b.
LLM_MODEL = SETTINGS.get("LLM_MODEL", "qwen3.5:9b")
SMART_RETAG_SKIP_ABOVE_SECONDS = SETTINGS.get("SMART_RETAG_SKIP_ABOVE_SECONDS")
SMART_RETAG_WORKERS_CAP = int(SETTINGS.get("SMART_RETAG_WORKERS_MAX", 16))
SMART_RETAG_WORKERS_DEFAULT = max(
    1, min(int(SETTINGS.get("SMART_RETAG_WORKERS", 3)), SMART_RETAG_WORKERS_CAP)
)
LLM_TIMEOUT = SETTINGS.get("LLM_TIMEOUT", 30)
SMART_RETAG_LLM_TIMEOUT = SETTINGS.get("SMART_RETAG_LLM_TIMEOUT")
SMART_RETAG_LLM_RETRIES = SETTINGS.get("SMART_RETAG_LLM_RETRIES")
REPO_DIR = os.path.dirname(SCRIPTS_DIR)
CHECKPOINT_PATH = os.path.join(REPO_DIR, "data", "retag_checkpoint.json")
QUARANTINE_DIR = os.path.join(LIBRARY, "_QUARANTINE")
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}
SKIP_DIRS = LIBRARY_SKIP_DIRS

BATCH_SIZE = 50
_tag_db_lock = threading.Lock()
_persist_lock = threading.RLock()

# Type code processing order — preset-demand-first
TYPE_CODE_ORDER = [
    "KIK", "SNR", "HAT", "CLP", "CYM", "RIM", "PRC",
    "BRK",
    "BAS",
    "SYN", "PAD", "KEY",
    "VOX",
    "FX", "SFX", "RSR",
    "GTR", "HRN", "STR",
    "AMB", "FLY", "TPE",
]

from tag_vocab import (
    TYPE_CODES as VALID_TYPE_CODES,
    VIBES as VALID_VIBES,
    TEXTURES as VALID_TEXTURES,
    GENRES as VALID_GENRES,
    ENERGIES as VALID_ENERGIES,
    PLAYABILITIES as VALID_PLAYABILITIES,
    GENRE_ALIASES as _GENRE_ALIASES,
    VIBE_ALIASES as _VIBE_ALIASES,
    TEXTURE_ALIASES as _TEXTURE_ALIASES,
)

# ── System prompt ──

TAGGER_SYSTEM_PROMPT = """You are a sample library curator for an SP-404 sampler used for LIVE PERFORMANCE at block parties, DJ sets, and dance events. You analyze audio features and metadata to generate a human-readable sonic description and quality score.

PRODUCTION PHILOSOPHY: This sampler is built for making people DANCE. The aesthetic is warm, soulful, hype — funk, soul, disco, dancehall, house, electro. Quality means "would this make the crowd move?" not "is this technically interesting." Vintage/lo-fi character is a FEATURE not a flaw.

You will receive:
- Audio features extracted by librosa (spectral centroid, MFCCs, spectral rolloff, chroma, zero-crossing rate, onset strength, RMS envelope, BPM, key)
- Filename and directory path
- File duration in seconds

Respond with ONLY a JSON object. No explanation, no markdown, no preamble. Do not wrap in code fences.

{
  "sonic_description": "<1-2 sentences describing what a producer would hear — timbre, character, mood, usefulness>",
  "quality_score": <1-5 integer>
}

quality_score for SP-404 LIVE DANCE PERFORMANCE:
  - 5: Would make the crowd move. Distinctive groove, warmth, or energy. Build a bank around it.
  - 4: Solid danceable character. Reliable workhorse for a set.
  - 3: Usable but generic — lacks distinctive character.
  - 2: Technical issues, boring, or wrong energy for a party context.
  - 1: Broken, unusable, or irrelevant to live performance.
  - Samples under 0.1s: almost always 1
  - Samples over 120s: almost always 1-2
  - Warm, groovy, funky samples with vintage character → score higher
  - Cold, sterile, or lifeless samples → score lower"""


def _build_prompt(filepath, features):
    """Build the user prompt with audio features for a single file."""
    rel = os.path.relpath(filepath, LIBRARY)
    fname = os.path.basename(filepath)
    dirpath = os.path.dirname(rel)

    lines = ["File: %s" % fname, "Directory: %s" % dirpath]

    field_map = [
        ('duration', 'Duration', '%.2fs'),
        ('bpm', 'BPM', '%.1f'),
        ('key', 'Key', '%s'),
        ('loudness_db', 'Loudness', '%.1f dB'),
        ('spectral_centroid', 'Spectral centroid', '%.0f Hz'),
        ('spectral_rolloff', 'Spectral rolloff', '%.0f Hz'),
        ('zero_crossing_rate', 'Zero-crossing rate', '%.4f'),
        ('onset_strength', 'Onset strength', '%.2f'),
        ('onset_count', 'Onset count', '%d'),
        ('rms_peak', 'RMS peak', '%.4f'),
        ('rms_mean', 'RMS mean', '%.4f'),
        ('attack_position', 'Attack position', '%.2f'),
    ]

    for key, label, fmt in field_map:
        val = features.get(key)
        if val is not None:
            lines.append("%s: %s" % (label, fmt % val))

    if features.get('mfcc'):
        lines.append("MFCCs: %s" % json.dumps(features['mfcc']))
    if features.get('chroma'):
        lines.append("Chroma: %s" % json.dumps(features['chroma']))

    return "\n".join(lines)


_llm_stats = {'calls': 0, 'success': 0, 'timeout': 0, 'http_error': 0,
              'empty': 0, 'parse_fail': 0, 'incomplete': 0,
              'connection_error': 0, 'invalid_json': 0}
_llm_stats_lock = threading.Lock()


def _bump_llm_stat(key, delta=1):
    with _llm_stats_lock:
        _llm_stats[key] = _llm_stats.get(key, 0) + delta


def _llm_stats_snapshot():
    with _llm_stats_lock:
        return dict(_llm_stats)


# Aliases imported from tag_vocab — single source of truth for variant spellings.


def _retag_llm_read_timeout_seconds():
    """HTTP read timeout for Ollama completion (qwen3.5 + librosa contention needs headroom)."""
    if SMART_RETAG_LLM_TIMEOUT is not None:
        return int(SMART_RETAG_LLM_TIMEOUT)
    return max(int(LLM_TIMEOUT), 420)


def _retag_llm_retries():
    """Number of extra attempts after the first (timeouts / 5xx retry)."""
    if SMART_RETAG_LLM_RETRIES is not None:
        return int(SMART_RETAG_LLM_RETRIES)
    return 3


def _skip_llm_for_duration(duration_sec):
    if SMART_RETAG_SKIP_ABOVE_SECONDS is None:
        return False
    if duration_sec is None:
        return False
    return float(duration_sec) >= float(SMART_RETAG_SKIP_ABOVE_SECONDS)


def _call_llm(prompt, model, retries=None):
    """Send prompt to Ollama and parse JSON response. Retries on timeout.

    Thin wrapper around llm_client.call_llm_chat() that injects the smart-retag
    system prompt and uses the long-running read timeout for big libraries.
    """
    if not LLM_ENDPOINT:
        return None

    if retries is None:
        retries = _retag_llm_retries()
    # Use long read timeout for retag (model latency + librosa contention)
    timeout = _retag_llm_read_timeout_seconds()

    messages = [
        {"role": "system", "content": TAGGER_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        return call_llm_chat(
            LLM_ENDPOINT,
            model,
            messages,
            timeout=timeout,
            retries=retries,
            json_mode=True,
            temperature=0.3,
            max_tokens=2048,
            on_stat=_bump_llm_stat,
        )
    except LLMError as exc:
        # All retries exhausted; log and return None to match legacy contract
        print("  LLM %s: %s" % (exc.code, exc.message), file=sys.stderr)
        return None


def _llm_tag_with_repair(full_path, features, verbose=True, repair_attempts=2):
    """Call LLM; if output is too thin for fetch, retry with stricter instructions.

    Returns (validated_tags_dict, ollama_model_used_or_None, skipped_due_to_duration).
    """
    dur = features.get('duration')
    fname = os.path.basename(full_path)
    if _skip_llm_for_duration(dur):
        if verbose:
            print("  SKIP LLM (duration %.1fs >= %ss): %s" % (
                float(dur), SMART_RETAG_SKIP_ABOVE_SECONDS, fname), flush=True)
        return {}, None, True

    model = LLM_MODEL
    prompt = _build_prompt(full_path, features)
    raw = _call_llm(prompt, model=model)
    validated = _validate_llm_tags(raw) if raw else {}
    if _enrichment_usable(validated):
        return validated, model, False
    for _ in range(repair_attempts):
        if verbose:
            print("  LLM repair pass (incomplete JSON / missing dimensions)...", flush=True)
        raw2 = _call_llm(prompt + SMART_RETAG_REPAIR_SUFFIX, model=model)
        validated = _validate_llm_tags(raw2) if raw2 else {}
        if _enrichment_usable(validated):
            return validated, model, False
    return validated, model, False


def _normalize_vocab_token(dim, token):
    t = str(token).strip().lower()
    if not t:
        return None
    if dim == 'genre':
        t = _GENRE_ALIASES.get(t, t)
        if t in VALID_GENRES:
            return t
    elif dim == 'vibe':
        t = _VIBE_ALIASES.get(t, t)
        if t in VALID_VIBES:
            return t
    elif dim == 'texture':
        t = _TEXTURE_ALIASES.get(t, t)
        if t in VALID_TEXTURES:
            return t
    return None


def _validate_llm_tags(llm_tags):
    """Validate and sanitize LLM output against allowed vocabularies."""
    if not isinstance(llm_tags, dict):
        return {}

    result = {}

    tc = str(llm_tags.get('type_code', '')).upper().strip()
    if tc in VALID_TYPE_CODES:
        result['type_code'] = tc

    play = str(llm_tags.get('playability', '')).lower().strip()
    if play in VALID_PLAYABILITIES:
        result['playability'] = play

    energy = str(llm_tags.get('energy', '')).lower().strip()
    if energy in VALID_ENERGIES:
        result['energy'] = energy

    for dim in ('vibe', 'texture', 'genre'):
        raw = llm_tags.get(dim, [])
        if isinstance(raw, str):
            raw = [r.strip().lower() for r in raw.split(',')]
        elif isinstance(raw, list):
            raw = [str(r).strip().lower() for r in raw]
        else:
            raw = []
        seen = []
        for v in raw:
            n = _normalize_vocab_token(dim, v)
            if n and n not in seen:
                seen.append(n)
        if seen:
            result[dim] = seen[:3]

    for field in ('sonic_description', 'instrument_hint'):
        val = llm_tags.get(field)
        if val and isinstance(val, str) and val.lower() != 'null':
            result[field] = val

    qs = llm_tags.get('quality_score')
    if isinstance(qs, int) and 1 <= qs <= 5:
        result['quality_score'] = qs
    elif isinstance(qs, (float, str)):
        try:
            qs = int(float(qs))
            if 1 <= qs <= 5:
                result['quality_score'] = qs
        except (ValueError, TypeError):
            pass

    return result


def _enrichment_usable(llm_tags):
    """True when LLM output has the minimum fields worth storing.

    Post-CLAP migration: only sonic_description + quality_score are required.
    """
    if not llm_tags:
        return False
    sonic = (llm_tags.get('sonic_description') or '').strip()
    if len(sonic) < 8:
        return False
    if 'quality_score' not in llm_tags:
        return False
    return True


SMART_RETAG_REPAIR_SUFFIX = """

CRITICAL — previous reply was incomplete. Reply with ONLY one JSON object (no markdown).
Required keys:
  "sonic_description" (1-2 sentence description of the sound), "quality_score" (integer 1-5).
"""


def _merge_tags(existing_entry, llm_tags, features, rel_path, mark_smart_retag_complete=True):
    """Merge validated LLM tags and features into a tag entry.

    If mark_smart_retag_complete is False, features are stored but we do not claim
    a finished smart_retag (tag_source stays honest; row can be retried).
    """
    entry = dict(existing_entry) if existing_entry else {}
    prev_source = existing_entry.get('tag_source') if existing_entry else None

    # LLM provides only sonic_description and quality_score now.
    # Subjective tags (vibe, texture, genre) are handled by CLAP embeddings.
    for key in ('sonic_description', 'quality_score'):
        if key in llm_tags:
            entry[key] = llm_tags[key]
    # Legacy: still accept type_code/playability from LLM if present (backward compat)
    for key in ('type_code', 'playability', 'instrument_hint'):
        if key in llm_tags:
            entry[key] = llm_tags[key]

    # Audio features
    if features:
        if features.get('bpm'):
            entry['bpm'] = features['bpm']
            entry['bpm_source'] = 'librosa'
        if features.get('key'):
            entry['key'] = features['key']
            entry['key_source'] = 'librosa'
        if features.get('loudness_db') is not None:
            entry['loudness_db'] = features['loudness_db']
        if features.get('duration'):
            entry['duration'] = features['duration']

        # Store feature vectors for similarity search
        stored = {}
        for k in ('spectral_centroid', 'spectral_rolloff', 'zero_crossing_rate',
                   'onset_strength', 'onset_count', 'rms_peak', 'rms_mean',
                   'attack_position', 'mfcc', 'chroma'):
            if features.get(k) is not None:
                stored[k] = features[k]
        if stored:
            entry['features'] = stored

    # Rebuild flat tag set (structural only — subjective handled by CLAP)
    tags = set()
    if entry.get('type_code'):
        tags.add(entry['type_code'])
    if entry.get('source'):
        tags.add(entry['source'])
    if entry.get('energy'):
        tags.add(entry['energy'])
    if entry.get('playability'):
        tags.add(entry['playability'])
    if entry.get('bpm'):
        tags.add("%dbpm" % int(entry['bpm']))
    entry['tags'] = sorted(tags)

    if mark_smart_retag_complete:
        entry['tag_source'] = 'smart_retag_v1'
        entry.pop('smart_retag_pending', None)
        entry['tagged_at'] = datetime.now().isoformat()
    elif prev_source == 'smart_retag_v1':
        # Already fully enriched — don't downgrade on a thin retry
        entry['tag_source'] = 'smart_retag_v1'
    else:
        entry.pop('retag_model', None)
        if prev_source:
            entry['tag_source'] = prev_source
        else:
            entry.pop('tag_source', None)
        entry['smart_retag_pending'] = True
    entry['path'] = rel_path

    return entry


# ── File I/O ──

def _load_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def _save_checkpoint(cp):
    import tempfile
    cp_dir = os.path.dirname(CHECKPOINT_PATH) or "."
    os.makedirs(cp_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=cp_dir)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cp, f, indent=2)
        os.replace(tmp, CHECKPOINT_PATH)
    except BaseException:
        os.unlink(tmp)
        raise


def _persist_tag_row(rel_path, entry):
    """Write one row to tags SQLite so a crash mid-batch does not lose work."""
    if not rel_path or not isinstance(entry, dict):
        return
    try:
        payload = json.loads(json.dumps(entry, default=str))
    except (TypeError, ValueError):
        payload = dict(entry)
    with _persist_lock:
        upsert_tag_entries(TAGS_FILE, {rel_path: payload})


def _save_slim_checkpoint(progress, meta):
    """Progress JSON for UI (no processed_files list — avoids huge rewrites)."""
    _save_checkpoint({
        "started_at": meta.get("started_at", ""),
        "last_updated": datetime.now().isoformat(),
        "total_files": meta.get("total_files", 0),
        "processed": progress.get("processed", 0),
        "tagged": progress.get("tagged", 0),
        "quarantined": progress.get("quarantined", 0),
        "errors": progress.get("errors", 0),
        "incomplete": progress.get("incomplete", 0),
        "batch_size": meta.get("batch_size", BATCH_SIZE),
        "llm_stats": _llm_stats_snapshot(),
        "avg_time_per_file_ms": int(meta.get("avg_ms", 0)),
    })


def _load_tags():
    from jambox_config import load_tag_db
    return load_tag_db(TAGS_FILE)


def _save_tags(db):
    from jambox_config import save_tag_db
    save_tag_db(TAGS_FILE, db)
    # Dual-write to normalized SQLite during transition
    try:
        from db import JamboxDB
        jdb = JamboxDB()
        jdb.import_from_tag_dict(db)
        jdb.close()
    except Exception:
        pass  # non-fatal — JSON is still the primary


def _walk_library(path_filter=None):
    root = path_filter or LIBRARY
    files = []
    for dirpath, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in filenames:
            if f.startswith('.'):
                continue
            if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full, LIBRARY)
                files.append((rel, full))
    return files


def _sort_by_demand(files, tag_db):
    """Sort by type code priority (kicks first, then snares, etc.)."""
    order_map = {tc: i for i, tc in enumerate(TYPE_CODE_ORDER)}
    default = len(TYPE_CODE_ORDER)

    def key(item):
        entry = tag_db.get(item[0], {})
        return order_map.get(entry.get('type_code', ''), default)

    return sorted(files, key=key)


# ── Core batch processing ──

def _entry_needs_smart_retag(entry):
    """False only for rows that already have full LLM enrichment (fetch-ready)."""
    if entry.get('tag_source') != 'smart_retag_v1':
        return True
    if entry.get('smart_retag_pending'):
        return True
    if not (entry.get('sonic_description') or '').strip():
        return True
    if entry.get('quality_score') is None:
        return True
    if not (entry.get('vibe') or entry.get('texture') or entry.get('genre')):
        return True
    return False


def _get_stored_features(tag_db, rel_path):
    """Reconstruct a features dict from stored vectors + entry metadata.

    Returns a features dict suitable for LLM prompt building, or None if
    the entry has no stored feature vectors.
    """
    entry = tag_db.get(rel_path, {})
    stored = entry.get('features')
    if not stored:
        return None
    features = dict(stored)
    for k in ('duration', 'bpm', 'key', 'loudness_db'):
        if entry.get(k) is not None:
            features[k] = entry[k]
    return features


def _process_single_file(rel_path, full_path, tag_db, dry_run, verbose,
                         delete_low_quality):
    """Process one file: extract features (or reuse stored), call LLM, merge.

    Returns a result dict consumed by the batch coordinator.
    Thread-safe: only reads tag_db under lock; writes happen in the caller.
    """
    fname = os.path.basename(rel_path)

    with _tag_db_lock:
        stored_features = _get_stored_features(tag_db, rel_path)
        existing = dict(tag_db.get(rel_path, {}))

    if stored_features and stored_features.get('spectral_centroid') is not None:
        features = stored_features
    else:
        features = extract_features(full_path)

    if not features:
        return {"rel_path": rel_path, "status": "error", "reason": "no_features"}

    if dry_run:
        return {"rel_path": rel_path, "status": "tagged", "features": features,
                "dry_run": True}

    skipped_long = False
    used_model = None
    llm_tags = {}
    usable = False
    if LLM_ENDPOINT:
        llm_tags, used_model, skipped_long = _llm_tag_with_repair(
            full_path, features, verbose=verbose)
        usable = _enrichment_usable(llm_tags)
        if not usable and not skipped_long:
            _bump_llm_stat('incomplete')
    mark_smart = bool(usable) if LLM_ENDPOINT else False
    entry = _merge_tags(existing, llm_tags, features, rel_path,
                        mark_smart_retag_complete=mark_smart)
    entry['retag_model'] = used_model if (usable and LLM_ENDPOINT) else None

    qs = entry.get('quality_score')
    tc = entry.get('type_code', '?')

    result = {
        "rel_path": rel_path,
        "full_path": full_path,
        "entry": entry,
        "usable": usable,
        "skipped_long": skipped_long,
        "llm_tags": llm_tags,
        "mark_smart": mark_smart,
        "qs": qs,
        "tc": tc,
    }

    if usable and qs is not None and qs <= 2:
        result["status"] = "low_quality"
    elif usable:
        result["status"] = "tagged"
    elif skipped_long:
        result["status"] = "skip_long"
    elif LLM_ENDPOINT and not llm_tags:
        result["status"] = "llm_fail"
    elif LLM_ENDPOINT:
        result["status"] = "incomplete"
    else:
        result["status"] = "features_only"

    return result


def retag_batch(files, tag_db, dry_run=False, verbose=True, workers=1,
                delete_low_quality=False, progress=None, checkpoint_meta=None):
    """Process a batch through feature extraction + LLM tagging.

    Returns (tagged, quarantined, errors, incomplete_n, completed_rel_paths).
    completed_rel_paths: rows safe to mark in resume checkpoint (omits LLM-incomplete when endpoint set).

    When ``progress`` / ``checkpoint_meta`` are set, each finished file updates SQLite via
    ``upsert_tag_entries`` and rewrites a slim ``retag_checkpoint.json`` so interrupts do not
    lose expensive feature/LLM work.
    """
    tagged = quarantined = errors = incomplete_n = 0
    llm_failures = 0
    completed_rel_paths = []
    cp_lock = threading.Lock()

    def _apply_progress_delta(
        *, errors_add=0, processed_add=0, tagged_add=0, quarantined_add=0, incomplete_add=0,
    ):
        if dry_run or not progress or not checkpoint_meta:
            return
        with cp_lock:
            if errors_add:
                progress["errors"] = progress.get("errors", 0) + errors_add
            if processed_add:
                progress["processed"] = progress.get("processed", 0) + processed_add
            if tagged_add:
                progress["tagged"] = progress.get("tagged", 0) + tagged_add
            if quarantined_add:
                progress["quarantined"] = progress.get("quarantined", 0) + quarantined_add
            if incomplete_add:
                progress["incomplete"] = progress.get("incomplete", 0) + incomplete_add
            elapsed = time.time() - checkpoint_meta.get("t0", time.time())
            meta = dict(checkpoint_meta)
            meta["avg_ms"] = int(elapsed * 1000 / max(progress.get("processed", 1), 1))
            _save_slim_checkpoint(progress, meta)

    def _handle_result(r):
        nonlocal tagged, quarantined, errors, incomplete_n, llm_failures
        rel_path = r["rel_path"]
        fname = os.path.basename(rel_path)
        status = r["status"]

        if status == "error":
            if verbose:
                print("  SKIP (no features): %s" % fname, flush=True)
            errors += 1
            completed_rel_paths.append(rel_path)
            _apply_progress_delta(errors_add=1, processed_add=1)
            return

        if r.get("dry_run"):
            f = r.get("features", {})
            if verbose:
                print("  DRY-RUN: %s (dur=%.1fs centroid=%.0f onsets=%d)" % (
                    fname, f.get('duration', 0),
                    f.get('spectral_centroid', 0),
                    f.get('onset_count', 0)), flush=True)
            tagged += 1
            completed_rel_paths.append(rel_path)
            return

        entry = r["entry"]
        full_path = r["full_path"]
        qs = r["qs"]
        tc = r["tc"]
        usable = r["usable"]
        skipped_long = r["skipped_long"]
        mark_smart = r["mark_smart"]
        vibe_str = ','.join(entry.get('vibe', [])[:2])
        desc = (entry.get('sonic_description') or '')[:50]

        if status == "low_quality":
            if delete_low_quality:
                try:
                    if os.path.exists(full_path):
                        os.remove(full_path)
                    with _tag_db_lock:
                        tag_db.pop(rel_path, None)
                    if not dry_run:
                        with _persist_lock:
                            delete_tag_paths(TAGS_FILE, [rel_path])
                    quarantined += 1
                    if verbose:
                        print("  DELETE q=%d %s: %s — %s" % (qs, tc, fname, desc), flush=True)
                except OSError:
                    pass
            else:
                os.makedirs(QUARANTINE_DIR, exist_ok=True)
                q_dest = os.path.join(QUARANTINE_DIR, rel_path)
                if not os.path.exists(q_dest):
                    os.makedirs(os.path.dirname(q_dest), exist_ok=True)
                    try:
                        shutil.move(full_path, q_dest)
                        quarantined += 1
                        q_rel = os.path.join("_QUARANTINE", rel_path)
                        entry['path'] = q_rel
                        with _tag_db_lock:
                            tag_db.pop(rel_path, None)
                            tag_db[q_rel] = entry
                        if not dry_run:
                            with _persist_lock:
                                delete_tag_paths(TAGS_FILE, [rel_path])
                            _persist_tag_row(q_rel, entry)
                        if verbose:
                            print("  QUARANTINE q=%d %s: %s — %s" % (qs, tc, fname, desc), flush=True)
                    except OSError:
                        pass
            completed_rel_paths.append(rel_path)
            _apply_progress_delta(quarantined_add=1, tagged_add=1, processed_add=1)
            return

        with _tag_db_lock:
            tag_db[rel_path] = entry
        if not dry_run:
            _persist_tag_row(rel_path, entry)

        if status == "llm_fail":
            llm_failures += 1
        if status == "incomplete":
            incomplete_n += 1
            if r.get("llm_tags") and verbose:
                print("  INCOMPLETE (features saved; will retry LLM on next run): %s" % fname, flush=True)

        tagged += 1
        if usable:
            src = "LLM"
            q_show = qs if qs is not None else "?"
        elif skipped_long:
            src = "SKIP-LONG"
            q_show = "—"
        elif LLM_ENDPOINT:
            src = "features" if not r.get("llm_tags") else "THIN"
            q_show = qs if qs is not None else "?"
        else:
            src = "features"
            q_show = qs if qs is not None else "?"
        if verbose:
            print("  %s | %s q=%s %s [%s]: %s — %s" % (
                rel_path, src, q_show, tc, vibe_str, fname, desc), flush=True)

        if mark_smart or not LLM_ENDPOINT or skipped_long:
            completed_rel_paths.append(rel_path)

        _apply_progress_delta(
            tagged_add=1,
            processed_add=1,
            incomplete_add=1 if status == "incomplete" else 0,
            errors_add=1 if status == "llm_fail" else 0,
        )

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_process_single_file, rel, full, tag_db, dry_run,
                            verbose, delete_low_quality): rel
                for rel, full in files
            }
            for fut in as_completed(futures):
                try:
                    _handle_result(fut.result())
                except Exception as exc:
                    rel = futures[fut]
                    print("  ERROR %s: %s" % (rel, exc), file=sys.stderr)
                    errors += 1
                    completed_rel_paths.append(rel)
                    _apply_progress_delta(errors_add=1, processed_add=1)
    else:
        for rel_path, full_path in files:
            try:
                result = _process_single_file(
                    rel_path, full_path, tag_db, dry_run, verbose,
                    delete_low_quality)
                _handle_result(result)
            except Exception as exc:
                print("  ERROR %s: %s" % (rel_path, exc), file=sys.stderr)
                errors += 1
                completed_rel_paths.append(rel_path)
                _apply_progress_delta(errors_add=1, processed_add=1)

    if llm_failures and verbose:
        print("  [batch LLM empty/fail: %d/%d]" % (llm_failures, len(files)), flush=True)
    if incomplete_n and verbose and LLM_ENDPOINT:
        print("  [batch incomplete (will retry): %d/%d]" % (incomplete_n, len(files)), flush=True)

    return tagged, quarantined, errors, incomplete_n, completed_rel_paths


def retag_single(rel_path, full_path, existing_entry=None):
    """Smart-retag a single file inline. Returns enriched tag entry or None.

    Designed for ingest pipeline use — extracts features, calls LLM, merges
    tags, returns the enriched entry without saving to disk (caller saves).
    Does NOT quarantine (caller decides).

    When LLM is unavailable, still returns features-only entry (BPM, key,
    loudness, feature vectors) so new files get librosa metadata stored for
    later LLM enrichment.
    """
    if not librosa_available():
        return None

    features = extract_features(full_path)
    if not features:
        return None

    if not LLM_ENDPOINT:
        existing = existing_entry or {}
        entry = _merge_tags(
            existing, {}, features, rel_path,
            mark_smart_retag_complete=False,
        )
        return entry

    llm_tags, used_model, _skipped = _llm_tag_with_repair(
        full_path, features, verbose=False, repair_attempts=2)
    usable = _enrichment_usable(llm_tags)
    existing = existing_entry or {}
    entry = _merge_tags(
        existing, llm_tags, features, rel_path,
        mark_smart_retag_complete=usable,
    )
    entry['retag_model'] = used_model if usable else None
    return entry


# ── Main runner ──

def run(args):
    if not librosa_available():
        print("ERROR: librosa not installed. Run: pip3 install librosa scipy")
        sys.exit(1)

    if not LLM_ENDPOINT and not args.dry_run:
        print("WARNING: SP404_LLM_ENDPOINT not set. Will extract features only.")

    tag_db = _load_tags()
    print("Tag DB: %d entries" % len(tag_db))

    # Determine files to process (on-disk tag rows are authoritative — no processed_files list).
    if args.resume:
        cp = _load_checkpoint()
        if cp:
            print(
                "Resume: last checkpoint %s — queue is rebuilt from tag DB (files still needing retag)."
                % (cp.get("last_updated") or "unknown",)
            )
        else:
            print("Resume: no checkpoint file yet — queue from tag DB only.")
    processed_files = []
    if args.path:
        path = os.path.expanduser(args.path)
        if not os.path.isabs(path):
            path = os.path.join(LIBRARY, path)
        files = _walk_library(path_filter=path)
        print("Path: %d files in %s" % (len(files), path))
    else:
        files = _walk_library()
        print("Library: %d files" % len(files))

    # Skip rows that already have full enrichment unless --force
    if not args.force:
        before = len(files)
        files = [(r, f) for r, f in files if _entry_needs_smart_retag(tag_db.get(r, {}))]
        skipped = before - len(files)
        if skipped:
            print("Skipping %d fetch-ready smart_retag rows (--force to redo)" % skipped)

    # Sort by preset demand
    files = _sort_by_demand(files, tag_db)

    if args.limit:
        files = files[:args.limit]
        print("Limited to %d" % len(files))

    if not files:
        print("Nothing to process.")
        return

    print("Processing %d files...\n" % len(files))
    workers = args.workers
    delete_low_quality = getattr(args, 'delete_low_quality', False)

    if LLM_ENDPOINT:
        skip_note = (
            " | skip LLM if duration >= %ss" % SMART_RETAG_SKIP_ABOVE_SECONDS
            if SMART_RETAG_SKIP_ABOVE_SECONDS is not None
            else ""
        )
        workers_note = " | workers=%d" % workers if workers > 1 else ""
        print(
            "LLM: %s%s | read timeout %ds | up to %d attempts/file%s"
            % (
                LLM_MODEL,
                skip_note,
                _retag_llm_read_timeout_seconds(),
                _retag_llm_retries() + 1,
                workers_note,
            ),
            flush=True,
        )

    if delete_low_quality:
        print("  DELETE mode: quality_score <= 2 files will be permanently deleted")

    total_tagged = total_quarantined = total_errors = total_incomplete = 0
    t0 = time.time()
    run_started_at = datetime.now().isoformat()
    progress = None
    checkpoint_meta = None
    if not args.dry_run:
        progress = {"processed": 0, "tagged": 0, "quarantined": 0, "errors": 0, "incomplete": 0}
        checkpoint_meta = {
            "started_at": run_started_at,
            "total_files": len(files),
            "batch_size": BATCH_SIZE,
            "t0": t0,
        }

    for i in range(0, len(files), BATCH_SIZE):
        batch = files[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(files) + BATCH_SIZE - 1) // BATCH_SIZE

        elapsed = time.time() - t0
        rate = (i / elapsed) if elapsed > 0 and i > 0 else 0
        eta = ((len(files) - i) / rate / 60) if rate > 0 else 0

        print("=== Batch %d/%d  |  %.0f/min  |  ETA %.0fm ===" % (
            batch_num, total_batches, rate * 60, eta), flush=True)

        t, q, e, inc, batch_done = retag_batch(
            batch, tag_db, dry_run=args.dry_run, verbose=not args.quiet,
            workers=workers, delete_low_quality=delete_low_quality,
            progress=progress, checkpoint_meta=checkpoint_meta,
        )

        total_tagged += t
        total_quarantined += q
        total_errors += e
        total_incomplete += inc
        processed_files.extend(batch_done)

        # Full JSON + JamboxDB sync each batch (SQLite already updated per file).
        if not args.dry_run:
            _save_tags(tag_db)

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("Smart Retag Complete")
    done_count = progress["processed"] if progress else len(processed_files)
    print("  Processed: %d  Tagged: %d  Quarantined: %d  Errors: %d  LLM-incomplete: %d" % (
        done_count, total_tagged, total_quarantined, total_errors, total_incomplete))
    print("  Time: %.1f min  Rate: %.0f files/min" % (
        elapsed / 60, done_count / max(elapsed / 60, 0.01)))
    print("  Tag DB: %d entries" % len(tag_db))
    s = _llm_stats_snapshot()
    if s.get('calls'):
        print("  LLM: %d calls, %d ok (%.0f%%), %d incomplete rows, %d timeout, %d parse fail, %d empty, %d http err" % (
            s['calls'], s['success'],
            s['success'] / max(s['calls'], 1) * 100,
            s['incomplete'], s['timeout'], s['parse_fail'], s['empty'], s['http_error']))


def run_revibe(args):
    """Re-vibe pass: re-interpret stored features with the current system prompt.

    Skips librosa extraction entirely — reads feature vectors already stored in
    _tags.json and re-sends them to the LLM with the (updated) production-aware
    prompt. Only overwrites subjective fields: vibe, texture, energy,
    quality_score, sonic_description, instrument_hint. Preserves type_code,
    playability, BPM, key, features, and all other objective data.

    This is the second pass after a full smart_retag run — same features,
    new interpretation. ~3-6x faster than a full re-run.
    """
    if not LLM_ENDPOINT:
        print("ERROR: SP404_LLM_ENDPOINT not set.")
        sys.exit(1)

    tag_db = _load_tags()
    print("Tag DB: %d entries" % len(tag_db))

    # Find entries that have stored features (from a prior smart_retag run)
    candidates = []
    for rel_path, entry in tag_db.items():
        if is_excluded_rel_path(rel_path):
            continue
        if entry.get('tag_source') != 'smart_retag_v1':
            continue
        stored_features = entry.get('features')
        if not stored_features:
            continue
        full_path = os.path.join(LIBRARY, rel_path)
        if os.path.exists(full_path):
            candidates.append((rel_path, full_path, entry))

    print("Files with stored features: %d" % len(candidates))

    if args.limit:
        candidates = candidates[:args.limit]
        print("Limited to %d" % args.limit)

    if not candidates:
        print("Nothing to re-vibe. Run --all first to extract features.")
        return

    print("Re-vibing %d files with updated production prompt...\n" % len(candidates))
    print(
        "LLM: %s | read timeout %ds | up to %d attempts/file"
        % (
            LLM_MODEL,
            _retag_llm_read_timeout_seconds(),
            _retag_llm_retries() + 1,
        ),
        flush=True,
    )

    # Subjective fields to overwrite
    REVIBE_FIELDS = ('vibe', 'texture', 'genre', 'energy', 'quality_score',
                     'sonic_description', 'instrument_hint')

    updated = errors = 0
    t0 = time.time()

    for i, (rel_path, full_path, entry) in enumerate(candidates):
        if i > 0 and i % BATCH_SIZE == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(candidates) - i) / rate / 60 if rate > 0 else 0
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(candidates) + BATCH_SIZE - 1) // BATCH_SIZE
            print("=== Re-vibe %d/%d  |  %.0f/min  |  ETA %.0fm ===" % (
                batch_num, total_batches, rate * 60, eta))

            # Save progress
            if not args.dry_run:
                _save_tags(tag_db)

        # Reconstruct features dict from stored vectors + entry metadata
        features = dict(entry.get('features', {}))
        for k in ('duration', 'bpm', 'key', 'loudness_db'):
            if entry.get(k) is not None:
                features[k] = entry[k]

        if args.dry_run:
            if not args.quiet:
                fname = os.path.basename(rel_path)
                old_vibe = ','.join(entry.get('vibe', [])[:2])
                print("  DRY-RUN: %s [%s]" % (fname, old_vibe))
            updated += 1
            continue

        llm_tags, used_model, _sk = _llm_tag_with_repair(
            full_path, features, verbose=not args.quiet)
        if not _enrichment_usable(llm_tags):
            errors += 1
            continue

        # Only overwrite subjective fields — preserve type_code, playability, etc.
        old_vibe = entry.get('vibe', [])
        for field in REVIBE_FIELDS:
            if field in llm_tags:
                entry[field] = llm_tags[field]

        # Rebuild flat tags
        tags = set()
        if entry.get('type_code'):
            tags.add(entry['type_code'])
        for v in entry.get('vibe', []):
            tags.add(v)
        for t in entry.get('texture', []):
            tags.add(t)
        for g in entry.get('genre', []):
            tags.add(g)
        if entry.get('source'):
            tags.add(entry['source'])
        if entry.get('energy'):
            tags.add(entry['energy'])
        if entry.get('playability'):
            tags.add(entry['playability'])
        if entry.get('bpm'):
            tags.add("%dbpm" % int(entry['bpm']))
        entry['tags'] = sorted(tags)

        entry['retag_model'] = used_model
        entry['tag_source'] = 'smart_retag_v2_revibe'
        entry['tagged_at'] = datetime.now().isoformat()
        tag_db[rel_path] = entry
        updated += 1

        if not args.quiet:
            new_vibe = ','.join(entry.get('vibe', [])[:2])
            q = entry.get('quality_score', '?')
            tc = entry.get('type_code', '?')
            fname = os.path.basename(rel_path)
            changed = '*' if old_vibe != entry.get('vibe', []) else ' '
            print(" %s q=%s %s [%s→%s]: %s" % (
                changed, q, tc, ','.join(old_vibe[:2]), new_vibe, fname))

    if not args.dry_run:
        _save_tags(tag_db)

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("Re-Vibe Pass Complete")
    print("  Updated: %d  Errors: %d" % (updated, errors))
    print("  Time: %.1f min  Rate: %.0f files/min" % (
        elapsed / 60, updated / max(elapsed / 60, 0.01)))


def run_retry_llm_failures(args):
    """Re-run LLM tagging on files that have features but no LLM enrichment.

    These are files where feature extraction succeeded but _call_llm returned
    None (timeout, parse failure, etc.). Uses stored features — no librosa call.
    """
    if not LLM_ENDPOINT:
        print("ERROR: SP404_LLM_ENDPOINT not set.")
        sys.exit(1)

    tag_db = _load_tags()
    print("Tag DB: %d entries" % len(tag_db))

    # Entries with extracted features that still need full LLM enrichment
    candidates = []
    for rel_path, entry in tag_db.items():
        if is_excluded_rel_path(rel_path):
            continue
        if not entry.get('features'):
            continue
        if not _entry_needs_smart_retag(entry):
            continue
        full_path = os.path.join(LIBRARY, rel_path)
        if os.path.exists(full_path):
            candidates.append((rel_path, full_path, entry))

    print("Files needing LLM retry: %d" % len(candidates))

    if args.limit:
        candidates = candidates[:args.limit]
        print("Limited to %d" % args.limit)

    if not candidates:
        print("No rows need full enrichment (or no on-disk files match).")
        return

    print("LLM: %s" % LLM_MODEL)
    print("Retrying LLM on %d files...\n" % len(candidates))

    success = errors = 0
    t0 = time.time()

    for i, (rel_path, full_path, entry) in enumerate(candidates):
        if i > 0 and i % BATCH_SIZE == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(candidates) - i) / rate / 60 if rate > 0 else 0
            print("=== Retry %d/%d  |  %.0f/min  |  ETA %.0fm ===" % (
                i, len(candidates), rate * 60, eta))
            if not args.dry_run:
                _save_tags(tag_db)

        # Reconstruct features from stored data
        features = dict(entry.get('features', {}))
        for k in ('duration', 'bpm', 'key', 'loudness_db'):
            if entry.get(k) is not None:
                features[k] = entry[k]

        if args.dry_run:
            fname = os.path.basename(rel_path)
            if not args.quiet:
                print("  DRY-RUN: %s" % fname)
            success += 1
            continue

        llm_tags, used_model, _sk = _llm_tag_with_repair(
            full_path, features, verbose=not args.quiet)
        usable = _enrichment_usable(llm_tags)
        existing = dict(entry)
        new_entry = _merge_tags(
            existing, llm_tags, features, rel_path,
            mark_smart_retag_complete=usable,
        )
        if usable:
            new_entry['retag_model'] = used_model
        tag_db[rel_path] = new_entry
        entry = new_entry

        if usable:
            success += 1
        else:
            errors += 1

        if not args.quiet:
            fname = os.path.basename(rel_path)
            tc = entry.get('type_code', '?')
            vibe_str = ','.join(entry.get('vibe', [])[:2])
            desc = (entry.get('sonic_description') or '')[:50]
            tag = "LLM" if usable else "INCOMPLETE"
            print("  %s q=%s %s [%s]: %s — %s" % (
                tag, entry.get('quality_score', '?'), tc, vibe_str, fname, desc))

    if not args.dry_run:
        _save_tags(tag_db)

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("LLM Retry Complete")
    print("  Success: %d  Errors: %d" % (success, errors))
    s = _llm_stats_snapshot()
    if s.get('calls'):
        print("  LLM: %d calls, %d ok (%.0f%%), %d timeout, %d parse fail" % (
            s['calls'], s['success'],
            s['success'] / max(s['calls'], 1) * 100,
            s['timeout'], s['parse_fail']))
    print("  Time: %.1f min" % (elapsed / 60))


def run_validate(args):
    """Stratified validation: process up to N files per type code, report quality."""
    per_type = args.limit or 5
    tag_db = _load_tags()
    all_files = _walk_library()

    by_type = {}
    for rel, full in all_files:
        tc = tag_db.get(rel, {}).get('type_code', 'UNKNOWN')
        by_type.setdefault(tc, []).append((rel, full))

    selected = []
    for tc in sorted(by_type):
        pool = by_type[tc]
        if not args.force:
            pool = [(r, f) for r, f in pool if _entry_needs_smart_retag(tag_db.get(r, {}))]
        selected.extend(pool[:per_type])

    if not selected:
        print("Nothing to validate — all files already enriched. Use --force to redo.")
        return

    print("Validation: %d files (%d per type code across %d types)" %
          (len(selected), per_type, len(by_type)))

    workers = getattr(args, 'workers', SMART_RETAG_WORKERS_DEFAULT) or SMART_RETAG_WORKERS_DEFAULT
    t, q, e, inc, _ = retag_batch(
        selected, tag_db, dry_run=args.dry_run, verbose=True, workers=workers)
    if not args.dry_run:
        _save_tags(tag_db)

    quality_scores = []
    for rel, _ in selected:
        qs = tag_db.get(rel, {}).get('quality_score')
        if isinstance(qs, (int, float)):
            quality_scores.append(qs)

    print("\n" + "=" * 60)
    print("Validation Summary")
    print("  Processed: %d  Tagged: %d  Quarantined: %d  Errors: %d  Incomplete: %d" %
          (len(selected), t, q, e, inc))
    if quality_scores:
        avg_q = sum(quality_scores) / len(quality_scores)
        print("  Quality scores: min=%.0f avg=%.1f max=%.0f (n=%d)" %
              (min(quality_scores), avg_q, max(quality_scores), len(quality_scores)))
    s = _llm_stats_snapshot()
    if s.get('calls'):
        print("  LLM: %d calls, %d ok (%.0f%%), %d timeout, %d parse fail" % (
            s['calls'], s['success'],
            s['success'] / max(s['calls'], 1) * 100,
            s['timeout'], s['parse_fail']))


def main():
    parser = argparse.ArgumentParser(description='Smart retag: LLM-powered sample tagger')
    parser.add_argument('--all', action='store_true', help='Process entire library')
    parser.add_argument('--resume', action='store_true', help='Resume from checkpoint')
    parser.add_argument('--validate', action='store_true',
                        help='Stratified validation: process N files per type code, print quality summary')
    parser.add_argument('--path', type=str, help='Process specific directory')
    parser.add_argument('--limit', type=int, help='Max files to process')
    parser.add_argument('--dry-run', action='store_true', help='Feature extraction only')
    parser.add_argument('--force', action='store_true', help='Retag already tagged files')
    parser.add_argument('--quiet', '-q', action='store_true', help='Less output')
    parser.add_argument('--workers', type=int, default=None,
                        help='Concurrent file workers (default from RAM or SP404_SMART_RETAG_WORKERS; cap %d)' % SMART_RETAG_WORKERS_CAP)
    parser.add_argument('--delete-low-quality', action='store_true',
                        help='Permanently delete quality_score <= 2 files instead of quarantining')
    parser.add_argument('--revibe', action='store_true',
                        help='Re-vibe pass: re-interpret stored features with updated prompt')
    parser.add_argument('--retry-llm-failures', action='store_true',
                        help='Re-run LLM on files that have features but no LLM enrichment')
    args = parser.parse_args()
    args.workers = (
        SMART_RETAG_WORKERS_DEFAULT
        if args.workers is None
        else max(1, min(int(args.workers), SMART_RETAG_WORKERS_CAP))
    )

    if args.revibe:
        run_revibe(args)
        return

    if args.retry_llm_failures:
        run_retry_llm_failures(args)
        return

    if args.validate:
        run_validate(args)
        return

    if not any([args.all, args.resume, args.path, args.limit]):
        parser.print_help()
        sys.exit(0)

    run(args)


if __name__ == '__main__':
    main()
