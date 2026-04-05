# Quality review (occasional human pass)

Automated pipelines (smart retag, vibe → fetch, ingest) keep the library moving; **someone still needs to spot-check** so bad tags or prompts do not compound.

## Long-run monitoring (ramp-down schedule)

Use a **wall-clock timer from when you start** a heavy job (e.g. `smart_retag --resume`). Adjust anchors if you sleep — pick up at the **next** tier.

| Phase | When (after start) | What to check |
|--------|---------------------|---------------|
| **Kickoff** | **+30 minutes** | **Progress:** `data/retag_checkpoint.json` `processed` / `last_updated` moved, or log lines advancing in `data/crunch_retag.log`. **Blackout → Live crunch** in the web UI. **Quick quality:** if new tags exist, `.venv/bin/python scripts/review_tag_outputs.py --limit 5 --seed 1` |
| **Hourly** | **+1 h, +2 h, +3 h, +4 h, +5 h, +6 h** (six passes) | Same **progress** checks. **Logs:** scan for `LLM timeout`, `parse fail`, `SKIP`. Optional: `--limit 5` random sample |
| **Bi-hourly** | **Every 2 h after hour 6** (e.g. +8 h, +10 h, +12 h …) until you are comfortable | Progress + **`.venv/bin/python scripts/review_tag_outputs.py --mode lowest-quality --limit 10`** + note any bad patterns |
| **Steady** | **Every 4 h** thereafter | **Full pass:** `--limit 15` random **and** `--mode lowest-quality --limit 15`; skim `_QUARANTINE/`; if vibe work ran, spot-check a preset in the UI |

**Tip:** Set repeating alarms or Calendar reminders with these labels so you do not rely on memory.

## Other cadence (ad hoc)

| When | What |
|------|------|
| After enabling a new model or prompt | 15–20 random `smart_retag_v1` rows |
| Weekly while a long retag runs | `lowest-quality` sample + a few `highest-quality` sanity checks |
| After changing `bank_config` / scoring | Fetch a bank in the UI and ear-test a handful of pads |

## Tag library (smart retag)

From repo root, with the project venv:

```bash
.venv/bin/python scripts/review_tag_outputs.py --limit 15
.venv/bin/python scripts/review_tag_outputs.py --mode lowest-quality --limit 25
.venv/bin/python scripts/review_tag_outputs.py --type-code BRK --limit 10 --markdown ~/Desktop/tag_review_scratch.md
```

Read **sonic_description**, **type_code**, **vibe/genre**, and **quality_score**. If a pattern is wrong, fix the **smart retag prompt** or vocab in `scripts/smart_retag.py` / spec docs — not one-off edits in `_tags.json`.

**Quarantine:** low `quality_score` retag can move files to `_QUARANTINE/` — skim that folder periodically.

## Vibe presets (web UI)

Use the vibe flow with **review** before apply: check parsed tags and draft pads. Reviewed sessions land in `data/vibe_sessions.sqlite` (gitignored) and can be exported with `training/vibe/prepare_dataset.py` after you are happy with them.

## Blackout / power menu

**Live crunch** shows retag checkpoint movement and log tails — use it to confirm jobs are still advancing, not as a substitute for reading tag content.

## If quality drops

1. Run `review_tag_outputs.py --mode lowest-quality`.
2. Compare with `training/vibe/eval_model.py --mode base` (parse/draft/ranking harness).
3. Roll back or tighten prompts before re-running bulk jobs (`--force` retag is expensive).
