# Bug Hunt Findings — April 3, 2026 (Session 3)

## Methodology
Full codebase audit against Session 2 handoff, Session 3 Cursor commits, and Cowork deliverables. Checked: code correctness, doc/code drift, missing deliverables, config alignment, and test coverage.

---

## BUGS (Code Issues)

### BUG-1: Root PAD_MAP.txt is v1 — gets deployed to SD card
**Severity:** Medium (actively misleading on hardware)
**File:** `PAD_MAP.txt` (repo root)
**Issue:** Root PAD_MAP.txt still shows v1 synthesized banks (Lo-Fi Hip-Hop, Witch House, Nu-Rave etc.) from the numpy synthesis era. `copy_to_sd.sh` line 40 copies THIS file to the SD card. Meanwhile `docs/PAD_MAP.txt` has the correct v3 layout. Users reading the cheat sheet on their SD card see completely wrong bank names and pad assignments.
**Fix:** Replace root `PAD_MAP.txt` with the contents of `docs/PAD_MAP.txt`, or change `copy_to_sd.sh` to copy from `docs/`.

### BUG-2: Training configs reference wrong model
**Severity:** Low (blocks future training, not current functionality)
**Files:** `training/vibe/configs/qwen2.5-7b-qlora.yaml`, `training/vibe/configs/qwen2.5-7b-draft-qlora.yaml`
**Issue:** Both training configs specify `base_model: Qwen/Qwen2.5-7B-Instruct` but Cowork's LLM research recommends Qwen3 8B, and `jambox_config.py` defaults `LLM_MODEL` to `qwen3`. When someone runs the training pipeline, the config will pull a different model than what inference uses. The Cowork research doc is explicit: "Recommended: Qwen3 8B (Primary Choice)."
**Fix:** Update training configs to `Qwen/Qwen3-8B-Instruct` (or whatever the HuggingFace model ID is for Qwen3 8B). Or create new config files `qwen3-8b-qlora.yaml` / `qwen3-8b-draft-qlora.yaml` alongside the existing ones.

### BUG-3: No web endpoint for vibe session history
**Severity:** Low (blocks data collection workflow, not core features)
**Files:** `web/api/vibe.py`
**Issue:** `vibe_training_store.py` has `list_sessions()` and `promote_dataset_status()` but there's no web API endpoint exposing them. The "collect real reviewed vibe sessions" next step (from the Cursor handoff) requires being able to browse past sessions and mark them as training-ready. Currently the only way to do this is via Python CLI.
**Fix:** Add `GET /api/vibe/sessions` (list recent sessions) and `POST /api/vibe/sessions/<id>/promote` (change dataset_status) endpoints to `web/api/vibe.py`.

---

## STALE DOCS (Doc/Code Drift)

### STALE-1: CLAUDE.md is significantly behind
**Severity:** High (Code agent reads this first — stale context = wrong decisions)
**File:** `CLAUDE.md`
**Issues:**
- Bank layout table shows old B-J layout, doesn't mention any Session 2 presets (riot-mode, minneapolis-machine, big-beat-blowout, synth-pop-dreams, brat-mode, etc.)
- No mention of vibe pipeline, parser modes (base/rag/fine_tuned), training scripts, eval suite, or session store
- No mention of `training/vibe/` or `training/pattern/` directories
- Key paths section missing: `VIBE_SESSIONS_DB`, `VIBE_EVAL_DIR`, `training/` directory
- Environment variables table missing: `SP404_VIBE_PARSER_MODE`, `SP404_FINE_TUNED_LLM_ENDPOINT`, `SP404_FINE_TUNED_LLM_MODEL`, `SP404_VIBE_RETRIEVAL_LIMIT`
- `web/api/vibe.py` endpoints not documented (generate, apply-bank, populate-bank, populate-status)
- Sample library stats still say "~9,600+ WAVs" — probably higher now after FLAC conversion and new ingests, and format is now FLAC not WAV
**Fix:** Comprehensive CLAUDE.md refresh. This is the highest-priority doc update because Code agent reads it on every session.

### STALE-2: README.md missing vibe pipeline details
**Severity:** Medium
**File:** `README.md`
**Issues:**
- Smart features section mentions vibe prompts but doesn't document parser modes, session logging, editable tag review, retrieval grounding, or eval suite
- No mention of `training/` directory or training pipeline
- Environment variables table missing the 4 new vibe-related vars
- Key paths section missing training paths
- Library stats probably stale
**Fix:** Add parser modes, training pipeline, and eval suite to Smart Features section. Add new env vars and paths.

### STALE-3: docs/TODO.md not updated for Session 2 or 3
**Severity:** Medium
**File:** `docs/TODO.md`
**Issues:**
- "In Progress" still shows generic "Cowork: Ongoing sample sourcing" — should reflect actual brief status
- Priority 1 still shows Big Beat/Synth-Pop/Brat as pending — these were delivered in Session 2
- Doesn't list any Session 3 completions (vibe pipeline, training scripts, eval suite)
- Missing new priorities: Ollama setup, fpcalc install, base vs rag comparison, expand evals, Riot Mode/Minneapolis Machine downloads
- "Waiting On" section is completely stale
**Fix:** Full TODO refresh reflecting actual status from HANDOFF_SESSION3.md.

### STALE-4: docs/ARCHITECTURE.md missing vibe training pipeline
**Severity:** Low (developers reference, not agent-critical)
**File:** `docs/ARCHITECTURE.md`
**Issues:**
- No architecture documentation for: vibe session store (SQLite), retrieval system, parser mode switching, training pipeline, eval harness, or training/pattern readiness gates
- "Future Ideas" section lists things that are now partially built (harmonic engine still future, but vibe and pattern are shipped)
**Fix:** Add "Personalized Vibe Intelligence" section covering session store, retrieval, parser modes, and training pipeline architecture.

### STALE-5: docs/HANDOFF.md is Session 1 only
**Severity:** Low (superseded by HANDOFF_SESSION2.md and HANDOFF_SESSION3.md)
**File:** `docs/HANDOFF.md`
**Fix:** Either update to point to the latest handoff, or rename to `HANDOFF_SESSION1.md` for archival. Latest should be `HANDOFF_SESSION3.md`.

---

## MISSING DELIVERABLES

### MISSING-1: 9 Session 2 presets not in repo
**Severity:** Medium (creative work done but not installed)
**Files missing from `presets/genre/`:**
- `riot-mode.yaml`
- `minneapolis-machine.yaml`
- `outlaw-country-kitchen.yaml`
- `karaoke-metal.yaml`
- `french-filter-house.yaml`
- `purity-ring-dreams.yaml`
- `crystal-chaos.yaml`
- `ween-machine.yaml`
- `azealia-mode.yaml`
**Issue:** Session 2 delivered these as a zip (`chat_playlist_mining_presets_delivery.zip`). They were "Drop in ~/Downloads for watcher auto-install" but may not have been processed if the watcher wasn't running, or if the delivery zip wasn't picked up.
**Fix:** Verify if the zip was processed. If not, manually install the 9 presets into `presets/genre/`. The preset YAML format is established — create from the Session 2 handoff specs (BPM, key, bank status are documented).

### MISSING-2: 5 Session 2 curated sets not in repo
**Severity:** Low
**Files missing from `sets/`:**
- `songwriting-session.yaml`
- `party-mode.yaml`
- `genre-explorer.yaml`
- `metal-hour.yaml`
- `tiger-dust-store.yaml`
**Issue:** Same delivery mechanism as presets — may not have been auto-ingested.
**Fix:** Create set YAML files from Session 2 specs.

### MISSING-3: Tag taxonomy doc not in repo
**Severity:** Low
**File missing:** `JAMBOX_TAG_TAXONOMY.md`
**Issue:** Session 2 produced a comprehensive 11-bank tag taxonomy. It was delivered as output but may not be in the repo. The existing `docs/TAGGING_SPEC.md` covers the original 7 dimensions but doesn't include the bank-specific taxonomy.
**Fix:** Either merge into `docs/TAGGING_SPEC.md` or add as a new doc.

---

## CLEAN (Verified Working)

These areas passed audit:

- **vibe_generate.py** — Parser mode switching (base/rag/fine_tuned) is clean. Fallback works. Retrieval context integrates properly.
- **vibe_retrieval.py** — Retrieves from sessions, presets, and library. Handles missing/empty DBs gracefully.
- **vibe_training_store.py** — SQLite schema is correct. CRUD operations look solid. Proper UTC timestamps and status tracking.
- **jambox_config.py** — All new config keys present (VIBE_PARSER_MODE, FINE_TUNED_LLM_ENDPOINT, FINE_TUNED_LLM_MODEL, VIBE_RETRIEVAL_LIMIT, VIBE_SESSIONS_DB, VIBE_EVAL_DIR). Validation is proper.
- **check_setup.py** — Reports parser mode and fine-tuned endpoint status. Good.
- **.gitignore** — `data/vibe_sessions.sqlite` and `artifacts/models/` properly excluded.
- **training/vibe/train_lora.py** — `_resolve_repo_path()` correctly resolves relative paths against REPO_DIR. The bug fix from Cursor is verified.
- **training/vibe/eval_model.py** — Evaluates parse, draft, and ranking. Loads JSONL correctly.
- **training/vibe/prepare_dataset.py** — Builds parse and draft examples from reviewed sessions. Handles missing JSON fields.
- **training/pattern/readiness.py** — Gates pattern training behind corpus/label/eval requirements. Won't let you train prematurely.
- **Eval data** — Seed suite is small (6-12 cases) but structurally correct. ranking_fixture.json aligns with prompt_to_ranking.jsonl.
- **Test coverage** — `test_personalized_training.py` covers session store, retrieval, API endpoints, parser modes, eval runner, dataset preparation, and path resolution. 
- **RAG degradation** — `vibe_generate.py` catches `IntegrationFailure` and falls back to keyword parsing. `vibe_retrieval.py` catches DB errors. Both degrade safely.
- **Web API (vibe.py)** — generate, apply-bank, populate-bank, populate-status all properly validated. Reviewed parsed tags get normalized (comma-separated strings → lists).

---

## Summary

| Category | Count | Priority |
|----------|-------|----------|
| Bugs | 3 | BUG-1 medium, BUG-2/3 low |
| Stale docs | 5 | STALE-1 high, STALE-2/3 medium, STALE-4/5 low |
| Missing deliverables | 3 | MISSING-1 medium, MISSING-2/3 low |
| Clean/verified | 14 items | — |

**Recommended fix order:**
1. BUG-1 (PAD_MAP.txt → SD card is actively wrong)
2. STALE-1 (CLAUDE.md refresh — Code agent depends on this)
3. MISSING-1 (install 9 presets from Session 2)
4. STALE-3 (TODO.md refresh)
5. BUG-3 (add session history API endpoint)
6. Everything else
