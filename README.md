# SP-404 Jam Box

A fully-loaded SP-404A/SX sampler SD card builder. Scripts, sample curation tools, and a ready-to-play genre bank layout for instant live jamming.

## What Is This?

This project turns a blank SD card into a **jam-ready SP-404** with 10 banks of curated samples spanning lo-fi hip-hop, witch house, nu-rave, electroclash, funk, IDM, ambient, and utility FX. Bank A stays empty for your own sounds, and Bank B is loaded with synthesized novelty FX (air horns, laser zaps, vinyl stops, etc.).

All samples are **royalty-free** (sourced from MusicRadar SampleRadar) or **generated from scratch** using numpy synthesis.

## SD Card Layout

```
SD_CARD/
├── ROLAND/
│   └── SP-404SX/
│       └── SMPL/
│           ├── B0000001.WAV  ... B0000012.WAV   (Bank B: Novelty FX)
│           ├── C0000001.WAV  ... C0000012.WAV   (Bank C: Lo-Fi Hip-Hop 88bpm)
│           ├── D0000001.WAV  ... D0000012.WAV   (Bank D: Witch House 70bpm)
│           ├── E0000001.WAV  ... E0000012.WAV   (Bank E: Nu-Rave 130bpm)
│           ├── F0000001.WAV  ... F0000012.WAV   (Bank F: Electroclash 120bpm)
│           ├── G0000001.WAV  ... G0000012.WAV   (Bank G: Funk & Horns 110bpm)
│           ├── H0000001.WAV  ... H0000012.WAV   (Bank H: IDM 140bpm)
│           ├── I0000001.WAV  ... I0000012.WAV   (Bank I: Ambient 80-105bpm)
│           └── J0000001.WAV  ... J0000012.WAV   (Bank J: Utility/FX)
├── PAD_MAP.txt   (cheat sheet — print this!)
└── copy_to_sd.sh (helper script)
```

**Audio format:** 16-bit / 44.1kHz / Mono PCM WAV (SP-404A native)

**Pad convention:** Pads 1-4 = drum hits, Pads 5-12 = loops & melodic

## Bank Overview

| Bank | Genre | BPM | Vibe |
|------|-------|-----|------|
| A | *Empty* | — | Your sounds |
| B | Novelty & FX | — | Air horn, laser zap, vinyl stop, risers |
| C | Lo-Fi Hip-Hop | 88 | Dusty beats, lo-fi textures |
| D | Witch House | 70 | Dark, slow, heavy, glitchy |
| E | Nu-Rave | 130 | High-energy synth percussion |
| F | Electroclash | 120 | Dirty synths, vinyl drums |
| G | Funk & Horns | 110 | Live funk grooves, clavinet, organ |
| H | IDM | 140 | Complex, glitchy, experimental |
| I | Ambient | 80-105 | Atmospheric pads, textures |
| J | Utility/FX | 120 | Transitions, risers, tools |

## Scripts

### Core Pipeline

| Script | Purpose |
|--------|---------|
| `scripts/pick_best_samples.py` | Selects best samples from library for each bank, converts to SP-404 format |
| `scripts/organize_library.py` | Sorts raw sample packs into categorized library (Drums, Melodic, Loops, SFX) |
| `scripts/gen_novelty.py` | Synthesizes 12 novelty FX sounds for Bank B using numpy |
| `scripts/copy_to_sd.sh` | Copies prepared files from working folder to mounted SD card |

### Legacy (Synthesis-Based)

These were used in the first version which generated all sounds from scratch before we switched to real samples:

| Script | Purpose |
|--------|---------|
| `scripts/legacy/synth_core.py` | Core synthesis library (oscillators, ADSR, filters) |
| `scripts/legacy/loop_core.py` | Loop generation library (drum patterns, chord progressions) |
| `scripts/legacy/gen_bank_*.py` | Per-bank generators (C through J) |
| `scripts/legacy/gen_loops_*.py` | Per-bank loop generators |
| `scripts/legacy/build_card.py` | Original card builder (synthesized everything) |

## Sample Library

Maintained at `~/Music/SP404-Sample-Library/`:

```
SP404-Sample-Library/          (~4.4 GB, 7,644 WAVs)
├── Drums/
│   ├── Kicks/                 (111 files)
│   ├── Snares-Claps/          (44 files)
│   ├── Hi-Hats/               (175 files)
│   ├── Percussion/            (485 files)
│   └── Drum-Loops/            (656 files)
├── Melodic/
│   ├── Bass/                  (364 files)
│   ├── Guitar/                (199 files)
│   ├── Keys-Piano/            (134 files)
│   └── Synths-Pads/           (135 files)
├── Loops/
│   └── Instrument-Loops/      (341 files)
├── SFX/
│   └── Stabs-Hits/            (114 files)
└── _RAW-DOWNLOADS/            (4,886 files — original packs)
```

### Source Packs (all from MusicRadar SampleRadar, royalty-free)

1. **80s-synths** (932 WAVs) — Polys, pads, bass loops, arps, leads
2. **drum-samples** (934 WAVs) — Assorted hits, electro/vinyl/IDM kits
3. **funk-samples** (376 WAVs) — Bass, guitar, organ, clavinet loops at 90-110bpm
4. **hiphop-essentials** (974 WAVs) — Drum hits, Oberheim DX, beats, loops
5. **idm-samples** (500 WAVs) — 5 kits at 100-165bpm
6. **lofi-samples** (587 WAVs) — Construction kits, drum loops, SFX
7. **soul-funk-samples** (393 WAVs) — Construction kits at 100-120bpm
8. **synth-percussion** (190 WAVs) — Vermona DRM1, WaveDrum loops

## SP-404 Technical Reference

### File Naming
- Format: `{BANK}{PAD_NUMBER}.WAV`
- Bank: A-J (single letter)
- Pad: 0000001-0000012 (7 digits, zero-padded)
- Example: `C0000001.WAV` = Bank C, Pad 1

### SD Card Requirements
- File system: FAT32
- Card placed in `ROLAND/SP-404SX/SMPL/` folder
- Samples load instantly — no import step needed
- Pattern files (`.PTN`) in `ROLAND/SP-404SX/PTN/` are proprietary binary

### Audio Format
- Sample rate: 44,100 Hz
- Bit depth: 16-bit
- Channels: Mono
- Codec: PCM (uncompressed WAV)
- Conversion command: `ffmpeg -y -i input.wav -ar 44100 -ac 1 -sample_fmt s16 -c:a pcm_s16le output.WAV`

### Live Performance Tips
- Hit pads 5-12 to layer loops simultaneously
- Use PATTERN SELECT + REC to record pad performances
- BPM range: 40-200 (CTRL 2 knob in pattern mode)
- Set samples to LOOP mode for continuous playback
- HOLD pad keeps sounds playing after release
- Layer effects (Filter, Lo-Fi, Isolator) while jamming

## Related Projects

- [spEdit404](https://github.com/bobgonzalez/spEdit404) — Create/modify SP-404SX pattern files from computer
- [Super Pads](https://github.com/MatthewCallis/super-pads) — Visual sample manager with drag-and-drop
- [ptn2midi](https://tyleroderkirk.github.io/ptn2midi/) — Convert SP-404SX patterns to MIDI
- [nitools](https://github.com/joanroig/nitools) — Convert Native Instruments resources for SP-404
- [SP-404SX format docs](https://gist.github.com/threedaymonk/701ca30e5d363caa288986ad972ab3e0) — Reverse-engineered sample format

## Quick Start

1. Format an SD card as FAT32
2. Clone this repo
3. Download sample packs (see `docs/SAMPLE_SOURCES.md`)
4. Run `python scripts/organize_library.py` to build your library
5. Run `python scripts/pick_best_samples.py` to curate and convert samples
6. Run `python scripts/gen_novelty.py` to generate Bank B FX
7. Run `bash scripts/copy_to_sd.sh` to write to SD card
8. Insert card into SP-404, jam immediately

## License

Scripts: MIT. Samples are royalty-free from MusicRadar SampleRadar.
