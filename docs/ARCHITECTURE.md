# Architecture & Design Decisions

## Overview

This project has two main components:

1. **SD Card Builder** — Scripts that curate, convert, and place samples onto an SP-404A/SX SD card
2. **Sample Library** — A permanent, categorized collection of royalty-free samples on disk

## Pipeline

```
MusicRadar SampleRadar ZIPs
        │
        ▼
  ~/Downloads/*.zip
        │
        ▼
  _UNZIPPED/ (raw extracted packs)
        │
        ├──► organize_library.py ──► ~/Music/SP404-Sample-Library/
        │                              ├── Drums/{Kicks,Snares,Hats,Perc,Loops}
        │                              ├── Melodic/{Bass,Guitar,Keys,Synths}
        │                              ├── Loops/Instrument-Loops
        │                              ├── SFX/Stabs-Hits
        │                              └── _RAW-DOWNLOADS/ (archive)
        │
        ├──► pick_best_samples.py ──► ROLAND/SP-404SX/SMPL/*.WAV
        │    (selects best per genre,     (Banks C-J, 96 files)
        │     converts to 16/44.1/mono)
        │
        └──► gen_novelty.py ──► ROLAND/SP-404SX/SMPL/B*.WAV
             (numpy synthesis)     (Bank B, 12 files)
```

## Design Decisions

### Why 16-bit/44.1kHz Mono?
The SP-404A (original) requires this exact format. The SX and MK2 accept higher rates but mono 44.1 is the universal common denominator. Keeps file sizes small on the SD card too.

### Why Pads 1-4 = Hits, 5-12 = Loops?
Natural performance layout. Left hand on drum hits, right hand layers loops and melodic content. Consistent across all banks so muscle memory transfers between genres.

### Why Real Samples Over Synthesis?
Version 1 synthesized everything from scratch using numpy. The results were functional but lacked the character of real recorded/processed samples. MusicRadar SampleRadar packs are royalty-free and provide much better source material, especially for organic sounds (funk guitar, drum breaks, synth pads recorded from actual hardware).

### Why Keep the Synthesis Scripts?
Bank B (novelty FX) is still synthesized because there's no good free source for "air horn" or "laser zap" samples that's reliably CC0. The numpy approach gives us exact control over these fun utility sounds. The legacy synthesis scripts are preserved for reference and potential future use.

### Bank Genre Selection
Chosen to cover a wide range of jam styles without overlap:
- **Lo-Fi Hip-Hop** (C): The default chill mode, most common SP-404 use case
- **Witch House** (D): Dark/slow counterpoint to the lo-fi bank
- **Nu-Rave** (E): High energy, fast — for when you need to go hard
- **Electroclash** (F): Dirty, punky electronic — bridges E and C
- **Funk & Horns** (G): Live instruments, organic feel — contrast to all the electronic banks
- **IDM** (H): Complex/experimental — for when you want to get weird
- **Ambient** (I): Atmospheric, textural — transitions and interludes
- **Utility/FX** (J): Transitions, risers, drops — performance tools

### SD Card Folder Convention
Files placed directly in `ROLAND/SP-404SX/SMPL/` with the correct naming (`{BANK}0000{PAD}.WAV`) are immediately accessible on the SP-404 without any import step. This bypasses the CANCEL+RESAMPLE import workflow entirely.

## File Format Details

### SP-404 WAV Naming
```
{Bank}{PadNumber}.WAV
  │       │
  │       └── 7 digits, zero-padded: 0000001 through 0000012
  └── Single letter: A through J
```

### ffmpeg Conversion Command
```bash
ffmpeg -y -i input.wav -ar 44100 -ac 1 -sample_fmt s16 -c:a pcm_s16le output.WAV
```
- `-ar 44100`: 44.1kHz sample rate
- `-ac 1`: Mono (downmix stereo)
- `-sample_fmt s16`: 16-bit signed integer
- `-c:a pcm_s16le`: Uncompressed PCM little-endian

### Pattern Files (PTN)
Pattern files in `ROLAND/SP-404SX/PTN/` are a proprietary binary format. They record real-time pad performances and can only be created on the unit itself (via PATTERN SELECT + REC). The [spEdit404](https://github.com/bobgonzalez/spEdit404) project has reverse-engineered this format and can create/modify patterns from a computer.

## Sample Library Organization

The `organize_library.py` script categorizes samples using filename and folder path keywords:

| Target Category | Keywords Matched |
|----------------|-----------------|
| Drums/Kicks | kick, bd, bass drum |
| Drums/Snares-Claps | snare, snr, clap, rim |
| Drums/Hi-Hats | hat, hh, hihat |
| Drums/Percussion | perc, shaker, tamb, conga |
| Drums/Drum-Loops | loop, beat (in drums context) |
| Melodic/Bass | bass (not drum) |
| Melodic/Guitar | guitar, gtr |
| Melodic/Keys-Piano | piano, keys, organ, clav, ep |
| Melodic/Synths-Pads | synth, pad, arp, lead |
| Loops/Instrument-Loops | loop (in melodic context) |
| SFX/Stabs-Hits | fx, stab, hit, riser |

## Future Ideas

- **Pattern pre-loading**: Use spEdit404 to create starter patterns for each bank
- **Bank themes as YAML**: Define bank layouts in config files instead of hardcoded Python
- **Auto-BPM matching**: Use librosa to detect BPM and auto-match samples to bank tempos
- **NAS integration**: Move library to QNAP NAS at `/Volumes/Temp QNAP/Audio Production`
- **Web UI**: Build a drag-and-drop bank editor (maybe fork Super Pads)
- **MK2 support**: Add 48kHz/stereo variant for SP-404 MK2 users
