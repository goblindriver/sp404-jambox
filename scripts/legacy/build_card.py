import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)
REPO_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings


SETTINGS = load_settings(REPO_DIR)
BASE = os.path.join(REPO_DIR, '_BANK-STAGING')
SMPL_DIR = SETTINGS["SD_SMPL_DIR"]

# Bank letter to staging folder mapping
# Banks A and B are left empty (user requested)
# Banks C-J get our synthesized content
bank_map = {
    'C': 'C-LofiHipHop',
    'D': 'D-WitchHouse',
    'E': 'E-NuRave',
    'F': 'F-Electroclash',
    'G': 'G-FunkHorns',
    'H': 'H-IDM',
    'I': 'I-AmbientTextural',
    'J': 'J-UtilityFX',
}


def main():
    if not os.path.isdir(SMPL_DIR):
        print(f"ERROR: SD card sample directory not found at {SMPL_DIR}")
        return 1
    if not os.path.isdir(BASE):
        print(f"ERROR: Staging directory not found at {BASE}")
        return 1

    print("Clearing existing samples from card...")
    removed = 0
    for f in os.listdir(SMPL_DIR):
        if f.upper().endswith('.WAV'):
            os.remove(os.path.join(SMPL_DIR, f))
            removed += 1
    print(f"Cleared {removed} samples.")

    total_copied = 0
    for bank_letter, folder_name in bank_map.items():
        src_dir = os.path.join(BASE, folder_name)
        if not os.path.isdir(src_dir):
            print(f"WARNING: {src_dir} not found, skipping bank {bank_letter}")
            continue

        wavs = sorted([f for f in os.listdir(src_dir) if f.lower().endswith('.wav')])

        print(f"\nBank {bank_letter} ({folder_name}): {len(wavs)} samples")

        for i, wav_file in enumerate(wavs, 1):
            if i > 12:
                print(f"  WARNING: More than 12 samples, skipping {wav_file}")
                continue

            dest_name = f"{bank_letter}{i:07d}.WAV"
            src_path = os.path.join(src_dir, wav_file)
            dest_path = os.path.join(SMPL_DIR, dest_name)

            shutil.copy2(src_path, dest_path)
            print(f"  {wav_file} -> {dest_name}")
            total_copied += 1

    print(f"\n=== TOTAL: {total_copied} samples copied to card ===")
    print(f"\nFinal SMPL directory listing:")
    for f in sorted(os.listdir(SMPL_DIR)):
        size = os.path.getsize(os.path.join(SMPL_DIR, f))
        print(f"  {f}  ({size:,} bytes)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
