# DPO Data Strategy — Jambox Taste Training
**Date:** 2026-04-04
**From:** Chat
**For:** Code + Chat reference
**Informed by:** Cowork's `DPO_TRAINING_FRAMEWORKS.md` research

---

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    STAGE 0: COLLECT TEACHER DATA                    │
│                         (happening now)                             │
│  Smart retag: qwen3:32b → 30K files → SQLite                      │
│  Re-vibe pass: production taste prompt → vibe_score + scene tags   │
│  Output: labeled dataset with descriptive + evaluative tags        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                    STAGE 1: SFT (DISTILLATION)                      │
│  Goal: Teach Qwen3 7B to mimic 32B tagging behavior                │
│  Data: 1,500–2,000 high-quality (input, 32B_output) pairs          │
│  Framework: Unsloth + QLoRA (r=16, α=32, lr=2e-4, 3 epochs)       │
│  Hardware: M3 24GB — QLoRA brings 7B to ~8-10GB                    │
│  Output: LoRA adapter checkpoint                                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                 STAGE 2: DEPLOY + COLLECT CORRECTIONS               │
│  Merge SFT adapter → GGUF → Ollama                                 │
│  Run 7B model on new/untagged samples                               │
│  Jason reviews in retag review UI → corrections = preference pairs  │
│  Auto-generate pairs from re-vibe dpo_signal field                  │
│  Target: 1,000–5,000 pairs (sweet spot per Cowork research)        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                    STAGE 3: DPO (ALIGNMENT)                         │
│  Goal: Align 7B to Jason's production aesthetic                     │
│  Data: 1,000+ preference pairs                                     │
│  Framework: Unsloth PatchDPOTrainer + TRL DPOTrainer                │
│  Hyperparams: r=16, α=32, lr=5e-5, 1 epoch, β=0.1                 │
│  Start from: SFT checkpoint (not base model)                        │
│  Hardware: M3 24GB — same QLoRA config, ~8-10GB                    │
│  Time: ~1-2 hours for 5K pairs                                     │
│  Output: DPO LoRA adapter checkpoint                                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                    STAGE 4: EXPORT + DEPLOY                         │
│  Merge DPO adapter → FP16 → GGUF (Q4/Q5/Q6) → Ollama              │
│  Model name: jambox-vibe                                            │
│  Serves at 7B speed, aligned to Jason's taste                       │
│  Replaces qwen3:32b for ongoing tagging (10x+ faster)              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Preference Pair Sources (Ranked by Effort)

### Source 1: Preset-Derived Pairs (FREE — already have the data)

Samples already assigned to curated presets (Tiger Dust Block Party, Riot Mode, Minneapolis Machine, etc.) are implicit **chosen** examples. They represent Jason's actual curation decisions.

**How to generate pairs:**
```
For each sample S assigned to a preset P:
  1. S's current production-aligned tags = CHOSEN
  2. Generate a degraded version:
     - Swap vibe from production (hype/warm/soulful) to consumption (nostalgic/dark/dreamy)
     - Lower energy by one level
     - Remove scene tag or set to generic
     - Reduce vibe_score by 0.2-0.3
  3. Degraded tags = REJECTED
  4. Prompt = sample metadata (filename, duration, BPM, key, loudness)
```

**Estimated yield:** ~120 pads across presets × 1 pair each = ~120 pairs. Low volume but high signal — these are real curation decisions.

**Quality:** High. These are ground-truth production preferences.

### Source 2: Re-Vibe dpo_signal Field (SEMI-AUTOMATIC)

The production taste prompt includes a `dpo_signal` field that auto-classifies each evaluation as `chosen`, `rejected`, or `neutral`.

**How to generate pairs:**
```
For each sample with dpo_signal = "chosen":
  1. Re-vibe output = CHOSEN
  2. Raw retag output (before re-vibe) = REJECTED
  3. Prompt = sample metadata

For each sample with dpo_signal = "rejected":
  1. This sample's re-vibe output is itself a REJECTED example
  2. Generate a corrected version (swap to production vibes) = CHOSEN
  3. Prompt = sample metadata
```

**Estimated yield:** If 60% of 30K files get `chosen` and 20% get `rejected`, that's ~18K chosen + ~6K rejected. More pairs than we need — subsample the best 5K.

**Quality:** Medium. The 32B model is generating both sides, so the contrast between chosen/rejected may be subtle. But volume compensates.

### Source 3: Manual Review UI Corrections (GOLD STANDARD)

Jason reviews model output in the retag review UI, corrects tags he disagrees with. Each correction is one preference pair.

**How to generate pairs:**
```
For each correction:
  1. Jason's corrected tags = CHOSEN
  2. Model's original tags = REJECTED
  3. Prompt = sample metadata
```

**Estimated yield:** 10-20 corrections per review session. At 1K target: ~50-100 sessions. At 5K target: ~250-500 sessions.

**Quality:** Highest. This is direct human preference signal. But slow.

**Accelerator:** Batch review mode — show 10 samples per screen, Jason swipes right (accept) or edits (correct). Accepted samples aren't wasted — they confirm the model is right, useful for calibration.

### Source 4: A/B Prompt Comparison (EXPERIMENTAL)

Run two prompt variants on the same sample. Jason picks which output he prefers.

**When to use:** Only if we need to refine the production taste prompt itself. Not for routine pair generation.

---

## Recommended Pair Mix

| Source | Pairs | % of Training Set | Priority |
|--------|-------|--------------------|----------|
| Preset-derived | ~120 | 2-3% | Include all — highest quality |
| Re-vibe dpo_signal | ~2,000 | 40% | Subsample diverse examples |
| Manual corrections | ~500-1,000 | 50-55% | Build over time via review UI |
| Hard negatives (see below) | ~200 | 5% | Critical for boundary cases |

**Total target: 3,000-5,000 pairs** — well above the 1K minimum, in Cowork's identified sweet spot.

### Hard Negatives

The most valuable training pairs are ones where the model is *almost right but subtly wrong*. These teach fine distinctions.

Examples of hard negatives for Jason's taste:
- Sample tagged `vibe: dark, energy: high` → model says production fit. But it's harsh noise, not danceable darkness. Correct: `skip`.
- Sample tagged `vibe: warm, genre: jazz` → model says strong fit. But it's a smooth jazz sax loop — wrong kind of warm. Correct: `marginal`.
- Sample tagged `vibe: hype, genre: EDM` → model says essential. But it's a generic festival build-up riser. Correct: `skip` (too polished, no grit).

**How to generate hard negatives:**
1. Run re-vibe pass
2. Filter for samples where `vibe_score` is between 0.4-0.6 (ambiguous zone)
3. Jason reviews these specifically — his corrections become the highest-value training pairs

---

## SFT Training Data Selection

Before DPO, we need 1,500-2,000 SFT pairs to teach the 7B the task itself.

**Selection criteria:**
1. Only use samples where retag + re-vibe both succeeded (no error cases)
2. Stratify by type_code — equal representation of KCK, SNR, PAD, BAS, etc.
3. Stratify by vibe_score — include the full 0.0-1.0 range, not just high scores
4. Stratify by genre — cover all 9+ genre presets
5. Include at least 50 examples from each scene type
6. Prefer samples with rich sonic_description (the caption quality finding from UTS research)

**Format:**
```python
{
    "instruction": "Tag this audio sample for an SP-404A sample library.",
    "input": "Filename: funk_bass_loop_112bpm.wav\nDuration: 4.2s\nBPM: 112\nKey: Em\nLoudness: -14.2 dB",
    "output": "<full tag JSON including vibe_score, scene, production_fit, etc.>"
}
```

---

## Eval Strategy

### Baseline (Before Training)
- Run Jambox tagger on 100 samples from AudenAI/UTS dataset (MIT license)
- Compare output to UTS ground truth
- Record accuracy per tag dimension

### Post-SFT Eval
- Same 100 UTS samples through the 7B SFT model
- Compare to 32B output (should be close — SFT is distillation)
- Also run on 50 preset-assigned samples — check if vibe_score aligns with actual curation

### Post-DPO Eval
- Same evals as above
- PLUS: 50 ambiguous-zone samples (vibe_score 0.4-0.6) — does DPO shift them toward production taste?
- PLUS: A/B blind test — Jason sees two tag sets per sample (32B vs 7B-DPO), picks which one he'd use. Win rate should be >50%.

### Ongoing
- Weekly eval health check (already scheduled via Cowork plugin)
- Track vibe_score distribution drift over time
- Flag if the model starts over-indexing on any single vibe or genre

---

## Timeline

| Phase | When | Depends On |
|-------|------|-----------|
| Smart retag completes | ~April 18 | Running now |
| SQLite migration | Before April 18 | ARCH-1 (Code) |
| Re-vibe pass | April 19-May 3 | Retag + SQLite done |
| SFT data selection | During re-vibe | SQLite queries |
| SFT training | May first week | Data selection done |
| Deploy 7B SFT → collect corrections | May ongoing | SFT trained + GGUF exported |
| DPO data reaches 1K pairs | ~June | Review UI usage |
| DPO training | June | 1K+ pairs collected |
| jambox-vibe model deployed | June-July | DPO trained + GGUF exported |

---

## Open Questions for Jason

1. **Review UI cadence** — How many review sessions per week are realistic? This determines how fast we hit 1K manual correction pairs.
2. **Hard negative threshold** — Is 0.4-0.6 the right ambiguous zone, or should it be wider/narrower?
3. **Scene tags** — Do the 8 scene types I defined cover your performance workflow, or are there contexts I'm missing?
4. **CLAP embeddings in pairs** — Should we include the 512-dim CLAP embedding as additional input to the model? Cowork's research suggests it runs overnight on 30K files. It could give the model acoustic signal beyond just metadata.

---

*This strategy produces a 7B model that tags samples the way Jason would — not just describing what they are, but knowing whether they belong in a set and where they'd go on the SP-404.*
