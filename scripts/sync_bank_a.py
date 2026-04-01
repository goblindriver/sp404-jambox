#!/usr/bin/env python3
"""
Two-way sync for Bank A (the user's creative bank).

When the SD card is mounted:
1. PULL: Save any Bank A samples FROM the card into the gold library
   - These are loops/patterns the user has edited on-device
   - Saved to ~/Music/SP404-Sample-Library/_GOLD/ with timestamps
2. PUSH: Load any new resampling candidates TO Bank A on the card
   - Sources from Downloads or a designated "resample" folder

Usage:
    python scripts/sync_bank_a.py pull      # save Bank A from card to library
    python scripts/sync_bank_a.py push      # load new content to Bank A
    python scripts/sync_bank_a.py sync      # both directions
"""
import os, sys, shutil, time, argparse, struct

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

SD_CARD = "/Volumes/SP-404SX"
SD_SMPL = os.path.join(SD_CARD, "ROLAND", "SP-404SX", "SMPL")

LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
GOLD_DIR = os.path.join(LIBRARY, "_GOLD")
GOLD_BANK_A = os.path.join(GOLD_DIR, "Bank-A")


def is_card_mounted():
    return os.path.isdir(SD_SMPL)


def get_bank_a_files():
    """Find all Bank A sample files on the SD card."""
    files = []
    if not is_card_mounted():
        return files
    for f in os.listdir(SD_SMPL):
        if f.startswith('A') and f.endswith('.WAV'):
            files.append(os.path.join(SD_SMPL, f))
    return sorted(files)


def pull_bank_a():
    """Save Bank A samples from SD card to gold library."""
    if not is_card_mounted():
        print("SD card not mounted at /Volumes/SP-404SX")
        return 0

    files = get_bank_a_files()
    if not files:
        print("No Bank A samples found on card.")
        return 0

    # Create timestamped session folder
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    session_dir = os.path.join(GOLD_BANK_A, f"session-{timestamp}")
    os.makedirs(session_dir, exist_ok=True)

    saved = 0
    for filepath in files:
        fname = os.path.basename(filepath)
        pad_num = fname[1:8].lstrip('0') or '0'
        dest = os.path.join(session_dir, f"A-pad{pad_num}_{fname}")

        # Check if file has actual audio (not just silence/empty)
        size = os.path.getsize(filepath)
        if size < 600:  # 512 header + minimal data
            print(f"  Skip {fname} (too small, likely empty)")
            continue

        shutil.copy2(filepath, dest)
        size_kb = size / 1024
        print(f"  Saved: {fname} ({size_kb:.0f}KB) → {os.path.basename(dest)}")
        saved += 1

    if saved:
        print(f"\n  {saved} samples saved to: {session_dir}")

        # Also copy to flat "latest" folder for easy access
        latest_dir = os.path.join(GOLD_BANK_A, "latest")
        if os.path.exists(latest_dir):
            shutil.rmtree(latest_dir)
        shutil.copytree(session_dir, latest_dir)
        print(f"  Latest copies: {latest_dir}")
    else:
        # Clean up empty session dir
        os.rmdir(session_dir)
        print("  No samples to save (all empty/too small).")

    return saved


def push_to_bank_a(source_files):
    """Load samples onto Bank A on the SD card."""
    if not is_card_mounted():
        print("SD card not mounted at /Volumes/SP-404SX")
        return 0

    from wav_utils import convert_and_tag

    loaded = 0
    for pad_num, source in enumerate(source_files[:12], start=1):
        sp404_name = f"A{pad_num:07d}.WAV"
        dest = os.path.join(SD_SMPL, sp404_name)

        print(f"  Pad {pad_num}: {os.path.basename(source)}")
        if convert_and_tag(source, dest, 'A', pad_num):
            loaded += 1
        else:
            print(f"    Conversion failed")

    print(f"\n  {loaded} samples loaded to Bank A")
    return loaded


def main():
    parser = argparse.ArgumentParser(description='Sync Bank A between SP-404 and library')
    parser.add_argument('action', choices=['pull', 'push', 'sync', 'status'],
                       help='pull=save from card, push=load to card, sync=both, status=show what\'s there')
    args = parser.parse_args()

    if args.action == 'status':
        if not is_card_mounted():
            print("SD card not mounted.")
            return

        files = get_bank_a_files()
        print(f"Bank A on card: {len(files)} samples")
        for f in files:
            size = os.path.getsize(f) / 1024
            print(f"  {os.path.basename(f)} ({size:.0f}KB)")

        # Show gold library
        if os.path.exists(GOLD_BANK_A):
            sessions = [d for d in os.listdir(GOLD_BANK_A) if d.startswith('session-')]
            print(f"\nGold library: {len(sessions)} saved sessions")
            for s in sorted(sessions)[-3:]:
                files_in = os.listdir(os.path.join(GOLD_BANK_A, s))
                print(f"  {s}: {len(files_in)} files")

    elif args.action == 'pull':
        print("=== Pulling Bank A from card → Gold Library ===")
        pull_bank_a()

    elif args.action == 'push':
        print("=== Push to Bank A not yet configured ===")
        print("Add source files to push in future implementation.")

    elif args.action == 'sync':
        print("=== Syncing Bank A ===")
        print("\n--- Pull (card → library) ---")
        pull_bank_a()
        print("\n--- Push would go here ---")


if __name__ == '__main__':
    main()
