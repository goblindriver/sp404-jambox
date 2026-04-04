# Chat Session Handoff — April 2, 2026 (Session 2)

> Drop this into the repo at docs/HANDOFF.md so the next Chat session has full context.

## What Happened This Session

### Cowork Briefs Delivered (6 total)
1. **Source Hunting: Big Beat Blowout** — breaks, acid bass, rave stabs, vocals. No licensing restrictions.
2. **Source Hunting: Synth-Pop Dreams** — pads, arps, clean drums, ethereal textures.
3. **Source Hunting: Brat Mode** — detuned synths, hard pop drums, glitch, attitude vocals.
4. **Sample Pack Curation Survey** — broad landscape scan of free/paid packs, catalog by bank fit.
5. **Sound Design References & Mood Boards** — production technique deep-dives for 5 bank concepts.
6. **Playlist Mining & Extraction** — browse all playlists, cluster analysis, stem split candidates.

**Cowork status:** Crashed mid-session (I/O mount error from disk space). Big Beat (~3.5 GB) and Synth-Pop Dreams (~1.2 GB) downloaded before crash. Session handoff doc written for recovery. 4 briefs remaining.

### Storage Overhaul
- Identified triple-copy storage problem (Downloads + archive + library = ~100 GB for 58 GB of content)
- Designed new model: FLAC library locally, no archive, internet is the archive, `_SOURCES.txt` for provenance
- Code implemented: FLAC conversion (58 GB → 15 GB, 74% savings), archive purge, Downloads cleanup. 260 MB free → 226 GB free.

### Doc Patches Delivered to Code
**Round 1 (core features):**
- PATCH_README.md — Plex, presets, watcher
- PATCH_ARCHITECTURE.md — Plex DB architecture, preset/set data model, watcher daemon
- PATCH_TODO.md — Completed items + new backlog
- PATCH_SAMPLE_SOURCES.md — Plex as metadata enrichment
- PATCH_CLAUDE_CODE_GUIDE.md — Preset/set workflows, Plex commands, watcher usage
- Code applied all patches, corrected CLI examples to actual API endpoints.

**Round 2 (smart features):**
- PATCH_README_smart_features.md
- PATCH_ARCHITECTURE_smart_features.md
- PATCH_CLAUDE_CODE_GUIDE_smart_features.md
- PATCH_SAMPLE_SOURCES_smart_features.md
- PATCH_TODO_full_refresh.md — Comprehensive backlog with priorities

### ChatGPT/Cursor Integration
A separate dev unit (ChatGPT + Cursor) built a "smart features" layer while Claude was offline:
- **Vibe prompts** — NL prompt → LLM → fetch parameters → ranked results (uses existing score_from_tags with Plex bonuses)
- **Pattern generation** — Magenta MusicVAE/GrooVAE → MIDI → audio (120s subprocess timeout added by Code)
- **Audio deduplication** — Chromaprint fingerprinting, ingest hook via --dedupe
- **Daily bank** — Auto-preset from trending tags, saves to presets/auto/ via preset_utils
- **Config centralization** — jambox_config.py, env-backed SETTINGS[...], all hardcoded paths eliminated

Code reviewed, found no conflicts, applied one fix (Magenta timeout), merged. 15/15 tests pass.

**Multi-agent protocol established:** ChatGPT/Cursor = "night shift contributor." Uses feature branches, submits PRs, Code reviews and merges. Handoff docs both directions.

### Bank Presets Drafted (3 new)
- `big-beat-blowout.yaml` — 130 BPM, Em, Chemical Brothers/Prodigy energy
- `synth-pop-dreams.yaml` — 110 BPM, Fm, Postal Service/MGMT vibes
- `brat-mode.yaml` — 128 BPM, Gm, Charli XCX/M.I.A. attitude

All use correct preset YAML format with 3-4 keywords per pad. Ready to drop into `presets/genre/`.

## What Still Needs Doing

### Immediate
- [ ] Code: Apply round 2 doc patches (smart features)
- [ ] Code: Drop 3 new preset YAMLs into `presets/genre/`, verify in web UI
- [ ] Code: Install fpcalc (`brew install chromaprint`), run first library dedupe
- [ ] Cowork: Restart session with handoff doc, resume remaining 4 briefs

### Soon
- [ ] Code: Set up local LLM endpoint for vibe prompts
- [ ] Code: Smoke test daily bank against real library
- [ ] Chat: Convert Cowork's 9 genre templates into preset YAML format (pending docs)
- [ ] Chat: Design curated sets for different session types

### Later
- [ ] Code: Install Magenta for pattern generation
- [ ] Code: Build "Build a Set" workflow modal
- [ ] Code: Playlist-to-bank feature
- [ ] Code: Harmonic engine (key families, harmonize endpoint, chemistry view)
- [ ] Code: Stem splitting priority queue (7 tracks from playlist analysis)
