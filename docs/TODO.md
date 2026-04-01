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

## In Progress

- [ ] **Cowork**: Ongoing sample sourcing — downloading packs to ~/Downloads watchfolder
- [ ] **Code**: Web UI refinements (ongoing)

## Backlog — Code

- [ ] Auto-BPM detection on untagged samples (librosa)
- [ ] Sample deduplication (detect near-duplicate WAVs)
- [ ] Waveform preview in web UI pad detail view
- [ ] Bank export/import as portable packages
- [ ] Library health check (find clipping, DC offset, silence)

## Backlog — Chat / Creative Direction

- [ ] Research additional genre banks (dub techno? jungle? g-funk?)
- [ ] Explore MK2 support (48kHz/stereo variant)
- [ ] Design "performance set" bank ordering for live gigs
- [ ] Curate a "starter kit" bank config for new users

## Backlog — Infrastructure

- [ ] NAS integration — move library to QNAP at `/Volumes/Temp QNAP/Audio Production`
- [ ] CI/CD for tag database updates
- [ ] Backup strategy for _tags.json and bank_config.yaml

---

*Last updated by Chat — April 2026*
