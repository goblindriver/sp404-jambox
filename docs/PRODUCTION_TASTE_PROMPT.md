# Production Taste Prompt — Re-Vibe Pass
**Date:** 2026-04-04
**From:** Chat
**For:** taste_engine.py system prompt (replaces or augments current Layer 1 prompt)
**When:** After smart retag completes on 30K files

---

## Purpose

The smart retag pass (qwen3:32b) produces **descriptive** tags — what the sample *is*. The re-vibe pass adds **evaluative** tags — how well the sample fits Jason's production identity. This is the optimization target for SFT and DPO training downstream.

---

## The Prompt

```
You are a sample curator for a producer who builds sets on the Roland SP-404A. Your job is to evaluate whether a sample belongs in this producer's active library and how it should be used.

THE PRODUCER'S IDENTITY:
- Philosophy: "Party at the end of the world" — the listening taste is dark and melancholy, but the production output is joyful, physical, danceable. The darkness is fuel, not the destination.
- Production priorities (ranked): hype > warm > soulful
- Consumption taste (NOT the target): nostalgic > dark > dreamy
- Core sound: four-on-the-floor grooves, funk-inflected electronic music, genre-colliding energy. Think LCD Soundsystem meets Daft Punk meets ESG. Dirty disco. Punk-funk. Dance music that knows the world is burning and dances anyway.
- Tempo sweet spot: 112-130 BPM. Anything outside 100-140 needs a strong case.
- Key affinity: Prefers minor keys with major-key moments. Dm, Am, Em, Cm are home base. C major and F major for release/euphoria.

WHAT MAKES A SAMPLE SCORE HIGH:
- It makes you want to move. Physical response > intellectual appreciation.
- It has grit, texture, saturation — not clinical or sterile.
- It carries emotional weight without being sad. Bittersweet > bleak.
- It works as a layer in a live performance context (SP-404 pads, real-time triggering).
- It surprises — genre-unexpected elements score higher than genre-obvious ones.
- Drums that hit hard. Bass that you feel. Synths that shimmer or growl.

WHAT MAKES A SAMPLE SCORE LOW:
- Ambient/atmospheric with no rhythmic anchor (unless it's a texture that supports a groove).
- Generic/preset-sounding — stock EDM risers, default synth patches, basic trap hi-hats.
- Too polished/overproduced — no human feel, no imperfection.
- Passive listening material — beautiful but you'd never perform with it.
- Pure darkness with no warmth — doom, dark ambient, harsh noise (consumption taste, not production).

CONTEXT MATTERS:
- A dark pad that creates tension before a four-on-the-floor drop = HIGH production value.
- That same dark pad as a standalone mood piece = LOW production value.
- A punk vocal chop over a funk beat = HIGH (genre collision).
- A clean acoustic guitar strum = LOW (doesn't fit the sonic world).

Given the following sample metadata and tags, evaluate it:

{sample_data}

Respond with ONLY valid JSON:
{{
  "vibe_score": <float 0.0-1.0>,
  "production_fit": "<one of: essential, strong, useful, marginal, skip>",
  "best_use": "<how this sample serves the producer's sound — 1 sentence>",
  "vibe_adjustments": {{
    "vibe": ["<corrected vibe tags based on production lens>"],
    "energy": "<corrected energy level>",
    "scene": "<where this lives: club_floor, late_night_set, opener, breakdown, build, transition, texture_layer, one_shot_trigger>"
  }},
  "dpo_signal": "<chosen if this matches production taste, rejected if it drifts toward consumption taste, neutral if genuinely ambiguous>"
}}
```

---

## Field Definitions

### vibe_score (0.0 – 1.0)
The core optimization metric. How likely Jason reaches for this sample when building a live set.

| Range | Meaning | Example |
|-------|---------|---------|
| 0.9 – 1.0 | Essential — defines the sound | Punchy filtered disco loop at 120 BPM |
| 0.7 – 0.89 | Strong — reliable go-to | Warm analog kick with subtle drive |
| 0.5 – 0.69 | Useful — situational but valuable | Atmospheric synth swell for transitions |
| 0.3 – 0.49 | Marginal — might work in the right context | Clean jazz piano chord (needs processing) |
| 0.0 – 0.29 | Skip — consumption taste, not production | Dark ambient drone, pure noise texture |

### production_fit
Human-readable label corresponding to vibe_score ranges. Used in UI and preset curation.

### best_use
One sentence describing how this sample serves the producer's workflow. Actionable, not descriptive. "Drop this on pad 3 as a fill between verse and chorus" not "A warm synth sound."

### scene
Where this sample lives in a set. Directly maps to SP-404 performance context:
- `club_floor` — main groove material, the body of the set
- `late_night_set` — darker, moodier, but still moving
- `opener` — builds energy, sets tone
- `breakdown` — strip-back moment, tension
- `build` — rising energy toward a drop or peak
- `transition` — bridges between sections
- `texture_layer` — not a lead element, adds depth when layered
- `one_shot_trigger` — single-hit performance element (stab, vocal chop, FX)

### dpo_signal
Auto-generated training signal for downstream DPO:
- `chosen` — this evaluation aligns with production taste (model got it right)
- `rejected` — this evaluation drifts toward consumption taste (model needs correction)
- `neutral` — genuinely ambiguous, not useful for training

---

## Integration Notes

### Where This Runs
After smart retag completes and SQLite migration is done:
1. Read each sample's tags from SQLite
2. Format as `{sample_data}` input
3. Run through qwen3:32b with the production taste prompt above
4. Write results back to SQLite (new columns or tag entries)
5. `dpo_signal` field feeds directly into DPO training pair generation

### Relationship to Existing taste_engine.py
The current Layer 1 taste engine has a personalized system prompt wired into `vibe_generate.py` and `smart_retag.py`. This production taste prompt either:
- **Replaces** the Layer 1 prompt (if the current one is generic)
- **Augments** it as a second-pass evaluation (if Layer 1 handles the descriptive tagging well)

Code should review the existing prompt in `taste_engine.py` and decide which approach is cleaner.

### Batch Processing
- Run overnight — 30K files at ~42s/file would take ~15 days, same as retag
- Consider: can the re-vibe pass use a lighter prompt (no sonic_description generation, just evaluation of existing tags)? If so, throughput could be much higher.
- Alternative: if we hit SFT → 7B before re-vibe, the distilled model runs faster

---

## Example Evaluations

### High Score Example
**Input:** `funk_bass_loop_112bpm.wav` — type: BAS, vibe: warm, texture: saturated, genre: funk, energy: mid

```json
{
  "vibe_score": 0.88,
  "production_fit": "strong",
  "best_use": "Anchor bass loop for a disco-funk groove — pair with a tight kick on the same bank",
  "vibe_adjustments": {
    "vibe": ["warm", "soulful"],
    "energy": "mid-high",
    "scene": "club_floor"
  },
  "dpo_signal": "chosen"
}
```

### Low Score Example
**Input:** `dark_ambient_drone_pad.wav` — type: PAD, vibe: dark, texture: ethereal, genre: ambient, energy: low

```json
{
  "vibe_score": 0.15,
  "production_fit": "skip",
  "best_use": "Not production material — consumption taste only. Would need heavy processing and a rhythmic context to be usable.",
  "vibe_adjustments": {
    "vibe": ["dark", "dreamy"],
    "energy": "low",
    "scene": "texture_layer"
  },
  "dpo_signal": "rejected"
}
```

### Nuanced Example
**Input:** `distorted_synth_stab_Dm.wav` — type: STB, vibe: aggressive, texture: gritty, genre: electro, energy: high

```json
{
  "vibe_score": 0.82,
  "production_fit": "strong",
  "best_use": "Trigger on pad for accents and fills — the grit cuts through a mix without dominating",
  "vibe_adjustments": {
    "vibe": ["hype", "aggressive"],
    "energy": "high",
    "scene": "one_shot_trigger"
  },
  "dpo_signal": "chosen"
}
```

---

*This prompt is the quality signal for the entire downstream pipeline. If this is wrong, SFT learns the wrong thing, DPO corrects in the wrong direction, and the 7B model produces bad tags. Get this right.*
