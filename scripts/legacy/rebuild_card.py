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

# File selection per bank: pads 1-4 = drum one-shots, pads 5-12 = loops
# For each bank, map pad number -> filename
bank_files = {
    'C': {
        1: '01_kick.wav', 2: '02_snare.wav', 3: '03_hat_closed.wav', 4: '04_shaker.wav',
        5: '05_bass_loop.wav', 6: '06_keys_loop.wav', 7: '07_pad_loop.wav', 8: '08_melody_loop.wav',
        9: '09_drum_loop1.wav', 10: '10_drum_loop2.wav', 11: '11_vinyl_loop.wav', 12: '12_ambient_loop.wav',
    },
    'D': {
        1: '01_808_kick.wav', 2: '02_dark_clap.wav', 3: '03_metal_hat.wav', 4: '04_industrial_perc.wav',
        5: '05_sub_bass_loop.wav', 6: '06_dark_riff_loop.wav', 7: '07_eerie_pad_loop.wav', 8: '08_dark_vocal_loop.wav',
        9: '09_drum_loop1.wav', 10: '10_drum_loop2.wav', 11: '11_dark_texture_loop.wav', 12: '12_drone_loop.wav',
    },
    'E': {
        1: '01_punchy_kick.wav', 2: '02_snappy_snare.wav', 3: '03_open_hat.wav', 4: '04_rave_clap.wav',
        5: '05_acid_bass_loop.wav', 6: '06_hoover_loop.wav', 7: '07_stab_loop.wav', 8: '08_supersaw_loop.wav',
        9: '09_drum_loop1.wav', 10: '10_drum_loop2.wav', 11: '11_arp_loop.wav', 12: '12_siren_loop.wav',
    },
    'F': {
        1: '01_808_kick.wav', 2: '02_clap.wav', 3: '03_tight_hat.wav', 4: '04_cowbell.wav',
        5: '05_dirty_bass_loop.wav', 6: '06_analog_lead_loop.wav', 7: '07_robot_vocal_loop.wav', 8: '08_stab_loop.wav',
        9: '09_drum_loop1.wav', 10: '10_drum_loop2.wav', 11: '11_sweep_loop.wav', 12: '12_static_loop.wav',
    },
    'G': {
        1: '01_funk_kick.wav', 2: '02_funk_snare.wav', 3: '03_funk_hat.wav', 4: '04_conga.wav',
        5: '05_funk_bass_loop.wav', 6: '06_horn_stab_loop.wav', 7: '07_horn_phrase_loop.wav', 8: '08_clavinet_loop.wav',
        9: '09_funk_loop1.wav', 10: '10_funk_loop2.wav', 11: '11_wah_guitar_loop.wav', 12: '12_scratch_loop.wav',
    },
    'H': {
        1: '01_glitch_kick.wav', 2: '02_broken_snare.wav', 3: '03_metal_hat.wav', 4: '04_glitch_perc.wav',
        5: '05_morph_bass_loop.wav', 6: '06_fm_synth_loop.wav', 7: '07_texture_loop.wav', 8: '08_granular_loop.wav',
        9: '09_idm_loop1.wav', 10: '10_idm_loop2.wav', 11: '11_stutter_loop.wav', 12: '12_drone_loop.wav',
    },
    'I': {
        1: '01_warm_pad.wav', 2: '02_deep_drone.wav', 3: '03_rain.wav', 4: '04_bell.wav',
        5: '05_warm_pad_loop.wav', 6: '06_drone_loop.wav', 7: '07_rain_loop.wav', 8: '08_bells_loop.wav',
        9: '09_atmo_loop.wav', 10: '10_ambient_drum_loop.wav', 11: '11_shimmer_loop.wav', 12: '12_glass_pad_loop.wav',
    },
    'J': {
        1: '01_riser.wav', 2: '02_down_sweep.wav', 3: '03_impact.wav', 4: '04_reverse_cymbal.wav',
        5: '05_vinyl_loop.wav', 6: '06_tape_hiss_loop.wav', 7: '07_glitch_loop.wav', 8: '08_sub_pulse_loop.wav',
        9: '09_riser_loop.wav', 10: '10_swoosh_loop.wav', 11: '11_click_loop.wav', 12: '12_room_loop.wav',
    },
}

# Bank letter -> staging folder name
folder_map = {
    'C': 'C-LofiHipHop', 'D': 'D-WitchHouse', 'E': 'E-NuRave', 'F': 'F-Electroclash',
    'G': 'G-FunkHorns', 'H': 'H-IDM', 'I': 'I-AmbientTextural', 'J': 'J-UtilityFX',
}

def main():
    if not os.path.isdir(SMPL_DIR):
        print(f"ERROR: SD card sample directory not found at {SMPL_DIR}")
        return 1
    if not os.path.isdir(BASE):
        print(f"ERROR: Staging directory not found at {BASE}")
        return 1

    missing_sources = []
    for bank_letter in 'CDEFGHIJ':
        folder_name = folder_map[bank_letter]
        src_dir = os.path.join(BASE, folder_name)
        if not os.path.isdir(src_dir):
            missing_sources.append(f"  MISSING DIR: {src_dir}")
            continue
        for filename in bank_files[bank_letter].values():
            src_path = os.path.join(src_dir, filename)
            if not os.path.exists(src_path):
                missing_sources.append(f"  MISSING: {src_path}")

    if missing_sources:
        print("ERROR: Refusing to clear card because some staging files are missing:")
        for entry in missing_sources:
            print(entry)
        return 1

    print("Clearing existing WAV files from card...")
    removed = 0
    for f in os.listdir(SMPL_DIR):
        if f.upper().endswith('.WAV'):
            os.remove(os.path.join(SMPL_DIR, f))
            removed += 1
    print(f"  Removed {removed} files")

    total = 0
    for bank_letter in 'CDEFGHIJ':
        folder_name = folder_map[bank_letter]
        src_dir = os.path.join(BASE, folder_name)
        files = bank_files[bank_letter]

        print(f"\nBank {bank_letter} ({folder_name}):")
        for pad_num, filename in sorted(files.items()):
            src_path = os.path.join(src_dir, filename)
            dest_name = f"{bank_letter}{pad_num:07d}.WAV"
            dest_path = os.path.join(SMPL_DIR, dest_name)

            shutil.copy2(src_path, dest_path)
            size_kb = os.path.getsize(dest_path) / 1024
            print(f"  ✓ Pad {pad_num:2d}: {filename:30s} -> {dest_name} ({size_kb:.0f}KB)")
            total += 1

    print(f"\n{'='*60}")
    print(f"TOTAL: {total} files copied to card")
    print("NO ERRORS - all files found and copied")

    total_size = sum(os.path.getsize(os.path.join(SMPL_DIR, f)) for f in os.listdir(SMPL_DIR))
    print(f"TOTAL CARD SIZE: {total_size/1024/1024:.1f} MB")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
