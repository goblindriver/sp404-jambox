#!/usr/bin/env python3
"""Detect near-duplicate samples in the library.

Approach: normalize each WAV to mono 22050Hz via ffmpeg, then compute a
short audio fingerprint (RMS envelope + zero-crossing summary). Files
with very similar fingerprints are flagged as duplicates.

Two modes:
  - Report: list duplicate groups (default)
  - Clean: move duplicates to _DUPES/ folder, keeping the best copy

Uses only ffmpeg + numpy (no librosa/scipy needed).

Usage:
    python scripts/dedup_library.py                  # report only
    python scripts/dedup_library.py --clean          # move dupes to _DUPES/
    python scripts/dedup_library.py --type BRK       # only check breaks
    python scripts/dedup_library.py --threshold 0.98 # stricter matching
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import numpy as np
from jambox_config import load_settings_for_script

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
DUPES_DIR = os.path.join(LIBRARY, "_DUPES")
FFMPEG = SETTINGS["FFMPEG_BIN"]
SKIP_DIRS = {"_RAW-DOWNLOADS", "_GOLD", "_DUPES"}


def compute_fingerprint(filepath):
    """Compute an audio fingerprint for deduplication.

    1. Decode to raw 16-bit mono 22050Hz PCM via ffmpeg
    2. Compute RMS envelope (64 frames)
    3. Compute zero-crossing rate envelope (64 frames)
    4. Concatenate into 128-dimensional fingerprint vector

    Returns numpy array of shape (128,) or None on failure.
    """
    try:
        # Decode to raw PCM via ffmpeg (fast, works with any format)
        result = subprocess.run([
            FFMPEG, '-y', '-i', filepath,
            '-ar', '22050', '-ac', '1', '-sample_fmt', 's16',
            '-f', 's16le', '-'
        ], capture_output=True, timeout=10)

        if result.returncode != 0 or len(result.stdout) < 100:
            return None

        samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0

        if len(samples) < 4410:  # less than 0.2s
            return None

        # Split into 64 frames
        n_frames = 64
        frame_size = len(samples) // n_frames
        if frame_size < 10:
            return None

        rms = np.zeros(n_frames)
        zcr = np.zeros(n_frames)

        for i in range(n_frames):
            start = i * frame_size
            frame = samples[start:start + frame_size]
            # RMS energy
            rms[i] = np.sqrt(np.mean(frame ** 2))
            # Zero-crossing rate
            signs = np.sign(frame)
            zcr[i] = np.sum(np.abs(np.diff(signs)) > 0) / len(frame)

        # Normalize each to unit length
        rms_norm = np.linalg.norm(rms)
        zcr_norm = np.linalg.norm(zcr)
        if rms_norm > 0:
            rms = rms / rms_norm
        if zcr_norm > 0:
            zcr = zcr / zcr_norm

        return np.concatenate([rms, zcr])

    except Exception:
        return None


def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_tag_db():
    try:
        with open(TAGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    parser = argparse.ArgumentParser(description='Detect duplicate samples')
    parser.add_argument('--clean', action='store_true', help='Move duplicates to _DUPES/')
    parser.add_argument('--type', help='Only check samples with this type code')
    parser.add_argument('--threshold', type=float, default=0.95,
                        help='Similarity threshold (0.0-1.0, default 0.95)')
    parser.add_argument('--limit', type=int, default=0, help='Limit files to scan')
    args = parser.parse_args()

    db = load_tag_db()
    if not db:
        print("ERROR: No tag database. Run: python scripts/tag_library.py")
        sys.exit(1)

    # Filter entries
    entries = list(db.items())
    if args.type:
        entries = [(k, v) for k, v in entries if v.get('type_code') == args.type.upper()]
        print(f"Filtered to {len(entries)} files with type={args.type.upper()}")
    if args.limit:
        entries = entries[:args.limit]

    print(f"Computing fingerprints for {len(entries)} files...")
    t0 = time.time()

    fingerprints = {}  # rel_path -> fingerprint
    for i, (rel_path, entry) in enumerate(entries):
        full_path = os.path.join(LIBRARY, rel_path)
        if not os.path.exists(full_path):
            continue

        fp = compute_fingerprint(full_path)
        if fp is not None:
            fingerprints[rel_path] = fp

        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            print(f"  [{i+1}/{len(entries)}] {rate:.0f} files/sec — {len(fingerprints)} fingerprinted")

    elapsed = time.time() - t0
    print(f"\nFingerprinted {len(fingerprints)} files in {elapsed:.1f}s")

    # Find duplicate groups using greedy clustering
    print(f"\nComparing fingerprints (threshold={args.threshold})...")
    paths = list(fingerprints.keys())
    fps = [fingerprints[p] for p in paths]
    used = set()
    groups = []

    for i in range(len(paths)):
        if i in used:
            continue
        group = [i]
        for j in range(i + 1, len(paths)):
            if j in used:
                continue
            sim = cosine_similarity(fps[i], fps[j])
            if sim >= args.threshold:
                group.append(j)
                used.add(j)
        if len(group) > 1:
            used.add(i)
            groups.append(group)

    # Report
    print(f"\n{'='*60}")
    print(f"DUPLICATE REPORT — {len(groups)} groups found")
    print(f"{'='*60}")

    total_dupes = 0
    total_bytes_reclaimable = 0

    for gi, group in enumerate(groups):
        group_paths = [paths[idx] for idx in group]
        # Keep the one with more tags (better metadata)
        scored = []
        for p in group_paths:
            entry = db.get(p, {})
            tag_count = len(entry.get('tags', []))
            size = os.path.getsize(os.path.join(LIBRARY, p)) if os.path.exists(os.path.join(LIBRARY, p)) else 0
            scored.append((p, tag_count, size))
        # Keep the one with most tags, then largest file
        scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
        keep = scored[0][0]
        dupes = [s[0] for s in scored[1:]]

        if gi < 30:  # Show first 30 groups
            print(f"\n  Group {gi+1}:")
            print(f"    KEEP: {keep}")
            for d in dupes:
                sz = os.path.getsize(os.path.join(LIBRARY, d)) if os.path.exists(os.path.join(LIBRARY, d)) else 0
                print(f"    DUPE: {d} ({sz // 1024}KB)")
                total_bytes_reclaimable += sz

        total_dupes += len(dupes)

        if args.clean:
            os.makedirs(DUPES_DIR, exist_ok=True)
            for d in dupes:
                src = os.path.join(LIBRARY, d)
                if os.path.exists(src):
                    # Preserve directory structure in _DUPES
                    dst = os.path.join(DUPES_DIR, d)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src, dst)

    if len(groups) > 30:
        print(f"\n  ... and {len(groups) - 30} more groups")

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Duplicate groups: {len(groups)}")
    print(f"  Total duplicates: {total_dupes}")
    print(f"  Reclaimable space: {total_bytes_reclaimable // (1024*1024)}MB")
    if args.clean:
        print(f"  Moved to: {DUPES_DIR}")
    else:
        print(f"  Run with --clean to move duplicates to _DUPES/")


if __name__ == '__main__':
    main()
