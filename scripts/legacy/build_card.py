import os
import shutil

BASE = '/sessions/happy-intelligent-edison/SP-404A-Samples/_BANK-STAGING'
CARD = '/sessions/happy-intelligent-edison/mnt/SP-404SX'
SMPL_DIR = os.path.join(CARD, 'ROLAND', 'SP-404SX', 'SMPL')

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

# SP-404SX naming: X0000001.WAV through X0000012.WAV
# where X is the bank letter (A-J) and the number is the pad (1-12)

# First, remove existing sample WAVs (but preserve .BIN files)
print("Clearing existing samples from card...")
for f in os.listdir(SMPL_DIR):
    if f.endswith('.WAV'):
        os.remove(os.path.join(SMPL_DIR, f))
        
print(f"Cleared. Remaining files: {os.listdir(SMPL_DIR)}")

# Now copy and rename our synthesized samples
total_copied = 0
for bank_letter, folder_name in bank_map.items():
    src_dir = os.path.join(BASE, folder_name)
    if not os.path.exists(src_dir):
        print(f"WARNING: {src_dir} not found, skipping bank {bank_letter}")
        continue
    
    # Get sorted list of WAV files
    wavs = sorted([f for f in os.listdir(src_dir) if f.endswith('.wav')])
    
    print(f"\nBank {bank_letter} ({folder_name}): {len(wavs)} samples")
    
    for i, wav_file in enumerate(wavs, 1):
        if i > 12:
            print(f"  WARNING: More than 12 samples, skipping {wav_file}")
            continue
        
        # SP-404SX naming format: X0000001.WAV
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
