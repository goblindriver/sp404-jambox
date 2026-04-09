# HANDOFF — Doc Sprint Assignments

**Date:** 2026-04-08
**From:** Chat
**To:** Code

---

## What's Ready

I've written the prose sections for three new docs. Here's where everything lives and what you need to do with each.

### 1. TAGGING_SPEC v4
**File:** `docs/TAGGING_SPEC_V4_PROSE.md` (Chat-authored prose)
**Your job:** Merge with mechanically-generated vocabulary tables from `tag_vocab.py`. Sections 4–7 have placeholder comments telling you exactly what to generate. The prose sections (1–3, 8–10) are final — don't edit those. Output goes to `docs/TAGGING_SPEC.md`, replacing the current version.

### 2. SCORING_ENGINE_SPEC
**File:** `docs/SCORING_ENGINE_SPEC.md`
**Your job:** Verify the config reference in the doc matches the actual `config/scoring.yaml` v7. If any weights or keys differ, update the doc to match the code (code wins). Otherwise this is ready to commit as-is.

### 3. DEPLOYMENT_RUNBOOK
**File:** `docs/DEPLOYMENT_RUNBOOK.md`
**Your job:** Verify the shell commands and paths are correct for the current repo layout. Specifically: confirm `copy_to_sd.sh` path, confirm `sd-card-template/` directory structure matches what's described, confirm `gen_padinfo.py` and `gen_patterns.py` are the correct script names. Fix any path errors, then commit.

---

## Your Independent Ship List (no Chat input needed)

These are from the CODE_BRIEF_DOC_UPDATE_PLAN. Ship them alongside or after the above:

1. **CLAUDE.md mechanical fixes** — stale retag numbers, dead path references (`jambox_tuning.py` → delete reference, `generate_patterns.py` → `gen_patterns.py`), missing vibe API endpoints, broken `SP404_ECOSYSTEM_RESEARCH.md` reference
2. **SP404_ECOSYSTEM_RESEARCH.md** — index stub for `docs/research/`. Table of contents with one-line descriptions of each file. Trivial.
3. **vibe_mappings.yaml** — add genre→instrument mappings for: baile-funk, breakcore, gqom, industrial-techno, uk-garage, world
4. **Empty preset directories** — create `presets/utility/`, `presets/palette/`, `presets/community/` with a one-line README.md in each
5. **API_REFERENCE.md skeleton** — auto-generate from Flask route definitions. Group by blueprint. Use the format I specified (endpoint, method, params, response, notes). I'll review and add context in a follow-up pass.

---

## Priority Order

1. Merge the three Chat docs (TAGGING_SPEC, SCORING_ENGINE_SPEC, DEPLOYMENT_RUNBOOK)
2. CLAUDE.md fixes
3. API_REFERENCE skeleton
4. Everything else

---

## One Rule

The three Chat-authored docs have prose sections that are final. If you find a factual error (wrong script name, wrong config key), fix it. If you disagree with a creative call (quality rubric wording, vibe/texture boundary explanation), flag it in a comment and I'll review — don't rewrite.

Go.
