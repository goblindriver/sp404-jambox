# SP-404 Jam Box

A fully-loaded SP-404A/SX sampler SD card builder with a web UI, intelligent sample matching, and a 9,600+ WAV library. Define your banks in YAML, fetch matching samples automatically, and deploy to SD card in one click.

## What Is This?

This project turns a blank SD card into a **jam-ready SP-404** with 10 genre-themed banks designed to harmonize and mix together. A Flask web UI lets you browse your library, edit bank layouts, preview audio, and run the full pipeline without touching the terminal.

All samples are **royalty-free** (MusicRadar SampleRadar + Freesound API).

## Bank Layout

Every bank key is diatonic to C major (Am, Dm, Em, F) so everything harmonizes. BPMs cluster around 112–130 for clean mixing.

| Bank | Name | BPM | Key | Vibe |
|------|------|-----|-----|------|
| A | Your Space | — | — | Empty — resample and chop on-device |
| B | Sessions | 120 | Am | Long-form breaks/tracks for live chopping |
| C | Drum Loops | 120 | XX | Pure rhythm across all genres |
| D | Funk | 112 | Em | Guitar-driven dance-punk, !!! energy |
| E | Disco | 120 | Am | Four-on-the-floor, warm, danceable |
| F | Electroclash | 120 | Dm | Dirty, minimal, Fischerspooner attitude |
| G | Nu-Rave | 128 | F | Neon blog-house, 2007 energy |
| H | Aggressive | 130 | Dm | Industrial-tinged, peak-time |
| I | Textures & Transitions | 120 | Am | Pads, risers, ambient glue |
| J | Utility & Fun | 120 | any | Speeches, gunshots, iconic SFX |

**Pad convention:** Pads 1–4 = drum hits (one-shots), Pads 5–12 = loops & melodic content

## Web UI

Launch: `cd web && python app.py` → http://localhost:5404

- Visual pad grid mirroring the SP-404 layout
- Click pads to edit descriptions, preview audio, fetch samples
- Drag-and-drop from library sidebar onto pads
- Library browser with dimension-aware tag cloud filtering
- Bank edit modal: name, BPM, key, notes
- Pipeline controls: Fetch All, Ingest Downloads, Build, Deploy
- SD card status indicator with auto-polling

## Pipeline

```
Sample Packs (MusicRadar / Freesound)
        │
        ▼
  ~/Downloads/*.zip
        │
        ▼
  ingest_downloads.py ──► ~/Music/SP404-Sample-Library/ (9,600+ WAVs)
        │                    └── _tags.json (auto-generated tag database)
        │
        ▼
  tag_library.py ──► Tags every sample across 7 dimensions
        │
        ▼
  fetch_samples.py ──► Scores library against bank_config.yaml pad descriptions
        │                  Falls back to Freesound API if no local match
        │
        ▼
  gen_padinfo.py ──► PAD_INFO.BIN (loop/gate mode per pad)
  gen_patterns.py ──► Starter .PTN pattern files
        │
        ▼
  copy_to_sd.sh ──► /Volumes/SP-404SX/ROLAND/SP-404SX/SMPL/
```

### Commands

```bash
# Full pipeline
python scripts/fetch_samples.py          # Fetch all banks
python scripts/fetch_samples.py --bank d # Fetch single bank
python scripts/fetch_samples.py --bank d --pad 1  # Fetch single pad
python scripts/gen_padinfo.py            # Generate PAD_INFO.BIN
python scripts/gen_patterns.py           # Generate starter patterns
bash scripts/copy_to_sd.sh              # Deploy to SD card

# Library management
python scripts/ingest_downloads.py       # Import new sample packs
python scripts/tag_library.py            # Tag entire library
python scripts/tag_library.py --update   # Tag new files only
```

## How Fetching Works

1. `fetch_samples.py` parses each pad description from `bank_config.yaml`
2. Scores every file in `_tags.json` against the query
3. Scoring: type code match = +10 (mismatch = −8), playability = +5, BPM/key = +3–4, keywords = +3 each
4. Global deduplication — no file used twice across any pad
5. Falls back to Freesound API if no local match (needs `FREESOUND_API_KEY` in `.env`)
6. Converts winner to 16-bit/44.1kHz/mono WAV with RLND chunk

## Tag System

Every sample is auto-tagged across 7 dimensions (see `docs/TAGGING_SPEC.md`):

| Dimension | What it answers | Examples |
|-----------|----------------|---------|
| type_code | What is it? | KIK, SNR, HAT, BAS, SYN, PAD, VOX, FX, BRK |
| vibe | What does it feel like? | dark, mellow, hype, dreamy, aggressive |
| texture | What does it sound like? | dusty, lo-fi, raw, clean, warm, bright |
| genre | What style? | funk, disco, house, electronic, ambient |
| energy | How intense? | low, mid, high |
| source | Where from? | kit, dug, synth, field, processed |
| playability | How to use it? | one-shot, loop, chop-ready, layer, transition |

### Tag Cloud API

- `GET /api/library/tags` — dimension-grouped tag frequencies
- `GET /api/library/by-tag?type_code=KIK&vibe=dark` — filter (OR within dimension, AND across)

## Sample Library

```
~/Music/SP404-Sample-Library/         (~9,600+ WAVs)
├── Ambient-Textural/Atmospheres
├── Drums/{Kicks, Snares-Claps, Hi-Hats, Percussion, Drum-Loops}
├── Loops/Instrument-Loops
├── Melodic/{Bass, Guitar, Keys-Piano, Synths-Pads}
├── SFX/Stabs-Hits
├── Vocals/Chops
├── Freesound/{bank-name}/           (API downloads with attribution)
├── _RAW-DOWNLOADS/                  (original packs, archived after ingest)
├── _GOLD/Bank-A/                    (saved Bank A sessions)
└── _tags.json                       (tag database)
```

## SD Card Structure

```
SD_CARD/
└── ROLAND/
    └── SP-404SX/
        ├── SMPL/
        │   ├── PAD_INFO.BIN
        │   ├── A0000001.WAV ... A0000012.WAV  (Bank A)
        │   └── ...through J0000012.WAV        (Bank J)
        └── PTN/
            └── PTN00001.BIN ... (pattern files)
```

### Audio Format

All output WAVs: **16-bit / 44.1kHz / Mono / PCM** (uncompressed)

```bash
ffmpeg -y -i input -ar 44100 -ac 1 -sample_fmt s16 -c:a pcm_s16le output.WAV
```

### File Naming

`{BANK}0000{PAD}.WAV` — e.g., `G0000007.WAV` = Bank G, Pad 7

## Multi-Agent Workflow

This project uses three Claude agents coordinated by the user:

| Agent | Role | Owns |
|-------|------|------|
| **Chat** | Creative direction, bank curation, documentation | Docs, tag vocabulary, genre research |
| **Code** | Implementation, scripts, web UI, pipeline | All code, `bank_config.yaml` updates |
| **Cowork** | Sample sourcing, downloading to watchfolders | Scraping, file acquisition |

See `CLAUDE.md` for full coordination details.

## Quick Start

1. Format an SD card as FAT32
2. Clone this repo
3. Run `python scripts/ingest_downloads.py` to import sample packs
4. Run `python scripts/tag_library.py` to build the tag database
5. Edit `bank_config.yaml` to define your banks (or use the web UI)
6. Run `python scripts/fetch_samples.py` to match and convert samples
7. Run `python scripts/gen_padinfo.py && python scripts/gen_patterns.py`
8. Run `bash scripts/copy_to_sd.sh` to deploy
9. Insert card into SP-404, jam immediately

Or: `cd web && python app.py` and do it all from http://localhost:5404

## Related Projects

- [spEdit404](https://github.com/bobgonzalez/spEdit404) — Create/modify SP-404SX pattern files
- [Super Pads](https://github.com/MatthewCallis/super-pads) — Visual sample manager
- [ptn2midi](https://tyleroderkirk.github.io/ptn2midi/) — Convert SP-404SX patterns to MIDI
- [SP-404SX format docs](https://gist.github.com/threedaymonk/701ca30e5d363caa288986ad972ab3e0) — Reverse-engineered sample format

## License

Scripts: MIT. Samples: royalty-free (MusicRadar SampleRadar + Freesound).
