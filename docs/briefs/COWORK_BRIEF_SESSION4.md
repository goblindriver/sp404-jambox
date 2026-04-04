# COWORK BRIEF — Session 4
**Date:** 2026-04-04
**From:** Chat (Claude)
**To:** Cowork Agent
**Project:** Jambox (SP-404A Sample Production System)

---

## Context

Smart retag is running on ~30,718 files using qwen3:32b (~42s/file, ~15-day run). 250 files processed so far. 38% error rate needs investigation but the run should continue — do not interrupt it.

Two new bank concepts — **Riot Mode** and **Minneapolis Machine** — emerged from YouTube playlist mining in Session 3 and have curated set YAMLs ready. Download and stem-split work is needed to populate them.

## Priority Tasks

### 1. Sample Sourcing — Riot Mode Bank
**Goal:** Source raw material for the Riot Mode preset (riot grrrl / punk / noise energy).

**Approach:** Use Splice and similar licensed sample platforms over direct scraping. Search for:
- Distorted guitar loops, power chord stabs
- Aggressive drum breaks, fast punk beats
- Shouted/screamed vocal chops, crowd noise
- Feedback textures, amp noise, lo-fi room tone

**Target:** 30–50 high-quality one-shots and loops. WAV format, 44.1kHz/16-bit (SP-404A native). Organize into a staging folder: `~/Music/SP404-Sample-Library/_staging/riot-mode/`

### 2. Sample Sourcing — Minneapolis Machine Bank
**Goal:** Source raw material for the Minneapolis Machine preset (Prince-adjacent funk/synth).

**Approach:** Same Splice-first strategy. Search for:
- Linn drum / LinnDrum-style hits and patterns
- Funky synth bass lines, Oberheim-style pads
- Clavinet and Rhodes chops
- Tight funk guitar scratches, muted stabs
- Falsetto vocal textures (royalty-free)

**Target:** 30–50 samples, same format specs. Staging folder: `~/Music/SP404-Sample-Library/_staging/minneapolis-machine/`

### 3. Stem Splitting Queue
**Status:** 500+ multitrack stems already ingested (Marvin Gaye, NIN, Phoenix, Nirvana, etc.)

**Action:** Continue processing the stem-split queue. Priority order:
1. Stems that align with existing preset vibes (Tiger Dust Block Party, Riot Mode, Minneapolis Machine)
2. Drums and percussion stems (highest utility for SP-404 pad mapping)
3. Melodic/harmonic stems (bass, keys, synths)
4. Vocal stems (last — most context-dependent)

**Output format:** WAV 44.1kHz/16-bit, filed into `~/Music/SP404-Sample-Library/_staging/stems-split/`

### 4. Error Rate Investigation Support
**Context:** Smart retag showing 38% error rate on first 250 files.

**Action:** If you have access to retag logs, pull a sample of 20 failed files and categorize failure reasons:
- Model timeout / OOM?
- Malformed JSON response from qwen3:32b?
- File read errors (corrupt WAV, missing metadata)?
- Tag schema validation failures?

Report findings back so Chat and Code can triage.

## Constraints & Reminders
- **Hardware:** Jason's machine is an M3 iMac 24GB — be mindful of concurrent resource usage while retag is running
- **SP-404A specs:** 120 pads total (banks A–J, 12 pads each). Sub pad is a hardware retrigger button, NOT a 13th sample slot
- **Banks A–B** are internal memory (survive SD card swaps) — don't target these for staging
- **No Freesound API** — it's been removed from the project
- **Repo:** `/Users/jasongronvold/Desktop/SP-404SX/sp404-jambox/`
- **Library:** `~/Music/SP404-Sample-Library/`

### 5. UTS Dataset Profiling (From Your Own Research)
**Reference:** Your `Unified_Tag_System_Research.md` brief — great work.

**Actions from your own recommendations:**
- **Download and profile the AudenAI/UTS dataset** (MIT license, 400K clips) from [HF](https://huggingface.co/datasets/AudenAI/UTS). Check tag distribution, identify which of the 3K tags overlap with Jambox's vocabulary, flag gaps.
- **Track OpenBEATs** ([espnet/OpenBEATs-Large-i3-as2m](https://hf.co/espnet/OpenBEATs-Large-i3-as2m)) — low adoption now but the masked token prediction approach could complement CLAP embeddings down the line.
- **Watch for Qwen3-Omni-Captioner fine-tunes** targeted at music/sample description — if one appears, flag it immediately as a potential qwen3:32b replacement.

**Output:** UTS tag overlap report (which UTS tags map to Jambox, which are net-new, which are irrelevant). Drop to `{repo}/docs/research/`.

### 6. File Routing Note
Chat is asking Code for a status report on the Downloads watcher. Once that's working, all your deliverables should auto-route when dropped in `~/Downloads/`. Until then, please manually place:
- Research docs → `{repo}/docs/research/`
- Briefs → `{repo}/docs/briefs/`
- Audio samples → `~/Music/SP404-Sample-Library/_staging/`

---

## Deliverables
| # | Deliverable | Location |
|---|------------|----------|
| 1 | Riot Mode raw samples (30–50) | `_staging/riot-mode/` |
| 2 | Minneapolis Machine raw samples (30–50) | `_staging/minneapolis-machine/` |
| 3 | Stem-split outputs (priority batch) | `_staging/stems-split/` |
| 4 | Error rate investigation notes | Report back to Chat |
| 5 | UTS tag overlap report | `{repo}/docs/research/` |

---

*End of brief. Next handoff expected after retag error rate is triaged and first download batch lands.*
