# Training regime during Claude blackout

**Audience:** Composer, shell agents, or anyone covering the repo when the primary coding agent is offline.

## Role

Do **not** invent a new roadmap. Re-open the **Personalized JamBox intelligence plan** (capture → evals → RAG baseline → LoRA → serving; pattern training separate) and **note which phase you are in**.

Each session: **one small move forward** plus **one number that proves it** (eval metric, export line count, test pass).

## Reality check

What lives in this repo today is mostly **offline tooling + logged data + supervised fine-tuning prep**, not a 24/7 RL daemon. A long horizon of “hard training” is a **project goal**; the **immediate** path is: **more gold data, stable evals, then LoRA when metrics justify it**. Avoid RL or architecture tangents until the supervised lane is clearly winning or the project explicitly green-lights them.

## “Computer working hard” (productive load, not scope creep)

| Activity | What it does | Good signal |
|----------|----------------|-------------|
| `.venv/bin/python training/vibe/eval_model.py --mode base` | Full eval JSON: parse / draft / ranking | Exit 0; metrics stable or improving vs last run |
| `.venv/bin/python training/vibe/compare_modes.py --modes base rag` | Compare modes when LLM is configured | `base` vs `rag` diverge meaningfully when `SP404_LLM_*` is live |
| `.venv/bin/python training/vibe/prepare_dataset.py` | Exports JSONL from **reviewed** vibe sessions | Growing output under `data/training/vibe/` |
| Web vibe flow (generate → edit → apply) | Fills supervision DB | `data/vibe_sessions.sqlite` grows (gitignored) |
| `.venv/bin/python -m unittest discover -s tests -q` | Regression guard | Green before/after substantive changes |
| `.venv/bin/python scripts/check_setup.py` | Env, paths, optional LLM | No blocking issues; LLM **READY** when you want non-fallback parses |

**Avoid:** new frameworks, rewriting trainers from scratch, “quick” orchestration layers, or RL experiments **without** the eval suite moving first.

## LLM and fallback

Without `SP404_LLM_ENDPOINT` (and related env), parse paths use **keyword fallback**; eval `details` / rationale should reflect that. For apples-to-apples `rag` vs `base` comparisons, configure `.env` at the repo root and ensure the endpoint is reachable.

## Pattern-training gate

`.venv/bin/python training/pattern/readiness.py` — **exit 1** until `data/midi/` and label files exist is **normal**. Do not force pattern work to “look busy.”

## LoRA lane

`training/vibe/train_lora.py` and `training/vibe/configs/*.yaml` expect a **GPU machine and extra Python deps**. Verify scripts and paths resolve; full training is on the user’s hardware and schedule.

## Monthly mindset (stay on the rails)

- **Steady evals:** Expand `data/evals/` gold rows incrementally; re-run `eval_model`; track scores somewhere you control (spreadsheet, notes).
- **Data before weights:** Run `prepare_dataset.py` after sessions accumulate **reviewed** rows; train only when export volume and eval gaps justify it.
- **Sync with `CLAUDE.md`** for canonical paths, audio rules, and coordination with other agents.

## One-line regime

Read `CLAUDE.md`, find your phase in the personalization plan, run eval + tests + (optional) `compare_modes`; grow sessions and dataset export; **no new architecture** — clearer metrics and more supervised data until LoRA is earned.
