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
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import (
    DROP_FIELD,
    LIBRARY_SKIP_DIRS,
    LONG_HOLD_DIRNAME,
    delete_tag_paths,
    export_tags_json,
    is_excluded_rel_path,
    library_rel_path,
    load_settings_for_script,
    merge_tag_fields,
    tag_rows,
    upsert_tag_entries,
    write_tag_changes,
)
from audio_analysis import (
    chroma_and_key, extract_features, is_available as librosa_available, numpy_elision_safe,
)
from library_walker import AUDIO_EXTENSIONS, is_appledouble
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
AUDIO_EXTS = AUDIO_EXTENSIONS  # same set ingest accepts, so no ingested file goes untagged
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

TAGGER_SYSTEM_PROMPT = """You are a sample library curator for an SP-404 sampler used for LIVE PERFORMANCE at block parties, DJ sets, and dance events. You analyze audio features and metadata to generate structured tags and a quality score.

PRODUCTION PHILOSOPHY: This sampler is built for making people DANCE. The aesthetic is warm, soulful, hype — funk, soul, disco, dancehall, house, electro. Quality means "would this make the crowd move?" not "is this technically interesting." Vintage/lo-fi character is a FEATURE not a flaw.

You will receive:
- Audio features extracted by librosa (spectral centroid, MFCCs, spectral rolloff, chroma, zero-crossing rate, onset strength, RMS envelope, BPM, key)
- Filename and directory path
- File duration in seconds

Respond with ONLY a JSON object. No explanation, no markdown, no preamble. Do not wrap in code fences.

{
  "sonic_description": "<1-2 sentences describing what a producer would hear — timbre, character, mood, usefulness>",
  "quality_score": <1-5 integer>,
  "type_code": "<3-letter code from TYPE_CODES, or null if unclear>",
  "vibe": ["<0-3 terms from VIBES>"],
  "texture": ["<0-3 terms from TEXTURES>"],
  "genre": ["<0-3 terms from GENRES>"],
  "energy": "<low | mid | high>",
  "instrument_hint": "<specific instrument like rhodes, 808, clavinet, melodica — or null>"
}

TYPE_CODES (pick ONE that best describes the sample's role):
KIK (kick drum), SNR (snare), HAT (hi-hat), CLP (clap), CYM (cymbal), RIM (rimshot),
PRC (percussion), BRK (drum break or full drum loop), BAS (bass), GTR (guitar),
KEY (keys/piano/rhodes/organ), SYN (synth lead/stab), PAD (atmospheric pad),
STR (strings), HRN (horns/brass), VOX (vocal), FX (effect), SFX (sound effect),
AMB (ambient/field recording), RSR (riser/build/transition), DRM (unclassified drum hit)

VIBES (emotional mood — pick 0-3 most fitting):
dark, hype, dreamy, nostalgic, aggressive, mellow, soulful, eerie, playful, gritty,
ethereal, triumphant, melancholic, tense, chill, uplifting, unfiltered, comforting

TEXTURES (sonic character — pick 0-3):
dusty, lo-fi, raw, clean, warm, saturated, bitcrushed, airy, crispy, glassy, muddy,
vinyl, tape, digital, organic, crunchy, warbly, bright, thick, thin, filtered

GENRES (style lineage — pick 0-3):
afrobeat, ambient, baile-funk, boom-bap, breakbeat, breakcore, city-pop, classical,
dancehall, disco, drill, drum-and-bass, dub, dubstep, electronic, experimental,
footwork, funk, gqom, gospel, hiphop, house, industrial, industrial-techno, jazz,
jungle, latin, lo-fi, lo-fi-hiphop, pop, psychedelic, punk, reggae, rnb, rock,
shoegaze, soul, techno, trap, trance, tropical, uk-garage, world

If you are uncertain about a dimension, return an empty array [] or null — do NOT
invent tags outside the approved vocabulary. Unknown terms will be discarded.

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
    rel = library_rel_path(filepath, LIBRARY) or os.path.basename(filepath)
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
              'connection_error': 0, 'invalid_json': 0, 'fallback': 0}
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


# Ingest retags one file at a time inline, so a stalled or stopped Ollama
# must cost seconds, not minutes, per file.
INGEST_LLM_TIMEOUT = max(int(LLM_TIMEOUT), 120)
INGEST_LLM_BACKOFF_SECONDS = 300
_llm_unavailable_until = 0.0


# Tagging is greedy (temperature 0): the same file gets the same tags on every
# run. At 0.3, a 200-file re-run on identical inputs changed about a quarter of
# quality scores and one in seven type codes (iMac, 2026-11-01). Quarantine
# votes stay sampled; at 0 a second opinion would only repeat the first.
TAG_TEMPERATURE = 0.0
VOTE_TEMPERATURE = 0.3


def _call_llm(prompt, model, retries=None, timeout=None, raise_errors=False, temperature=TAG_TEMPERATURE):
    """Send prompt to the LLM and parse JSON response. Retries on timeout / 5xx.

    Thin wrapper around llm_client.call_llm_chat() that injects the smart-retag
    system prompt and uses the long-running read timeout for big libraries.
    With raise_errors, transport failures raise LLMError instead of returning
    None, so callers can tell "server down" from "unparseable reply".
    """
    if not LLM_ENDPOINT:
        return None

    if retries is None:
        retries = _retag_llm_retries()
    if timeout is None:
        # Long read timeout for batch retag (model latency + librosa contention)
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
            fallback_endpoint=SETTINGS.get("LLM_FALLBACK_ENDPOINT"),
            timeout=timeout,
            retries=retries,
            json_mode=True,
            temperature=temperature,
            max_tokens=SETTINGS.get("SMART_RETAG_MAX_TOKENS", 400),
            on_stat=_bump_llm_stat,
            backend=SETTINGS.get("LLM_BACKEND", "auto"),
            num_ctx=SETTINGS.get("LLM_NUM_CTX"),
        )
    except LLMError as exc:
        # All retries exhausted; log and return None to match legacy contract
        print("  LLM %s: %s" % (exc.code, exc.message), file=sys.stderr)
        if raise_errors:
            raise
        return None


def _llm_tag_with_repair(full_path, features, verbose=True, repair_attempts=2,
                         retries=None, timeout=None, temperature=TAG_TEMPERATURE):
    """Call LLM; if output is too thin for fetch, retry with stricter instructions.

    The repair pass only follows a reply that came back incomplete: when the
    server can't be reached or times out, asking again with a stricter prompt
    can't help, so it gives up at once.

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
    try:
        raw = _call_llm(prompt, model=model, retries=retries, timeout=timeout, raise_errors=True,
                        temperature=temperature)
    except LLMError:
        return {}, model, False
    validated = _validate_llm_tags(raw) if raw else {}
    if _enrichment_usable(validated):
        return validated, model, False
    for _ in range(repair_attempts):
        if verbose:
            print("  LLM repair pass (incomplete JSON / missing dimensions)...", flush=True)
        try:
            raw2 = _call_llm(prompt + SMART_RETAG_REPAIR_SUFFIX, model=model,
                             retries=retries, timeout=timeout, raise_errors=True,
                             temperature=temperature)
        except LLMError:
            break
        validated = _validate_llm_tags(raw2) if raw2 else {}
        if _enrichment_usable(validated):
            return validated, model, False
    return validated, model, False


def _second_quality_opinion(full_path, features, verbose=False):
    """Score a file again: (quality_score, validated tags), or (None, {}) without a usable reply."""
    tags, _model, _skipped = _llm_tag_with_repair(full_path, features, verbose=verbose,
                                                  temperature=VOTE_TEMPERATURE)
    if not _enrichment_usable(tags):
        return None, {}
    return tags['quality_score'], tags


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

    sonic_description + quality_score are required.
    vibe / texture / genre / energy / type_code / instrument_hint are best-effort —
    stored when present and in-vocab, skipped when absent. A thin reply that has
    description+quality but no dims is still useful (better than a retry loop).
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
  "sonic_description" (1-2 sentence description), "quality_score" (integer 1-5).
Recommended keys (include when confident, omit otherwise — do not invent):
  "type_code" (3-letter role), "vibe" (array), "texture" (array), "genre" (array),
  "energy" (low|mid|high), "instrument_hint" (specific instrument or null).
"""


def _user_set_quality(entry):
    """A quality score a person set (quality_source "user") outranks the model's."""
    return (entry or {}).get('quality_source') == 'user' and (entry or {}).get('quality_score') is not None


def _keep_user_quality(entry, existing_entry, llm_tags):
    """Put the person's score back; the model's goes next to it, as model_quality_score."""
    if 'quality_score' in llm_tags:
        entry['model_quality_score'] = llm_tags['quality_score']
    entry['quality_score'] = existing_entry['quality_score']


def _merge_tags(existing_entry, llm_tags, features, rel_path, mark_smart_retag_complete=True):
    """Merge validated LLM tags and features into a tag entry.

    If mark_smart_retag_complete is False, features are stored but we do not claim
    a finished smart_retag (tag_source stays honest; row can be retried).
    """
    entry = dict(existing_entry) if existing_entry else {}
    prev_source = existing_entry.get('tag_source') if existing_entry else None

    # LLM provides description + quality + subjective dims (vibe/texture/genre/energy).
    # CLAP embeddings (populated separately) are the Tier-3 refinement layer, not the
    # primary source.
    for key in ('sonic_description', 'quality_score',
                'vibe', 'texture', 'genre', 'energy',
                'type_code', 'playability', 'instrument_hint'):
        if key in llm_tags:
            entry[key] = llm_tags[key]
    if _user_set_quality(existing_entry):
        _keep_user_quality(entry, existing_entry, llm_tags)

    # Audio features. A BPM or key read from the filename ("140BPM C Maj") is the
    # pack's own label and beats librosa's estimate, which is often half/double time.
    if features:
        if features.get('bpm') and entry.get('bpm_source') != 'filename':
            entry['bpm'] = features['bpm']
            entry['bpm_source'] = 'librosa'
        if features.get('key') and entry.get('key_source') != 'filename':
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

    # Rebuild flat tag set (structural + subjective, matches legacy tag_library layout)
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
    for dim in ('vibe', 'texture', 'genre'):
        vals = entry.get(dim)
        if isinstance(vals, list):
            tags.update(v for v in vals if isinstance(v, str) and v)
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
            with open(CHECKPOINT_PATH, encoding="utf-8") as f:
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
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cp, f, indent=2)
        os.replace(tmp, CHECKPOINT_PATH)
    except BaseException:
        os.unlink(tmp)
        raise


def _json_safe(entry):
    try:
        return json.loads(json.dumps(entry, default=str))
    except (TypeError, ValueError):
        return dict(entry)


def _changed_fields(before, after):
    """Fields of *after* that differ from *before* (one row), plus DROP_FIELD for
    keys *after* removed: a merge only sets keys, so a cleared flag such as
    smart_retag_pending would otherwise stay in the DB and re-queue the row forever."""
    changed = {k: v for k, v in after.items() if before.get(k, _MISSING) != v}
    changed.update({k: DROP_FIELD for k in before if k not in after})
    return changed


_MISSING = object()


def _move_file_and_row(src_rel, dest_rel, entry):
    """Move a library file and re-key its tag row so the two never end up apart.

    The row moves in one transaction once the file has moved. If that write
    fails or is interrupted (Ctrl-C while SQLite waits on a busy DB), the file
    goes back to wherever the DB still points. Refuses to overwrite a file or
    row already at *dest_rel*.
    """
    src, dest = os.path.join(LIBRARY, src_rel), os.path.join(LIBRARY, dest_rel)
    if os.path.exists(dest) or tag_rows(TAGS_FILE, [dest_rel]):
        raise FileExistsError("%s is already taken" % dest_rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(src, dest)
    try:
        with _persist_lock:
            write_tag_changes(TAGS_FILE, deletes=[src_rel], upserts={dest_rel: _json_safe(entry)})
    except BaseException:
        try:
            landed = bool(tag_rows(TAGS_FILE, [dest_rel]))
        except Exception:
            landed = False
        if not landed:
            shutil.move(dest, src)
        raise


def _persist_tag_row(rel_path, entry, before=None):
    """Write one row to the tag DB so a crash mid-batch does not lose work.

    With *before* (the row as it was when this run read it), only the fields
    this run changed are merged, so a long run never reverts what ingest,
    Discogs or the UI wrote to the same row in the meantime. Rows with no
    prior state are inserted whole.
    """
    if not rel_path or not isinstance(entry, dict):
        return
    payload = _json_safe(entry)
    with _persist_lock:
        if before:
            fields = _changed_fields(before, payload)
            if fields:
                merge_tag_fields(TAGS_FILE, {rel_path: fields})
        else:
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


def _save_changes(pending):
    """Merge {rel_path: changed_fields} into the tag DB and clear *pending*."""
    if pending:
        merge_tag_fields(TAGS_FILE, pending)
        pending.clear()


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
                if is_appledouble(full):
                    continue
                rel = library_rel_path(full, LIBRARY)
                if rel:
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

def _completed(futures, poll=1.0):
    """as_completed() that wakes every *poll* seconds so Ctrl-C reaches the main
    thread; a bare wait can't be interrupted on Windows."""
    pending = set(futures)
    while pending:
        done, pending = wait(pending, timeout=poll, return_when=FIRST_COMPLETED)
        yield from done


def _cancel_queued(pool):
    """On Ctrl-C, drop files not started yet, so leaving the pool waits only for in-flight ones."""
    pool.shutdown(wait=False, cancel_futures=True)
    print("\nInterrupted: finishing in-flight files, dropping the rest of the queue.",
          file=sys.stderr, flush=True)


def _entry_needs_smart_retag(entry):
    """False only for rows that already have full LLM enrichment (fetch-ready).

    Enrichment means sonic_description + quality_score: the post-CLAP prompt
    returns only those, so requiring vibe/texture/genre too re-queued rows
    (DRM/HRN/UNK, revibed rows) on every --all run forever.
    """
    if not str(entry.get('tag_source') or '').startswith('smart_retag'):
        return True
    if entry.get('smart_retag_pending'):
        return True
    if not (entry.get('sonic_description') or '').strip():
        return True
    if entry.get('quality_score') is None:
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
    before = _json_safe(existing)

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
    confirmed_low = unconfirmed_low = False
    # A user-set score is never voted on: the retag doesn't quarantine it either way.
    if usable and qs is not None and qs <= 2 and not _user_set_quality(existing):
        # A single score is close to a coin flip at the 2/3 line, so a file
        # is quarantined only on two low votes (the second one sampled). A passing
        # second reply replaces the first; an unanswered one moves nothing
        # and leaves the row queued, so the next run votes again.
        votes = [qs]
        second, second_tags = _second_quality_opinion(full_path, features, verbose)
        if second is not None:
            votes.append(second)
        if second is not None and second > 2:
            llm_tags = second_tags
            entry = _merge_tags(existing, llm_tags, features, rel_path)
            entry['retag_model'] = used_model
            qs = second
        confirmed_low = second is not None and second <= 2
        unconfirmed_low = second is None
        if unconfirmed_low:
            entry['smart_retag_pending'] = True
        entry['quality_votes'] = votes
    tc = entry.get('type_code', '?')

    result = {
        "rel_path": rel_path,
        "full_path": full_path,
        "entry": entry,
        "before": before,
        "usable": usable,
        "skipped_long": skipped_long,
        "llm_tags": llm_tags,
        "mark_smart": mark_smart,
        "qs": qs,
        "tc": tc,
    }

    if confirmed_low:
        result["status"] = "low_quality"
    elif unconfirmed_low:
        result["status"] = "incomplete"
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
                q_rel = QUARANTINE_PREFIX + rel_path
                q_entry = {**entry, 'path': q_rel}
                try:
                    _move_file_and_row(rel_path, q_rel, q_entry)
                except FileExistsError:
                    # That quarantine slot is taken: keep the file here, with its votes.
                    _persist_tag_row(rel_path, entry, before=r.get("before"))
                except Exception as exc:
                    print("  QUARANTINE FAILED (file and row left as they were) %s: %s" % (
                        rel_path, exc), file=sys.stderr)
                else:
                    quarantined += 1
                    with _tag_db_lock:
                        tag_db.pop(rel_path, None)
                        tag_db[q_rel] = q_entry
                    if verbose:
                        print("  QUARANTINE q=%d %s: %s — %s" % (qs, tc, fname, desc), flush=True)
            completed_rel_paths.append(rel_path)
            _apply_progress_delta(quarantined_add=1, tagged_add=1, processed_add=1)
            return

        with _tag_db_lock:
            tag_db[rel_path] = entry
        if not dry_run:
            _persist_tag_row(rel_path, entry, before=r.get("before"))

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
            handled = set()

            def _handle_future(fut):
                nonlocal errors
                handled.add(fut)
                try:
                    _handle_result(fut.result())
                except Exception as exc:
                    rel = futures[fut]
                    print("  ERROR %s: %s" % (rel, exc), file=sys.stderr)
                    errors += 1
                    completed_rel_paths.append(rel)
                    _apply_progress_delta(errors_add=1, processed_add=1)

            try:
                for fut in _completed(futures):
                    _handle_future(fut)
            except KeyboardInterrupt:
                _cancel_queued(pool)
                pool.shutdown(wait=True)     # in-flight files finish; save them too
                for fut in futures:
                    if fut not in handled and not fut.cancelled():
                        _handle_future(fut)
                raise
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

    global _llm_unavailable_until
    if not LLM_ENDPOINT or time.time() < _llm_unavailable_until:
        # No LLM (or it just failed): store features now, LLM later via
        # smart_retag --retry-llm-failures / --all.
        existing = existing_entry or {}
        entry = _merge_tags(
            existing, {}, features, rel_path,
            mark_smart_retag_complete=False,
        )
        return entry

    calls_before = _llm_stats_snapshot()
    llm_tags, used_model, _skipped = _llm_tag_with_repair(
        full_path, features, verbose=False, repair_attempts=1,
        retries=0, timeout=INGEST_LLM_TIMEOUT)
    calls_after = _llm_stats_snapshot()
    if any(calls_after.get(k, 0) > calls_before.get(k, 0) for k in ("connection_error", "timeout")):
        # Server down or stalled: skip the LLM for the next files of this ingest.
        _llm_unavailable_until = time.time() + INGEST_LLM_BACKOFF_SECONDS
        print("  LLM unavailable; storing features only for the next %ds" % INGEST_LLM_BACKOFF_SECONDS)
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
    if getattr(args, 'file', None):
        full = os.path.expanduser(args.file)
        if not os.path.isabs(full):
            full = os.path.join(LIBRARY, full)
        rel = library_rel_path(full, LIBRARY)
        if not rel or not os.path.isfile(full):
            print("ERROR: not a file in the library: %s" % args.file)
            sys.exit(1)
        files = [(rel, full)]
    elif args.path:
        path = os.path.expanduser(args.path)
        if not os.path.isabs(path):
            path = os.path.join(LIBRARY, path)
        files = _walk_library(path_filter=path)
        print("Path: %d files in %s" % (len(files), path))
    else:
        files = _walk_library()
        print("Library: %d files" % len(files))

    if getattr(args, 'type', None):
        type_code = args.type.upper()
        files = [(r, f) for r, f in files if (tag_db.get(r) or {}).get('type_code') == type_code]
        print("Type %s: %d files" % (type_code, len(files)))

    # Skip rows that already have full enrichment unless --force (or one named --file)
    if not args.force and not getattr(args, 'file', None):
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

    if not args.dry_run:
        export_tags_json(TAGS_FILE)

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
        if s.get('fallback'):
            print("  LLM fallback: %d calls went to %s" % (s['fallback'], SETTINGS.get("LLM_FALLBACK_ENDPOINT")))


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
    pending = {}
    t0 = time.time()

    for i, (rel_path, full_path, entry) in enumerate(candidates):
        before = _json_safe(entry)
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
                _save_changes(pending)

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
        existing = dict(entry)
        for field in REVIBE_FIELDS:
            if field in llm_tags:
                entry[field] = llm_tags[field]
        if _user_set_quality(existing):
            _keep_user_quality(entry, existing, llm_tags)

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
        pending[rel_path] = _changed_fields(before, _json_safe(entry))
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
        _save_changes(pending)
        export_tags_json(TAGS_FILE)

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
    pending = {}
    t0 = time.time()

    for i, (rel_path, full_path, entry) in enumerate(candidates):
        if i > 0 and i % BATCH_SIZE == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(candidates) - i) / rate / 60 if rate > 0 else 0
            print("=== Retry %d/%d  |  %.0f/min  |  ETA %.0fm ===" % (
                i, len(candidates), rate * 60, eta))
            if not args.dry_run:
                _save_changes(pending)

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
        pending[rel_path] = _changed_fields(_json_safe(existing), _json_safe(new_entry))
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
        _save_changes(pending)
        export_tags_json(TAGS_FILE)

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


QUARANTINE_PREFIX = "_QUARANTINE/"


def _vote_majority(votes):
    """'keep' or 'quarantine' once two quality votes agree, else None."""
    high = sum(1 for v in votes if v > 2)
    if high >= 2:
        return "keep"
    if len(votes) - high >= 2:
        return "quarantine"
    return None


def _recheck_candidates(tag_db, type_code=None):
    """Quarantined smart-retag rows whose single low score was never confirmed.

    Yields (q_rel, rel, entry, votes) for files still in _QUARANTINE/ whose
    original slot is free; rows already settled by two agreeing votes are skipped.
    """
    for q_rel, entry in tag_db.items():
        if not q_rel.startswith(QUARANTINE_PREFIX) or not isinstance(entry, dict):
            continue
        if not str(entry.get('tag_source') or '').startswith('smart_retag'):
            continue
        qs = entry.get('quality_score')
        if not isinstance(qs, int) or qs > 2:
            continue
        if type_code and str(entry.get('type_code') or '').upper() != type_code.upper():
            continue
        votes = [v for v in (entry.get('quality_votes') or [qs]) if isinstance(v, int)]
        if _vote_majority(votes):
            continue
        rel = q_rel[len(QUARANTINE_PREFIX):]
        if rel in tag_db or os.path.exists(os.path.join(LIBRARY, rel)):
            continue
        if os.path.exists(os.path.join(LIBRARY, q_rel)):
            yield q_rel, rel, entry, votes


def _recheck_one(q_rel, rel, entry, votes, verbose=False):
    """Collect votes until two agree. Returns (verdict, votes, tags of the last passing reply).

    Scored under the file's original path, so the prompt sees the folder it
    was first judged in rather than _QUARANTINE/.
    """
    features = _get_stored_features({q_rel: entry}, q_rel)
    if not features or features.get('spectral_centroid') is None:
        features = extract_features(os.path.join(LIBRARY, q_rel))
    if not features:
        return "no_features", votes, {}
    keep_tags = {}
    while _vote_majority(votes) is None:
        score, tags = _second_quality_opinion(os.path.join(LIBRARY, rel), features, verbose)
        if score is None:
            return "llm_fail", votes, {}
        votes = votes + [score]
        if score > 2:
            keep_tags = tags
    return _vote_majority(votes), votes, keep_tags


def _restore_from_quarantine(q_rel, rel, entry, votes, keep_tags):
    """Move a file back to its original folder and re-key its row in one write."""
    restored = _merge_tags(entry, keep_tags, None, rel)
    restored['quality_score'] = sorted(votes)[len(votes) // 2]
    restored['quality_votes'] = votes
    restored['retag_model'] = LLM_MODEL
    _move_file_and_row(q_rel, rel, restored)
    return restored


def run_recheck_quarantine(args):
    """Second opinion on quarantined files: restore those that score >= 3 on a majority of votes.

    A dry run unless --apply: the votes are still collected (and cost LLM calls),
    but nothing is moved or written, so an --apply run votes afresh.
    """
    if not LLM_ENDPOINT:
        print("ERROR: SP404_LLM_ENDPOINT not set.")
        sys.exit(1)

    tag_db = _load_tags()
    candidates = list(_recheck_candidates(tag_db, type_code=args.type))
    print("Quarantined files with one unconfirmed low score: %d" % len(candidates))
    if args.limit:
        candidates = candidates[:args.limit]
        print("Limited to %d" % args.limit)
    if not candidates:
        return
    print("%s | LLM: %s | workers: %d\n" % (
        "APPLY" if args.apply else "DRY RUN (add --apply to move files)", LLM_MODEL, args.workers))

    counts = {"keep": 0, "quarantine": 0, "llm_fail": 0, "no_features": 0, "error": 0}
    t0 = time.time()
    interrupted = False
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_recheck_one, q_rel, rel, entry, votes): (q_rel, rel, entry)
                   for q_rel, rel, entry, votes in candidates}
        try:
            for i, fut in enumerate(_completed(futures), 1):
                q_rel, rel, entry = futures[fut]
                try:
                    verdict, votes, keep_tags = fut.result()
                    if args.apply and verdict == "keep":
                        _restore_from_quarantine(q_rel, rel, entry, votes, keep_tags)
                    elif args.apply and verdict == "quarantine":
                        with _persist_lock:
                            merge_tag_fields(TAGS_FILE, {q_rel: {"quality_votes": votes}})
                except Exception as exc:
                    print("  ERROR %s: %s" % (q_rel, exc), file=sys.stderr)
                    counts["error"] += 1
                    continue
                counts[verdict] += 1
                if not args.quiet:
                    label = {"keep": "RESTORE", "quarantine": "STAYS"}.get(verdict, verdict.upper())
                    print("  %s votes=%s %s: %s" % (label, votes, entry.get('type_code', '?'), rel), flush=True)
                if i % BATCH_SIZE == 0:
                    rate = i / max(time.time() - t0, 1e-6)
                    print("=== Recheck %d/%d  |  %.0f/min ===" % (i, len(candidates), rate * 60), flush=True)
        except KeyboardInterrupt:
            # Every restore so far is already written; summarize them, then stop.
            _cancel_queued(pool)
            interrupted = True

    if args.apply and (counts["keep"] or counts["quarantine"]):
        export_tags_json(TAGS_FILE)

    print("\n" + "=" * 60)
    print("Quarantine recheck %s" % (
        "interrupted" if interrupted else "complete" if args.apply else "(dry run)"))
    print("  %s: %d  Stay quarantined: %d  LLM failures: %d  No features: %d  Errors: %d" % (
        "Restored" if args.apply else "Would restore", counts["keep"], counts["quarantine"],
        counts["llm_fail"], counts["no_features"], counts["error"]))
    print("  Time: %.1f min" % ((time.time() - t0) / 60))
    if interrupted:
        raise KeyboardInterrupt


CHROMA_REFRESH_MARKER = 'chroma_refreshed'


def _refresh_candidates(tag_db, type_code=None, force=False):
    """(rel, full_path, entry) for rows with a stored chroma vector whose file is on disk."""
    for rel, entry in tag_db.items():
        if not isinstance(entry, dict):
            continue
        features = entry.get('features')
        if not isinstance(features, dict) or features.get('chroma') is None:
            continue
        if entry.get(CHROMA_REFRESH_MARKER) and not force:
            continue
        if type_code and str(entry.get('type_code') or '').upper() != type_code.upper():
            continue
        full = os.path.join(LIBRARY, rel)
        if os.path.exists(full):
            yield rel, full, entry


def _chroma_changes(entry, chroma, key):
    """Fields to merge for one refreshed row; the marker lets an interrupted run resume.

    Only librosa keys are recomputed: filename keys never came from chroma.
    """
    changes = {CHROMA_REFRESH_MARKER: datetime.now().strftime('%Y-%m-%d')}
    features = entry.get('features') or {}
    if features.get('chroma') != chroma:
        changes['features'] = {**features, 'chroma': chroma}
    if entry.get('key_source') == 'librosa' and key != entry.get('key'):
        changes['key'] = key
        if key is None:
            changes['key_source'] = None
    return changes


def run_refresh_chroma(args):
    """Recompute stored chroma vectors and librosa keys from the audio, without the LLM.

    For rows written where numpy corrupted chroma_cqt (see
    audio_analysis.numpy_elision_safe). A dry run unless --apply; --force also
    redoes rows an earlier --apply already refreshed.
    """
    tag_db = _load_tags()
    candidates = list(_refresh_candidates(tag_db, type_code=args.type, force=args.force))
    print("Rows with stored chroma to refresh: %d" % len(candidates))
    if args.limit:
        candidates = candidates[:args.limit]
        print("Limited to %d" % args.limit)
    if not candidates:
        return
    print("%s | workers: %d\n" % (
        "APPLY" if args.apply else "DRY RUN (add --apply to write the DB)", args.workers))

    counts = {"checked": 0, "chroma_changed": 0, "key_changed": 0, "unreadable": 0}
    key_moves = {}
    pending = {}
    t0 = time.time()
    interrupted = False
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(chroma_and_key, full): (rel, entry) for rel, full, entry in candidates}
        try:
            for i, fut in enumerate(_completed(futures), 1):
                rel, entry = futures[fut]
                result = fut.result()
                if result is None:
                    counts["unreadable"] += 1
                    continue
                changes = _chroma_changes(entry, *result)
                counts["checked"] += 1
                if 'features' in changes:
                    counts["chroma_changed"] += 1
                if 'key' in changes:
                    counts["key_changed"] += 1
                    move = (entry.get('key'), changes['key'])
                    key_moves[move] = key_moves.get(move, 0) + 1
                    if not args.quiet and counts["key_changed"] <= 20:
                        print("  KEY %s -> %s: %s" % (move[0], move[1], rel), flush=True)
                if args.apply:
                    pending[rel] = changes
                    if len(pending) >= BATCH_SIZE:
                        with _persist_lock:
                            _save_changes(pending)
                if i % 500 == 0:
                    rate = i / max(time.time() - t0, 1e-6)
                    print("=== Refresh %d/%d  |  %.0f/min ===" % (i, len(candidates), rate * 60), flush=True)
        except KeyboardInterrupt:
            _cancel_queued(pool)
            interrupted = True

    if args.apply:
        with _persist_lock:
            _save_changes(pending)
        export_tags_json(TAGS_FILE)

    print("\n" + "=" * 60)
    print("Chroma refresh %s" % (
        "interrupted" if interrupted else "complete" if args.apply else "(dry run)"))
    print("  Checked: %d  Chroma changed: %d  Librosa keys changed: %d  Unreadable: %d" % (
        counts["checked"], counts["chroma_changed"], counts["key_changed"], counts["unreadable"]))
    for (old, new), n in sorted(key_moves.items(), key=lambda kv: -kv[1])[:10]:
        print("    %s -> %s: %d" % (old, new, n))
    print("  Time: %.1f min" % ((time.time() - t0) / 60))
    if interrupted:
        raise KeyboardInterrupt


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
    parser.add_argument('--file', type=str, help='Retag one file (library-relative or absolute path)')
    parser.add_argument('--type', type=str, help='Only files with this type code (e.g. FX, KIK)')
    parser.add_argument('--limit', type=int, help='Max files to process')
    parser.add_argument('--dry-run', action='store_true', help='Feature extraction only')
    parser.add_argument('--force', action='store_true',
                        help='Retag already tagged files (with --refresh-chroma: redo refreshed rows)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Less output')
    parser.add_argument('--workers', type=int, default=None,
                        help='Concurrent file workers (default from RAM or SP404_SMART_RETAG_WORKERS; cap %d)' % SMART_RETAG_WORKERS_CAP)
    parser.add_argument('--delete-low-quality', action='store_true',
                        help='Permanently delete quality_score <= 2 files instead of quarantining')
    parser.add_argument('--revibe', action='store_true',
                        help='Re-vibe pass: re-interpret stored features with updated prompt')
    parser.add_argument('--retry-llm-failures', action='store_true',
                        help='Re-run LLM on files that have features but no LLM enrichment')
    parser.add_argument('--recheck-quarantine', action='store_true',
                        help='Re-score quarantined files and restore those a majority of votes rates >= 3')
    parser.add_argument('--refresh-chroma', action='store_true',
                        help='Recompute stored chroma and librosa keys from the audio, no LLM (dry run unless --apply)')
    parser.add_argument('--apply', action='store_true',
                        help='With --recheck-quarantine or --refresh-chroma: write the changes (default is a dry run)')
    args = parser.parse_args()
    if not numpy_elision_safe():
        print("ERROR: this Python/numpy pair silently corrupts large arrays (numpy < 2.3 "
              "on Python 3.14+), so features would be stored wrong. Use Python 3.12, "
              "or numpy >= 2.3.", file=sys.stderr)
        sys.exit(1)
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

    if args.recheck_quarantine:
        run_recheck_quarantine(args)
        return

    if args.refresh_chroma:
        run_refresh_chroma(args)
        return

    if args.validate:
        run_validate(args)
        return

    if not any([args.all, args.resume, args.path, args.limit, args.file, args.type]):
        parser.print_help()
        sys.exit(0)

    run(args)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped. Every finished file is saved; run the same command again "
              "(--resume for --all) to continue.", file=sys.stderr)
        sys.exit(130)
