# SP-404 Jam Box

A fully-loaded SP-404A sampler SD card builder with a web UI, intelligent sample matching, and a 30K+ sample library. Define your banks in YAML or with natural language, fetch matching samples automatically, and deploy to SD card in one click.

## What Is This?

This project turns a blank SD card into a **jam-ready SP-404** with 10 genre-themed banks designed to harmonize and mix together. A Flask web UI lets you browse your library, edit bank layouts, describe sounds in plain English, preview audio, and run the full pipeline without touching the terminal.

## Bank Layout — Tiger Dust Block Party

Every bank key is diatonic to C major so everything harmonizes. BPMs cluster around 90–130 for clean mixing. Energy arc: warm up → groove → peak → breathe → weapons.

| Bank | Name | BPM | Key | Energy | Vibe |
|------|------|-----|-----|--------|------|
| A | Soul Kitchen | 98 | G | Low | Dusty soul grooves, golden hour opener |
| B | Funk Muscle | 112 | Em | High | James Brown tight, Parliament nasty |
| C | Disco Inferno | 118 | Am | High | Four-on-the-floor, lush strings |
| D | Boom Bap Cipher | 90 | Dm | Mid | Golden age hip-hop, vinyl crackle |
| E | Caribbean Heat | 108 | Cm | High | Dancehall riddims, tropical bass |
| F | Electro Sweat | 120 | Dm | High | Dance-punk, dirty synths, LCD energy |
| G | Neon Rave | 128 | F | High | Blog-house, rave stabs, 2007 warehouse |
| H | Peak Hour | 125 | Gm | High | Maximum intensity, the drop |
| I | Dub Cooldown | 100 | Am | Low | Echo chamber, melodica, reverb for days |
| J | Weapons Cache | 120 | XX | Mid | Air horns, sirens, transitions, impacts |

**Pad convention:** Pads 1–4 = drum one-shots. Pads 5–8 = loops & breaks. Pads 9–10 = melodic. Pads 11–12 = texture/FX.

## Quick Start

```bash
# Setup
git clone <repo> && cd sp404-jambox
bash scripts/bootstrap.sh          # Create .venv, install deps

# Build a card
./.venv/bin/python web/app.py      # Launch web UI → http://localhost:5404
# Or from terminal:
python scripts/fetch_samples.py    # Match samples to all banks
python scripts/gen_padinfo.py      # Generate PAD_INFO.BIN
bash scripts/copy_to_sd.sh        # Deploy to SD card
```

See [docs/DEPLOYMENT_RUNBOOK.md](docs/DEPLOYMENT_RUNBOOK.md) for the full step-by-step.

## Web UI

`./.venv/bin/python web/app.py` → http://localhost:5404

- Visual pad grid mirroring the SP-404 layout
- Natural language vibe prompts — describe a sound, get matched samples
- Drag-and-drop from library sidebar onto pads
- Preset browser with 22+ genre presets
- Personal music integration (Plex-powered, 33K+ tracks)
- Pipeline controls: Fetch, Build, Deploy, Watch, Retag
- SD card status with one-click deploy and eject

## Smart Features

All local-first, no cloud required:

- **Vibe Prompts** — Describe a mood/genre in plain English, get ranked sample matches via local LLM
- **Smart Retag** — LLM-powered dimensional tagging (vibe, texture, genre, energy, quality)
- **CLAP Embeddings** — Semantic audio search via text-to-audio similarity
- **Audio Analysis** — librosa BPM/key/loudness detection
- **Stem Splitting** — Background Demucs separation for tracks >60s
- **Audio Dedup** — Multi-tier fingerprint + timbral + semantic duplicate detection
- **Daily Bank** — Auto-generates fresh presets from library activity
- **Card Intelligence** — Learns from your live performance (pad reuse, velocity, BPM stability)

## Documentation

| Doc | What it covers |
|-----|---------------|
| [CLAUDE.md](CLAUDE.md) | Full project context for agents and contributors |
| [docs/TAGGING_SPEC.md](docs/TAGGING_SPEC.md) | Tag vocabulary, dimensions, quality rubric |
| [docs/DEPLOYMENT_RUNBOOK.md](docs/DEPLOYMENT_RUNBOOK.md) | Complete build-to-card workflow |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | All 78 API endpoints |
| [docs/SP404_ECOSYSTEM_RESEARCH.md](docs/SP404_ECOSYSTEM_RESEARCH.md) | Research index |
| [docs/SMART_RETAG_SPEC.md](docs/SMART_RETAG_SPEC.md) | LLM retag system prompt and config |

## Multi-Agent Workflow

This project uses three Claude agents coordinated by the user:

| Agent | Role | Owns |
|-------|------|------|
| **Chat** | Creative direction, bank curation, documentation | Docs, tag vocabulary, genre research |
| **Code** | Implementation, scripts, web UI, pipeline | All code, config, deployment |
| **Cowork** | Sample sourcing, downloading to watchfolders | Scraping, file acquisition |

See [CLAUDE.md](CLAUDE.md) for full coordination details and key paths.

## Related Projects

- [spEdit404](https://github.com/bobgonzalez/spEdit404) — Create/modify SP-404SX pattern files
- [Super Pads](https://github.com/MatthewCallis/super-pads) — Visual sample manager
- [ptn2midi](https://tyleroderkirk.github.io/ptn2midi/) — Convert SP-404SX patterns to MIDI

## License

Scripts: MIT. Samples: royalty-free (MusicRadar SampleRadar + curated packs).
