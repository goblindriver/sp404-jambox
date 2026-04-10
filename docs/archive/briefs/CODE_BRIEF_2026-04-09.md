# Code Brief — 2026-04-09

**Session:** Doc sprint + bug hunt + menu bar launcher
**Agent:** Code (Opus)
**Duration:** ~2 hours

---

## What Shipped

### Documentation (8 files)

1. **TAGGING_SPEC.md — full rewrite (v4)**
   Chat prose sections (1–3, 8–10) preserved verbatim. Sections 4–7 generated mechanically from `tag_vocab.py`: 18 vibes, 21 textures, 43 genres grouped by 8 families, all alias tables. Fixed two factual errors in Chat's decision tree (`KCK`→`KIK`, `PER`→`PRC`). This is now the single human-readable reference for the tag system.

2. **CLAUDE.md — mechanical fixes**
   - Library size: ~20,925 → ~30,700 FLACs
   - Tag database: ~20,925 → ~26,700 entries
   - Smart retag: 108 → ~700 tagged files
   - Added 2 missing vibe endpoints (inspire-bank, generate-fetch-bank)
   - Fixed ecosystem research reference
   - Updated vibe dimension examples (removed `warm`, added 3 new v4 terms)
   - Added `chromatic` to playability examples

3. **API_REFERENCE.md — skeleton (78 routes)**
   Auto-generated from all 11 Flask blueprints. Format per Jason's spec (endpoint, blueprint, params, response, notes). Sets routes marked as unimplemented. Ready for Chat's context/examples review pass.

4. **DEPLOYMENT_RUNBOOK.md** — Placed in docs/. All paths verified correct.

5. **SP404_ECOSYSTEM_RESEARCH.md** — Index stub linking all 9 research docs.

6. **README.md** — Updated to Tiger Dust Block Party layout, smart features overview, links to all docs. No duplication.

7. **Preset directory stubs** — Created `presets/palette/` and `presets/community/` with README files.

### Code Fixes (3 files)

8. **plex_client.py** — Migrated MOOD_TO_VIBE mapping: `warm` → `comforting` for 6 moods (groovy, sensual, sultry, funky, smooth, silky). Aligns Plex metadata with TAGGING_SPEC v4 vibe/texture boundary.

### Tooling (2 files)

9. **Menu bar launcher** — `tools/jambox_menubar.py` (rumps-based macOS status bar app). Shows server status, library count, SD card state. Quick actions: Open UI, Start/Stop Server, Fetch All, Ingest, Deploy, Daily Bank. Desktop .app wrapper at `~/Desktop/Jambox.app`.

10. **Bootstrap fix** — `.venv` was missing. Ran `bootstrap.sh`, installed deps. Fixed `launch.json` to use venv python and correct model name.

---

## What Was Skipped (Per Jason's Instructions)

- **SCORING_ENGINE_SPEC.md** — Jason said Chat owns this. See config drift findings below.
- **WEB_UI_GUIDE.md** — Deferred, UI still changing.
- **vibe_mappings.yaml** — All 6 missing genres were already present. No changes needed.

---

## Bug Hunt Results

### Test Suite: 153 tests, 151 pass, 2 fail

| Test | Status | Notes |
|------|--------|-------|
| All 151 other tests | PASS | Full coverage across 15 test files |
| `test_evaluate_ranking_uses_fixture_library` | FAIL | `top1_accuracy: 0.0` — ranking eval returns 0 matches against fixture |
| `test_rank_library_matches_reuses_score_cache` | FAIL | `rank_library_matches` returns 0 results |

**Root cause:** Both failures trace to the same issue — `rank_library_matches` returns zero candidates against the eval fixture. Likely the fixture's tag structure doesn't match what the scoring engine's query parser expects, or there's a minimum score threshold filtering everything out. The ranking eval confirms: 0/6 queries match. Parse and draft evals are strong (type_code: 100%, playability: 100%, pad_prefix: 100%).

### API Health: 78 endpoints, 1 broken

| Issue | Severity | Detail |
|-------|----------|--------|
| `POST /api/vibe/generate` → 500 timeout | **High** | The vibe generate endpoint times out with qwen3:32b (~35s limit). Works fine with 8b. Either increase `SP404_LLM_TIMEOUT` or default to 8b for the generate subprocess. |
| Sets endpoints → 404 | Medium | `/api/sets`, `/api/sets/{slug}/apply`, `/api/sets/save-current` are documented but not implemented. Marked as "Not Yet Implemented" in API_REFERENCE. |
| Discogs model download race | Low | Multiple threads trigger simultaneous downloads on startup. Cosmetic log spam only. |

### Documentation Audit: Clean after fixes

All cross-references verified. Tag vocab tables match `tag_vocab.py` exactly. Flask route count matches. Research index complete. One remaining low-severity gap: the `FCTRY/` directory in `sd-card-template/` is undocumented in the runbook (factory reset data, doesn't affect workflow).

---

## Scoring Engine Config Drift (For Chat's SCORING_ENGINE_SPEC)

This is the biggest finding. The spec Chat wrote has significant structural drift from reality:

### What the spec gets wrong

1. **Invents a `dimensions:` section** that doesn't exist in `scoring.yaml` or code. The actual YAML uses a flat `weights:` dict.
2. **Invents a `legacy:` section** with a `plex_skip_penalty` that doesn't exist anywhere in the codebase.
3. **Wrong function signature** — describes `method="auto"` parameter; actual detection is via `clap_similarity` kwarg.
4. **Describes `get_tags()` abstraction** for ARCH-1 SQLite migration that was never built.
5. **Places score cache in scoring_engine** — it's actually in `jambox_cache.py`, managed by `fetch_samples.py`.

### Hardcoded values that should be in config

5 weights in `_weighted_sum()` are hardcoded literals, not pulled from scoring.yaml:
- `playability: 0.15`, `duration: 0.10`, `legacy scale: 0.6`, `key_compat: 0.33`, `energy_mismatch: -0.66`

### Dead config keys

16 of 22 keys in `weights:` are **never read** by `scoring_engine.py`. They appear to be vestiges from the pre-blackout scoring engine that weren't cleaned up during the merge. The `clap:` section also has 7 dead keys (`bpm_close_bonus`, `bpm_near_bonus`, `key_exact_bonus`, `key_compatible_bonus`, `playability_mismatch_penalty`, `duration_mismatch_penalty`, `min_similarity`).

### Recommendation

The spec needs to be rewritten from the actual code, not the idealized config. `scoring_engine.py` (417 lines) is the source of truth. The config cleanup (extracting hardcoded values, removing dead keys) is a separate code task.

---

## What's Next (Suggested Priorities)

1. **Smart retag acceleration** — Still at ~700/30,700 (2.3%). This remains the #1 blocker for fetch quality. The retag checkpoint hasn't advanced since April 4.
2. **Scoring config cleanup** — Extract the 5 hardcoded weights into scoring.yaml, remove the 23 dead keys. Then rewrite the spec from code.
3. **Ranking eval fix** — The 0/6 ranking failures need investigation. Likely a fixture format mismatch.
4. **Vibe generate timeout** — Either bump `SP404_LLM_TIMEOUT` for 32b, or configure the generate endpoint to use 8b while retag uses 32b.
5. **Sets API implementation** — 3 documented endpoints with no routes.
6. **Plex `warm` → `comforting` migration** — Code done, but existing Plex-derived tags in `_tags.json` still have `warm` as a vibe. Need a migration pass on the tag database.
