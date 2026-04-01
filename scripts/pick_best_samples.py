#!/usr/bin/env python3
"""
Pick the best downloaded samples for each SP-404 bank and prepare them.
Bank layout:
  A-B: Empty (user)
  C: Lo-fi Hip-Hop (88 bpm) - pads 1-4 drum hits, 5-12 loops
  D: Witch House (70 bpm) - dark, slow, heavy
  E: Nu-Rave (130 bpm) - high energy electronic
  F: Electroclash (120 bpm) - dirty synths, beats
  G: Funk & Horns (105 bpm) - groovy, live feel
  H: IDM (140 bpm) - glitchy, complex
  I: Ambient (80 bpm) - textural, atmospheric
  J: Utility/FX (120 bpm) - transitions, tools
"""
import os, glob, subprocess, shutil, random, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wav_utils import convert_and_tag

SRC = os.path.expanduser("~/Music/SP404-Sample-Library/_RAW-DOWNLOADS")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
CARD = os.path.join(REPO_DIR, "sd-card-template", "ROLAND", "SP-404SX", "SMPL")
STAGING = os.path.join(REPO_DIR, "_CARD_STAGING")
os.makedirs(STAGING, exist_ok=True)

def get_wav_info(path):
    """Get duration and sample rate of a WAV file"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', path],
            capture_output=True, text=True, timeout=5
        )
        import json
        data = json.loads(result.stdout)
        duration = float(data.get('format', {}).get('duration', 0))
        streams = data.get('streams', [{}])
        sr = int(streams[0].get('sample_rate', 0)) if streams else 0
        channels = int(streams[0].get('channels', 0)) if streams else 0
        bits = int(streams[0].get('bits_per_sample', 0)) if streams else 0
        return {'duration': duration, 'sr': sr, 'channels': channels, 'bits': bits}
    except:
        return None

def convert_for_sp404(src, dst):
    """Convert any WAV to SP-404 compatible format: 16-bit, 44.1kHz, mono"""
    subprocess.run([
        'ffmpeg', '-y', '-i', src,
        '-ar', '44100', '-ac', '1', '-sample_fmt', 's16', '-c:a', 'pcm_s16le',
        dst
    ], capture_output=True, timeout=30)
    return os.path.exists(dst)

def find_wavs(base_path, pattern="**/*.wav"):
    """Find all WAV files recursively"""
    results = glob.glob(os.path.join(base_path, pattern), recursive=True)
    # Filter out __MACOSX junk
    return [r for r in results if '__MACOSX' not in r]

# ========================================
# BANK C: Lo-fi Hip-Hop (88 bpm)
# ========================================
print("=== BANK C: Lo-fi Hip-Hop ===")
bank_c = {}

# Pad 1-4: Drum hits from hip-hop essentials
hh_drums = os.path.join(SRC, "hiphop-essentials/Hip-Hop Essentials/Drum Hits")
kicks = sorted(find_wavs(hh_drums, "Kcks/*.wav"))
snares = sorted(find_wavs(hh_drums, "Snrs/*.wav"))
hats = sorted(find_wavs(hh_drums, "Hats/*.wav"))

if kicks: bank_c[1] = kicks[0]  # Kick
if snares: bank_c[2] = snares[0]  # Snare
if hats: bank_c[3] = hats[0]  # Hat
claps = find_wavs(hh_drums, "Claps/*.wav")
if claps: bank_c[4] = claps[0]  # Clap

# Pad 5-12: Lo-fi loops
lofi_drums = sorted(find_wavs(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/Lo-Fi DrumLoops")))
lofi_kits = sorted(find_wavs(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/ConstructionKits")))

# Pick drum loops around ~90bpm (kit 03 is 90bpm, kit 01 is 100bpm)
kit90 = [f for f in lofi_kits if '03(90)' in f]
kit100 = [f for f in lofi_kits if '01(100)' in f]
kit70 = [f for f in lofi_kits if '05(70)' in f]

# Bass from lofi multisample
lofi_bass = sorted(find_wavs(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/BonusMultiSamples/Bass01")))
lofi_lead = sorted(find_wavs(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/BonusMultiSamples/Lead01")))

if lofi_drums: bank_c[5] = lofi_drums[0]  # Lo-fi drum loop 1
if len(lofi_drums) > 1: bank_c[6] = lofi_drums[1]  # Lo-fi drum loop 2
# Pick bass and melodic from construction kits
bass_90 = [f for f in kit90 if 'bass' in f.lower() or 'Bass' in f]
keys_90 = [f for f in kit90 if 'key' in f.lower() or 'synth' in f.lower() or 'pad' in f.lower()]
if bass_90: bank_c[7] = bass_90[0]
elif lofi_bass: bank_c[7] = lofi_bass[len(lofi_bass)//2]  # Middle C-ish
if keys_90: bank_c[8] = keys_90[0]
elif lofi_lead: bank_c[8] = lofi_lead[len(lofi_lead)//2]
# More from construction kits - grab variety
other_90 = [f for f in kit90 if f not in bass_90 and f not in keys_90]
if other_90: bank_c[9] = other_90[0]
if len(other_90) > 1: bank_c[10] = other_90[1]
# Lo-fi FX
lofi_fx = sorted(find_wavs(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/SoundFX")))
if lofi_fx: bank_c[11] = lofi_fx[0]
if len(lofi_fx) > 1: bank_c[12] = lofi_fx[1]

for pad, path in bank_c.items():
    print(f"  Pad {pad}: {os.path.basename(path)}")

# ========================================
# BANK D: Witch House / Dark (70 bpm)
# ========================================
print("\n=== BANK D: Witch House / Dark ===")
bank_d = {}

# Use kit 05(70) from lo-fi pack which is slow and dark
# Plus some 80s synth dark pads
dark_kit = [f for f in lofi_kits if '05(70)' in f]
dark_drums = [f for f in dark_kit if 'drum' in f.lower() or 'beat' in f.lower()]
dark_bass = [f for f in dark_kit if 'bass' in f.lower()]
dark_other = [f for f in dark_kit if f not in dark_drums and f not in dark_bass]

# Drum hits - use something heavy
hh_perc = find_wavs(hh_drums, "Percussion/*.wav")
oberheim = find_wavs(hh_drums, "Oberheim DX/*.wav")

if oberheim: bank_d[1] = oberheim[0]  # Heavy kick
if len(oberheim) > 1: bank_d[2] = oberheim[1]  # Snare
if len(oberheim) > 2: bank_d[3] = oberheim[2]  # Hat
if len(oberheim) > 3: bank_d[4] = oberheim[3]  # Perc

# 80s synth pads (dark, long)
synth_pads = sorted(find_wavs(os.path.join(SRC, "80s-synths/80s Synths Samples/Polys and Pads")))
synth_bass = sorted(find_wavs(os.path.join(SRC, "80s-synths/80s Synths Samples/Bass Loops")))

if dark_drums: bank_d[5] = dark_drums[0]
if len(dark_drums) > 1: bank_d[6] = dark_drums[1] 
elif len(lofi_drums) > 2: bank_d[6] = lofi_drums[2]
if dark_bass: bank_d[7] = dark_bass[0]
elif synth_bass: bank_d[7] = synth_bass[0]
if synth_pads: bank_d[8] = synth_pads[0]
if len(synth_pads) > 10: bank_d[9] = synth_pads[10]
if dark_other: bank_d[10] = dark_other[0]
if len(dark_other) > 1: bank_d[11] = dark_other[1]
if len(lofi_fx) > 2: bank_d[12] = lofi_fx[2]

for pad, path in bank_d.items():
    print(f"  Pad {pad}: {os.path.basename(path)}")

# ========================================
# BANK E: Nu-Rave (130 bpm)
# ========================================
print("\n=== BANK E: Nu-Rave ===")
bank_e = {}

# Synth percussion for electronic drums
sp_loops = sorted(find_wavs(os.path.join(SRC, "synth-percussion")))
# 80s synth arps and leads for rave energy
synth_arps = sorted(find_wavs(os.path.join(SRC, "80s-synths/80s Synths Samples/Arps and Leads")))
# Filter for ~130bpm if possible
arps_130 = [f for f in synth_arps if '130' in f]
if not arps_130: arps_130 = [f for f in synth_arps if '120' in f or '140' in f]
if not arps_130: arps_130 = synth_arps

# Drum kit electro hits
electro_kits = find_wavs(os.path.join(SRC, "drum-samples/musicradar-drum-samples/Drum Kits/Kit 5 - Electro"))
if not electro_kits:
    electro_kits = find_wavs(os.path.join(SRC, "drum-samples/musicradar-drum-samples/Drum Kits/Kit 4 - Electro"))

if electro_kits and len(electro_kits) >= 4:
    bank_e[1] = electro_kits[0]
    bank_e[2] = electro_kits[1]
    bank_e[3] = electro_kits[2]
    bank_e[4] = electro_kits[3]

if sp_loops: bank_e[5] = sp_loops[0]
if len(sp_loops) > 1: bank_e[6] = sp_loops[1]
if arps_130: bank_e[7] = arps_130[0]
if len(arps_130) > 1: bank_e[8] = arps_130[1]
pads_130 = [f for f in synth_pads if '130' in f]
if not pads_130: pads_130 = [f for f in synth_pads if '120' in f]
if pads_130: bank_e[9] = pads_130[0]
if len(pads_130) > 1: bank_e[10] = pads_130[1]
if len(sp_loops) > 2: bank_e[11] = sp_loops[2]
if len(sp_loops) > 3: bank_e[12] = sp_loops[3]

for pad, path in bank_e.items():
    print(f"  Pad {pad}: {os.path.basename(path)}")

# ========================================
# BANK F: Electroclash (120 bpm)
# ========================================
print("\n=== BANK F: Electroclash ===")
bank_f = {}

# Hip-hop beats at ~120 work for electroclash
hh_beats = sorted(find_wavs(os.path.join(SRC, "hiphop-essentials/Hip-Hop Essentials/Beats")))
hh_loops = sorted(find_wavs(os.path.join(SRC, "hiphop-essentials/Hip-Hop Essentials/Loops")))
hh_shots = sorted(find_wavs(os.path.join(SRC, "hiphop-essentials/Hip-Hop Essentials/Single Shots")))

# Vinyl kit drums
vinyl_kit = find_wavs(os.path.join(SRC, "drum-samples/musicradar-drum-samples/Drum Kits/Kit 10 - Vinyl"))
if vinyl_kit and len(vinyl_kit) >= 4:
    bank_f[1] = vinyl_kit[0]
    bank_f[2] = vinyl_kit[1]
    bank_f[3] = vinyl_kit[2]
    bank_f[4] = vinyl_kit[3]

# 80s synth bass loops at 120
bass_120 = [f for f in synth_bass if '120' in f]
arps_120 = [f for f in synth_arps if '120' in f]
pads_120 = [f for f in synth_pads if '120' in f]

if hh_beats: bank_f[5] = hh_beats[0]
if len(hh_beats) > 1: bank_f[6] = hh_beats[1]
if bass_120: bank_f[7] = bass_120[0]
elif synth_bass: bank_f[7] = synth_bass[len(synth_bass)//3]
if arps_120: bank_f[8] = arps_120[0]
if pads_120: bank_f[9] = pads_120[0]
if hh_shots: bank_f[10] = hh_shots[0]
if len(hh_shots) > 1: bank_f[11] = hh_shots[1]
if hh_loops: bank_f[12] = hh_loops[0]

for pad, path in bank_f.items():
    print(f"  Pad {pad}: {os.path.basename(path)}")

# ========================================
# BANK G: Funk & Horns (105 bpm)
# ========================================
print("\n=== BANK G: Funk & Horns ===")
bank_g = {}

funk_base = os.path.join(SRC, "funk-samples/musicradar-funk-samples")
sf_base = os.path.join(SRC, "soul-funk-samples/musicradar-soul-funk-samples")

# Drum hits from drum pack
drum_base = os.path.join(SRC, "drum-samples/musicradar-drum-samples")
all_kicks = sorted(find_wavs(drum_base, "Assorted Hits/Kicks/*.wav"))
all_snares = sorted(find_wavs(drum_base, "Assorted Hits/Snares/*.wav"))
all_hats = sorted(find_wavs(drum_base, "Assorted Hits/Hi Hats/*.wav"))

if all_kicks: bank_g[1] = all_kicks[len(all_kicks)//2]  # Pick a mid-range kick
if all_snares: bank_g[2] = all_snares[0]
if all_hats: bank_g[3] = all_hats[0]
cymbals = sorted(find_wavs(drum_base, "Assorted Hits/Cymbals/*.wav"))
if cymbals: bank_g[4] = cymbals[0]

# Funk loops at ~110bpm (closest to 105)
funk_110 = os.path.join(funk_base, "110bpm loops")
funk_bass = sorted(find_wavs(funk_110, "Bass/*.wav"))
funk_guitar = sorted(find_wavs(funk_110, "Guitar/*.wav"))
funk_organ = sorted(find_wavs(funk_110, "Organ/*.wav"))
funk_clav = sorted(find_wavs(funk_110, "Clavinet/*.wav"))
funk_piano = sorted(find_wavs(funk_110, "Piano/*.wav"))
funk_ep = sorted(find_wavs(funk_110, "Electric Piano/*.wav"))

# Soul-funk beats at 110
sf_110 = os.path.join(sf_base, "soul-n-funk-110bpm")
sf_beats = sorted(find_wavs(sf_110, "Beats 110bpm/*.wav"))

if sf_beats: bank_g[5] = sf_beats[0]  # Funk drum loop
if len(sf_beats) > 1: bank_g[6] = sf_beats[1]  # Another funk beat
if funk_bass: bank_g[7] = funk_bass[0]  # Funk bass loop
if funk_guitar: bank_g[8] = funk_guitar[0]  # Funk guitar loop
if funk_organ: bank_g[9] = funk_organ[0]  # Organ loop
if funk_clav: bank_g[10] = funk_clav[0]  # Clavinet loop
if funk_ep: bank_g[11] = funk_ep[0]  # Electric piano
if funk_piano: bank_g[12] = funk_piano[0]  # Piano

for pad, path in bank_g.items():
    print(f"  Pad {pad}: {os.path.basename(path)}")

# ========================================
# BANK H: IDM (140 bpm)
# ========================================
print("\n=== BANK H: IDM ===")
bank_h = {}

idm_base = os.path.join(SRC, "idm-samples/musicradar-idm-samples")
# Kit 03 is 140bpm - perfect match
idm_140_base = sorted(find_wavs(os.path.join(idm_base, "Kit 03 140bpm/Base Kit")))
idm_140_alt = sorted(find_wavs(os.path.join(idm_base, "Kit 03 140bpm/Alternate")))
# Kit 01 is 160bpm - also good
idm_160_base = sorted(find_wavs(os.path.join(idm_base, "Kit 01 160bpm/Base Kit")))

if idm_140_base and len(idm_140_base) >= 4:
    bank_h[1] = idm_140_base[0]
    bank_h[2] = idm_140_base[1]
    bank_h[3] = idm_140_base[2]
    bank_h[4] = idm_140_base[3]

# More IDM loops
all_idm = idm_140_base + idm_140_alt
for i, pad in enumerate(range(5, 13)):
    idx = i + 4  # Start after the drum hits
    if idx < len(all_idm):
        bank_h[pad] = all_idm[idx]

for pad, path in bank_h.items():
    print(f"  Pad {pad}: {os.path.basename(path)}")

# ========================================
# BANK I: Ambient (80 bpm)
# ========================================
print("\n=== BANK I: Ambient ===")
bank_i = {}

# 80s synth pads - pick the longest, most atmospheric ones
# Filter for slower tempos
slow_pads = [f for f in synth_pads if '80bpm' in f or '90bpm' in f or '100bpm' in f]
if not slow_pads: slow_pads = synth_pads[:20]

# Lo-fi FX and textures
lofi_all_fx = sorted(find_wavs(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/SoundFX")))

# Synth perc for gentle rhythms
wavedrum = sorted(find_wavs(os.path.join(SRC, "synth-percussion/musicradar-synth-percussion-samples/WaveDrum_Loops")))

if all_hats and len(all_hats) > 5: bank_i[1] = all_hats[5]  # Soft hat
if hh_perc: bank_i[2] = hh_perc[0]
if wavedrum: bank_i[3] = wavedrum[0]  # Gentle wave drum
if len(wavedrum) > 1: bank_i[4] = wavedrum[1]

if slow_pads: bank_i[5] = slow_pads[0]
if len(slow_pads) > 1: bank_i[6] = slow_pads[1]
if len(slow_pads) > 2: bank_i[7] = slow_pads[2]
if len(slow_pads) > 3: bank_i[8] = slow_pads[3]
if lofi_all_fx: bank_i[9] = lofi_all_fx[0]
if len(lofi_all_fx) > 1: bank_i[10] = lofi_all_fx[1]
if len(slow_pads) > 4: bank_i[11] = slow_pads[4]
if len(slow_pads) > 5: bank_i[12] = slow_pads[5]

for pad, path in bank_i.items():
    print(f"  Pad {pad}: {os.path.basename(path)}")

# ========================================
# BANK J: Utility/FX
# ========================================
print("\n=== BANK J: Utility/FX ===")
bank_j = {}

# Grab a mix of FX, textures, and utility sounds
misc_perc = sorted(find_wavs(os.path.join(SRC, "synth-percussion/musicradar-synth-percussion-samples/Misc_Synth_Perc_Loops")))
vermona = sorted(find_wavs(os.path.join(SRC, "synth-percussion/musicradar-synth-percussion-samples/Vermona_DRM1_MK3_Loops")))

if lofi_all_fx and len(lofi_all_fx) > 2: bank_j[1] = lofi_all_fx[2]
if len(lofi_all_fx) > 3: bank_j[2] = lofi_all_fx[3]
if misc_perc: bank_j[3] = misc_perc[0]
if len(misc_perc) > 1: bank_j[4] = misc_perc[1]
if vermona: bank_j[5] = vermona[0]
if len(vermona) > 1: bank_j[6] = vermona[1]
if hh_shots and len(hh_shots) > 2: bank_j[7] = hh_shots[2]
if len(hh_shots) > 3: bank_j[8] = hh_shots[3]
if len(lofi_all_fx) > 4: bank_j[9] = lofi_all_fx[4]
if len(misc_perc) > 2: bank_j[10] = misc_perc[2]
if len(vermona) > 2: bank_j[11] = vermona[2]
if len(lofi_all_fx) > 5: bank_j[12] = lofi_all_fx[5]

for pad, path in bank_j.items():
    print(f"  Pad {pad}: {os.path.basename(path)}")

# ========================================
# Convert and stage all files
# ========================================
print("\n=== CONVERTING AND STAGING ===")
all_banks = {'C': bank_c, 'D': bank_d, 'E': bank_e, 'F': bank_f, 
             'G': bank_g, 'H': bank_h, 'I': bank_i, 'J': bank_j}

converted = 0
failed = 0
for bank_letter, bank_map in all_banks.items():
    for pad_num, src_path in bank_map.items():
        sp404_name = f"{bank_letter}{pad_num:07d}.WAV"
        dst_path = os.path.join(STAGING, sp404_name)
        if convert_and_tag(src_path, dst_path, bank_letter, pad_num):
            converted += 1
        else:
            failed += 1
            print(f"  FAILED: {sp404_name} from {os.path.basename(src_path)}")

print(f"\nConverted: {converted}, Failed: {failed}")
print(f"Staged in: {STAGING}")
