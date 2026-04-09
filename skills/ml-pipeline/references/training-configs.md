# Training Configs & Model Details

## Current LLM Setup

| Setting | Value |
|---------|-------|
| Model | qwen3:32b via Ollama |
| Endpoint | `http://localhost:11434/v1/chat/completions` |
| Timeout | 90s |
| Parser mode | base (default), rag (with LLM), fine_tuned (future) |

## QLoRA Training Config

From `training/vibe/configs/qwen2.5-7b-qlora.yaml`:

| Parameter | Value |
|-----------|-------|
| Base model | Qwen/Qwen2.5-7B-Instruct |
| LoRA r | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.05 |
| Target modules | q_proj, k_proj, v_proj, o_proj |
| Learning rate | 2e-4 |
| Epochs | 3 |
| Batch size | 1 (gradient accumulation: 8) |
| Max seq length | 2048 |
| Quantization | 4-bit (bnb float16 compute) |
| Save steps | 100 |

## Eval Thresholds

| Metric | Passing | Notes |
|--------|---------|-------|
| Parse accuracy (type_code) | >80% | Exact match on 12 prompts |
| Parse accuracy (playability) | >75% | Exact match |
| Draft quality (pad prefix match) | >70% | Right type codes in draft |
| Ranking top-1 accuracy | >60% | Correct sample ranked first |

## Scoring Weights (config/scoring.yaml)

| Weight | Value |
|--------|-------|
| type_exact | 10 |
| type_related | 3 |
| type_mismatch | -8 |
| playability_exact | 5 |
| playability_mismatch | -4 |
| bpm_close | 4 |
| bpm_near | 2 |
| bpm_far | -2 |
| key_exact | 3 |
| key_compatible | 1 |
| keyword_dimension | 3 |
| keyword_tag | 2 |
| keyword_filename | 1 |
| oneshot_long_penalty | -3 |
| loop_short_penalty | -3 |
| plex_moods_bonus | 1 |
| plex_play_count_bonus | 2 |

## Pattern Training (Dormant)

Gated behind `training/pattern/readiness.py`:
- Curated MIDI corpus needed (>=50 files in `data/midi/`)
- Style labels needed (`data/pattern_labels.jsonl`)
- Eval prompts needed (`data/pattern_evals.jsonl`)
- No MIDI corpus exists yet — intentionally separate from vibe training
