# Chat Session Handoff — April 3, 2026 (Session 3)

> Drop this into the repo at docs/HANDOFF_SESSION3.md to restore full context.

## Session Summary

Audited all progress since Session 2, reconciled Cursor implementation against original plan, and ingested Cowork research deliverables. The big milestone: **Personalized JamBox Intelligence is on main** — the full vibe pipeline shipped in Cursor with training scripts, eval harness, RAG retrieval, and UI review flow. Cowork delivered LLM research, Minneapolis Machine sources, and Riot Mode sources.

---

## What Shipped Since Session 2 (Cursor / Code Agent)

### Personalized Vibe Intelligence Pipeline (MERGED TO MAIN)

**Commits:**
- `c3e0282` — Add personalized vibe training pipeline
- `1153330` — Ignore generated vibe training artifacts

**New capabilities:**
- Persistent vibe session logging with correction capture
- Editable parsed-tag review in the UI (user can fix tags before they're stored)
- Parser modes: `base` / `rag` / `fine_tuned` (switchable)
- RAG retrieval grounding from prior sessions, presets, and library hints
- Seed eval suite under `data/evals/`
- Training/eval/export/serving scripts under `training/vibe/`
- Separate pattern-training readiness gates under `training/pattern/`

**Bug fixes in final pass:**
- RAG retrieval degrades safely if tag DB is unavailable/malformed
- `train_lora.py` resolves repo-relative dataset/output paths correctly
- Removed generated `data/vibe_sessions.sqlite` from source control
- `.gitignore` updated for runtime/model artifacts

---

## Cowork Deliverables Received This Session

### 1. Jambox LLM Post-Training Research (1,180 lines)
**Status:** Received & reviewed. Validates and expands Session 2's LLM strategy.

Key decisions confirmed:
- **Hybrid approach:** Fine-tune for tagging/format, RAG for dynamic content
- **Base model:** Qwen3 8B via Ollama (runs on Apple Silicon via Metal)
- **Training method:** QLoRA via MLX (Apple Silicon) or Unsloth (NVIDIA)
- **Dataset target:** 1,000–2,000 examples (diminishing returns beyond 5,000)
- **Data sources:** Library metadata (~8K records), sound design docs (~300 examples), tag taxonomy (~200 examples), Claude-generated synthetic data (~1,000 examples)
- **RAG stack:** ChromaDB + nomic-embed-text via Ollama
- **Deployment:** Ollama Modelfile with adapter weights, OpenAI-compatible API

Training hyperparameters documented (LoRA r=16, α=32, lr=2e-4, 3 epochs).
Full system prompt and Modelfile template provided.
4-week training timeline mapped.

### 2. Minneapolis Machine Sources (700 lines)
**Status:** Received. Source hunting complete. Ready for Cowork download brief.

Coverage: Boom-bap drums, experimental/polyrhythmic drums, noise/glitch textures, distorted bass, vocal chops, dark ambient pads, and platform aggregators.

Top picks per category:
- **Drums:** Diginoiz Boom Bap (135 shots), Samples From Mars Vinyl Drums, Ultimate Boom Bap (2,088 shots), SoundPacks Boom Bap Vol 1
- **Experimental:** 99Sounds Massamolla (99 abstract percussion), SampleRadar Experimental Breaks (282)
- **Noise/Texture:** Static Kit (46 hardware-sourced), SampleRadar 502 Noise/Hiss/Crackle, The Weird Side (182 glitch)
- **Bass:** Looperman distorted 808s, Abletunes 50 key-labeled 808s
- **Vocals:** Looperman chops, Ghosthack 900+ acapellas
- **Ambient:** Pixabay drones, SONNISS Obscurum (61 dark drones), Wraith synth (230 instruments)

Estimated total: ~6–10 GB across core + expansion + specialized sources.
Overlap with Brat Mode noted (noise/glitch textures share sources).

### 3. Riot Mode Sources (630 lines)
**Status:** Received. Source hunting complete. Ready for Cowork download brief.

Coverage: Punk drums, distorted guitar, ska brass/horns, gang/shout vocals, lo-fi textures, full construction kits.

Top picks per category:
- **Drums:** Looperman Punk Drums (100+), Wikiloops Punk Rock (75+), MusicRadar 1000 Drums
- **Guitar:** Sample Focus distorted punk guitar (ESP EC-300), Freesound Chem distortion pack
- **Ska Brass:** Sample Focus ska brass sections, horns, skanks
- **Vocals:** JST Gang Vocals, 91Vocals Gang Vocals
- **Textures:** Sample Focus noise collection
- **Construction:** We Sound Human Punk kits, Slooply free packs

Estimated total: ~2–5 GB, 1,000+ unique samples.

---

## Progress Audit: Session 2 Action Plan vs Actual

### Priority 1: Code Quick Wins

| Task | Status | Notes |
|------|--------|-------|
| Install fpcalc, run library dedupe | **NOT STARTED** | Still needs `brew install chromaprint` |
| Smoke test daily bank | **NOT STARTED** | Functional but untested |
| Wire TASTE_SYSTEM_PROMPT into llm_client.py | **SUPERSEDED** | Full vibe pipeline shipped — system prompt wiring is now part of the parser mode system. Cowork's research doc has the definitive system prompt. Need to verify the shipped prompt matches or update. |
| Install Ollama, pull Qwen3 8B | **NOT STARTED** | Required for any local inference. Blocks base vs rag comparison. |

### Priority 2: Cowork Execution

| Task | Status | Notes |
|------|--------|-------|
| Execute Brat Mode downloads brief | **NOT STARTED** | Brief written Session 2 |
| Execute Free Essentials downloads brief | **NOT STARTED** | Brief written Session 2 |
| Execute Riot Mode source hunting brief | **COMPLETE** | Sources doc received this session (630 lines). Download brief still needed. |
| Execute Minneapolis Machine source hunting brief | **COMPLETE** | Sources doc received this session (700 lines). Download brief still needed. |
| Begin stem splitting (top 20) | **NOT STARTED** | Stem split brief written Session 2 |

### Priority 3: LLM Training Pipeline

| Task | Status | Notes |
|------|--------|-------|
| Mine library metadata (20,925 files → JSONL) | **NOT STARTED** | Cowork research has the script skeleton |
| Convert reference docs to training examples | **NOT STARTED** | Strategy documented in research |
| Generate synthetic training data via Claude API | **NOT STARTED** | Prompt template ready in research |
| Fine-tune v1 with MLX on Apple Silicon | **NOT STARTED** | But: training scripts shipped in Cursor (`training/vibe/`), eval harness ready, readiness gates in place |

### Priority 4: Active Development

| Task | Status | Notes |
|------|--------|-------|
| UI streamlining | **PARTIAL** | Editable parsed-tag review shipped. Full UI brief from Session 1 may have more items. |
| Session to Instrument pipeline | **NOT STARTED** | Brief from Session 1 |
| Scale mapping + pattern system | **NOT STARTED** | `training/pattern/` readiness gates placed but no MIDI corpus yet |

---

## Updated System State

### What's Live
- File watcher (watchdog)
- Plex integration (33k tracks, 298 moods, 412 styles)
- Preset system (presets/ + sets/ + web UI browser)
- FLAC library (15 GB, 20,925 files)
- SD card reader/writer
- Smart features (structurally complete, dormant)
- Centralized config (jambox_config.py)
- Delivery protocol (_DELIVERY.yaml)
- **NEW:** Vibe session logging + correction capture
- **NEW:** Editable parsed-tag review in UI
- **NEW:** Parser mode switching (base / rag / fine_tuned)
- **NEW:** RAG retrieval grounding (sessions, presets, library hints)
- **NEW:** Eval suite (data/evals/)
- **NEW:** Training scripts (training/vibe/)
- **NEW:** Pattern training gates (training/pattern/)

### Dormant (needs external setup)
- Vibe inference — needs Ollama + Qwen3 8B installed
- Fine-tuned model — needs training data + QLoRA run
- RAG knowledge base — needs ChromaDB + embeddings indexed
- Pattern generation — needs Magenta checkpoints + MIDI corpus
- Dedupe — needs `fpcalc` (`brew install chromaprint`)
- Daily bank — functional but untested

### Delivered but Not Yet Executed
- 9 genre presets + 5 curated sets (Session 2, zip delivered)
- 11-bank tag taxonomy (Session 2)
- 40-track stem-split queue (Session 2)
- 5 Cowork briefs (Session 2 — brat downloads, free essentials, stem splitting, riot sources✓, minneapolis sources✓)
- LLM taste profile (Session 2)
- LLM post-training research (this session)
- Minneapolis Machine sources catalog (this session)
- Riot Mode sources catalog (this session)

### Not Yet Built
- Fine-tuned jambox-tagger model
- ChromaDB RAG index
- Preference tracking system
- Session to Instrument pipeline
- Full UI streamlining
- Harmonic engine
- Scale mapping / melodic patterns

---

## What To Do Next

### Immediate: Validate Cursor Ship (Bug Hunt)
1. **Verify system prompt alignment** — Compare the taste system prompt in the shipped code against Cowork's definitive prompt from the LLM research doc. Reconcile any drift.
2. **Test parser mode switching** — Confirm base/rag/fine_tuned modes degrade gracefully when Ollama isn't installed.
3. **Test vibe session logging** — Create a session, log corrections, verify persistence.
4. **Test editable tag review** — Confirm UI flow for reviewing and editing parsed tags.
5. **Test eval suite** — Run seed evals, confirm they pass.
6. **Verify .gitignore** — Ensure no runtime artifacts slip into source control.

### Priority 1: Unblock Local Inference
1. Install Ollama (`brew install ollama` or from ollama.ai)
2. Pull Qwen3 8B (`ollama pull qwen3:8b`)
3. Pull nomic-embed-text (`ollama pull nomic-embed-text`)
4. Verify Jambox can connect to Ollama endpoint
5. Run base parser mode against real samples — establish baseline metrics

### Priority 2: Unblock Dedupe & Daily Bank
1. `brew install chromaprint` → get `fpcalc`
2. Run library dedupe across 20,925 files
3. Smoke test daily bank end-to-end

### Priority 3: Write Download Briefs for New Sources
Cowork has source catalogs but needs download execution briefs for:
1. **Riot Mode downloads** — Convert RIOT_MODE_SOURCES.txt into a Cowork download brief (top 10 priority list is already in the doc)
2. **Minneapolis Machine downloads** — Convert MINNEAPOLIS_MACHINE_SOURCES.txt into a Cowork download brief (core foundation + expansion layers defined)

### Priority 4: Begin Training Data Pipeline
1. Mine library metadata (20,925 files → JSONL) using script from research doc
2. Convert sound design reference docs to training examples (~300)
3. Generate synthetic examples via Claude API (~1,000)
4. Human validation pass on sample of 200
5. First QLoRA run — but **only after** base vs rag comparison on real data

### Priority 5: Expand Evals
1. Expand gold eval set beyond seed examples
2. Collect real reviewed vibe sessions (from the new UI flow)
3. Run base vs rag comparisons on real data
4. Only then invest in QLoRA fine-tuning

---

## Cowork & Code Agent Briefing

### For Cowork (Next Assignments)

**Assignment 1: Riot Mode Download Execution**
Source catalog: RIOT_MODE_SOURCES.txt (received this session)
Action: Download top 10 priority sources. Convert all to WAV. Organize by category (drums, guitar, brass, vocals, textures). Target: ~2-5 GB.

**Assignment 2: Minneapolis Machine Download Execution**
Source catalog: MINNEAPOLIS_MACHINE_SOURCES.txt (received this session)
Action: Download core foundation (5 packs, ~3-5 GB) first. Then expansion layer. Organize by category. Watch for overlap with Brat Mode noise/glitch sources — dedupe across banks.

**Assignment 3: Brat Mode Downloads** (from Session 2 brief — still pending)

**Assignment 4: Free Essentials Downloads** (from Session 2 brief — still pending)

**Assignment 5: Stem Splitting** (from Session 2 brief — top 20 candidates, still pending)

### For Code Agent (Next Assignments)

**Assignment 1: Bug Hunt on Vibe Pipeline**
- Verify all parser modes degrade gracefully without Ollama
- Test session logging round-trip
- Test editable tag review flow
- Run seed eval suite, confirm green
- Verify system prompt in code matches Cowork's definitive version

**Assignment 2: fpcalc + Dedupe**
- `brew install chromaprint`
- Run dedupe against full library (20,925 files)
- Report duplicate count and space savings

**Assignment 3: Daily Bank Smoke Test**
- End-to-end test of daily bank generation
- Verify preset output format and SD card write path

**Assignment 4: Ollama Setup + Baseline**
- Install Ollama, pull Qwen3 8B + nomic-embed-text
- Wire endpoint into Jambox config
- Run base parser against 10 real samples, capture baseline metrics

---

## Hardware Context
- **Apple Silicon** (specific chip unknown — M1/M2/M3/M4)
- MLX for local fine-tuning (QLoRA)
- Ollama for local inference (Metal acceleration)
- 15 GB FLAC library, ~226 GB free disk space (check current)

---

## All Files This Session

```
INPUTS (from Cowork):
├── Jambox_LLM_Post_Training_Research.md (1,180 lines)
├── MINNEAPOLIS_MACHINE_SOURCES.txt (700 lines)
└── RIOT_MODE_SOURCES.txt (630 lines)

INPUTS (from Cursor):
└── Commits c3e0282, 1153330 on main (vibe pipeline + .gitignore)

OUTPUTS (this session):
├── HANDOFF_SESSION3.md (this document)
├── COWORK_BRIEF_riot_mode_downloads.md (new)
└── COWORK_BRIEF_minneapolis_machine_downloads.md (new)
```
