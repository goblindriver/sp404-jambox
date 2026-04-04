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
- [x] SP404A Field Manual — #1 LLM training doc for SP-404A context
- [x] Tiger Dust Block Party — 10 presets + curated set
- [x] Riot Mode + Minneapolis Machine — Bank concepts defined, set YAMLs ready
- [x] Cross-media taste profiler — Movies/books/games/music → vibe fingerprint
- [x] Multitrack stem ingestion — 500+ stems (Marvin Gaye, NIN, Phoenix, Nirvana, etc.)
- [x] Movie clip extraction pipeline
- [x] DPO training architecture designed
- [x] RL pipeline approved by Chat
- [x] Cowork plugins installed — HF connector, Engineering Plugin, Plugin Creator, Scheduled Tasks
- [x] Cowork research delivered — UTS (CVPR 2026), DPO frameworks, CLAP model comparison, film SFX databases, MIDI corpus

## Active — Running Now

- [ ] **Smart retag** — qwen3:32b running on ~30,718 files. ~42s/file, ~250 processed. **38% error rate needs investigation.** ~15 day run. DO NOT INTERRUPT.

## CRITICAL — ARCH-1: SQLite Migration

- [ ] **Code**: Migrate `_tags.json` → SQLite (`data/jambox.db`). Schema spec in `CODE_BRIEF_session4.md`. Must complete before retag finishes (~15 days). Dual-write during transition.

## Session 4 — Active Priorities

### Code (CODE_BRIEF_SESSION4.md)
1. [ ] **Error rate triage** — Categorize 38% failure rate. Top buckets: parse failure, OOM, file read, schema validation. Patch top failure mode, re-run failed files.
2. [ ] **Docs reorg** — Run `docs_reorg.sh`, fix broken refs. See `CONVENTIONS.md` for rules.
3. [ ] **Watcher expansion** — Add document routing to `ingest_downloads.py --watch`. Route per `CONVENTIONS.md` routing table. Normalize filenames to SCREAMING_SNAKE_CASE. Audio intake unchanged.
4. [ ] **ARCH-1 SQLite migration** — See above. Includes CLAP embeddings table.
5. [ ] **Plugin v0.1.1** — Sub pad fix (retrigger button, not 13th slot, 120 pads total). Freesound removal. SP-404SX folder structure verification.

### Cowork (COWORK_BRIEF_session4.md)
5. [ ] **Riot Mode sourcing** — 30-50 samples via Splice. Staging: `_staging/riot-mode/`
6. [ ] **Minneapolis Machine sourcing** — 30-50 samples via Splice. Staging: `_staging/minneapolis-machine/`
7. [ ] **Stem-split queue** — Priority batch from 500+ ingested stems.
8. [ ] **Error rate log analysis** — Pull 20 failed files, categorize failure reasons, report back.
9. [ ] **UTS dataset profiling** — Download AudenAI/UTS (MIT, 400K clips), tag overlap analysis with Jambox vocabulary.
10. [ ] **Track OpenBEATs + Qwen3-Omni-Captioner fine-tunes** — Flag if music-specific versions appear.

### Chat (This Session)
11. [ ] **Production taste prompt** — Draft the re-vibe prompt encoding Jason's "party at the end of the world" philosophy. Production target: hype > warm > soulful.
12. [ ] **DPO data strategy** — Define how preference pairs are generated. Preset-derived + manual correction hybrid. Informed by Cowork's DPO research (SFT → DPO, 1K-5K pairs, Unsloth + TRL).
13. [ ] **TODO update** — ✅ This file.
14. [ ] **Code + Cowork briefs** — ✅ Delivered.

## Later — Post-Retag

- [ ] **Re-vibe pass** — Run production taste prompt across all tagged samples. Generate vibe_score.
- [ ] **TF-IDF vocabulary emergence** — Run on sonic_descriptions in SQLite. Surface missed tags. V2 taxonomy.
- [ ] **CLAP embedding pass** — `laion/larger_clap_music`, 512-dim, ~1-2 hours overnight for 30K files. Store in SQLite `clap_embeddings` table.
- [ ] **SFT fine-tune** — Distill qwen3:32b → Qwen3 7B via Unsloth + QLoRA. 1-2K high-quality training pairs from retag outputs.
- [ ] **DPO training** — 1K+ preference pairs from review UI corrections. Unsloth PatchDPOTrainer + TRL. 1 epoch, lr=5e-5, β=0.1.
- [ ] **GGUF export** — Merge DPO adapter → FP16 → GGUF → Ollama `jambox-vibe` model.
- [ ] **UTS calibration eval** — Run Jambox tagger against UTS ground truth for baseline accuracy.
- [ ] **Optimization measurements** — Before/after metrics on tag quality, vibe alignment, error rate.

## Backlog

### Preset System
- [ ] "Build a Set" workflow modal
- [ ] Community preset import
- [ ] Playlist-to-bank feature

### Harmonic Engine
- [ ] Key-to-family mapping
- [ ] Harmonize API endpoint
- [ ] Harmonic filter in tag cloud
- [ ] Chemistry view — cross-bank compatibility

### Stem Splitting Queue
- [ ] Block Rockin' Beats — legendary break
- [ ] Deceptacon — bass line + drum machine
- [ ] Feel It Still — Motown drum loop + bass
- [ ] I Feel Love — vocal + Moroder sequencer
- [ ] Firestarter — breaks + bass
- [ ] Teardrop — everything → Textures bank
- [ ] D.A.N.C.E. — vocal chops as performance triggers

### Quality of Life
- [ ] Trending dashboard — Visualize trending.json in web UI
- [ ] Dedupe report UI — Side-by-side comparison
- [ ] Vibe prompt history — Save and recall
- [ ] Batch export — Full bank to SP-404 format

### Taste Engine (Remaining Phases)
- [ ] Phase 2: Fine-tune — QLoRA (now SFT → DPO per Cowork research)
- [ ] Phase 3: RAG — ChromaDB with sound design refs, taxonomy, presets
- [ ] Phase 4: Preference learning — Accept/reject signals in review UI

---

*Last updated by Chat — April 4, 2026 (Session 4)*
