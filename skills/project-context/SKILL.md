---
name: project-context
description: Core Jambox project context and multi-agent coordination. Use when any agent needs to understand "what is Jambox", "how do the agents work together", "where do files go", "what's the delivery pipeline", or when starting a new session and needing project orientation.
version: 0.2.0
---

# SP-404 Jam Box — Project Context

## What Is Jambox?

An SP-404A/SX sampler SD card builder. Curates royalty-free samples into genre-themed banks for instant live jamming. Built with Python scripts, ffmpeg for audio conversion, numpy for synthesis, and a local LLM pipeline for intelligent tagging and vibe-driven bank generation.

## Multi-Agent Workflow

Three Claude agents coordinate on this project:

| Agent | Role | Tools |
|-------|------|-------|
| **Code** (Claude Code) | Writes code, manages the repo, runs pipelines, builds the web UI | Full repo access, bash, scripts |
| **Chat** (Claude chat) | Taste-driven creative direction, bank curation, genre research, tag vocabulary design, documentation | Conversation, doc authoring |
| **Cowork** (Claude background agent) | Scrapes sample sources, downloads to watchfolders, leaves instructions | Web access, file downloads |

### Coordination Rules
- Chat may provide instructions via CLAUDE.md or via messages relayed by the user
- All deliverables flow through `~/Downloads/` — Code ingests them via `scripts/ingest_downloads.py`
- Chat owns documentation — Code should not create or update doc files unless asked
- After ingesting new samples, re-tag: `python scripts/tag_library.py --update`

## Key Paths

| Path | Purpose |
|------|---------|
| Repo | `/Users/jasongronvold/Desktop/SP-404SX/sp404-jambox/` |
| SD card mount | `/Volumes/SP-404SX` |
| Sample library | `~/Music/SP404-Sample-Library/` (~20,925 FLACs) |
| Tag database | `~/Music/SP404-Sample-Library/_tags.json` |
| Raw downloads archive | `~/Music/SP404-Sample-Library/_RAW-DOWNLOADS/` |
| Bank config | `bank_config.yaml` |
| Tagging spec | `docs/TAGGING_SPEC.md` |
| Personal music (Plex) | `/Volumes/Jansen's FL Drobo/Multimedia/Music` (~33,400 tracks) |
| Web UI | `web/` (Flask on localhost:5404) |
| Vibe sessions DB | `data/vibe_sessions.sqlite` (runtime, gitignored) |
| Scoring config | `config/scoring.yaml` |
| Vibe mappings | `config/vibe_mappings.yaml` |

## Delivery Pipeline

### Audio Files
Audio files (samples, packs) arriving in `~/Downloads/` are ingested via `scripts/ingest_downloads.py`:
1. Extracted from zips/archives
2. Converted to FLAC for library storage
3. Auto-tagged via `tag_library.py --update`
4. Chromaprint fingerprinted + dedup checked (dupes go to `_DUPES/`)
5. Stem-split if >60s (background Demucs)
6. Originals archived to `~/Downloads/_PROCESSED/`

### Doc Deliverables
`.md` and `.txt` files routed by naming convention:
- `CLAUDE.md` → repo root (backup of old as `.bak`)
- `HANDOFF_*.md`, `BUG_HUNT_*.md` → `docs/`
- `CODE_BRIEF_*.md`, `COWORK_BRIEF_*.md` → `docs/briefs/`
- `*_SOURCES.txt` → `docs/sources/`
- `*_Research.md` → `docs/research/`

### Watcher Mode
`python scripts/ingest_downloads.py --watch` — background daemon, auto-ingests new files as they appear.

## Pipeline Commands

1. Edit `bank_config.yaml` to define desired sounds per bank/pad
2. Fetch samples: `python scripts/fetch_samples.py` (or `--bank b`, `--bank b --pad 1`)
3. Generate PAD_INFO.BIN: `python scripts/gen_padinfo.py`
4. Generate starter patterns: `python scripts/gen_patterns.py`
5. Deploy to SD card: `bash scripts/copy_to_sd.sh`

## Audio Format (CRITICAL)

All output WAVs MUST be: **16-bit / 44.1kHz / Mono / PCM (uncompressed)**

Convert with: `ffmpeg -y -i input -ar 44100 -ac 1 -sample_fmt s16 -c:a pcm_s16le output.WAV`

Library storage format is FLAC (lossless). Output to SD card is always WAV.

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SP404_LLM_ENDPOINT` | Local LLM endpoint | (disabled) |
| `SP404_LLM_MODEL` | LLM model name | `qwen3` |
| `SP404_VIBE_PARSER_MODE` | Parser mode: base, rag, fine_tuned | `base` |
| `SP404_SAMPLE_LIBRARY` | Sample library root | `~/Music/SP404-Sample-Library` |
| `SP404_FFMPEG` | ffmpeg binary path | `/opt/homebrew/bin/ffmpeg` |

## Web UI

Launch: `cd web && python app.py` (runs on localhost:5404)

Features: visual pad grid, library browser with tag cloud, vibe prompt bar, preset browser, set selector, My Music (Plex), daily bank generator, file watcher toggle, disk usage panel, power button dashboard.
