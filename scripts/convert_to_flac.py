#!/usr/bin/env python3
"""
Batch convert WAV sample library to FLAC (lossless, ~50-60% smaller).

Converts in-place: for each WAV, creates FLAC, verifies it, updates
_tags.json, then deletes the WAV. Resumable — skips already-converted files.

Usage:
    python scripts/convert_to_flac.py                  # convert all
    python scripts/convert_to_flac.py --dry-run        # preview only
    python scripts/convert_to_flac.py --verify-only    # check existing FLACs
    python scripts/convert_to_flac.py --path Drums/Kicks  # convert one folder
"""
import argparse
import json
import os
import subprocess
import sys
import time
from jambox_config import LIBRARY_SKIP_DIRS, LONG_HOLD_DIRNAME, load_settings_for_script

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
FFMPEG = SETTINGS["FFMPEG_BIN"]
FFPROBE = SETTINGS["FFPROBE_BIN"]

# Directories to skip (not samples)
SKIP_DIRS = LIBRARY_SKIP_DIRS | {'.git'}


def load_tags():
    """Load _tags.json."""
    from jambox_config import load_tag_db
    return load_tag_db(TAGS_FILE)


def save_tags(tags):
    """Write tag database via jambox_config (SQLite + JSON)."""
    from jambox_config import save_tag_db
    save_tag_db(TAGS_FILE, tags)


def convert_wav_to_flac(wav_path):
    """Convert a single WAV to FLAC. Returns FLAC path or None on failure."""
    flac_path = os.path.splitext(wav_path)[0] + '.flac'

    result = subprocess.run(
        [FFMPEG, '-y', '-i', wav_path, '-c:a', 'flac', '-compression_level', '5', flac_path],
        capture_output=True, text=True, timeout=60
    )

    if result.returncode != 0:
        # Clean up failed output
        if os.path.exists(flac_path):
            os.remove(flac_path)
        return None

    return flac_path


def verify_flac(flac_path):
    """Verify a FLAC file can be decoded. Returns True if valid."""
    try:
        result = subprocess.run(
            [FFPROBE, '-v', 'error', '-select_streams', 'a:0',
             '-show_entries', 'stream=codec_name,sample_rate,channels',
             '-of', 'json', flac_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
        return len(streams) > 0 and streams[0].get('codec_name') == 'flac'
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return False


def find_wavs(subpath=None):
    """Find all WAV files in the library."""
    base = os.path.join(LIBRARY, subpath) if subpath else LIBRARY
    wavs = []
    for root, dirs, files in os.walk(base):
        # Skip special directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for f in sorted(files):
            if f.lower().endswith('.wav'):
                wavs.append(os.path.join(root, f))
    return wavs


def batch_convert(subpath=None, dry_run=False, verify_only=False):
    """Convert all WAVs to FLAC with _tags.json migration."""
    wavs = find_wavs(subpath)
    tags = load_tags()

    total = len(wavs)
    converted = 0
    skipped = 0
    failed = 0
    bytes_saved = 0

    print(f"Found {total} WAV files in library")
    if dry_run:
        print("DRY RUN — no files will be modified\n")
    if verify_only:
        print("VERIFY ONLY — checking existing FLACs\n")

    start_time = time.time()

    for i, wav_path in enumerate(wavs):
        rel_path = os.path.relpath(wav_path, LIBRARY)
        flac_path = os.path.splitext(wav_path)[0] + '.flac'
        flac_rel = os.path.splitext(rel_path)[0] + '.flac'

        # Progress
        if (i + 1) % 100 == 0 or i == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{total}] {rate:.0f} files/sec, ETA {eta:.0f}s — {rel_path[:60]}")

        # Already converted?
        if os.path.exists(flac_path):
            if verify_only:
                if not verify_flac(flac_path):
                    print(f"  INVALID: {flac_rel}")
                    failed += 1
                else:
                    skipped += 1
            else:
                skipped += 1
            continue

        if verify_only:
            # No FLAC exists, count as needing conversion
            failed += 1
            continue

        if dry_run:
            wav_size = os.path.getsize(wav_path)
            est_flac = int(wav_size * 0.45)  # rough estimate
            est_saved = wav_size - est_flac
            bytes_saved += est_saved
            converted += 1
            continue

        # Convert
        wav_size = os.path.getsize(wav_path)
        result_path = convert_wav_to_flac(wav_path)

        if not result_path:
            print(f"  FAILED: {rel_path}")
            failed += 1
            continue

        # Verify
        if not verify_flac(result_path):
            print(f"  VERIFY FAILED: {flac_rel}")
            os.remove(result_path)
            failed += 1
            continue

        flac_size = os.path.getsize(result_path)
        saved = wav_size - flac_size
        bytes_saved += saved

        # Update _tags.json — persist before deleting the original WAV.
        if rel_path in tags:
            tags[flac_rel] = tags.pop(rel_path)
            try:
                save_tags(tags)
            except OSError:
                print(f"  TAG UPDATE FAILED: {rel_path}")
                tags[rel_path] = tags.pop(flac_rel)
                if os.path.exists(result_path):
                    os.remove(result_path)
                failed += 1
                continue

        # Delete original WAV
        try:
            os.remove(wav_path)
        except OSError:
            print(f"  DELETE FAILED: {rel_path}")
            failed += 1
            continue
        converted += 1

    if not dry_run and not verify_only and converted > 0:
        print(f"\n  Updated _tags.json ({len(tags)} entries)")

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"{'DRY RUN ' if dry_run else ''}Results:")
    print(f"  Converted: {converted}")
    print(f"  Skipped (already FLAC): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Space saved: {_human_size(bytes_saved)}")
    print(f"  Time: {elapsed:.1f}s")

    return converted, skipped, failed, bytes_saved


def _human_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def main():
    parser = argparse.ArgumentParser(description='Convert WAV library to FLAC')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    parser.add_argument('--verify-only', action='store_true', help='Check existing FLACs')
    parser.add_argument('--path', type=str, help='Subpath within library (e.g. Drums/Kicks)')
    args = parser.parse_args()

    batch_convert(subpath=args.path, dry_run=args.dry_run, verify_only=args.verify_only)


if __name__ == '__main__':
    main()
