# Session 3 Handoff — April 3-4, 2026

> Drop into `~/Downloads` — the doc pipeline routes it to `docs/` automatically.

---

## What Happened This Session

Session 3 was an audit, reconciliation, and planning session that turned into a full build cycle when Code shipped a massive infrastructure update mid-session.

**Chat delivered:** Updated CLAUDE.md, bug hunt report, 2 Cowork download briefs, Tiger Dust Block Party (10-bank performance set with 10 new presets), SP-404 ecosystem research doc, smart retag specification, optimization plan, and 3 Code agent briefs.

**Code delivered:** All 4 original assignments plus 3 bonus features and 7 bug fixes across 8 commits.

**Cowork delivered:** LLM post-training research, open-source tools research, Minneapolis Machine sources, Riot Mode sources, and SP-404 ecosystem research.

---

## Current System State

### All Green — Power Button Dashboard

| Feature | Status |
|---------|--------|
| LLM | Ollama Qwen3 8B connected, 10-prompt baseline captured |
| librosa | BPM/key/loudness analysis, inline during ingest |
| fpcalc | Chromaprint fingerprinting, inline during ingest |
| demucs | Background stem splitting for tracks >60s |
| watcher | Live, monitoring ~/Downloads (audio + docs) |

### What Shipped This Cycle (Code Agent)

**Original assignments (all complete):**
1. Vibe pipeline validation — parser modes degrade gracefully, session logging works, eval suite runs, system prompt verified
2. fpcalc + dedupe — full library scan (30,511 files), 11.5 GB reclaimable at 0.95 threshold
3. Daily bank smoke test — fixed all-SFX bug and deterministic weight selection
4. Ollama + baseline — Qwen3 8B running, endpoint wired into config

**Bonus features:**
- Unified ingest pipeline — FLAC conversion, librosa analysis, fingerprinting, dedup, background stem splitting, all in one automated flow
- Doc delivery pipeline — watcher auto-routes Chat/Cowork `.md`/`.txt` deliverables by naming convention
- Power button UI — server status dashboard with live feature checkmarks and restart

**Bug fixes:** bank_config.yaml corruption (Banks A/B missing), watcher pack detection, watcher crash on moved folders, Demucs invocation, watcher UI dark state, Python 3.9 syntax error

**Commits:** `1a255eb`, `49d49fc`, `3ec9f0c`, `2eeacdb`, `58d65be`, `2f12eec`, `65d5f86`, `94f8595`

### Dormant

| Feature | What It Needs |
|---------|---------------|
| Fine-tuned model | Training data + QLoRA run |
| RAG knowledge base | ChromaDB + embeddings indexed |
| CLAP embeddings | LAION-CLAP model + embedding pass |
| Pattern generation | Magenta checkpoints + MIDI corpus |
| Smart retag | Pipeline built + overnight pass (see Priority 0) |

### Delivered, Not Yet Installed

- 9 Session 2 genre presets + 5 curated sets
- Tiger Dust Block Party set + 10 new presets (this session)
- SP-404 ecosystem research doc
- Smart retag spec, optimization plan, measurement briefs

---

## The #1 Problem

**Only 108 of 30,511 files have real dimensional tags.** The fetch system is fundamentally broken — every kick scores the same because none have genre/vibe/texture tags. Scoring weight tuning, preset refinement, eval comparisons — none of it matters until the library is properly tagged.

This is why Smart Retag is Priority 0. Everything else waits.

---

## Priorities

### Priority 0: Smart Retag (blocks everything)

Run every file through librosa feature extraction + Ollama LLM tagging. See `SMART_RETAG_SPEC.md` for full system prompt, quality rubric, trim policy, and vocabulary.

**Architecture:**
- CLI batch tool (`scripts/smart_retag.py`) for the 30k overnight pass — too heavy for the webapp
- Inline retag in ingest pipeline for new files arriving via watcher (~2s per file, acceptable)
- Webapp monitors progress + provides tag review UI — doesn't do the computation

**Execution:**
1. Code builds `scripts/smart_retag.py` with checkpoint/resume
2. Validate on 100-file batch — Chat reviews output, tunes the prompt
3. Retag Phase 1: Tiger Dust demand order (KIK → SNR → HAT → PRC → BRK → BAS → SYN/PAD/KEY → VOX/FX/RSR → GTR/HRN/STR)
4. Retag Phase 2: Full overnight pass on remaining files
5. Quarantine quality 1-2 files to `_QUARANTINE/`, generate review report
6. Every tagged file becomes a training example (~30k total)

**New capabilities from retag:**
- 5 new type codes: GTR, HRN, KEY, STR, RSR
- `texture` as a scored tag dimension
- `instrument_hint` for specific instrument matching
- `quality_score` (1-5) for curation
- `sonic_description` for human browsing
- Multi-resolution feature store: Chromaprint + MFCC vectors + future CLAP embeddings, all stored per file. Extract once, query at any resolution forever.

### Priority 1: Feed the Machine (Cowork Downloads)

Pipeline auto-ingests, auto-tags, fingerprints, and dedups on arrival. New files also get inline smart retag when Ollama is available.

1. Execute Riot Mode download brief — 2-5 GB, 1000+ samples
2. Execute Minneapolis Machine download brief — 6-10 GB, 3 phases
3. Execute Brat Mode downloads (Session 2 brief, still pending)
4. Execute Free Essentials downloads (Session 2 brief, still pending)
5. Download NearTao's SP-404 guide + original SP-404 manual → `docs/references/`

### Priority 2: Optimization Measurements (after retag)

See `OPTIMIZATION_PLAN.md` and `CODE_BRIEF_optimization_measurements.md`.

1. Fetch Quality Audit on Tiger Dust — load set, fetch all, listen to every pad, score hit/close/miss (ears required)
2. Library Coverage Analysis — automated report of tag distributions and gaps
3. Tag Accuracy Audit — spot-check 50 retag outputs for correctness
4. Base vs RAG eval comparison — run eval suite in both modes, generate comparison report (gates QLoRA investment)
5. Performance baselines — preview latency, fetch time, bank switch speed

### Priority 3: Training Data Pipeline

Smart retag generates ~30k training examples automatically. Additional work:

1. Convert NearTao guide sections to Q&A training pairs for RAG corpus
2. Create resample workflow training examples from ecosystem research
3. Generate synthetic examples via Claude API (~1,000)
4. Human validation pass on sample of 200
5. First QLoRA run — only after base vs RAG comparison confirms value

### Priority 4: Workflow Polish

1. Single-pad re-fetch — "Next" button cycles through top-N candidates without re-fetching
2. Preview latency optimization — target <500ms click-to-sound
3. Full set fetch performance — target <30s for 120 pads
4. MFCC diversity enforcement — prevent fetch from returning 5 copies of the same sound
5. CLAP embedding pass — enable natural language search against audio content

---

## Agent Assignments

### Cowork

| # | Assignment | Source | Est. Size |
|---|-----------|--------|-----------|
| 1 | Riot Mode downloads | `COWORK_BRIEF_riot_mode_downloads.md` | 2-5 GB |
| 2 | Minneapolis Machine downloads | `COWORK_BRIEF_minneapolis_machine_downloads.md` | 6-10 GB |
| 3 | Brat Mode downloads | Session 2 brief | 3-5 GB |
| 4 | Free Essentials downloads | Session 2 brief | 2-3 GB |
| 5 | Stem splitting (top 20) | Session 2 brief | — |
| 6 | NearTao guide + SP-404 manual | `SP404_ECOSYSTEM_RESEARCH.md` | ~50 MB |

### Code Agent

| # | Assignment | Spec Doc | Priority |
|---|-----------|----------|----------|
| 7 | Smart Retag Pipeline | `SMART_RETAG_SPEC.md` | **TOP — blocks everything** |
| 8 | Install presets (Session 2 + Tiger Dust) | Preset YAMLs in `presets/` and `sets/` | Medium |
| 9 | Optimization measurements | `CODE_BRIEF_optimization_measurements.md` | After retag |
| 10 | Install ecosystem research doc | `SP404_ECOSYSTEM_RESEARCH.md` → `docs/` | Low |
| 11 | Dedupe review | Spot-check 20 pairs from `_DUPES/` | Low |

---

## Tiger Dust Block Party

New default performance set. 10 banks designed as the arc of a block party from golden hour to last call.

| Bank | Preset | BPM | Key | Energy | The Moment |
|------|--------|-----|-----|--------|------------|
| A | Soul Kitchen | 98 | G | Low | Golden hour, smoke off the grill |
| B | Funk Muscle | 112 | Em | High | Hips start moving |
| C | Disco Inferno | 118 | Am | High | Full dance floor, everyone's auntie is dancing |
| D | Boom Bap Cipher | 90 | Dm | Mid | Tempo drops, heads nod, someone freestyles |
| E | Caribbean Heat | 108 | Cm | High | Summer explodes, dancehall takes over |
| F | Electro Sweat | 120 | Dm | High | The weird turn — LCD at the cookout |
| G | Neon Rave | 128 | F | High | Glow sticks appear, blog-house filters |
| H | Peak Hour | 125 | Gm | High | THE MOMENT — maximum intensity |
| I | Dub Cooldown | 100 | Am | Low | The big exhale — echo chamber bass |
| J | Weapons Cache | 120 | XX | Mid | Air horns, sirens, impacts — always ready |

**Harmonic design:** Core diatonic family (C major): G, Em, Am, Dm, F — banks A-D and F-G harmonize. Cm and Gm provide darker contrast for Caribbean Heat and Peak Hour. Banks C/I share Am for easy disco→cooldown bridge. Banks D/F share Dm for hip-hop→electro crossfade.

**Tempo clusters:** 112/118/120 mix cleanly (core party). 125/128 mix cleanly (peak energy). 90 and 100 are intentional drop-downs.

---

## Reference Docs Produced This Session

| Document | Purpose | Route |
|----------|---------|-------|
| `CLAUDE.md` | Code agent primary context (full refresh) | Repo root |
| `SMART_RETAG_SPEC.md` | LLM tagger system prompt, quality rubric, trim policy, feature store, multi-resolution similarity | `docs/` |
| `OPTIMIZATION_PLAN.md` | 4-tier optimization roadmap with Phase 0 smart retag | `docs/` |
| `CODE_BRIEF_optimization_measurements.md` | Measurement assignments for Code agent | `docs/briefs/` |
| `CODE_BRIEF_bug_fixes.md` | Bug fix list (all complete) | `docs/briefs/` |
| `CODE_BRIEF_doc_ingest.md` | Doc delivery pipeline spec (shipped) | `docs/briefs/` |
| `SP404_ECOSYSTEM_RESEARCH.md` | SP-404 ecosystem map | `docs/` |
| `BUG_HUNT_SESSION3.md` | Codebase audit results | `docs/` |
| `COWORK_BRIEF_riot_mode_downloads.md` | Download execution brief | `docs/briefs/` |
| `COWORK_BRIEF_minneapolis_machine_downloads.md` | Download execution brief | `docs/briefs/` |

---

## Hardware Context

- **Apple Silicon** (M-series, specific chip unknown)
- MLX for local fine-tuning (QLoRA)
- Ollama for local inference (Metal acceleration)
- ~30,511 files in sample library
- ~226 GB free disk space (check current — 11.5 GB reclaimable from `_DUPES/`)
