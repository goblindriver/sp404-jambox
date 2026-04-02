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
- [x] Tag database (`_tags.json`) — 9,600+ samples tagged
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

## In Progress

- [ ] **Cowork**: Ongoing sample sourcing — downloading packs to ~/Downloads watchfolder
- [ ] **Code**: Web UI refinements (ongoing)

## Backlog — Preset System

- [ ] **"Build a Set" workflow modal** — Guided UI flow for assembling a new set of 10 presets from the library
- [ ] **Community preset import** — Import preset YAML files from external sources (shared files, URLs, community repos)
- [ ] **Playlist-to-bank feature** — Select a Plex playlist → auto-generate a bank preset using tracks' mood/style/BPM metadata to define fetch rules

## Backlog — New Bank Presets

- [ ] **Big Beat Blowout** — ~130 BPM, heavy breaks, acid bass, Chemical Brothers/Prodigy/Fatboy Slim energy
- [ ] **Synth-Pop Dreams** — ~110 BPM, Fm/Am, airy pads, arps, Postal Service/MGMT/Empire Of The Sun
- [ ] **Brat Mode** — ~128 BPM, buzzy detuned synths, hard pop drums, Charli XCX/M.I.A./Slayyyter
- [ ] Convert Cowork's genre templates (9 genres from producer workflow research) into preset format
- [ ] Design curated sets for different session types (live DJ, songwriting, sound design exploration)

## Backlog — Harmonic Engine

- [ ] Map every key to diatonic family
- [ ] Harmonize API endpoint
- [ ] Harmonic filter in tag cloud
- [ ] Chemistry view showing cross-bank compatibility

## Backlog — Stem Splitting Priority Queue

- [ ] Block Rockin' Beats — legendary break
- [ ] Deceptacon — bass line + drum machine
- [ ] Feel It Still — Motown drum loop + bass
- [ ] I Feel Love — vocal + Moroder sequencer
- [ ] Firestarter — breaks + bass
- [ ] Teardrop — everything → Textures bank
- [ ] D.A.N.C.E. — vocal chops as performance triggers

## Backlog — Cowork Pipeline

- [ ] Source hunting: Big Beat Blowout samples
- [ ] Source hunting: Synth-Pop Dreams samples
- [ ] Source hunting: Brat Mode samples
- [ ] Sample pack curation survey (broad landscape scan)
- [ ] Sound design reference mood boards (5 banks)
- [ ] Playlist mining and extraction (all music playlists)

## Backlog — Infrastructure

- [ ] Bank export/import as portable packages
- [ ] CI/CD for tag database updates
- [ ] Backup strategy for _tags.json and bank_config.yaml
- [ ] Explore MK2 support (48kHz/stereo variant)

---

*Last updated by Chat + Code — April 2, 2026*
