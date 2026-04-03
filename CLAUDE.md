# SP-404 Jam Box

## Project Context
SP-404A/SX sampler SD card builder. Curates royalty-free samples into genre-themed banks for instant live jamming. Built with Python scripts, ffmpeg for audio conversion, numpy for synthesis, and a local LLM pipeline for intelligent tagging and vibe-driven bank generation.

## Multi-Agent Workflow
This project is worked on by multiple Claude agents coordinated by the user:
- **Claude Code** (this agent): writes code, manages the repo, runs pipelines, builds the web UI
- **Chat** (Claude chat): taste-driven creative direction, bank curation, genre research, tag vocabulary design, documentation, orchestrating between agents
- **Cowork** (Claude background agent): scrapes sample sources, downloads to watchfolders, leaves instructions

### How to coordinate
- Chat may provide instructions via this file or via messages relayed by the user
- **Chat**: creative direction (bank layouts, genre palettes, tag vocabularies), documentation, orchestrating between agents
- **Code**: implementation (scripts, web UI, pipeline), code changes, deployment
- **Cowork**: sample sourcing (scraping, downloading to watchfolders), research deliverables
- **All deliverables flow through `~/Downloads/`** — Code ingests them via `scripts/ingest_downloads.py`:
  - Audio files (samples, packs) → ingested into the sample library, tagged, converted to FLAC
  - Doc deliverables (`.md`, `.txt`) → routed to `docs/` by naming convention (see routing table in script)
  - `CLAUDE.md` → copied to repo root (backup of old version kept as `.bak`)
  - Originals move to `~/Downloads/_PROCESSED/` after routing
- When Chat suggests new banks or tag changes, update `bank_config.yaml` and `docs/TAGGING_SPEC.md` accordingly
- Chat owns docs — Code should not create or update documentation files unless asked (the ingest pipeline routes Chat's docs, it doesn't author them)
- After ingesting new samples, re-tag: `python scripts/tag_library.py --update`

## Key Paths
- **Repo**: `/Users/jasongronvold/Desktop/SP-404SX/sp404-jambox/`
- **SD card mount**: `/Volumes/SP-404SX`
- **Sample library**: `~/Music/SP404-Sample-Library/` (~20,925 FLACs, 15 GB)
- **Tag database**: `~/Music/SP404-Sample-Library/_tags.json`
- **Raw downloads archive**: `~/Music/SP404-Sample-Library/_RAW-DOWNLOADS/`
- **Bank config**: `bank_config.yaml` (defines all banks, pads, BPM, key)
- **Tagging spec**: `docs/TAGGING_SPEC.md` (type codes, tag dimensions, filename conventions)
- **Personal music library**: `/Volumes/Jansen's FL Drobo/Multimedia/Music` (~33,400 tracks, Drobo NAS)
- **Plex database**: `~/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db` (READ-ONLY)
- **Plex client**: `scripts/plex_client.py` (read-only SQLite queries for moods, styles, art, play counts)
- **Ingest log**: `~/Music/SP404-Sample-Library/_ingest_log.json`
- **Web UI**: `web/` (Flask app on http://localhost:5404)
- **Vibe sessions DB**: `data/vibe_sessions.sqlite` (runtime, gitignored)
- **Eval suite**: `data/evals/` (prompt_to_parse, prompt_to_draft, prompt_to_ranking)
- **Training scripts**: `training/vibe/` (prepare_dataset, train_lora, eval_model, compare_modes, serve_model)
- **Training configs**: `training/vibe/configs/` (QLoRA YAML configs)
- **Pattern training gates**: `training/pattern/` (readiness checks, requirements)
- **Scoring config**: `config/scoring.yaml` (tunable fetch scoring weights)
- **Vibe mappings**: `config/vibe_mappings.yaml` (genre→instrument, keyword aliases)

## Audio Format (CRITICAL)
All output WAVs MUST be: 16-bit / 44.1kHz / Mono / PCM (uncompressed)
Convert with: `ffmpeg -y -i input -ar 44100 -ac 1 -sample_fmt s16 -c:a pcm_s16le output.WAV`
WAVs also get an RLND chunk (Roland proprietary pad metadata) and leading silence trimmed — handled by `scripts/wav_utils.py`.

**Library storage format**: FLAC (lossless, ~50-60% smaller than WAV). Ingest converts to FLAC on arrival. Output to SD card is always WAV per the SP-404 spec.

## SP-404 SD Card File Naming
- Path on card: `ROLAND/SP-404SX/SMPL/`
- Naming: `{BANK_LETTER}0000{PAD_NUMBER}.WAV`
- Banks: A through J (10 banks), Pads: 1-12 per bank
- Example: `G0000007.WAV` = Bank G, Pad 7

## Current Bank Layout

### Tiger Dust Block Party (default performance set)
| Bank | Name | BPM | Key | Energy | Purpose |
|------|------|-----|-----|--------|---------|
| A | Soul Kitchen | 98 | G | Low | Golden hour opener. Dusty soul grooves. |
| B | Funk Muscle | 112 | Em | High | James Brown tight, Parliament nasty. |
| C | Disco Inferno | 118 | Am | High | Four-on-the-floor, lush strings, full dance floor. |
| D | Boom Bap Cipher | 90 | Dm | Mid | Golden age hip-hop, vinyl crackle, 808 weight. |
| E | Caribbean Heat | 108 | Cm | High | Dancehall riddims, soca drums, tropical bass. |
| F | Electro Sweat | 120 | Dm | High | Dance-punk tension, dirty synths, LCD at the cookout. |
| G | Neon Rave | 128 | F | High | Blog-house filters, rave stabs, 2007 warehouse energy. |
| H | Peak Hour | 125 | Gm | High | THE MOMENT. Maximum intensity. The drop. |
| I | Dub Cooldown | 100 | Am | Low | Echo chamber bass, melodica, reverb for days. |
| J | Weapons Cache | 120 | XX | Mid | Air horns, sirens, scratches, transitions, impacts. |

**Energy arc:** warm up → get moving → full groove → change pace → summer → get weird → build → PEAK → breathe → weapons anytime

### Legacy Default Set (v3)
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

### Available Genre Presets
| Preset | BPM | Key | Vibe |
|--------|-----|-----|------|
| soul-kitchen | 98 | G | Dusty soul, golden hour warmth |
| funk-muscle | 112 | Em | James Brown tight, Parliament nasty |
| disco-inferno | 118 | Am | Nile Rodgers guitar, lush strings |
| boom-bap-cipher | 90 | Dm | Golden age hip-hop, vinyl crackle |
| caribbean-heat | 108 | Cm | Dancehall riddims, soca, tropical bass |
| electro-sweat | 120 | Dm | Dance-punk, dirty synths, LCD energy |
| neon-rave | 128 | F | Blog-house, rave stabs, 2007 warehouse |
| peak-hour | 125 | Gm | Maximum intensity, big drops |
| dub-cooldown | 100 | Am | Echo chamber, melodica, spacious reverb |
| weapons-cache | 120 | XX | Air horns, sirens, transitions, impacts |
| big-beat-blowout | 130 | Em | Chemical Brothers warehouse energy |
| synth-pop-dreams | 110 | Fm | Airy melancholy, Postal Service intimacy |
| brat-mode | 128 | Gm | Buzzy detuned synths, Charli XCX attitude |
| riot-mode | 160 | E | Punk/riot grrrl/ska-punk |
| minneapolis-machine | 90 | Db | P.O.S/Doomtree experimental hip-hop |
| outlaw-country-kitchen | 95 | G | Country/Americana |
| karaoke-metal | 140 | Em | Heavy metal |
| french-filter-house | 122 | Dm | Modjo/electroclash filter house |
| purity-ring-dreams | 108 | Ab | Synth-pop, #1 reference artist |
| crystal-chaos | 135 | Fm | Brat Mode dark wing |
| ween-machine | 110 | C | Genre-chameleon |
| azealia-mode | 130 | Bbm | Art-pop/house-rap |

**Harmonic design**: Default set keys (Am, Dm, Em, F) are diatonic to C major — everything harmonizes across banks.
**Tempo design**: 112/120/128/130 BPM cluster — all mix cleanly.
**Pad convention** (12 pads per bank, SP-404A):
- Pads 1-4: Drum one-shots (kick, snare, hat, perc)
- Pads 5-8: Loops & breaks (choppable rhythm, melodic loops)
- Pads 9-10: Melodic content (bass, chords, leads)
- Pads 11-12: Texture/FX (risers, transitions, ambient, vocal chops)

This aligns with how professional SP-404 content packs organize pads (rhythm low, melodic mid, texture high). The MK2 uses 16 pads — Jambox targets the SP-404A's 12-pad layout.

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
6. Scoring weights are tunable via `config/scoring.yaml`

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
- One-shot: `python scripts/ingest_downloads.py` — process all pending packs/files from ~/Downloads
- Watcher mode: `python scripts/ingest_downloads.py --watch` — background daemon using watchdog, auto-ingests new files as they appear in ~/Downloads
- Docs only: `python scripts/ingest_downloads.py --docs-only` — route doc deliverables without processing audio
- The watcher waits for file sizes to stabilize before processing (handles in-progress downloads)

### Audio Pipeline (Unified — shipped April 2026)
Every audio file that enters the library gets the full pipeline automatically:
- **Audio analysis** (`scripts/audio_analysis.py`): librosa BPM/key/loudness detection (fallback when filename has no metadata)
- **Fingerprinting**: Chromaprint fingerprinting + inline dedup check (dupes auto-move to `_DUPES/`)
- **Stem splitting**: Background Demucs split for tracks >60s (ThreadPoolExecutor, non-blocking). Invocation: `python3 -m demucs`
- **Tagging**: Auto-runs `tag_library.py --update`, enriches entries with `bpm_source`, `key_source`, `loudness_db` fields
- Reads `_SOURCE.txt` files left by Cowork and stores context in `_tags.json`
- Reads `_DELIVERY.yaml` manifests from Chat delivery zips and auto-installs presets
- Converts to FLAC on ingest for storage efficiency

### Doc Pipeline
Routes `.md` and `.txt` deliverables from Chat and Cowork to the correct repo location by naming convention:
- `CLAUDE.md` → repo root (backs up old as `CLAUDE.md.bak`)
- `HANDOFF_*.md`, `BUG_HUNT_*.md`, `SP404_*.md` → `docs/`
- `CODE_BRIEF_*.md`, `COWORK_BRIEF_*.md` → `docs/briefs/`
- `*_SOURCES.txt` → `docs/sources/`
- `*_Research.md` → `docs/research/`
- Unrecognized `.md`/`.txt` → skipped with warning in log
- Originals move to `~/Downloads/_PROCESSED/` after routing

### Logging & UI
- Logs to `~/Music/SP404-Sample-Library/_ingest_log.json`
- Web UI has a Watch toggle button to start/stop the watcher, and an activity feed

## Plex Integration (Personal Music)
The "My Music" browser in the web UI reads from the local Plex Media Server's SQLite database (read-only, never writes).

### What Plex provides
- **298 mood tags** per track (Aggressive, Brooding, Energetic, etc.) → mapped to our vibe dimension
- **412 style tags** (Alternative/Indie Rock, Hardcore Punk, etc.) → mapped to our genre dimension
- **Artist bios/summaries**, country, album art
- **Record labels** per album
- **Audio loudness analysis** (gain, peak, LRA)
- **Play counts** (when available) → used as relevance boost in fetch scoring
- **33,408 tracks** across 1,005 artists

### Mood → Vibe mapping
Plex moods are mapped to our 15 vibe tags in `scripts/plex_client.py:MOOD_TO_VIBE`. Examples:
- Aggressive/Hostile/Menacing → `aggressive`
- Energetic/Rousing/Lively → `hype`
- Brooding/Ominous/Sinister → `dark`
- Passionate/Earnest/Heartfelt → `soulful`

### Music API (web/api/music.py)
- `GET /api/music/status` — library stats, source (plex vs id3)
- `GET /api/music/browse` — artists, genres, moods, styles, decades
- `GET /api/music/artist/<name>` — full artist detail with albums, tracks, vibes
- `GET /api/music/track/<id>` — full track metadata including moods, loudness
- `GET /api/music/mood/<mood>` — tracks by Plex mood
- `GET /api/music/style/<style>` — tracks by Plex style
- `GET /api/music/search?q=` — text search
- `POST /api/music/split` — stem-split a track (carries Plex metadata to stems)
- `GET /api/music/art?thumb=<url>` — proxy album art from Plex metadata store

### Split & Sample with Plex metadata
When stem-splitting a personal track, all Plex metadata flows through:
- Plex moods → `plex_moods` + mapped `vibe` tags in `_tags.json`
- Plex styles → mapped `genre` tags
- Energy inferred from moods (high/mid/low)
- Texture inferred from moods (raw/warm/airy)
- Source marked as `personal` with artist/album/title provenance

## Personalized Vibe Intelligence (NEW — shipped April 2026)

### Overview
A full LLM-powered pipeline for turning natural language vibe prompts into SP-404 bank presets. Three parser modes, persistent session logging, editable tag review, and a training pipeline for fine-tuning.

### Parser Modes
- **base**: Keyword fallback parser. No LLM required. Extracts type codes, playability, and dimensional keywords from the prompt text. Always available.
- **rag**: Retrieval-grounded parsing. Calls the LLM with context retrieved from prior sessions, matching presets, and library tag statistics. Requires `SP404_LLM_ENDPOINT`.
- **fine_tuned**: Uses a QLoRA-adapted model endpoint. Requires `SP404_FINE_TUNED_LLM_ENDPOINT`. Falls back to base on failure.

Set mode via `SP404_VIBE_PARSER_MODE=base|rag|fine_tuned`.

### Session Logging
Every vibe generation creates a session in `data/vibe_sessions.sqlite` tracking:
- Prompt, BPM, key, bank
- Parser mode and model label
- Parsed tags (original and user-reviewed)
- Draft preset (original and user-reviewed)
- Applied preset and fetch results
- Dataset status (raw → reviewed → exported) for training data curation

### Retrieval Grounding (RAG mode)
`scripts/vibe_retrieval.py` builds context from three sources:
1. **Historical sessions**: Past vibe sessions with matching keywords (prefers reviewed ones)
2. **Preset examples**: Existing presets with matching tags/vibes
3. **Library hints**: Tag frequency statistics from the sample library for matching keywords

### Training Pipeline
Located in `training/vibe/`:
- `prepare_dataset.py` — Extracts reviewed sessions into JSONL training data (parse + draft tasks)
- `train_lora.py` — QLoRA fine-tuning using transformers + peft + bitsandbytes
- `eval_model.py` — Offline evaluation: parse accuracy, draft quality, ranking correctness
- `compare_modes.py` — Run eval suite across base/rag/fine_tuned and compare
- `serve_model.py` — Serve a GGUF model via llama.cpp's OpenAI-compatible server
- `configs/` — QLoRA training configs (LoRA r=16, α=32, lr=2e-4, 3 epochs)

### Eval Suite
Seed evals in `data/evals/`:
- `prompt_to_parse.jsonl` — 12 prompts with expected type_code, playability, keywords
- `prompt_to_draft.jsonl` — 6 prompts with expected pad prefixes and keyword presence
- `prompt_to_ranking.jsonl` + `ranking_fixture.json` — 6 prompts with expected top-1 ranking against a fixture library

Run: `python training/vibe/eval_model.py --mode base`

### Pattern Training Readiness
`training/pattern/readiness.py` gates pattern-model training behind:
- Curated MIDI corpus (≥50 files in `data/midi/`)
- Style labels (`data/pattern_labels.jsonl`)
- Eval prompts (`data/pattern_evals.jsonl`)
- Configured checkpoint output directory

Pattern training is intentionally separate from vibe training. No MIDI corpus exists yet.

### Vibe API Endpoints (web/api/vibe.py)
- `POST /api/vibe/generate` — Parse prompt, return suggestions + session_id
- `POST /api/vibe/apply-bank` — Apply reviewed draft to a bank (with optional auto-fetch)
- `POST /api/vibe/populate-bank` — End-to-end: LLM parse → preset → load → fetch
- `GET /api/vibe/populate-status/<job_id>` — Poll background populate job

## Sample Library Structure
```
~/Music/SP404-Sample-Library/
├── Ambient-Textural/Atmospheres
├── Drums/{Kicks, Snares-Claps, Hi-Hats, Percussion, Drum-Loops}
├── Loops/Instrument-Loops
├── Melodic/{Bass, Guitar, Keys-Piano, Synths-Pads}
├── SFX/Stabs-Hits
├── Vocals/Chops
├── Stems/{source-name}/           (Demucs stem splits)
├── Freesound/{bank-name}/         (API downloads with attribution)
├── _RAW-DOWNLOADS/                (original packs, ingested packs moved here)
├── _DUPES/                        (fingerprint-detected duplicates, review before deleting)
├── _GOLD/Bank-A/                  (saved Bank A sessions)
├── _tags.json                     (tag database, ~20,925 entries)
└── _ingest_log.json               (watcher activity log)
```

**Format**: All library files are FLAC (lossless). Output to SD card converts to 16-bit WAV.

## Web UI
Launch: `cd web && python app.py` (runs on http://localhost:5404)
- Visual pad grid mirroring the SP-404 layout
- Click pads to edit descriptions, preview audio, fetch samples
- Drag-and-drop from library sidebar or OS file explorer onto pads
- Library sidebar: browse folders + dimension-aware tag cloud
- Bank edit modal (pencil button): name, BPM, key, notes
- Pipeline controls: Fetch All, Ingest Downloads, Build, Deploy
- SD card status indicator with auto-polling
- **Vibe prompt bar**: describe a mood/genre, review parsed tags, edit draft pads, apply to bank
- **Editable parsed-tag review**: correct LLM output before applying
- Preset browser: browse, search, filter, preview, drag presets onto bank tabs
- Set selector: switch entire bank configurations instantly
- My Music: browse personal library by artist, mood, style (Plex-powered)
- Daily Bank button: generate a fresh auto preset for the current bank
- File watcher toggle with activity feed
- Disk usage panel with cleanup controls
- **Power button**: Server status dashboard showing feature availability (LLM, librosa, fpcalc, demucs, watcher) with live checkmarks. Restart Server button for clean respawns.

## Bank Preset Library

Bank configurations are standalone YAML files in `presets/`, organized by category. Presets can be browsed, searched, previewed, and dragged onto bank tabs in the web UI. Sets group 10 presets into saved configurations for different session types. The existing `bank_config.yaml` remains fully expanded for backward compatibility.

### Preset Categories
`genre/`, `utility/`, `song-kits/`, `palette/`, `community/`, `auto/`

### Preset API
- `GET /api/presets` — list/search presets (filter by category, query, tag, bpm, key)
- `GET /api/presets/<ref>` — full preset detail
- `POST /api/presets/load` — load preset into a bank
- `POST /api/presets/from-bank/<letter>` — save current bank as preset
- `POST /api/presets/daily` — generate daily auto preset
- `GET /api/sets` — list sets
- `POST /api/sets/<slug>/apply` — apply a set
- `POST /api/sets/save-current` — save current config as set

## Smart Features

Local-first creative tools. Status shown in the Power Button UI dashboard.

### Natural Language Vibe Prompts — LIVE
Describe the sound you're hearing — the system translates it into fetch parameters via a local LLM. Three parser modes (base/rag/fine_tuned). Results scored against the full library including Plex metadata. Connected to Ollama Qwen3 8B. See "Personalized Vibe Intelligence" section above for full details.

### Audio Analysis — LIVE
librosa-powered BPM, key, and loudness detection. Runs inline during ingest. Results stored in `_tags.json` with `bpm_source`, `key_source`, `loudness_db` fields. Module: `scripts/audio_analysis.py`.

### Audio Deduplication — LIVE
Chromaprint fingerprint-based duplicate detection. Runs inline during ingest (no separate pass needed). Dupes auto-move to `_DUPES/`. Found 11.5 GB reclaimable at 0.95 threshold on first full library scan. Fingerprinting also available on demand.

### Stem Splitting — LIVE
Background Demucs stem splitting for tracks >60s. Runs via ThreadPoolExecutor (non-blocking). Invocation: `python3 -m demucs`. Stems land in `Stems/{source-name}/` with metadata carried from parent track.

### Daily Bank — LIVE
Auto-generates a fresh preset each day from recent/trending library activity. Presets land in `presets/auto/`. Uses type-balanced candidate selection and rank-based weights (bugs fixed this session).

### Pattern Generation (Magenta) — DORMANT
Generate drum patterns and melodic sequences with human-feel swing using MusicVAE/GrooVAE. Outputs SP-404 .PTN pattern files. Requires Magenta checkpoints. Falls back to starter patterns if Magenta unavailable.

### Centralized Configuration
All paths and service endpoints managed through `scripts/jambox_config.py` with environment variable overrides.

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SP404_LLM_ENDPOINT` | Local LLM endpoint for vibe prompts | (disabled) |
| `SP404_LLM_MODEL` | LLM model name | `qwen3` |
| `SP404_LLM_TIMEOUT` | LLM request timeout (seconds) | `30` |
| `SP404_VIBE_PARSER_MODE` | Parser mode: base, rag, fine_tuned | `base` |
| `SP404_FINE_TUNED_LLM_ENDPOINT` | Endpoint for fine-tuned model | (disabled) |
| `SP404_FINE_TUNED_LLM_MODEL` | Fine-tuned model name | (disabled) |
| `SP404_VIBE_RETRIEVAL_LIMIT` | Max retrieval examples per query | `4` |
| `SP404_MUSICVAE_CHECKPOINT_DIR` | MusicVAE model checkpoints | (disabled) |
| `SP404_MAGENTA_COMMAND` | Magenta pattern generation command | `music_vae_generate` |
| `SP404_FINGERPRINT_TOOL` | Audio fingerprint tool | `fpcalc` |
| `SP404_DAILY_BANK_SOURCE` | Daily bank source (`recent` or `trending`) | `recent` |
| `SP404_TRENDING_FILE` | Path to trending.json | `$REPO/trending.json` |
| `SP404_SAMPLE_LIBRARY` | Sample library root | `~/Music/SP404-Sample-Library` |
| `SP404_FFMPEG` | ffmpeg binary path | `/opt/homebrew/bin/ffmpeg` |

## Key Paths (All Features)

```
scripts/jambox_config.py           # Centralized configuration
scripts/vibe_generate.py           # NL vibe -> fetch parameters (parser modes)
scripts/vibe_retrieval.py          # RAG retrieval for vibe parsing
scripts/vibe_training_store.py     # Persistent vibe session store (SQLite)
scripts/generate_patterns.py       # Magenta pattern generation
scripts/deduplicate_samples.py     # Audio deduplication
scripts/audio_analysis.py          # BPM/key/loudness detection (librosa)
scripts/daily_bank.py              # Daily preset generator
scripts/plex_client.py             # Plex DB client (read-only)
scripts/preset_utils.py            # Preset/set resolution and management
config/scoring.yaml                # Tunable scoring weights
config/vibe_mappings.yaml          # Genre→instrument mappings, keyword aliases
training/vibe/eval_model.py        # Offline eval runner
training/vibe/prepare_dataset.py   # Session → training data
training/vibe/train_lora.py        # QLoRA training script
training/vibe/compare_modes.py     # Cross-mode eval comparison
training/vibe/serve_model.py       # Local GGUF model server
training/vibe/configs/             # Training hyperparameter configs
training/pattern/readiness.py      # Pattern training readiness gates
data/evals/                        # Seed eval suite
data/vibe_sessions.sqlite          # Runtime session store (gitignored)
web/api/vibe.py                    # POST /api/vibe/generate, apply-bank, populate-bank
web/api/pattern.py                 # POST /api/pattern/generate
trending.json                      # Tag trend data
```

## Pattern Files
Pattern files (.PTN) in `ROLAND/SP-404SX/PTN/` are proprietary binary format.
Generated via `scripts/gen_patterns.py` using vendored spEdit404 (`scripts/spedit404/`).

## PAD_INFO.BIN
`ROLAND/SP-404SX/SMPL/PAD_INFO.BIN` — per-pad metadata (loop/gate/BPM).
Generated by `scripts/gen_padinfo.py` — auto-sets loop mode for pads 5-12, gate for 1-4.

## RLND WAV Chunk
SP-404SX WAVs include a proprietary "RLND" chunk (466 bytes) encoding device ID and pad index.
Injected by `scripts/wav_utils.py:inject_rlnd()` during sample conversion.

## SP-404 Ecosystem Context

### Hardware Target
Jambox targets the **SP-404A** (original, not MK2). Key differences from MK2:
- 12 pads per bank (not 16)
- No project file import — output is WAV files + PAD_INFO.BIN + patterns on SD card
- No firmware features like Loop Capture, Groove Function, Sound Generator, or Serato integration
- Community research and paid packs skew MK2 — filter accordingly

### LLM Training Data Sources (from ecosystem research)
These should feed the RAG corpus and/or synthetic training examples:
- **NearTao's Unofficial Guide** (free PDF) — the best single document on SP-404 workflow. Convert sections to Q&A pairs.
- **Resample workflow patterns** — teach the model to suggest resample chains and effect pairings
- **Pad organization conventions** from paid packs — rhythm low, melodic mid, texture high
- **SP-404 effects reference** — which effects suit which sample types (Vinyl Sim for warmth, DJFX Looper for glitch, etc.)

### Community Resources
- sp-forums.com — original SP-404 community, tips & tricks
- r/SP404 (Reddit) — active subreddit, beat showcases, technique discussion
- Key producers to study: Dibiase (chain-resampling), STLNDRMS (hybrid MPC+404), Flying Lotus (effects processing)
- LofiAndy, CremaSound, SPVIDZ — paid pack creators whose bank architectures inform Jambox's structure

Full ecosystem research doc: see `docs/SP404_ECOSYSTEM_RESEARCH.md`

## Important Notes
- The SP-404A (original, non-SX) is more restrictive — always use 44.1kHz/16-bit/mono
- FAT32 filesystem required on SD card
- Always safely eject the SD card before removing from computer
- ffmpeg is at `/opt/homebrew/bin/ffmpeg` (all scripts use absolute paths)
- Library is FLAC for storage; output to SD card is always WAV
- Vibe sessions DB is runtime-only (gitignored) — training data is exported via prepare_dataset.py
