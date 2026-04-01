# SP-404 Jam Box

## Project Context
SP-404A/SX sampler SD card builder. Curates royalty-free samples into genre-themed banks for instant live jamming. Built with Python scripts, ffmpeg for audio conversion, and numpy for synthesis.

## Key Paths
- SD card mount: /Volumes/SP-404SX
- Sample library: ~/Music/SP404-Sample-Library (~4.4GB, 7,644 WAVs)
- Raw downloads archive: ~/Music/SP404-Sample-Library/_RAW-DOWNLOADS/
- This repo: scripts, docs, and SD card template

## Audio Format (CRITICAL)
All output WAVs MUST be: 16-bit / 44.1kHz / Mono / PCM (uncompressed)
Convert with: `ffmpeg -y -i input -ar 44100 -ac 1 -sample_fmt s16 -c:a pcm_s16le output.WAV`
Verify with: `ffprobe -v quiet -print_format json -show_streams file.wav`

## SP-404 SD Card File Naming
- Path on card: `ROLAND/SP-404SX/SMPL/`
- Naming: `{BANK_LETTER}0000{PAD_NUMBER}.WAV`
- Banks: A through J (10 banks)
- Pads: 0000001 through 0000012 (12 pads per bank)
- Example: `G0000007.WAV` = Bank G, Pad 7
- Files placed here are IMMEDIATELY accessible on the SP-404 (no import needed)

## Current Bank Layout
- Bank A: EMPTY (user's own sounds)
- Bank B: Novelty FX (synthesized with numpy) — air horn, laser zap, vinyl stop, etc.
- Bank C: Lo-Fi Hip-Hop (88 bpm)
- Bank D: Witch House (70 bpm)
- Bank E: Nu-Rave (130 bpm)
- Bank F: Electroclash (120 bpm)
- Bank G: Funk & Horns (110 bpm)
- Bank H: IDM (140 bpm)
- Bank I: Ambient (80-105 bpm)
- Bank J: Utility/FX (120 bpm)

Pad convention: Pads 1-4 = drum hits, Pads 5-12 = loops & melodic content

## Pipeline Commands
1. Organize raw packs into library: `python scripts/organize_library.py`
2. Pick best samples for each bank: `python scripts/pick_best_samples.py`
3. Generate novelty FX for Bank B: `python scripts/gen_novelty.py`
4. Deploy to SD card: `bash scripts/copy_to_sd.sh`

## Sample Sources
All from MusicRadar SampleRadar (royalty-free). 8 packs total: 80s-synths, drum-samples, funk-samples, hiphop-essentials, idm-samples, lofi-samples, soul-funk-samples, synth-percussion.
See docs/SAMPLE_SOURCES.md for download URLs and pack details.

## Sample Library Structure
```
~/Music/SP404-Sample-Library/
├── Drums/{Kicks, Snares-Claps, Hi-Hats, Percussion, Drum-Loops}
├── Melodic/{Bass, Guitar, Keys-Piano, Synths-Pads}
├── Loops/Instrument-Loops
├── SFX/Stabs-Hits
└── _RAW-DOWNLOADS/ (complete original packs)
```

## Pattern Files
Pattern files (.PTN) in `ROLAND/SP-404SX/PTN/` are proprietary binary format. They can ONLY be created by recording on the SP-404 itself, OR using [spEdit404](https://github.com/bobgonzalez/spEdit404) which has reverse-engineered the format.

## Related Community Tools
- spEdit404: Pattern file editor (create patterns from computer!)
- Super Pads: Visual sample manager
- ptn2midi: Convert patterns to MIDI

## Important Notes
- The SP-404A (original, non-SX) is more restrictive — always use 44.1kHz/16-bit/mono
- FAT32 filesystem required on SD card
- Maximum filename length limited by FAT32 (our naming convention is well within limits)
- Always safely eject the SD card before removing from computer
- Keep _BACKUP_ORIGINAL/ folder as safety net
