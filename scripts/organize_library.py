import shutil, os, glob

LIB = os.path.expanduser("~/Music/SP404-Sample-Library")
SRC = os.path.join(LIB, "_RAW-DOWNLOADS")
RAW = SRC  # Raw downloads are already in the library

# Copy entire unzipped packs into _RAW-DOWNLOADS for archive
for pack_dir in sorted(glob.glob(os.path.join(SRC, "*"))):
    name = os.path.basename(pack_dir)
    dest = os.path.join(RAW, name)
    if not os.path.exists(dest):
        shutil.copytree(pack_dir, dest, dirs_exist_ok=True)
        print(f"Archived: {name}")
    else:
        print(f"Already exists: {name}")

# Now organize into categories
counts = {}

def copy_wav(src, dest_folder, prefix=""):
    os.makedirs(dest_folder, exist_ok=True)
    fname = os.path.basename(src)
    if prefix:
        fname = f"{prefix}_{fname}"
    dest = os.path.join(dest_folder, fname)
    if not os.path.exists(dest):
        shutil.copy2(src, dest)
        counts[dest_folder] = counts.get(dest_folder, 0) + 1

# === DRUMS ===
# Drum hits from drum-samples pack
drum_base = os.path.join(SRC, "drum-samples/musicradar-drum-samples")
for wav in glob.glob(os.path.join(drum_base, "Assorted Hits/Kicks/*.wav")):
    copy_wav(wav, os.path.join(LIB, "Drums/Kicks"), "MR")
for wav in glob.glob(os.path.join(drum_base, "Assorted Hits/Snares/*.wav")):
    copy_wav(wav, os.path.join(LIB, "Drums/Snares-Claps"), "MR")
for wav in glob.glob(os.path.join(drum_base, "Assorted Hits/Hi Hats/*.wav")):
    copy_wav(wav, os.path.join(LIB, "Drums/Hi-Hats"), "MR")
for wav in glob.glob(os.path.join(drum_base, "Assorted Hits/Cymbals/*.wav")):
    copy_wav(wav, os.path.join(LIB, "Drums/Percussion"), "MR-cymbal")

# Drum kits
for kit_dir in glob.glob(os.path.join(drum_base, "Drum Kits/*")):
    for wav in glob.glob(os.path.join(kit_dir, "*.wav")):
        fname = os.path.basename(wav).lower()
        if "kick" in fname or "bd" in fname:
            copy_wav(wav, os.path.join(LIB, "Drums/Kicks"), os.path.basename(kit_dir))
        elif "snare" in fname or "sd" in fname or "clap" in fname:
            copy_wav(wav, os.path.join(LIB, "Drums/Snares-Claps"), os.path.basename(kit_dir))
        elif "hat" in fname or "hh" in fname:
            copy_wav(wav, os.path.join(LIB, "Drums/Hi-Hats"), os.path.basename(kit_dir))
        else:
            copy_wav(wav, os.path.join(LIB, "Drums/Percussion"), os.path.basename(kit_dir))

# Hip-hop drum hits
hh_base = os.path.join(SRC, "hiphop-essentials/Hip-Hop Essentials")
for wav in glob.glob(os.path.join(hh_base, "Drum Hits/Kcks/*.wav")):
    copy_wav(wav, os.path.join(LIB, "Drums/Kicks"), "HH")
for wav in glob.glob(os.path.join(hh_base, "Drum Hits/Snrs/*.wav")):
    copy_wav(wav, os.path.join(LIB, "Drums/Snares-Claps"), "HH")
for wav in glob.glob(os.path.join(hh_base, "Drum Hits/Hats/*.wav")):
    copy_wav(wav, os.path.join(LIB, "Drums/Hi-Hats"), "HH")
for wav in glob.glob(os.path.join(hh_base, "Drum Hits/Cymbals/*.wav")):
    copy_wav(wav, os.path.join(LIB, "Drums/Percussion"), "HH-cymbal")
for d in ["Beatbox", "Oberheim DX", "Claps", "Percussion"]:
    for wav in glob.glob(os.path.join(hh_base, f"Drum Hits/{d}/*.wav")):
        copy_wav(wav, os.path.join(LIB, "Drums/Percussion"), f"HH-{d}")

# Drum loops from various packs
for wav in glob.glob(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/Lo-Fi DrumLoops/*.wav")):
    copy_wav(wav, os.path.join(LIB, "Drums/Drum-Loops"), "lofi")

# Hip-hop beats
for wav in glob.glob(os.path.join(hh_base, "Beats/**/*.wav"), recursive=True):
    copy_wav(wav, os.path.join(LIB, "Drums/Drum-Loops"), "HH")

# Synth percussion loops
for wav in glob.glob(os.path.join(SRC, "synth-percussion/**/*.wav"), recursive=True):
    copy_wav(wav, os.path.join(LIB, "Drums/Drum-Loops"), "synthperc")

# === MELODIC ===
# Funk bass, guitar, keys, organ loops
funk_base = os.path.join(SRC, "funk-samples/musicradar-funk-samples")
for bpm_dir in glob.glob(os.path.join(funk_base, "*bpm*")):
    bpm = os.path.basename(bpm_dir).replace(" loops", "")
    for wav in glob.glob(os.path.join(bpm_dir, "Bass/*.wav")):
        copy_wav(wav, os.path.join(LIB, "Melodic/Bass"), f"funk-{bpm}")
    for wav in glob.glob(os.path.join(bpm_dir, "Guitar/*.wav")):
        copy_wav(wav, os.path.join(LIB, "Melodic/Guitar"), f"funk-{bpm}")
    for wav in glob.glob(os.path.join(bpm_dir, "Piano/*.wav")):
        copy_wav(wav, os.path.join(LIB, "Melodic/Keys-Piano"), f"funk-{bpm}")
    for wav in glob.glob(os.path.join(bpm_dir, "Electric Piano/*.wav")):
        copy_wav(wav, os.path.join(LIB, "Melodic/Keys-Piano"), f"funk-{bpm}-ep")
    for wav in glob.glob(os.path.join(bpm_dir, "Organ/*.wav")):
        copy_wav(wav, os.path.join(LIB, "Melodic/Keys-Piano"), f"funk-{bpm}-organ")
    for wav in glob.glob(os.path.join(bpm_dir, "Clavinet/*.wav")):
        copy_wav(wav, os.path.join(LIB, "Melodic/Keys-Piano"), f"funk-{bpm}-clav")
    for wav in glob.glob(os.path.join(bpm_dir, "Monosynth/*.wav")):
        copy_wav(wav, os.path.join(LIB, "Melodic/Synths-Pads"), f"funk-{bpm}")

# Soul-funk loops
sf_base = os.path.join(SRC, "soul-funk-samples/musicradar-soul-funk-samples")
for bpm_dir in glob.glob(os.path.join(sf_base, "soul-n-funk-*")):
    bpm = os.path.basename(bpm_dir).replace("soul-n-funk-", "")
    for sub in glob.glob(os.path.join(bpm_dir, "*")):
        subname = os.path.basename(sub).lower()
        for wav in glob.glob(os.path.join(sub, "*.wav")):
            if "bass" in subname:
                copy_wav(wav, os.path.join(LIB, "Melodic/Bass"), f"soul-{bpm}")
            elif "guitar" in subname:
                copy_wav(wav, os.path.join(LIB, "Melodic/Guitar"), f"soul-{bpm}")
            elif "organ" in subname or "rhodes" in subname or "piano" in subname:
                copy_wav(wav, os.path.join(LIB, "Melodic/Keys-Piano"), f"soul-{bpm}")
            elif "beat" in subname or "drum" in subname:
                copy_wav(wav, os.path.join(LIB, "Drums/Drum-Loops"), f"soul-{bpm}")

# 80s synth pads and leads
synth_base = os.path.join(SRC, "80s-synths/80s Synths Samples")
for wav in glob.glob(os.path.join(synth_base, "Polys and Pads/**/*.wav"), recursive=True):
    copy_wav(wav, os.path.join(LIB, "Melodic/Synths-Pads"), "80s")
for wav in glob.glob(os.path.join(synth_base, "Arps and Leads/**/*.wav"), recursive=True):
    copy_wav(wav, os.path.join(LIB, "Melodic/Synths-Pads"), "80s-lead")
for wav in glob.glob(os.path.join(synth_base, "Bass Loops/**/*.wav"), recursive=True):
    copy_wav(wav, os.path.join(LIB, "Melodic/Bass"), "80s")

# Hip-hop loops and single shots
for wav in glob.glob(os.path.join(hh_base, "Loops/**/*.wav"), recursive=True):
    fname = os.path.basename(wav).lower()
    if "bass" in fname:
        copy_wav(wav, os.path.join(LIB, "Melodic/Bass"), "HH")
    elif "key" in fname or "piano" in fname or "rhodes" in fname:
        copy_wav(wav, os.path.join(LIB, "Melodic/Keys-Piano"), "HH")
    elif "synth" in fname or "pad" in fname:
        copy_wav(wav, os.path.join(LIB, "Melodic/Synths-Pads"), "HH")
    else:
        copy_wav(wav, os.path.join(LIB, "Loops/Instrument-Loops"), "HH")

for wav in glob.glob(os.path.join(hh_base, "Single Shots/**/*.wav"), recursive=True):
    copy_wav(wav, os.path.join(LIB, "SFX/Stabs-Hits"), "HH")

# Lo-fi construction kits and FX
for wav in glob.glob(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/ConstructionKits/**/*.wav"), recursive=True):
    copy_wav(wav, os.path.join(LIB, "Loops/Instrument-Loops"), "lofi")
for wav in glob.glob(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/SoundFX/*.wav")):
    copy_wav(wav, os.path.join(LIB, "SFX/Stabs-Hits"), "lofi")
for wav in glob.glob(os.path.join(SRC, "lofi-samples/musicradar-lofi-samples/BonusMultiSamples/**/*.wav"), recursive=True):
    fname = os.path.basename(wav).lower()
    if "bass" in fname or "Bass" in os.path.dirname(wav):
        copy_wav(wav, os.path.join(LIB, "Melodic/Bass"), "lofi-multi")
    else:
        copy_wav(wav, os.path.join(LIB, "Melodic/Synths-Pads"), "lofi-multi")

# === IDM ===
idm_base = os.path.join(SRC, "idm-samples/musicradar-idm-samples")
for kit_dir in glob.glob(os.path.join(idm_base, "Kit*")):
    kit_name = os.path.basename(kit_dir).replace(" ", "-")
    for wav in glob.glob(os.path.join(kit_dir, "**/*.wav"), recursive=True):
        fname = os.path.basename(wav).lower()
        if "drum" in fname or "beat" in fname or "loop" in fname:
            copy_wav(wav, os.path.join(LIB, "Drums/Drum-Loops"), f"IDM-{kit_name}")
        elif "bass" in fname:
            copy_wav(wav, os.path.join(LIB, "Melodic/Bass"), f"IDM-{kit_name}")
        elif "pad" in fname or "synth" in fname or "atmos" in fname:
            copy_wav(wav, os.path.join(LIB, "Melodic/Synths-Pads"), f"IDM-{kit_name}")
        else:
            copy_wav(wav, os.path.join(LIB, "Loops/Instrument-Loops"), f"IDM-{kit_name}")

# Print summary
print("\n=== LIBRARY ORGANIZATION SUMMARY ===")
for folder in sorted(counts.keys()):
    rel = folder.replace(LIB + "/", "")
    print(f"  {rel}: {counts[folder]} files")
print(f"\n  TOTAL organized: {sum(counts.values())} files")
