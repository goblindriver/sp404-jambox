---
name: ml-pipeline
description: ML pipeline architecture — smart retag, audio similarity, training pipeline, taste profiles, and DPO training plan. Use when the user asks about "training pipeline", "smart retag", "DPO", "fine-tune", "CLAP", "taste profile", "how does the ML work", "retag status", "similarity", "dedup", or needs guidance on the ML systems.
version: 0.2.0
---

# ML Pipeline

## Architecture Overview

- **Smart retag**: librosa feature extraction → Ollama qwen3:32b → structured dimensional tags
- **Three-tier similarity**: Chromaprint (exact) → MFCC (timbral) → CLAP (semantic)
- **Training**: SFT distillation (32b→7b) then DPO on user corrections
- **Taste profiling**: production (hype>warm>soulful) vs consumption (nostalgic>dark>dreamy)

## Smart Retag

Runs every file through librosa feature extraction + Ollama LLM tagging to generate real dimensional tags (vibe, texture, genre, energy, instrument_hint, quality_score, sonic_description).

### Commands
- **Batch CLI**: `python scripts/smart_retag.py` — full library pass with checkpoint/resume
- **Re-vibe**: `python scripts/smart_retag.py --revibe` — re-run LLM tags without re-extracting features
- **Inline**: runs during ingest for new files (~42s/file on 32b)
- **Monitor**: web UI shows progress, or check `data/retag_checkpoint.json`

### Processing Flow
1. librosa extracts features: spectral centroid, MFCCs (13-coeff), chroma, ZCR, onset strength, RMS peak
2. Chromaprint fingerprint generated and stored
3. Features + filename + folder context sent to Ollama qwen3:32b
4. LLM returns structured JSON: type_code, vibe, texture, genre, energy, instrument_hint, quality_score, sonic_description
5. Quality 1-2 files auto-moved to `_QUARANTINE/` for human review

### Checkpoint System
- Progress saved to `data/retag_checkpoint.json` after each batch
- Survives crashes and restarts — picks up where it left off
- Tracks: last processed file, batch number, error count, total processed

## Feature Store

Tags + audio features stored together in `_tags.json` (migrating to SQLite). Per-file entry includes:

- **Chromaprint**: exact/near-exact fingerprint
- **librosa features**: spectral_centroid, mfcc (13 coefficients), chroma (12 bins), zero_crossing_rate, onset_strength, rms_peak
- **CLAP embedding**: 512-dim vector (future — initially null)
- **Dimensional tags**: type_code, vibe, texture, genre, energy, playability, instrument_hint, quality_score, sonic_description
- **Audio metadata**: bpm, key, loudness_db, bpm_source, key_source

Extract once, query at any resolution forever.

## Three-Tier Audio Similarity

| Tier | Method | What It Catches | Status |
|------|--------|----------------|--------|
| 1 | Chromaprint | Exact/near-exact duplicates | LIVE — runs during ingest |
| 2 | MFCC cosine distance | Same sound, different recording | LIVE — queries stored features |
| 3 | CLAP embeddings | Semantically similar sounds | FUTURE — needs one embedding pass |

Tier 1 found 11.5 GB reclaimable at 0.95 threshold. Dupes auto-move to `_DUPES/`.

## Taste Profiles

Two separate profiles reflecting different optimization targets:

### Production Profile (`data/taste_profile_production.json`)
What Jason wants to BUILD — optimization target for bank generation and fetch scoring.
- Top vibes: hype > warm > soulful > aggressive > gritty
- Top genres: funk, electronic, hiphop, disco, dancehall

### Consumption Profile (`data/taste_profile_consumption.json`)
What Jason LISTENS TO — context only, not a direct optimization target.
- Top vibes: nostalgic > dark > dreamy > melancholic > ethereal

### Cross-Media Sources
- 33K music tracks (Plex moods → vibe mapping)
- 2.4K movies, 4.8K TV episodes (genre/mood extraction)
- Audiobooks, games, field recordings
- Built by `scripts/taste_profiler.py`

## Vibe Intelligence

### Parser Modes
| Mode | How It Works | Requires |
|------|-------------|----------|
| base | Keyword fallback, no LLM | Always available |
| rag | LLM + retrieved context from sessions, presets, library stats | `SP404_LLM_ENDPOINT` |
| fine_tuned | QLoRA-adapted model | `SP404_FINE_TUNED_LLM_ENDPOINT` |

Set via `SP404_VIBE_PARSER_MODE=base|rag|fine_tuned`.

### Session Logging
Every vibe generation creates a session in `data/vibe_sessions.sqlite` tracking prompt, parsed tags, draft preset, fetch results, and review status.

## Training Pipeline

Located in `training/vibe/`:

| Script | Purpose |
|--------|---------|
| `prepare_dataset.py` | Extract reviewed sessions into JSONL training data |
| `train_lora.py` | QLoRA fine-tuning (r=16, alpha=32, lr=2e-4) |
| `eval_model.py` | Offline eval: parse accuracy, draft quality, ranking |
| `compare_modes.py` | Cross-mode comparison (base vs rag vs fine_tuned) |
| `serve_model.py` | Serve GGUF model via llama.cpp |

### Eval Suite
Seed evals in `data/evals/`:
- `prompt_to_parse.jsonl` — 12 prompts with expected type_code, playability, keywords
- `prompt_to_draft.jsonl` — 6 prompts with expected pad prefixes
- `prompt_to_ranking.jsonl` — 6 prompts with expected ranking against fixture library

Run: `python training/vibe/eval_model.py --mode base`

## DPO Training (Planned)

- **Source**: retag corrections (chosen=user edit, rejected=LLM original)
- **Framework**: Unsloth PatchDPOTrainer + TRL DPOTrainer
- **Minimum**: 1,000 preference pairs. Sweet spot: 5,000.
- **Goal**: Distill 32b→7b for inline inference speed while preserving tag quality
- **Additional signals**: Plex play counts, fetch accept/reject, bank performance

See `references/training-configs.md` for current hyperparameters and model details.
