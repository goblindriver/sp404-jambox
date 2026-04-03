# TODO — SP-404 Jam Box

> Shared task tracker across Chat, Code, and Cowork.
> Updated by Chat. Code and Cowork reference this for priorities.

---

## Completed

- [x] Bank layout v3 — Funk/Disco/Electroclash/Nu-Rave/Aggressive theme set
- [x] Harmonic design — all keys diatonic to C major
- [x] Tempo clustering — 112/120/128/130 BPM
- [x] YAML bank config (`bank_config.yaml`) — decoupled from scripts
- [x] Tag system — 7 dimensions (type, vibe, texture, genre, energy, source, playability)
- [x] Tag database (`_tags.json`) — 40,000+ samples tagged
- [x] Fetch pipeline with scoring and deduplication
- [x] Freesound API fallback
- [x] Web UI — pad grid, library sidebar, tag cloud, pipeline controls
- [x] Ingest pipeline (`ingest_downloads.py`)
- [x] PAD_INFO.BIN generation (loop/gate per pad)
- [x] Pattern generation via vendored spEdit404
- [x] RLND chunk injection
- [x] Naming/tagging spec (`TAGGING_SPEC.md`)
- [x] Documentation sync (README, ARCHITECTURE, PAD_MAP, CLAUDE_CODE_GUIDE, SAMPLE_SOURCES all updated to v3)
- [x] Waveform preview in web UI pad detail view
- [x] Auto-BPM detection on untagged samples (onset-based, 94.5% hit rate)
- [x] Library health check (clipping, DC offset, silence detection)
- [x] Sample deduplication (fingerprint + cosine similarity)
- [x] Demucs stem separation pipeline
- [x] Personal music library integration (My Music browser)
- [x] Background file watcher — `ingest_downloads.py --watch` with watchdog, stable file detection, _SOURCE.txt reading, auto-tagging, _ingest_log.json, web UI toggle + activity feed
- [x] Plex integration — Read-only SQLite access, 298 mood tags + 412 style tags mapped to internal vibes/genres, artist detail with bios/art/country, Plex metadata carried through stem splitting, scoring boost in fetch_samples.py
- [x] Bank preset library — Standalone YAML presets in `presets/<category>/`, sets in `sets/`, web UI preset browser with search/filter/preview/drag-to-slot, "Save as Preset" button, migrated all 9 existing banks
- [x] Smart features integration — Vibe prompts (LLM), pattern generation (Magenta/.PTN), audio deduplication (fpcalc), daily bank presets
- [x] Centralized config — `scripts/jambox_config.py` with `SETTINGS[key]` pattern and `SP404_*` env overrides
- [x] FLAC conversion — Handled during ingest pipeline
- [x] Storage overhaul — `_RAW-DOWNLOADS/` archive, ingest log, dedup pipeline
- [x] Doc patches applied — README, ARCHITECTURE, CLAUDE_CODE_GUIDE, SAMPLE_SOURCES, TODO refreshed with smart features, config system, corrections
- [x] Taste engine (Layer 1) — `scripts/taste_engine.py` with personalized system prompt wired into vibe_generate.py and smart_retag.py
- [x] Scale mapping + pattern engine — `scripts/scale_pattern.py` with arpeggio, sequence, progression, euclidean patterns
- [x] Jam session stem splitting — 4-stem Demucs split, chops, ingested to library
- [x] Songwriter preset — `presets/song-kits/jam-session-songwriter.yaml` with scale mapping + 4 patterns
- [x] 9 genre presets + 5 curated sets from Chat (playlist mining analysis)
- [x] SD card auto-scan — Reads PAD_INFO.BIN + WAV inventory on card insert, shows per-pad status in UI
- [x] Vibe-to-Bank — Full bank population from natural language prompt (LLM → 12 pads → preset → fetch)
- [x] Library expansion — 57 sample packs ingested (9,600 → 40,000+ files)

## In Progress

- [ ] **Cowork**: Ongoing sample sourcing — downloading packs to ~/Downloads watchfolder
- [ ] **Code**: Web UI refinements (ongoing)
- [ ] **Code**: Downloads triage — ingesting remaining sample packs from watchfolder/big_beat/synth_pop

## Priority 1 — Activate Dormant Features

- [ ] **Install fpcalc / Chromaprint** — `brew install chromaprint`. Run library-wide dedupe on 40k+ samples.
- [ ] **Smoke test daily bank** — Run `POST /api/presets/daily` against real library. Verify output.
- [ ] **Install Magenta / MusicVAE** — Set up checkpoints, verify pattern generation works.

## Priority 2 — Preset System Expansion

- [ ] **"Build a Set" workflow modal** — Guided UI flow for assembling a new set of 10 presets
- [ ] **Community preset import** — Import preset YAML files from external sources
- [ ] **Playlist-to-bank feature** — Select a Plex playlist → auto-generate a bank preset

## Priority 3 — Harmonic Engine

- [ ] Key-to-family mapping
- [ ] Harmonize API endpoint
- [ ] Harmonic filter in tag cloud
- [ ] Chemistry view — cross-bank compatibility visualization

## Priority 4 — Stem Splitting Priority Queue

- [ ] Block Rockin' Beats — legendary break
- [ ] Deceptacon — bass line + drum machine
- [ ] Feel It Still — Motown drum loop + bass
- [ ] I Feel Love — vocal + Moroder sequencer
- [ ] Firestarter — breaks + bass
- [ ] Teardrop — everything → Textures bank
- [ ] D.A.N.C.E. — vocal chops as performance triggers

## Priority 5 — Quality of Life

- [ ] **Trending dashboard** — Visualize trending.json data in web UI
- [ ] **Dedupe report UI** — Display dedupe results with side-by-side comparison
- [ ] **Vibe prompt history** — Save and recall previous vibe prompts
- [ ] **Batch export** — Export entire bank to SP-404 format (FLAC → WAV for all 12 pads)

## Priority 6 — Taste Engine (Phases 2-4)

- [ ] **Phase 2: Fine-tune** — QLoRA training of Qwen3 8B via MLX on Apple Silicon (~2,000 examples)
- [ ] **Phase 3: RAG** — ChromaDB indexed with sound design refs, tag taxonomy, presets
- [ ] **Phase 4: Preference learning** — Track accept/reject signals in preferences.json

## Waiting On

- [ ] **Cowork**: Riot Mode source hunting (brief delivered)
- [ ] **Cowork**: Minneapolis Machine source hunting (brief delivered)
- [ ] **Cowork**: Resume remaining briefs from session crash
- [ ] **Chat**: Genre template presets from Cowork's 9 genre templates (pending docs)
- [ ] **Chat**: Set configs for different session types

---

*Last updated by Chat + Code — April 3, 2026*
