# SP-404 Jam Box

## Project Context
SP-404A/SX sampler SD card builder. Curates royalty-free samples into genre-themed banks for instant live jamming. Built with Python scripts, ffmpeg for audio conversion, and numpy for synthesis.

## Multi-Agent Workflow
This project is worked on by multiple Claude agents coordinated by the user:
- **Claude Code** (this agent): writes code, manages the repo, runs pipelines, builds the web UI
- **Chat** (Claude chat): taste-driven creative direction, bank curation, genre research, tag vocabulary design
- **Cowork** (Claude background agent): scrapes sample sources, downloads to watchfolders, leaves instructions

### How to coordinate
- Chat may provide instructions via this file or via messages relayed by the user
- **Chat**: creative direction (bank layouts, genre palettes, tag vocabularies), documentation, orchestrating between agents
- **Code**: implementation (scripts, web UI, pipeline), code changes, deployment
- **Cowork**: sample sourcing (scraping, downloading to watchfolders)
- Cowork drops samples into `~/Downloads/` watchfolders — Code ingests them via `scripts/ingest_downloads.py`
- When Chat suggests new banks or tag changes, update `bank_config.yaml` and `docs/TAGGING_SPEC.md` accordingly
- Chat owns docs — Code should not create or update documentation files unless asked
- After ingesting new samples, re-tag: `python scripts/tag_library.py --update`

## Key Paths
- **Repo**: `/Users/jasongronvold/Desktop/SP-404SX/sp404-jambox/`
- **SD card mount**: `/Volumes/SP-404SX`
- **Sample library**: `~/Music/SP404-Sample-Library/` (~9,600+ WAVs)
- **Tag database**: `~/Music/SP404-Sample-Library/_tags.json`
- **Raw downloads archive**: `~/Music/SP404-Sample-Library/_RAW-DOWNLOADS/`
- **Bank config**: `bank_config.yaml` (defines all banks, pads, BPM, key)
- **Tagging spec**: `docs/TAGGING_SPEC.md` (type codes, tag dimensions, filename conventions)
- **Web UI**: `web/` (Flask app on http://localhost:5404)

## Audio Format (CRITICAL)
All output WAVs MUST be: 16-bit / 44.1kHz / Mono / PCM (uncompressed)
Convert with: `ffmpeg -y -i input -ar 44100 -ac 1 -sample_fmt s16 -c:a pcm_s16le output.WAV`
WAVs also get an RLND chunk (Roland proprietary pad metadata) and leading silence trimmed — handled by `scripts/wav_utils.py`.

## SP-404 SD Card File Naming
- Path on card: `ROLAND/SP-404SX/SMPL/`
- Naming: `{BANK_LETTER}0000{PAD_NUMBER}.WAV`
- Banks: A through J (10 banks), Pads: 1-12 per bank
- Example: `G0000007.WAV` = Bank G, Pad 7

## Current Bank Layout
| Bank | Name | BPM | Key | Purpose |
|------|------|-----|-----|---------|
| A | Your Space | — | — | User's own sounds (empty) |
| B | Sessions | 120 | Am | Long-form breaks/tracks for live chopping |
| C | Drum Loops | 120 | XX | Pure rhythm across all genres |
| D | Funk | 112 | Em | Guitar-driven dance-punk, !!! energy |
| E | Disco | 120 | Am | Four-on-the-floor, warm, danceable |
| F | Electroclash | 120 | Dm | Dirty, minimal, Fischerspooner attitude |
| G | Nu-Rave | 128 | F | Neon blog-house, 2007 energy |
| H | Aggressive | 130 | Dm | Industrial-tinged, peak-time |
| I | Textures & Transitions | 120 | Am | Pads, risers, ambient glue |
| J | Utility & Fun | 120 | any | Speeches, gunshots, cash registers, iconic SFX |

**Harmonic design**: All keys (Am, Dm, Em, F) are diatonic to C major — everything harmonizes across banks.
**Tempo design**: 112/120/128/130 BPM cluster — all mix cleanly.
**Pad convention**: Pads 1-4 = drum hits (one-shots), Pads 5-12 = loops & melodic content

## Tag System & Dimensions
Auto-tag library: `python scripts/tag_library.py` (incremental: `--update`)

### Tag Dimensions (from TAGGING_SPEC.md)
| Dimension | What it answers | Examples |
|-----------|----------------|---------|
| type_code | What is it? | KIK, SNR, HAT, BAS, SYN, PAD, VOX, FX, BRK, RSR |
| vibe | What does it feel like? | dark, mellow, hype, dreamy, nostalgic, aggressive |
| texture | What does it sound like? | dusty, lo-fi, raw, clean, warm, bitcrushed |
| genre | What style? | funk, disco, house, electronic, ambient, soul |
| energy | How intense? | low, mid, high |
| source | Where from? | kit, dug, synth, field, processed |
| playability | How to use it? | one-shot, loop, chop-ready, layer, transition |

### Pad Description Format
Each pad in `bank_config.yaml` uses: `TYPE_CODE keyword keyword playability`
- Type code first (3 letters, caps): KIK, BRK, SYN, VOX, etc.
- 2-3 keywords from any dimension (vibe, texture, genre)
- Playability last: one-shot, loop, chop-ready, layer, transition
- **Less is more** — 3-4 total keywords get better matches than 6-7

Example: `BAS funk warm loop` — finds a warm funk bass loop
Example: `KIK hard aggressive one-shot` — finds a hard aggressive kick

### How Fetching Works
1. `fetch_samples.py` parses each pad description into structured fields
2. Scores every file in the tag database (`_tags.json`) against the query
3. Type code match = +10 points (mismatch = -8), playability = +5, BPM/key = +3-4, keywords = +3 each
4. Global deduplication: no file used twice across any pad
5. Falls back to Freesound.org API if no local match (needs `FREESOUND_API_KEY` in `.env`)

### Tag Cloud API
- `GET /api/library/tags` — dimension-grouped tag frequencies
- `GET /api/library/by-tag?type_code=KIK&vibe=dark&genre=funk` — dimension filtering (OR within, AND across)

## Pipeline Commands
1. Edit `bank_config.yaml` to define desired sounds per bank/pad
2. Fetch samples: `python scripts/fetch_samples.py` (or `--bank b`, `--bank b --pad 1`)
3. Generate PAD_INFO.BIN: `python scripts/gen_padinfo.py`
4. Generate starter patterns: `python scripts/gen_patterns.py`
5. Deploy to SD card: `bash scripts/copy_to_sd.sh`

## Ingest Downloads
`python scripts/ingest_downloads.py` — extracts sample packs from ~/Downloads, auto-categorizes WAVs into library, then moves processed packs to `_RAW-DOWNLOADS/` to keep Downloads clean.

## Sample Library Structure
```
~/Music/SP404-Sample-Library/
├── Ambient-Textural/Atmospheres
├── Drums/{Kicks, Snares-Claps, Hi-Hats, Percussion, Drum-Loops}
├── Loops/Instrument-Loops
├── Melodic/{Bass, Guitar, Keys-Piano, Synths-Pads}
├── SFX/Stabs-Hits
├── Vocals/Chops
├── Freesound/{bank-name}/  (API downloads with attribution)
├── _RAW-DOWNLOADS/          (original packs, ingested packs moved here)
├── _GOLD/Bank-A/            (saved Bank A sessions)
└── _tags.json               (tag database, ~9,600 entries)
```

## Web UI
Launch: `cd web && python app.py` (runs on http://localhost:5404)
- Visual pad grid mirroring the SP-404 layout
- Click pads to edit descriptions, preview audio, fetch samples
- Drag-and-drop from library sidebar or OS file explorer onto pads
- Library sidebar: browse folders + dimension-aware tag cloud
- Bank edit modal (pencil button): name, BPM, key, notes
- Pipeline controls: Fetch All, Ingest Downloads, Build, Deploy
- SD card status indicator with auto-polling

## Pattern Files
Pattern files (.PTN) in `ROLAND/SP-404SX/PTN/` are proprietary binary format.
Generated via `scripts/gen_patterns.py` using vendored spEdit404 (`scripts/spedit404/`).

## PAD_INFO.BIN
`ROLAND/SP-404SX/SMPL/PAD_INFO.BIN` — per-pad metadata (loop/gate/BPM).
Generated by `scripts/gen_padinfo.py` — auto-sets loop mode for pads 5-12, gate for 1-4.

## RLND WAV Chunk
SP-404SX WAVs include a proprietary "RLND" chunk (466 bytes) encoding device ID and pad index.
Injected by `scripts/wav_utils.py:inject_rlnd()` during sample conversion.

## Important Notes
- The SP-404A (original, non-SX) is more restrictive — always use 44.1kHz/16-bit/mono
- FAT32 filesystem required on SD card
- Always safely eject the SD card before removing from computer
- ffmpeg is at `/opt/homebrew/bin/ffmpeg` (all scripts use absolute paths)
