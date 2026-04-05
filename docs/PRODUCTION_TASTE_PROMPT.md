# PRODUCTION TASTE PROMPT — Jambox Re-Vibe Pass
**Date:** 2026-04-04
**From:** Chat (Claude)
**Status:** Active — awaiting retag completion + SQLite migration before deployment

---

## Purpose

After smart retag finishes tagging ~30K samples with raw descriptive tags, the re-vibe pass runs this prompt on every sample to answer one question: **"Would Jason reach for this when building a set?"**

This is NOT a general quality assessment. It's a production-taste filter tuned to Jason's specific aesthetic.

---

## Jason's Production Identity

### The Philosophy: "Party at the End of the World"
The consumption taste is dark — nostalgic, moody, atmospheric. But the production taste is joyful, danceable, four-on-the-floor. The darkness shows up as *contrast* — tension before the drop, a haunted vocal over a driving beat, melancholy chords under euphoric energy. The darkness serves the party, never kills it.

### Production Taste Stack (optimization target)
1. **Hype** — infectious, magnetic energy. Not aggressive for its own sake.
2. **Warm** — analog character, saturation, tape feel. Vintage over pristine.
3. **Soulful** — human groove, swing, vocal presence. Machines with feelings.

### Consumption Taste Stack (context, NOT the target)
1. **Nostalgic** — 80s synths, 90s breakbeats, vintage textures
2. **Dark** — minor keys, tension, atmosphere, dread-as-beauty
3. **Dreamy** — reverb, delay, space, ethereal

### The Tension That Makes It Work
A sample that's purely dark/ambient scores LOW for production — Jason listens to that but doesn't build sets with it. But a dark sample with a danceable backbone scores HIGH — that's the sweet spot. The production taste is about finding darkness that *moves*.

### Genre Affinities (production context)
High affinity: house, disco, electro, funk, synth-pop, new wave, breakbeat, acid, italo disco, EBM, nu-rave, electroclash
Medium affinity: hip-hop, trip-hop, dub, afrobeat, UK garage, jungle, drum & bass
Low affinity (but not zero): ambient, drone, noise, field recording, classical, acoustic folk
Context-dependent: punk, riot grrrl, industrial (high energy but needs the right texture)

---

## Vibe Score: Sub-Dimensions

Each sample gets scored on 5 sub-dimensions (0.0–1.0) plus a composite `vibe_score`.

### Dimension Definitions

#### 1. `danceability` (0.0–1.0)
Can you move to this? Does it have rhythmic drive, groove, pulse?
- 1.0 = four-on-the-floor house kick, driving disco beat, infectious funk groove
- 0.7 = syncopated breakbeat, head-nod hip-hop, swung percussion
- 0.4 = ambient pulse, slow throb, implied rhythm
- 0.1 = static texture, drone, field recording, no rhythmic content

#### 2. `warmth` (0.0–1.0)
Does it have analog character, saturation, organic feel?
- 1.0 = tape-saturated, vinyl-warm, tube-driven, Rhodes/Wurlitzer
- 0.7 = subtle harmonic distortion, warm digital synth, round bass
- 0.4 = clean but not sterile, neutral production
- 0.1 = clinical, hyper-digital, cold, thin, brittle

#### 3. `soul` (0.0–1.0)
Does it feel human? Groove, swing, vocal presence, emotional weight?
- 1.0 = raw vocal performance, live funk band, gospel-inflected anything
- 0.7 = chopped vocal sample with character, swung drums, expressive synth line
- 0.4 = programmed but groovy, quantized with feel
- 0.1 = mechanical, robotic, purely algorithmic, no human imprint

#### 4. `tension` (0.0–1.0)
Does it create productive darkness — contrast, drama, edge that serves the set?
- 1.0 = minor key over driving beat, acid line building to release, haunted vocal over four-on-the-floor
- 0.7 = moody chord progression, filtered build, suspenseful texture
- 0.4 = neutral mood, neither dark nor bright
- 0.1 = purely bright, major key, no shadow, no edge
- NOTE: High tension is GOOD when paired with high danceability. High tension with low danceability = ambient (low vibe_score).

#### 5. `texture_fit` (0.0–1.0)
Does the sonic character fit the Jambox aesthetic? Considers production quality, era feel, sample usability on the SP-404.
- 1.0 = perfectly SP-404 ready, vintage analog character, sits in a mix instantly, loop-ready or chop-ready
- 0.7 = good character, might need minor processing, solid palette piece
- 0.4 = usable but generic, stock-library feel, needs work
- 0.1 = wrong format, too long, too noisy (bad noise), unusable on hardware

### Composite Vibe Score

```
vibe_score = (
    danceability * 0.30 +
    warmth * 0.20 +
    soul * 0.20 +
    tension * 0.15 +
    texture_fit * 0.15
)
```

Danceability is weighted highest because Jason's production identity is fundamentally about movement. Warmth and soul are equally weighted as the two "character" dimensions. Tension and texture_fit are supporting dimensions.

### Score Interpretation
- **0.8–1.0** → Core library. First-reach samples. Auto-eligible for preset population.
- **0.6–0.8** → Strong utility. Good for fills, transitions, texture layers.
- **0.4–0.6** → Situational. Might work in specific contexts. Available but not prioritized.
- **0.2–0.4** → Low fit. Kept for completeness but rarely surfaced.
- **0.0–0.2** → Quarantine candidate. Review for deletion or archive.

---

## The Prompt

### System Prompt (for qwen3:32b or future fine-tuned model)

```
You are a production taste engine for a music producer named Jason who performs on a Roland SP-404A sampler.

## Jason's Philosophy: "Party at the End of the World"

Jason's consumption taste is dark and nostalgic, but his production taste is joyful, danceable, and four-on-the-floor. The darkness in his sets serves as contrast and tension, never as the destination. Every sample should earn its place by answering: "Does this make you want to move?"

This philosophy has a direct hardware analog: the SP-404's resampling workflow. You feed in darkness — a moody sample, a haunted vocal, a brooding chord — and the machine's effects chain (Vinyl Sim, DJFX Looper, Isolator) adds warmth, grit, and life. Dark input becomes danceable output. A raw dark sample is not low-value — it is PRE-PROCESSED material. Score it based on what it BECOMES after resampling, not just what it is now.

## Production Taste Stack

1. HYPE — infectious, magnetic energy. Not aggressive for its own sake.
2. WARM — analog character, saturation, tape feel. Vintage over pristine.
3. SOULFUL — human groove, swing, vocal presence. Machines with feelings.

## Cultural DNA

Jason's aesthetic descends from a specific lineage:
- Trip-hop (DJ Shadow, Massive Attack) → crate-digging as religion, vinyl patina, cinematic atmosphere
- Abstract hip-hop (Madlib, J Dilla, MF DOOM) → SP-303 resampling, broken quantization, "drunk drums," jazz-sample alchemy
- UK bass/dubstep (Burial, Kode9) → sub-bass architecture, empty space as power, 3AM loneliness made danceable
- LA beat scene (Flying Lotus, Nosaj Thing, Teebs) → the convergence point. All of the above filtered through the SP-404 and performed live at Low End Theory
- Nujabes and the Japanese parallel → jazz-inflected warmth, spiritual dimension, lo-fi beauty

These scenes share one principle: LIMITATIONS AS CREATIVE FUEL. Dilla making Donuts on an SP-303 in a hospital bed. Burial making Untrue in Sound Forge with no DAW. The constraints of the SP-404 — limited pads, destructive resampling, characterful effects — force creative decisions that become genre-defining sounds.

## High-Value Textures (boost texture_fit when present)

- vinyl_patina — crackle, warmth, degradation (the SP Vinyl Sim sound)
- tape_saturation — cassette-era warmth, Tascam 4-track character
- broken_quantization — Dilla's drunk drums, humanized swing, off-grid feel
- sub_bass_architecture — UK dubstep's contribution to the low end
- jazz_harmonic_vocabulary — Rhodes chords, upright bass, brushed cymbals, modal harmony
- cinematic_atmosphere — trip-hop's film-score sensibility, reverb as storytelling
- resampled_texture — audible processing artifacts from SP-style resample chains

## Genre Affinities

High: house, disco, electro, funk, synth-pop, new wave, breakbeat, acid, italo disco, EBM, nu-rave, electroclash
Medium: hip-hop, trip-hop, dub, afrobeat, UK garage, jungle, drum & bass, lo-fi hip hop, beat music
Low (but not zero): ambient, drone, noise, field recording, classical, acoustic folk
Context-dependent: punk, riot grrrl, industrial (high energy but needs the right texture)

## Scoring Instructions

Score each sample on 5 dimensions (0.0–1.0):

1. danceability — rhythmic drive, groove, pulse. Four-on-the-floor = high. Head-nod = medium. Drone = low.
2. warmth — analog character, saturation, organic feel. Tape/vinyl/tube = high. Clean digital = mid. Cold/brittle = low.
3. soul — human feel, groove, swing, vocal presence. Live performance = high. Swung programming = mid. Robotic = low.
4. tension — productive darkness that serves a set. Minor key + driving beat = high. Moody build = mid. Pure bright = low. CRITICAL: high tension + high danceability = GOOD (darkness that moves). High tension + low danceability = ambient (low composite score).
5. texture_fit — SP-404 readiness, era feel, usability. Vintage analog character + loop/chop ready = high. Generic stock = mid. Unusable on hardware = low. BOOST for high-value textures listed above.

Compute composite:
vibe_score = danceability * 0.30 + warmth * 0.20 + soul * 0.20 + tension * 0.15 + texture_fit * 0.15

Also provide:
- production_tags: 2-4 tags from this vocabulary: "floor-filler", "tension-builder", "warm-groove", "acid-edge", "vinyl-patina", "tape-warmth", "drunk-drums", "sub-weight", "jazz-harmony", "cinematic-mood", "resample-ready", "cosmic-jazz", "lo-fi-grit", "broken-beat", "vocal-chop", "build-and-release", "set-opener", "peak-energy", "cool-down", "texture-layer"
- set_context: one sentence describing where in a set this sample lives (e.g. "Opening mood-setter before the first four-on-the-floor drop")
- scene: where this sound lives. Values: "club_floor", "warehouse", "low_end_theory", "bedroom_lo-fi", "outdoor_festival", "cinematic", "cosmic_spiritual", "film_underscore", "late_night_drive", "after_hours"

Respond ONLY in JSON. No preamble, no markdown fencing.
```

### User Prompt Template

```
Sample: {filename}
Duration: {duration_ms}ms
BPM: {bpm}
Key: {key}
Loudness: {loudness_db} dB

Raw Tags:
- type_code: {type_code}
- genre: {genre}
- vibe: {vibe}
- texture: {texture}
- energy: {energy}
- instrument_hint: {instrument_hint}
- sonic_description: {sonic_description}
- quality_score: {quality_score}
```

### Expected Output

```json
{
  "danceability": 0.85,
  "warmth": 0.70,
  "soul": 0.65,
  "tension": 0.55,
  "texture_fit": 0.80,
  "vibe_score": 0.74,
  "production_tags": ["warm-groove", "floor-ready", "vintage-funk"],
  "set_context": "Mid-set groove lock — keeps the floor moving without peaking too early",
  "scene": "club_floor"
}
```

---

## DPO Data Strategy: Hybrid Approach

### Overview
Combine two data sources to build preference pairs for DPO training:

1. **Preset-derived pairs** (automated, bulk) — use existing bank curation as implicit signal
2. **Manual correction pairs** (human, high-quality) — Jason reviews and corrects vibe scores

### Source 1: Preset-Derived Pairs (Automated)

Samples already assigned to presets (Tiger Dust Block Party, Riot Mode, etc.) are implicit "chosen" examples — Jason already said "yes" to these by putting them in a bank.

**Generating pairs:**
- **Chosen:** Run the taste prompt on a preset-assigned sample. The output reflects production-aligned scoring. If the raw score seems too low for a sample Jason explicitly chose, adjust the chosen output to reflect high vibe_score (0.7+) with accurate sub-dimensions.
- **Rejected:** Take a similar sample (same type_code, similar genre) that is NOT in any preset. Run the taste prompt. If it scores similarly to the chosen sample, manually downweight the rejected version's key dimensions to create contrast.

**Pair quality controls:**
- Only use presets where Jason personally curated the pad assignments (not auto-generated daily banks)
- Ensure rejected samples are plausibly similar (same type_code) — don't pair a kick drum against a pad synth
- Aim for subtle differences in scoring, not dramatic ones. The model needs to learn nuance, not obvious distinctions.

**Estimated yield:** ~120 preset-assigned pads across all banks × ~3 rejected candidates each = ~360 pairs

### Source 2: Manual Correction Pairs (Human Review)

Jason reviews vibe scores in a review UI and corrects them. Each correction generates one preference pair.

**Workflow:**
1. Re-vibe pass runs on a batch of samples (start with 100–200)
2. Jason sees: sample name, audio preview, raw tags, sub-dimension scores, vibe_score
3. Jason adjusts any score he disagrees with (drag sliders or type values)
4. System saves: `(prompt, jason_version=chosen, model_version=rejected)`

**Accelerators:**
- **Batch review mode:** Show 10 samples per screen, highlight only those with vibe_score in the 0.4–0.7 range (the ambiguous zone where corrections matter most)
- **Quick actions:** "Too high" / "Too low" / "Way off" buttons that auto-adjust by -0.2 / +0.2 / flag-for-manual
- **Focus on disagreements:** Only surface samples where the model's score diverges from preset-derived expectations

**Estimated yield:** 10–20 corrections per session × 50–100 sessions = 500–2,000 pairs

### Combined Pipeline

```
Phase 1: Preset-derived pairs (~360 pairs)
├── Extract all preset-assigned samples
├── Run taste prompt on each
├── Generate rejected variants from similar unassigned samples
├── Quality filter: discard pairs with <0.1 score difference
└── Output: SFT + initial DPO training data

Phase 2: Manual corrections (500–2,000 pairs over time)
├── Run re-vibe pass on batches
├── Jason reviews in batch review UI
├── Each correction = one preference pair
├── Accumulate over sessions
└── Output: Ongoing DPO refinement data

Phase 3: Active learning (future)
├── Model flags low-confidence samples for review
├── Jason reviews only uncertain cases
├── Maximum information gain per correction
└── Output: Efficient targeted DPO data
```

### Minimum Viable DPO

Per Cowork's research:
- **500 pairs:** Noticeable improvement — achievable with preset-derived (360) + one focused review session (140)
- **1,000 pairs:** Measurable gains — achievable within first month of review sessions
- **5,000 pairs:** Sweet spot — achievable over 2–3 months of casual review

### Training Schedule (per Cowork DPO Research)

```
Step 1: SFT — Distill qwen3:32b → Qwen3 7B
├── 1-2K high-quality (input, 32B_output) pairs from retag
├── Unsloth + QLoRA, r=16, α=32, lr=2e-4, 3 epochs
└── Result: 7B that mimics 32B behavior

Step 2: DPO — Align to Jason's taste
├── 500+ preference pairs (preset-derived + manual)
├── Unsloth PatchDPOTrainer + TRL DPOTrainer
├── lr=5e-5, 1 epoch, β=0.1
├── Start from SFT checkpoint
└── Result: 7B aligned to production taste

Step 3: Export
├── Merge DPO adapter → FP16
├── Convert → GGUF via llama.cpp
├── Quantize Q4/Q5/Q6
├── Deploy via Ollama as "jambox-vibe"
└── Runs at 7B speed for inline inference
```

---

## SQLite Integration

Vibe scores go into the existing tags table via the key-value pattern:

```sql
-- Sub-dimensions
INSERT INTO tags (sample_id, tag_key, tag_value, confidence, model_version)
VALUES (123, 'danceability', '0.85', 0.85, 'qwen3:32b-revibe-v1');

-- Composite score
INSERT INTO tags (sample_id, tag_key, tag_value, confidence, model_version)
VALUES (123, 'vibe_score', '0.74', NULL, 'qwen3:32b-revibe-v1');

-- Production tags
INSERT INTO tags (sample_id, tag_key, tag_value, model_version)
VALUES (123, 'production_tag', 'warm-groove', 'qwen3:32b-revibe-v1');
INSERT INTO tags (sample_id, tag_key, tag_value, model_version)
VALUES (123, 'production_tag', 'floor-ready', 'qwen3:32b-revibe-v1');

-- Scene
INSERT INTO tags (sample_id, tag_key, tag_value, model_version)
VALUES (123, 'scene', 'club_floor', 'qwen3:32b-revibe-v1');

-- Set context (longer text, stored as tag_value)
INSERT INTO tags (sample_id, tag_key, tag_value, model_version)
VALUES (123, 'set_context', 'Mid-set groove lock — keeps the floor moving without peaking too early', 'qwen3:32b-revibe-v1');
```

### DPO Pairs Table (new)

```sql
CREATE TABLE dpo_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER NOT NULL REFERENCES samples(id),
    prompt TEXT NOT NULL,
    chosen TEXT NOT NULL,              -- JSON string of chosen output
    rejected TEXT NOT NULL,            -- JSON string of rejected output
    source TEXT NOT NULL,              -- 'preset_derived' or 'manual_correction'
    preset_name TEXT,                  -- if preset-derived, which preset
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_dpo_source ON dpo_pairs(source);
CREATE INDEX idx_dpo_sample ON dpo_pairs(sample_id);
```

---

## Dependencies

This work requires (in order):
1. ✅ Smart retag to finish (running now, ~15 days)
2. ✅ ARCH-1 SQLite migration (Code, in progress)
3. Re-vibe pass script (Code, new task after SQLite)
4. Review UI for manual corrections (Code, new task)
5. DPO pair generation script (Code, new task)

---

## Weights Discussion

The current weights (danceability 0.30, warmth 0.20, soul 0.20, tension 0.15, texture_fit 0.15) are a starting hypothesis. After the first manual review session, Jason should evaluate whether the composite score "feels right" or if weights need adjustment. The DPO process will eventually learn the implicit weights from corrections, making the explicit formula less important over time — but it's a good bootstrap.

---

*Created by Chat — April 4, 2026 (Session 4)*
*Depends on: SMART_RETAG_SPEC.md, ARCH-1 SQLite migration, Cowork DPO_TRAINING_FRAMEWORKS.md, Cowork SP404_SCENE_HISTORY.md*
