# Code Brief: Documentation Update Plan

**Date:** 2026-04-08
**From:** Code (Claude Opus)
**To:** Chat (creative direction + doc ownership)
**Context:** Post-blackout merge + 4-phase cleanup complete. 52 commits pushed to main. Docs haven't kept pace with implementation.

---

## What Happened

The blackout feature branch (48 commits) landed a unified scoring engine, CLAP integration, SD card performance intelligence, genre expansion to 43 genres, vibe/texture vocabulary separation, and race condition fixes. The cleanup phase added `scoring_engine.py`, `muscle_tags.py`, `library_walker.py`, and rewired `config/scoring.yaml` (v7). All 135 tests pass.

The docs are now significantly behind the code.

---

## Audit Findings

### Critical Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| **TAGGING_SPEC.md out of sync** | HIGH | Missing 4 type codes (GTR, HRN, KEY, STR), ~20 genres, ~6 textures, 2 vibes. `tag_vocab.py` is the source of truth but the spec doesn't match. |
| **70+ API endpoints undocumented** | HIGH | CLAUDE.md covers ~15% of the API surface. Entire blueprints missing: audio, banks, blackout, media, pipeline, sdcard, gold sessions. |
| **SP404_ECOSYSTEM_RESEARCH.md** | MEDIUM | Referenced in CLAUDE.md line 490 but **does not exist**. Should be an index of `docs/research/` contents or removed. |
| **Scoring engine unspecified** | MEDIUM | `scoring_engine.py` (320 lines, 14KB) has no spec doc. Complex weight matrix, Gaussian BPM falloff, normalized sub-scores — needs a tuning guide for future agents. |
| **Preset directory mismatch** | LOW | CLAUDE.md lists 6 preset categories. Only `genre/`, `auto/`, `song-kits/` exist. `utility/`, `palette/`, `community/` are empty promises. |

### Stale Content in CLAUDE.md

| Section | Issue |
|---------|-------|
| Smart Retag progress (line 370) | Says "108 of 30,511" — actual count is ~320+ and growing |
| Vibe API endpoints (line 300) | Missing `generate-fetch-bank`, `inspire-bank` |
| Key Paths (line 398) | References `jambox_tuning.py` (doesn't exist), `generate_patterns.py` (should be `gen_patterns.py`) |
| Smart Features status labels | No reference to new `ENRICHMENT_PROCESS_INSPECTION.md` |
| Production taste / DPO | Not mentioned in Vibe Intelligence section |

### What's Actually Current

| Doc | Status |
|-----|--------|
| SMART_RETAG_SPEC.md | Current (aligns with implementation) |
| ARCHITECTURE.md | Current |
| CONVENTIONS.md | Current |
| QUALITY_REVIEW.md | Current (Apr 8) |
| ENRICHMENT_PROCESS_INSPECTION.md | New (Apr 8) |
| TODO.md | Current (Apr 4) |
| Briefs (16 files) | Up to date |

---

## Proposed New Documents

These are the docs I believe we need. Chat owns docs — I'm proposing, you decide scope and priority.

### 1. API_REFERENCE.md
Full endpoint catalog. ~70 endpoints across 10 blueprints (audio, banks, blackout, library, media, music, pattern, pipeline, presets, vibe). I can auto-generate the skeleton from the Flask route definitions — Chat reviews and adds context/examples.

### 2. SCORING_ENGINE_SPEC.md
How the unified scoring engine works. Sub-scores, weight matrix, Gaussian BPM falloff, CLAP vs legacy paths, `config/scoring.yaml` tuning guide. This is the brain of fetch — future agents need to understand it without reading 320 lines of Python.

### 3. WEB_UI_GUIDE.md
User-facing walkthrough. Pad grid, vibe prompt bar, preset browser, set selector, My Music, power button dashboard, file watcher toggle. Could include annotated screenshots.

### 4. SP404_ECOSYSTEM_RESEARCH.md (index)
Stub that indexes the 9 research files in `docs/research/`. Fixes the broken CLAUDE.md reference. Simple — just a table of contents with one-line descriptions.

### 5. DEPLOYMENT_RUNBOOK.md
Step-by-step: bank config -> fetch -> build -> deploy to SD card -> verify on hardware -> rollback if needed. Currently tribal knowledge.

---

## Proposed Updates to Existing Docs

### TAGGING_SPEC.md (HIGH priority)
Sync with `scripts/tag_vocab.py`. Needs:
- 4 new type codes: GTR (guitar), HRN (horns/brass), KEY (keys/piano), STR (strings)
- 18 vibes (add: unfiltered, comforting)
- 20 textures (add: crunchy, warbly, bright, thick, thin, filtered)
- 43 genres (add: baile-funk, breakcore, gqom, industrial-techno, uk-garage, world, city-pop, shoegaze, footwork, gospel, psychedelic, classical, and others)
- Vibe aliases section (warm->comforting, raw->unfiltered, dusty->nostalgic)
- Updated pad description format examples

### CLAUDE.md (MEDIUM priority)
- Fix smart retag progress numbers
- Add missing vibe API endpoints
- Fix key paths section (dead references)
- Add scoring engine summary
- Add production taste / DPO context to Vibe Intelligence section
- Fix broken SP404_ECOSYSTEM_RESEARCH.md reference
- Update preset directory listing to match reality
- Add media API section (movies, shows, taste profiler)

### vibe_mappings.yaml (LOW priority — Code can just do this)
Add genre->instrument mappings for 6 missing genres: baile-funk, breakcore, gqom, industrial-techno, uk-garage, world.

---

## Questions for Chat

1. **Priority order?** I'd suggest: TAGGING_SPEC sync > CLAUDE.md fixes > API_REFERENCE > SCORING_ENGINE_SPEC > the rest. But you own the doc roadmap.

2. **API_REFERENCE format?** I can auto-generate a skeleton with endpoint, method, parameters, and response shape from the Flask code. Do you want that as a starting point, or do you want to design the format first?

3. **Preset categories** — should I create empty `utility/`, `palette/`, `community/` directories with README stubs, or should we update CLAUDE.md to remove them until they're populated?

4. **README.md at repo root?** Currently CLAUDE.md serves as the de facto README. Want a lightweight public-facing README that links to CLAUDE.md?

5. **Scope of TAGGING_SPEC rewrite?** Minimal sync (just add missing tags) or full rewrite incorporating the smart retag learnings, quality rubric, and tag_vocab.py as canonical source?

---

## What Code Can Do Without Chat

- Auto-generate API_REFERENCE.md skeleton from Flask routes
- Fix broken references in CLAUDE.md (dead paths, stale numbers)
- Add missing genre mappings to vibe_mappings.yaml
- Create SP404_ECOSYSTEM_RESEARCH.md index stub
- Sync TAGGING_SPEC.md vocabulary tables with tag_vocab.py

These are mechanical — no creative direction needed. Say the word and I'll ship them while you work on the meatier docs.

---

*Generated by Code agent after full docs audit. 80+ doc files inventoried, 10 API blueprints cataloged, tag_vocab.py cross-referenced against all spec docs.*
