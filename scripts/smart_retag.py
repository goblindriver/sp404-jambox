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
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings_for_script
from audio_analysis import extract_features, is_available as librosa_available

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
LLM_ENDPOINT = SETTINGS.get("LLM_ENDPOINT", "")
LLM_MODEL = SETTINGS.get("LLM_MODEL", "qwen3")
LLM_TIMEOUT = SETTINGS.get("LLM_TIMEOUT", 30)
REPO_DIR = os.path.dirname(SCRIPTS_DIR)
CHECKPOINT_PATH = os.path.join(REPO_DIR, "data", "retag_checkpoint.json")
QUARANTINE_DIR = os.path.join(LIBRARY, "_QUARANTINE")
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}
SKIP_DIRS = {"_RAW-DOWNLOADS", "_GOLD", "_DUPES", "_QUARANTINE", "Stems"}

BATCH_SIZE = 50

# Type code processing order — preset-demand-first
TYPE_CODE_ORDER = [
    "KIK", "SNR", "HAT", "CLP", "CYM", "RIM", "PRC",
    "BRK", "SMP",
    "BAS",
    "SYN", "PAD", "KEY",
    "VOX",
    "FX", "SFX", "RSR",
    "GTR", "HRN", "STR",
    "AMB", "FLY", "TPE",
]

VALID_TYPE_CODES = {
    "KIK", "SNR", "HAT", "CLP", "CYM", "RIM", "PRC", "BRK", "DRM",
    "BAS", "GTR", "KEY", "SYN", "PAD", "STR", "BRS", "PLK", "WND", "VOX", "SMP",
    "FX", "SFX", "AMB", "FLY", "TPE", "RSR", "HRN",
}

VALID_VIBES = {
    "dark", "warm", "hype", "dreamy", "nostalgic", "aggressive", "mellow",
    "soulful", "eerie", "playful", "gritty", "ethereal", "triumphant",
    "melancholic", "tense", "chill", "uplifting",
}

VALID_TEXTURES = {
    "dusty", "lo-fi", "raw", "clean", "warm", "saturated", "bitcrushed",
    "airy", "crispy", "glassy", "muddy", "vinyl", "tape", "digital",
    "organic", "crunchy", "warbly", "bright", "thick", "thin", "filtered",
}

VALID_GENRES = {
    "funk", "soul", "disco", "house", "electronic", "hiphop", "dub",
    "ambient", "jazz", "rock", "punk", "dancehall", "latin", "pop", "rnb",
    "industrial", "boom-bap", "lo-fi", "tropical", "afrobeat",
    "lo-fi-hiphop", "trap", "drill", "gospel", "uk-garage", "footwork",
    "city-pop", "psychedelic", "reggae", "classical", "world",
}

VALID_ENERGIES = {"low", "mid", "high"}
VALID_PLAYABILITIES = {"one-shot", "loop", "chop-ready", "chromatic", "layer", "transition"}

# ── System prompt ──

TAGGER_SYSTEM_PROMPT = """You are a sample library tagger for an SP-404 sampler. You analyze audio features and metadata to generate precise tags that help a fetch system find the right sample for a musical context.

You will receive:
- Audio features extracted by librosa (spectral centroid, MFCCs, spectral rolloff, chroma, zero-crossing rate, onset strength, RMS envelope, BPM, key)
- Filename and directory path
- File duration in seconds

Respond with ONLY a JSON object. No explanation, no markdown, no preamble. Do not wrap in code fences.

{
  "type_code": "<one of: KIK, SNR, HAT, PRC, BAS, SYN, PAD, VOX, FX, BRK, RSR, GTR, HRN, KEY, STR>",
  "playability": "<one of: one-shot, loop, chop-ready, layer, transition>",
  "vibe": ["<1-3 tags from: dark, warm, hype, dreamy, nostalgic, aggressive, mellow, soulful, eerie, playful, gritty, ethereal, triumphant, melancholic, tense>"],
  "texture": ["<1-2 tags from: dusty, lo-fi, raw, clean, warm, saturated, bitcrushed, airy, crispy, glassy, muddy, vinyl, tape, digital, organic>"],
  "genre": ["<1-2 tags from: funk, soul, disco, house, electronic, hiphop, dub, ambient, jazz, rock, punk, dancehall, latin, pop, rnb, industrial, boom-bap, lo-fi, tropical, afrobeat>"],
  "energy": "<one of: low, mid, high>",
  "sonic_description": "<1 sentence describing the sound character>",
  "quality_score": <1-5 integer>,
  "instrument_hint": "<specific instrument if identifiable, null otherwise>"
}

RULES:
- type_code is the PRIMARY classification. Get this right above all else.
- Use audio features to inform tags, not just the filename. Filenames lie.
- For type_code, use spectral features:
  - KIK: low spectral centroid (<1500), strong onset, short duration, minimal high-frequency
  - SNR: mid-high centroid, sharp onset, broadband noise, short duration
  - HAT: high centroid (>4000), high zero-crossing rate, very short duration
  - PRC: variable centroid, strong onset, short-to-mid duration
  - BAS: low centroid (<2000), sustained or rhythmic, strong low-frequency energy
  - SYN: mid centroid, sustained, harmonic content, evolving timbre
  - PAD: low-mid centroid, long sustained, slow attack (attack_position > 0.3), ambient character
  - VOX: mid centroid, formant structure in MFCCs, variable duration
  - FX: unusual spectral profile, non-musical or abstract
  - BRK: rhythmic onsets (onset_count > 4), multiple transients, longer duration (>2s)
  - RSR: rising spectral energy over time, building character
  - GTR: mid centroid, plucked/strummed onset pattern, harmonic series
  - HRN: mid-high centroid, brass formant structure, sustained
  - KEY: mid centroid, percussive onset with sustained harmonics
  - STR: mid centroid, bowed onset, rich harmonic series, sustained
- playability heuristics:
  - Duration <2s and strong single onset -> one-shot
  - Duration >2s with rhythmic onsets (onset_count > 4) -> loop or chop-ready
  - Duration >2s with steady/evolving RMS -> layer or loop
  - Rising RMS envelope (attack_position > 0.7) -> transition or riser
- quality_score for SP-404 live performance:
  - 5: Instantly usable, distinctive, would build a bank around it
  - 4: Solid, good character, reliable workhorse
  - 3: Usable but generic
  - 2: Technical issues, boring, redundant
  - 1: Broken, unusable, irrelevant
  - Samples under 0.1s: almost always 1
  - Samples over 120s: almost always 1-2
  - Vintage/lo-fi character is a FEATURE not a flaw"""


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

    # Suppress qwen3 reasoning to save tokens and get direct JSON
    lines.append("")
    lines.append("/no_think")

    return "\n".join(lines)


def _call_llm(prompt):
    """Send prompt to Ollama and parse JSON response."""
    if not LLM_ENDPOINT:
        return None

    import requests

    try:
        resp = requests.post(
            LLM_ENDPOINT,
            json={"model": LLM_MODEL, "messages": [
                {"role": "system", "content": TAGGER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ], "temperature": 0.3, "max_tokens": 2048},
            timeout=max(LLM_TIMEOUT, 90),
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        if not content:
            return None

        content = content.strip()
        # Strip markdown fences
        if content.startswith("```"):
            content = re.sub(r'^```\w*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)
            content = content.strip()
        # Strip <think> blocks (qwen3 reasoning)
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

        # Try parsing JSON, fix common truncation issues
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try fixing truncated JSON (trailing comma, missing closing brace)
            fixed = content.rstrip().rstrip(',')
            if not fixed.endswith('}'):
                fixed += '}'
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return None
    except Exception:
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

    for dim, valid_set in [('vibe', VALID_VIBES), ('texture', VALID_TEXTURES), ('genre', VALID_GENRES)]:
        raw = llm_tags.get(dim, [])
        if isinstance(raw, str):
            raw = [r.strip().lower() for r in raw.split(',')]
        elif isinstance(raw, list):
            raw = [str(r).strip().lower() for r in raw]
        else:
            raw = []
        valid = [v for v in raw if v in valid_set]
        if valid:
            result[dim] = valid[:3]

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


def _merge_tags(existing_entry, llm_tags, features, rel_path):
    """Merge validated LLM tags and features into a tag entry."""
    entry = dict(existing_entry) if existing_entry else {}

    # LLM tags overwrite filename-inferred ones
    for key in ('type_code', 'playability', 'vibe', 'texture', 'genre',
                'energy', 'sonic_description', 'quality_score', 'instrument_hint'):
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

    # Rebuild flat tag set
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

    entry['tag_source'] = 'smart_retag_v1'
    entry['tagged_at'] = datetime.now().isoformat()
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
    os.makedirs(os.path.dirname(CHECKPOINT_PATH), exist_ok=True)
    with open(CHECKPOINT_PATH, 'w') as f:
        json.dump(cp, f, indent=2)


def _load_tags():
    from jambox_config import load_tag_db
    return load_tag_db(TAGS_FILE)


def _save_tags(db):
    from jambox_config import save_tag_db
    save_tag_db(TAGS_FILE, db)


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

def retag_batch(files, tag_db, dry_run=False, verbose=True):
    """Process a batch through feature extraction + LLM tagging.

    Returns (tagged, quarantined, errors).
    """
    tagged = quarantined = errors = 0

    for rel_path, full_path in files:
        fname = os.path.basename(rel_path)

        # 1. Extract features
        features = extract_features(full_path)
        if not features:
            if verbose:
                print("  SKIP (no features): %s" % fname)
            errors += 1
            continue

        if dry_run:
            if verbose:
                print("  DRY-RUN: %s (dur=%.1fs centroid=%.0f onsets=%d)" % (
                    fname, features.get('duration', 0),
                    features.get('spectral_centroid', 0),
                    features.get('onset_count', 0)))
            tagged += 1
            continue

        # 2. Build prompt and call LLM
        prompt = _build_prompt(full_path, features)
        raw_llm = _call_llm(prompt)
        llm_tags = _validate_llm_tags(raw_llm) if raw_llm else {}

        # 3. Merge into tag DB
        existing = tag_db.get(rel_path, {})
        entry = _merge_tags(existing, llm_tags, features, rel_path)
        tag_db[rel_path] = entry

        quality = entry.get('quality_score', 3)
        tc = entry.get('type_code', '?')
        vibe_str = ','.join(entry.get('vibe', [])[:2])
        desc = (entry.get('sonic_description') or '')[:50]

        # 4. Quarantine low quality
        if quality <= 2:
            os.makedirs(QUARANTINE_DIR, exist_ok=True)
            q_dest = os.path.join(QUARANTINE_DIR, os.path.basename(full_path))
            if not os.path.exists(q_dest):
                try:
                    shutil.move(full_path, q_dest)
                    quarantined += 1
                    if verbose:
                        print("  QUARANTINE q=%d %s: %s — %s" % (quality, tc, fname, desc))
                except OSError:
                    pass
            continue

        tagged += 1
        src = "LLM" if llm_tags else "features"
        if verbose:
            print("  %s q=%d %s [%s]: %s — %s" % (src, quality, tc, vibe_str, fname, desc))

    return tagged, quarantined, errors


# ── Main runner ──

def run(args):
    if not librosa_available():
        print("ERROR: librosa not installed. Run: pip3 install librosa scipy")
        sys.exit(1)

    if not LLM_ENDPOINT and not args.dry_run:
        print("WARNING: SP404_LLM_ENDPOINT not set. Will extract features only.")

    tag_db = _load_tags()
    print("Tag DB: %d entries" % len(tag_db))

    # Determine files to process
    if args.resume:
        cp = _load_checkpoint()
        if not cp:
            print("No checkpoint found. Use --all to start fresh.")
            sys.exit(1)
        done = set(cp.get('processed_files', []))
        all_files = _walk_library()
        files = [(r, f) for r, f in all_files if r not in done]
        print("Resuming: %d remaining of %d" % (len(files), len(all_files)))
    elif args.path:
        path = os.path.expanduser(args.path)
        if not os.path.isabs(path):
            path = os.path.join(LIBRARY, path)
        files = _walk_library(path_filter=path)
        print("Path: %d files in %s" % (len(files), path))
    else:
        files = _walk_library()
        print("Library: %d files" % len(files))

    # Skip already smart-tagged unless --force
    if not args.force:
        before = len(files)
        files = [(r, f) for r, f in files
                 if tag_db.get(r, {}).get('tag_source') != 'smart_retag_v1']
        skipped = before - len(files)
        if skipped:
            print("Skipping %d already tagged (--force to redo)" % skipped)

    # Sort by preset demand
    files = _sort_by_demand(files, tag_db)

    if args.limit:
        files = files[:args.limit]
        print("Limited to %d" % len(files))

    if not files:
        print("Nothing to process.")
        return

    print("Processing %d files...\n" % len(files))

    total_tagged = total_quarantined = total_errors = 0
    processed_files = []
    t0 = time.time()

    for i in range(0, len(files), BATCH_SIZE):
        batch = files[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(files) + BATCH_SIZE - 1) // BATCH_SIZE

        elapsed = time.time() - t0
        rate = (i / elapsed) if elapsed > 0 and i > 0 else 0
        eta = ((len(files) - i) / rate / 60) if rate > 0 else 0

        print("=== Batch %d/%d  |  %.0f/min  |  ETA %.0fm ===" % (
            batch_num, total_batches, rate * 60, eta))

        t, q, e = retag_batch(batch, tag_db, dry_run=args.dry_run,
                               verbose=not args.quiet)
        total_tagged += t
        total_quarantined += q
        total_errors += e

        for rel, _ in batch:
            processed_files.append(rel)

        # Save after each batch
        if not args.dry_run:
            _save_tags(tag_db)
            _save_checkpoint({
                'started_at': datetime.now().isoformat() if i == 0 else None,
                'last_updated': datetime.now().isoformat(),
                'total_files': len(files),
                'processed': len(processed_files),
                'tagged': total_tagged,
                'quarantined': total_quarantined,
                'errors': total_errors,
                'batch_size': BATCH_SIZE,
                'processed_files': processed_files,
                'avg_time_per_file_ms': int(elapsed * 1000 / max(len(processed_files), 1)),
            })

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("Smart Retag Complete")
    print("  Processed: %d  Tagged: %d  Quarantined: %d  Errors: %d" % (
        len(processed_files), total_tagged, total_quarantined, total_errors))
    print("  Time: %.1f min  Rate: %.0f files/min" % (
        elapsed / 60, len(processed_files) / max(elapsed / 60, 0.01)))
    print("  Tag DB: %d entries" % len(tag_db))


def main():
    parser = argparse.ArgumentParser(description='Smart retag: LLM-powered sample tagger')
    parser.add_argument('--all', action='store_true', help='Process entire library')
    parser.add_argument('--resume', action='store_true', help='Resume from checkpoint')
    parser.add_argument('--validate', action='store_true', help='Validation mode')
    parser.add_argument('--path', type=str, help='Process specific directory')
    parser.add_argument('--limit', type=int, help='Max files to process')
    parser.add_argument('--dry-run', action='store_true', help='Feature extraction only')
    parser.add_argument('--force', action='store_true', help='Retag already tagged files')
    parser.add_argument('--quiet', '-q', action='store_true', help='Less output')
    args = parser.parse_args()

    if not any([args.all, args.resume, args.validate, args.path, args.limit]):
        parser.print_help()
        sys.exit(0)

    run(args)


if __name__ == '__main__':
    main()
