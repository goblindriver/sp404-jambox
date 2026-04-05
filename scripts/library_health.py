#!/usr/bin/env python3
"""Library health check — find clipping, DC offset, silence, and BPM gaps.

Scans the sample library and reports:
  - Clipping: samples that hit 0dBFS (digital max) frequently
  - DC offset: samples with significant DC bias
  - Silence: samples that are mostly silent
  - Missing BPM: loops/breaks with no BPM tag (candidates for auto-detection)

Uses only numpy + struct (no librosa/scipy needed).

Usage:
    python scripts/library_health.py                    # full scan
    python scripts/library_health.py --fix-bpm          # also detect and write BPM
    python scripts/library_health.py --type BRK         # only check breaks
"""
import argparse
import json
import os
import subprocess
import sys
import time
import numpy as np
from jambox_config import LONG_HOLD_DIRNAME, load_settings_for_script, save_tag_db as _config_save_tag_db

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
FFMPEG = SETTINGS["FFMPEG_BIN"]
SKIP_DIRS = {"_RAW-DOWNLOADS", "_GOLD", "_DUPES", "_QUARANTINE", LONG_HOLD_DIRNAME}


def read_pcm_samples(filepath, max_seconds=60):
    """Decode audio to float32 PCM samples via ffmpeg. Caps at max_seconds to limit RAM.

    Handles WAV, FLAC, MP3, AIF, and any format ffmpeg supports.
    Returns numpy array of float32 samples in [-1, 1] or None on failure.
    """
    try:
        cmd = [
            FFMPEG, "-y", "-i", filepath,
            "-t", str(max_seconds),
            "-ar", "44100", "-ac", "1", "-f", "s16le", "-acodec", "pcm_s16le",
            "pipe:1",
        ]
        result = subprocess.run(
            cmd, capture_output=True, timeout=30,
        )
        if result.returncode != 0 or len(result.stdout) < 4:
            return None
        samples = np.frombuffer(result.stdout, dtype=np.int16)
        return samples.astype(np.float32) / 32768.0
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


def check_clipping(samples, threshold=0.99, max_ratio=0.01):
    """Check if a sample has excessive clipping.

    Returns (is_clipping, clip_ratio).
    """
    if len(samples) == 0:
        return False, 0.0
    clipped = np.sum(np.abs(samples) >= threshold)
    ratio = clipped / len(samples)
    return ratio > max_ratio, round(ratio, 4)


def check_dc_offset(samples, threshold=0.02):
    """Check for DC offset (mean significantly away from zero).

    Returns (has_offset, offset_value).
    """
    if len(samples) == 0:
        return False, 0.0
    mean = np.mean(samples)
    return abs(mean) > threshold, round(float(mean), 4)


def check_silence(samples, threshold=0.005, silent_ratio=0.95):
    """Check if a sample is mostly silence.

    Returns (is_silent, silent_portion).
    """
    if len(samples) == 0:
        return True, 1.0
    silent = np.sum(np.abs(samples) < threshold)
    ratio = silent / len(samples)
    return ratio > silent_ratio, round(ratio, 4)


def detect_bpm_from_onset(samples, sr=44100):
    """Simple onset-based BPM detection using energy peaks.

    Uses a basic approach: compute short-time energy, find peaks,
    measure inter-onset intervals, estimate BPM.
    Returns estimated BPM or None.
    """
    if len(samples) < sr * 2:  # need at least 2 seconds
        return None

    # Compute short-time energy (frame size ~23ms = 1024 samples at 44100)
    frame_size = 1024
    hop = 512
    n_frames = (len(samples) - frame_size) // hop

    if n_frames < 10:
        return None

    energy = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop
        frame = samples[start:start + frame_size]
        energy[i] = np.sum(frame ** 2)

    # Normalize energy
    max_e = np.max(energy)
    if max_e == 0:
        return None
    energy = energy / max_e

    # Find onset peaks (energy jumps)
    diff = np.diff(energy)
    diff[diff < 0] = 0  # only positive changes

    # Threshold: significant energy increases
    threshold = np.mean(diff) + 1.5 * np.std(diff)
    if threshold <= 0:
        return None

    peaks = []
    for i in range(1, len(diff) - 1):
        if diff[i] > threshold and diff[i] > diff[i-1] and diff[i] > diff[i+1]:
            peaks.append(i)

    if len(peaks) < 4:
        return None

    # Compute inter-onset intervals
    intervals = np.diff(peaks) * hop / sr  # in seconds
    intervals = intervals[(intervals > 0.2) & (intervals < 2.0)]  # 30-300 BPM range

    if len(intervals) < 3:
        return None

    # Median interval → BPM
    median_interval = np.median(intervals)
    bpm = 60.0 / median_interval

    # Snap to common BPMs (within 3%)
    common_bpms = [70, 75, 80, 85, 88, 90, 95, 100, 105, 110, 112, 115,
                   120, 122, 125, 128, 130, 135, 138, 140, 145, 150, 160, 170, 174, 180]
    for common in common_bpms:
        if abs(bpm - common) / common < 0.03:
            return common

    return round(bpm)


def load_tag_db():
    """Load tag database."""
    from jambox_config import load_tag_db as _load
    return _load(TAGS_FILE)


def save_tag_db(db):
    """Save tag database (delegates to jambox_config for SQLite + JSON consistency)."""
    _config_save_tag_db(TAGS_FILE, db)


def main():
    parser = argparse.ArgumentParser(description='Library health check')
    parser.add_argument('--fix-bpm', action='store_true', help='Auto-detect and write BPM for untagged samples')
    parser.add_argument('--type', help='Only check samples with this type code (e.g., BRK, KIK)')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of files to check')
    args = parser.parse_args()

    db = load_tag_db()
    if not db:
        print("ERROR: No tag database found. Run: python scripts/tag_library.py")
        sys.exit(1)

    print(f"Scanning {len(db)} tagged files...\n")

    issues = {
        'clipping': [],
        'dc_offset': [],
        'silence': [],
        'missing_bpm': [],
    }
    bpm_detected = 0
    checked = 0

    entries = list(db.items())
    if args.type:
        entries = [(k, v) for k, v in entries if v.get('type_code') == args.type.upper()]
        print(f"Filtered to {len(entries)} files with type={args.type.upper()}")

    if args.limit:
        entries = entries[:args.limit]

    t0 = time.time()
    for i, (rel_path, entry) in enumerate(entries):
        full_path = os.path.join(LIBRARY, rel_path)
        if not os.path.exists(full_path):
            continue

        if not full_path.lower().endswith(('.wav', '.flac', '.mp3', '.aif', '.aiff', '.ogg')):
            continue

        samples = read_pcm_samples(full_path)
        if samples is None:
            continue

        checked += 1

        # Clipping check
        is_clipping, clip_ratio = check_clipping(samples)
        if is_clipping:
            issues['clipping'].append((rel_path, clip_ratio))

        # DC offset check
        has_offset, offset_val = check_dc_offset(samples)
        if has_offset:
            issues['dc_offset'].append((rel_path, offset_val))

        # Silence check
        is_silent, silent_ratio = check_silence(samples)
        if is_silent:
            issues['silence'].append((rel_path, silent_ratio))

        # Missing BPM check (only for loops/breaks)
        tc = entry.get('type_code', '')
        play = entry.get('playability', '')
        if not entry.get('bpm') and (tc in ('BRK', 'SMP') or play == 'loop'):
            if args.fix_bpm:
                detected = detect_bpm_from_onset(samples)
                if detected:
                    entry['bpm'] = detected
                    if f"{detected}bpm" not in entry.get('tags', []):
                        entry.setdefault('tags', []).append(f"{detected}bpm")
                        entry['tags'] = sorted(entry['tags'])
                    bpm_detected += 1
                    issues['missing_bpm'].append((rel_path, f"detected: {detected}"))
                else:
                    issues['missing_bpm'].append((rel_path, "undetectable"))
            else:
                issues['missing_bpm'].append((rel_path, "no BPM"))

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            print(f"  [{i+1}/{len(entries)}] {rate:.0f} files/sec")

    elapsed = time.time() - t0

    # Report
    print(f"\n{'='*60}")
    print(f"LIBRARY HEALTH REPORT — {checked} files checked in {elapsed:.1f}s")
    print(f"{'='*60}")

    print(f"\n🔴 Clipping ({len(issues['clipping'])} files):")
    for path, ratio in issues['clipping'][:20]:
        print(f"  {ratio*100:.1f}% clipped — {path}")
    if len(issues['clipping']) > 20:
        print(f"  ... and {len(issues['clipping']) - 20} more")

    print(f"\n🟡 DC Offset ({len(issues['dc_offset'])} files):")
    for path, offset in issues['dc_offset'][:20]:
        print(f"  offset={offset:.4f} — {path}")
    if len(issues['dc_offset']) > 20:
        print(f"  ... and {len(issues['dc_offset']) - 20} more")

    print(f"\n⚪ Mostly Silent ({len(issues['silence'])} files):")
    for path, ratio in issues['silence'][:20]:
        print(f"  {ratio*100:.1f}% silent — {path}")
    if len(issues['silence']) > 20:
        print(f"  ... and {len(issues['silence']) - 20} more")

    print(f"\n🔵 Missing BPM ({len(issues['missing_bpm'])} loops/breaks):")
    for path, note in issues['missing_bpm'][:20]:
        print(f"  {note} — {path}")
    if len(issues['missing_bpm']) > 20:
        print(f"  ... and {len(issues['missing_bpm']) - 20} more")

    if args.fix_bpm and bpm_detected > 0:
        print(f"\n✅ Auto-detected BPM for {bpm_detected} files — saving to _tags.json...")
        save_tag_db(db)

    # Summary
    total_issues = sum(len(v) for v in issues.values())
    print(f"\n{'='*60}")
    print(f"Total issues: {total_issues}")
    print(f"  Clipping: {len(issues['clipping'])}")
    print(f"  DC offset: {len(issues['dc_offset'])}")
    print(f"  Silent: {len(issues['silence'])}")
    print(f"  Missing BPM: {len(issues['missing_bpm'])}")


if __name__ == '__main__':
    main()
