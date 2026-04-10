# CODE BRIEF — Blackout Branch Audit
**Date:** 2026-04-08
**From:** Code Agent (Opus)
**To:** Chat
**Branch:** `feat/blackout-training-dashboard` (48 commits, 134 files, +15,886/-2,629 lines)
**Tests:** 134 passing

---

## Context

Jason asked me to audit the `blackout` feature branch — work done with other models while I was away. My job: assess quality, determine what's worth keeping, and plan the merge + optimization pass. I did a deep four-agent audit of every changed file. Here's what Chat needs to know to build the plan.

---

## Branch Topology

- Branched from `main` at `0bd5ab3`
- 48 commits, tip at `4291303`
- `origin/main` has only the first commit (`93a6fcc`); the other 47 are branch-only
- Clean fast-forward merge possible — no conflicts
- All 134 tests pass on the branch

---

## What Was Built (The Good Stuff)

### New Engines
| Script | Lines | What It Does | Quality |
|--------|-------|-------------|---------|
| `clap_engine.py` | 426 | CLAP semantic audio search — cosine similarity on embeddings | Excellent |
| `discogs_engine.py` | 409 | Discogs genre + danceability via ONNX model | Good |
| `discogs_fetch_bridge.py` | 139 | Genre token extraction for fetch scoring | Good |
| `card_intelligence.py` | 608 | Three-tier SD card reader (device/jambox/user samples) | Very Good |
| `tag_vocab.py` | 123 | Single source of truth for all tag vocabularies | Excellent |

### Smart Retag Hardening
- Per-file SQLite persistence (no more losing work on crash)
- Worker threading with configurable caps (default 3, max 16)
- Thread-safe stats via locks
- Slim checkpoints (progress counters only, SQLite is source of truth)
- LLM routing by duration (primary model for short samples, 8b for long)

### Scoring Overhaul
- CLAP embeddings as primary ranking signal (cosine similarity 0-1)
- Legacy tag-based scoring as fallback when no embeddings
- Diverse sampling via `choose_diverse_match()` with fetch history cooldown
- Energy dimension scoring (+3 match, -2 mismatch)
- Discogs keyword bonuses in CLAP path
- Danceability threshold checks for dance/groove/party queries
- Score version bumped to 6 (was 1)

### Web UI
- Stepped vibe workflow: generate → review tags → save preset → load → fetch
- Blackout training dashboard (host metrics, crunch progress, feature status)
- SD Card Intelligence panel
- CLAP/Discogs status in power menu
- Various UX polish (power menu dismiss, mutual exclusion, lock-state)

### Library Tools
- `library_trim.py` — Multi-pass library pruning (duration, dedup, quality)
- `tag_hygiene.py` — Folder-aware rule-based tag fixes
- `audit_retag_effectiveness.py` — Coverage vs gaps measurement
- `low_rank_audit.py` — Pad curation scoring with severity ratings
- `muscle_tags_round1-4.py` — Bulk type_code corrections
- `move_long_samples_to_hold.py` — Isolate >60s samples
- `review_tag_outputs.py` — Manual QA sampling tool
- `benchmark_ollama_models.py` — Model comparison harness

### Hardening (28+ bugs fixed across 10 commits)
- Atomic writes for tag DB and config
- Path traversal protection
- Standardized API error responses
- Global error handlers
- Connection safety for async endpoints
- Centralized SKIP_DIRS

---

## What Needs Work (The Honest Part)

### Architecture Issues

**1. Dual scoring paths are disconnected**
The CLAP path uses hardcoded bonus values (0.03, 0.018, etc.) while the legacy path uses `scoring.yaml` weights. Changing weights in the config **only affects the fallback path**. The `weights` dict is loaded in the CLAP function but never referenced. This means tuning scoring.yaml does nothing when CLAP is active (which is the intended primary path).

**2. Three dead weights in scoring.yaml**
`bed_complement` (3), `toolkit_survival` (5), `session_survival` (2) — defined but zero references in any scoring logic. Config noise.

**3. SD card performance bonuses are orphaned**
card_intelligence collects pattern usage, BPM adjustments, and velocity data. These get scored in the legacy tag path (+4, +3, +2) but are completely ignored in the CLAP path. The intelligence pipeline works; it's just not wired to the primary scorer.

**4. muscle_tags is copy-paste x4**
Four separate scripts (round1 through round4) with ~90% identical code. Same `_patch()` helper duplicated four times. Same imports, same load/save pattern. Needs consolidation into one script with a rule config.

**5. Library walker duplicated**
`_walk_library_audio()` appears in both clap_engine.py and discogs_engine.py with nearly identical logic. Should be extracted to a shared utility.

### Frontend

**app.js is a 2,935-line monolith** — no module system, global state object, innerHTML without sanitization (XSS risk), no error boundaries. It works for the happy path but is fragile. This is the biggest tech debt item but also the hardest to address incrementally.

### Race Conditions
- Job state dicts (`_vibe_jobs`, `_retag_jobs`) have lock gaps between existence checks and access
- Tag DB cache globals in library.py aren't thread-safe
- Watcher state set to "running" before watcher actually starts

### Scoring Calibration
- Score cache grew from 100→500 results per entry (5x memory) with no clear justification
- BPM scoring still uses 3-tier step function instead of smooth interpolation
- No A/B testing or quality metrics comparing CLAP vs legacy match quality

---

## Tagging Schema Opportunities

Now that `tag_vocab.py` exists as the canonical vocabulary, these optimizations become tractable:

1. **Dimension overlap** — `dusty`, `raw`, `warm` exist in both vibe AND texture. A sample tagged "warm" gets double-scored (+6 instead of +3). Either deduplicate across dimensions or make scoring dimension-aware.

2. **quality_score not in CLAP scoring** — Smart retag extracts it (1-5), stores it, but the CLAP path never uses it. Easy win.

3. **Genre-aware weight profiles** — Ambient queries should prioritize duration/texture; house queries should prioritize BPM/energy. Currently one-size-fits-all.

4. **Plex play count not in CLAP path** — 33K tracks of listening data available but only the legacy fallback uses it.

5. **Genre mappings incomplete** — tag_vocab knows 30+ genres but vibe_mappings.yaml only maps 12 to instruments. Prompts for "afrobeat" or "city-pop" fall back to generic SYN/KEY.

---

## Merge Verdict

**All 48 commits are worth keeping.** The work is real and addresses genuine gaps. The issues are integration/polish, not fundamentals. Clean fast-forward merge, then targeted cleanup passes.

### Suggested Priority Order for Cleanup Plan

**Tier 1 — Wire it right (before using in anger)**
- Unify CLAP/legacy scoring so config changes affect both paths
- Remove dead weights from scoring.yaml
- Wire SD card performance bonuses into CLAP path
- Consolidate muscle_tags into single script
- Extract shared library walker

**Tier 2 — Scoring quality (makes fetch results better)**
- Resolve dimension overlap in tag vocabulary
- Add quality_score + Plex play count to CLAP scoring
- Expand genre→instrument mappings to cover all known genres
- Smooth BPM interpolation
- Right-size score cache (500 is probably overkill)

**Tier 3 — Robustness (prevents surprises)**
- Fix race conditions in job state management
- Thread-safe tag DB cache
- Fix watcher state initialization order
- Add error boundaries to app.js critical paths

**Tier 4 — Polish (nice to have)**
- Genre-aware scoring weight profiles
- app.js modularization
- API response format standardization
- Additional test coverage for threading edge cases

---

## What I Need From Chat

A step-by-step plan I can follow that:
1. Sequences the merge and cleanup in the right order
2. Tells me which optimizations to bundle vs. separate commits
3. Flags any creative/taste decisions (e.g., how to resolve vibe vs texture overlap — rename? separate? both?)
4. Considers impact on the running smart retag process (don't break what's working)
5. Accounts for Jason's actual workflow — he's building banks for live jamming, not running a CI pipeline

Looking forward to the plan.
