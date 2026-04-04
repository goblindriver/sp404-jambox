# Smart Retag: LLM Tagger Specification

**Date:** April 3, 2026
**From:** Chat
**To:** Code Agent
**Re:** System prompt, quality rubric, trim policy, vocabulary, processing order, and runtime architecture for the smart retag pipeline

---

## 0. Architecture: What Runs Where

### CLI Batch Tool: `scripts/smart_retag.py`
The heavy lifter. Runs from terminal, not inside the webapp.

```bash
# Validation batch (100 files, type_code priority order)
python scripts/smart_retag.py --validate --limit 100

# Full library pass (overnight, checkpoint/resume)
python scripts/smart_retag.py --all

# Resume interrupted run
python scripts/smart_retag.py --resume

# Retag specific directory
python scripts/smart_retag.py --path ~/Music/SP404-Sample-Library/Drums/

# Dry run (extract features + build prompts, don't call LLM)
python scripts/smart_retag.py --dry-run --limit 10
```

**Why CLI:** Each file costs ~0.1s librosa + ~1-3s Ollama. At 30k files that's 17+ hours. Running inside Flask would block the UI, and a webapp restart mid-run risks losing progress. The CLI tool writes a checkpoint file (`data/retag_checkpoint.json`) after every batch so it can resume from any interruption.

**Checkpoint format:**
```json
{
  "started_at": "2026-04-04T22:00:00Z",
  "last_updated": "2026-04-05T03:45:12Z",
  "total_files": 30511,
  "processed": 18200,
  "tagged": 17850,
  "quarantined": 350,
  "errors": 12,
  "current_phase": "tiger_dust_demand",
  "current_type_code": "SYN",
  "batch_size": 50,
  "avg_time_per_file_ms": 1850
}
```

### Inline Retag: Inside `scripts/ingest_downloads.py`
When a single new file arrives via the watcher, the smart retag runs as one more step in the existing ingest pipeline:

1. Convert to FLAC ✅ (already exists)
2. Extract librosa features ✅ (already exists — `audio_analysis.py`)
3. Chromaprint fingerprint + dedup ✅ (already exists)
4. **Smart retag: send features to Ollama, parse tags** ← NEW
5. Write enriched tags to `_tags.json` ✅ (already exists, now with richer data)
6. Background Demucs stem split if >60s ✅ (already exists)

One LLM call (~2s) added to the existing per-file flow. Acceptable for single-file ingest. If Ollama is unavailable, fall back to filename-based tagging (current behavior) and flag the file for later retag.

### Webapp: Monitoring + Review Only
The webapp doesn't do the retagging — it observes and enables human correction.

**Power Button Dashboard additions:**
- Retag status: `18,200 / 30,511 tagged (59.6%) — ~6h remaining`
- "Start Retag" button → spawns `smart_retag.py` as subprocess, polls checkpoint file
- "Pause Retag" → writes pause flag to checkpoint, CLI stops after current batch
- Retag history: last run timestamp, files processed, quarantine count

**Tag Review UI** (editable parsed-tag review — already exists):
- Surface smart_retag output for correction
- User corrections become gold-standard training examples
- Filter by: recently retagged, low confidence, specific type_code

**Quarantine Browser** (new, simple):
- Browse files in `_QUARANTINE/` with their quality scores and sonic_descriptions
- "Keep" → move back to library, upgrade quality score
- "Delete" → permanent removal
- Bulk actions: "Delete all quality 1" with confirmation

### Training: Standalone CLI, Always
```bash
python training/vibe/prepare_dataset.py   # Export training data
python training/vibe/train_lora.py        # QLoRA fine-tune
python training/vibe/eval_model.py        # Evaluate
```
GPU-bound, runs occasionally. Never inside the webapp.

---

## 1. System Prompt for the Tagger LLM

```
You are a sample library tagger for an SP-404 sampler. You analyze audio features and metadata to generate precise tags that help a fetch system find the right sample for a musical context.

You will receive:
- Audio features extracted by librosa (spectral centroid, MFCCs, spectral rolloff, chroma, zero-crossing rate, onset strength, RMS envelope, BPM, key)
- Filename and directory path
- File duration in seconds

Respond with ONLY a JSON object. No explanation, no markdown, no preamble.

{
  "type_code": "<one of: KIK, SNR, HAT, PRC, BAS, SYN, PAD, VOX, FX, BRK, RSR, GTR, HRN, KEY, STR>",
  "playability": "<one of: one-shot, loop, chop-ready, layer, transition>",
  "vibe": ["<1-3 tags from: dark, warm, hype, dreamy, nostalgic, aggressive, mellow, soulful, eerie, playful, gritty, ethereal, triumphant, melancholic, tense>"],
  "texture": ["<1-2 tags from: dusty, lo-fi, raw, clean, warm, saturated, bitcrushed, airy, crispy, glassy, muddy, vinyl, tape, digital, organic>"],
  "genre": ["<1-2 tags from: funk, soul, disco, house, electronic, hiphop, dub, ambient, jazz, rock, punk, dancehall, latin, pop, rnb, industrial, boom-bap, lo-fi, tropical, afrobeat>"],
  "energy": "<one of: low, mid, high>",
  "sonic_description": "<1 sentence describing the sound character — what would a producer hear?>",
  "quality_score": <1-5 integer>,
  "instrument_hint": "<specific instrument if identifiable: rhodes, clavinet, 808, tambourine, melodica, congas, etc. null if not identifiable>"
}

RULES:
- type_code is the PRIMARY classification. Get this right above all else.
- Use audio features to inform tags, not just the filename. Filenames lie.
- For type_code, use spectral features:
  - KIK: low spectral centroid, strong onset, short duration, minimal high-frequency
  - SNR: mid-high centroid, sharp onset, broadband noise, short duration
  - HAT: high centroid, high zero-crossing rate, very short duration
  - PRC: variable centroid, strong onset, short-to-mid duration
  - BAS: low centroid, sustained or rhythmic, strong low-frequency energy
  - SYN: mid centroid, sustained, harmonic content, evolving timbre
  - PAD: low-mid centroid, long sustained, slow attack, ambient character
  - VOX: mid centroid, formant structure in MFCCs, variable duration
  - FX: unusual spectral profile, non-musical or abstract
  - BRK: rhythmic onsets, multiple transients, longer duration (>2s typically)
  - RSR: rising spectral energy over time, building character
  - GTR: mid centroid, plucked/strummed onset pattern, harmonic series
  - HRN: mid-high centroid, brass formant structure, sustained
  - KEY: mid centroid, percussive onset with sustained harmonics (piano/organ/rhodes)
  - STR: mid centroid, bowed onset, rich harmonic series, sustained
- playability heuristics:
  - Duration <2s and strong single onset → one-shot
  - Duration >2s with rhythmic onsets → loop or chop-ready
  - Duration >2s with steady/evolving RMS → layer or loop
  - Rising RMS envelope → transition or riser
  - Chop-ready: longer samples with clear internal structure (verse, phrase, musical sentence)
- vibe is subjective but guided by features:
  - Low centroid + slow attack + warm MFCCs → warm, mellow, soulful
  - High centroid + strong onsets + broadband → aggressive, hype, gritty
  - High centroid + low energy + sparse → ethereal, dreamy, eerie
  - Mid centroid + swing rhythm + vintage texture → nostalgic, dusty
- energy is about intensity and density:
  - low: sparse, ambient, gentle, atmospheric
  - mid: moderate activity, groove-oriented, head-nodding
  - high: dense, loud, driving, peak-time
- quality_score criteria (see Section 2 below for full rubric)
- instrument_hint: be specific when possible. "synth" is too generic — say "supersaw", "acid 303", "FM bell", "analog pad". null is fine for drums and FX.
- When in doubt between two type_codes, prefer the one that's more useful for pad assignment (e.g., a funky guitar riff is GTR not BRK, even if it has rhythmic content)
```

### Additional Type Codes (New)

The original TAGGING_SPEC had 10 type codes. The retag adds 5 more for better instrument resolution:

| Code | What | Why |
|------|------|-----|
| GTR | Guitar | Distinct from SYN — different performance context, different pad behavior |
| HRN | Horns/Brass | Tiger Dust needs funk horns, ska brass, soul horn sections |
| KEY | Keys/Piano | Rhodes, organ, clavinet, piano — distinct from generic SYN |
| STR | Strings | Orchestral strings, violin, cello — distinct timbre from pads |
| RSR | Riser/Build | Was already in pad descriptions but not a formal type_code |

These new codes should be added to `docs/TAGGING_SPEC.md` and the fetch scoring system.

---

## 2. Quality Scoring Rubric

Quality is **Jambox-specific** — we're asking "does this sample earn a pad on an SP-404 for live performance?" Not "is this a technically good recording."

| Score | Label | Criteria |
|-------|-------|----------|
| **5** | Essential | Instantly usable. Distinctive character. Sits perfectly in a mix. You'd build a bank around this sound. Would survive resample passes through SP-404 effects without turning to mud. |
| **4** | Strong | Solid, usable, good character. Might need minor EQ but belongs in the library. Reliable workhorse sample. |
| **3** | Decent | Usable in context but not special. Generic drum hit, stock synth preset, nothing wrong but nothing memorable. The "fine" category. |
| **2** | Weak | Technical issues (clipping, excessive noise, bad trim points), too similar to better versions already in the library, or simply boring. Could be replaced without anyone noticing. |
| **1** | Cut | Broken (corrupt, silent, extreme artifacts), completely unusable (wrong format, absurd length), or irrelevant to any SP-404 use case (full mixed tracks, podcast intros, sound design for film). |

### LLM Guidance for Quality Scoring

Include these heuristics in the system prompt context:

```
QUALITY SCORING for SP-404 live performance context:
- Samples under 0.1s are almost always 1 (too short to be useful)
- Samples over 120s are almost always 1-2 (too long for pad-based workflow)
- Ideal one-shot duration: 0.1s - 3s
- Ideal loop duration: 2s - 30s
- Ideal chop-ready duration: 5s - 60s
- Clipping (RMS near 0dB with flat peaks) penalizes by 1 point
- Dead silence at start/end (>0.5s) penalizes by 1 point (bad trim)
- Extreme low-frequency rumble without musical content: penalize by 1 point
- Files from renowned sample packs (Samples From Mars, Splice, etc.) get benefit of the doubt
- Vintage/lo-fi character is a FEATURE not a flaw — dusty is good, broken is bad
- Mono is fine (SP-404A is mono output anyway)
```

---

## 3. Trim Policy

### Tiers

| Quality Score | Action | Destination |
|---------------|--------|-------------|
| 5 | Keep | Library (no change) |
| 4 | Keep | Library (no change) |
| 3 | Keep | Library (no change) — these are the "decent bench players" |
| 2 | Quarantine | Move to `_QUARANTINE/` — human review before delete |
| 1 | Quarantine | Move to `_QUARANTINE/` — human review before delete |

**Never auto-delete.** Always quarantine. The `_QUARANTINE/` folder mirrors `_DUPES/` in concept — a staging area for review.

### Quarantine Review Workflow

After the retag pass:
1. Code generates a quarantine report: `data/reports/quarantine_review.md`
2. Report shows: total files quarantined, total size, breakdown by quality score and type_code
3. Report includes 10 random samples from each score tier with filenames and sonic_description
4. Jason reviews the report, spot-checks a few files, gives thumbs up/down
5. If approved: bulk delete quarantined files, reclaim space
6. If false positives found: adjust scoring rubric, re-run on quarantined files

### Relevance Scoring (Phase 2 — after initial retag)

After the full retag, run a second pass:
- For each file: does ANY preset in the system (Tiger Dust + all genre presets) have a pad description that would match this file?
- Files that match zero presets → flag as "unmatched" (not quarantine — they might match future presets)
- Coverage gaps surfaced: which pad descriptions have <3 candidates? Those are the download priorities.

---

## 4. Tag Vocabulary Refinements

### Additions to TAGGING_SPEC.md

**New type codes:** GTR, HRN, KEY, STR, RSR (see Section 1)

**New genre tags:**
- `boom-bap` — distinct from generic hiphop (dustier, vinyl-oriented, 85-95 BPM)
- `tropical` — dancehall-adjacent but broader (soca, reggaeton, afrobeat)
- `lo-fi` — as a genre tag (lo-fi hip-hop, lo-fi house) distinct from lo-fi as a texture
- `afrobeat` — Fela Kuti polyrhythmic energy, distinct from generic world music

**New texture tags:**
- `vinyl` — crackle, warmth, that specific frequency roll-off
- `tape` — saturation, wow/flutter, compression character
- `organic` — acoustic/natural source, not synthesized
- `digital` — clean, precise, quantized, modern

**New vibe tags:**
- `triumphant` — big, victorious, arms-in-the-air (for Peak Hour)
- `tense` — building pressure, not yet released (for builds and risers)

**New instrument_hint vocabulary** (non-exhaustive, LLM should be creative):
- Drums: 808, 909, SP-1200, vinyl break, live kit, processed break
- Bass: sub, 808 sub, acid 303, Moog, slap, fingered, synth bass
- Keys: rhodes, wurlitzer, clavinet, organ (B3/farfisa/vox), grand piano, upright piano
- Synth: supersaw, acid, FM, analog, wavetable, granular
- Guitar: clean, overdriven, distorted, acoustic, funk chicken-scratch, reggae skank
- Brass: trumpet, trombone, sax (alto/tenor/soprano), horn section, ska brass
- Strings: violin, cello, string section, pizzicato
- Percussion: congas, bongos, shaker, tambourine, cowbell, woodblock, cabasa, guiro, timbales, steel pan, djembe

---

## 5. Processing Order

**Preset-demand-first.** Don't process randomly — process in the order that makes fetch work fastest.

### Phase 1: Tiger Dust Demand (tag what the default set needs)
1. All files with type_code KIK (kicks are pad 1 in every bank)
2. All files with type_code SNR
3. All files with type_code HAT
4. All files with type_code PRC
5. All files with type_code BRK (breaks/loops — pads 5-8)
6. All files with type_code BAS
7. All files with type_code SYN, PAD, KEY
8. All files with type_code VOX, FX, RSR
9. All files with type_code GTR, HRN, STR

After each batch: run a fetch dry-run on Tiger Dust. Report how many pads now have differentiated candidates vs. before.

### Phase 2: Everything Else
Process remaining untagged files in directory order. This catches any files the type_code pre-filter missed.

### Phase 3: Re-score
After full retag: re-run quality scoring on everything, now with the full library context (the LLM can spot dupes and redundancy better when it's seen the whole collection).

---

## 6. Validation Protocol

Before the overnight run, validate on a small batch:

1. **Pull 100 files** — 10 each from: kicks, snares, hats, percussion, breaks, bass, synths, pads, vocals, FX
2. **Run the retag pipeline** on these 100
3. **Chat reviews the output** — checks type_code accuracy, vibe/texture appropriateness, quality scores, instrument_hints
4. **Tune the prompt** based on what's wrong
5. **Run again** on the same 100, verify improvement
6. **Green light** the full overnight pass

Expected issues to catch in validation:
- Type_code confusion (breaks getting tagged as drums, pads getting tagged as synths)
- Quality scores too generous or too harsh
- Genre tags too broad (everything is "electronic")
- Vibe tags too narrow (everything is "dark" or "warm")
- instrument_hint hallucinations (LLM invents instruments that aren't there)

---

## 7. Integration Points

### _tags.json Schema Update

Current tag entry:
```json
{
  "file": "path/to/sample.flac",
  "type_code": "KIK",
  "playability": "one-shot",
  "vibe": ["warm"],
  "genre": ["funk"],
  "energy": "mid",
  "bpm": 0,
  "key": "XX",
  "source": "kit"
}
```

New tag entry (after smart retag):
```json
{
  "file": "path/to/sample.flac",
  "type_code": "KIK",
  "playability": "one-shot",
  "vibe": ["warm", "nostalgic"],
  "texture": ["dusty", "vinyl"],
  "genre": ["funk", "soul"],
  "energy": "mid",
  "bpm": 0,
  "bpm_source": "librosa",
  "key": "XX",
  "key_source": "librosa",
  "loudness_db": -12.3,
  "source": "kit",
  "instrument_hint": "vinyl break",
  "sonic_description": "Warm dusty kick with vinyl crackle, soft transient, mid-low punch",
  "quality_score": 4,
  "tag_source": "smart_retag_v1",
  "tagged_at": "2026-04-04T03:22:15Z",
  "features": {
    "chromaprint": "AQADtNIyRcm...",
    "spectral_centroid": 1245.3,
    "spectral_rolloff": 4200.7,
    "zero_crossing_rate": 0.042,
    "onset_strength": 18.5,
    "rms_peak": -6.2,
    "mfcc": [12.3, -4.5, 2.1, 0.8, -1.2, 3.4, -0.9, 1.1, -2.3, 0.5, -0.3, 1.7, -1.8],
    "chroma": [0.8, 0.1, 0.3, 0.05, 0.6, 0.2, 0.1, 0.9, 0.15, 0.4, 0.05, 0.3],
    "clap_embedding": null
  }
}
```

**Feature store principle:** Extract audio features once during the retag pass, store them in `_tags.json` alongside the tags. All subsequent similarity queries run against stored vectors — never re-read the audio file. The `features` object is the foundation for multi-resolution deduplication and similarity search.

### Multi-Resolution Similarity (Feature Store)

Three tiers of similarity, each using features already extracted or easily added. Extract once, query forever.

**Tier 1: Chromaprint (exact/near-exact dupes) — ALREADY RUNNING**
- What it catches: same file from two packs, same file with different metadata/trim
- Resolution: binary — either a match or not (at threshold)
- Current threshold: 0.95
- Stored as: `features.chromaprint` (fingerprint string)
- Speed: instant lookup against stored fingerprints

**Tier 2: MFCC Cosine Similarity (timbral dupes) — FREE, FEATURES ALREADY EXTRACTED**
- What it catches: "same instrument, different recording." Two snare recordings from different sessions. Same synth preset in two different packs. Same loop at different gain.
- Resolution: continuous 0.0-1.0 similarity score
- Stored as: `features.mfcc` (13-coefficient vector, already extracted by librosa)
- Computation: cosine similarity between MFCC vectors — pure math, no audio I/O
- Suggested threshold: 0.92 for "likely same sound," 0.85 for "similar character"
- Use cases:
  - Dedup pass that catches what Chromaprint misses
  - "Find similar" button in the UI — click a pad, see other files with similar timbre
  - Fetch diversity enforcement — prevent the top 5 candidates from all sounding identical

**Tier 3: CLAP Embeddings (semantic similarity) — REQUIRES ONE ADDITIONAL PASS**
- What it catches: "sounds like a dusty vinyl break" — semantic audio similarity via natural language
- Resolution: continuous, in embedding space
- Stored as: `features.clap_embedding` (512-dim vector, initially null)
- Requires: LAION-CLAP model (identified in Cowork open-source tools research)
- Computation: one forward pass per file (~0.5s on Apple Silicon), then cosine similarity between embeddings
- Use cases:
  - Natural language search against audio content: "find me something warm and Rhodes-like"
  - Vibe-based bank coherence scoring: do all samples in a bank cluster together in embedding space?
  - Smart fetch: score candidates by embedding similarity to a reference sound, not just tag matching
  - Replaces/augments the LLM for fetch scoring — faster and more consistent than an LLM call per query

**Implementation plan:**
1. Smart retag stores Chromaprint + librosa features (Tier 1 + 2) — **do this now**
2. CLAP embedding pass as a separate overnight job after retag is validated — **do this later**
3. `features.clap_embedding` starts as null, filled in by the CLAP pass
4. New script: `scripts/similarity_search.py` — query stored features at any tier
5. Webapp integration: "Find Similar" button on pad view, uses Tier 2 (MFCC) by default, Tier 3 (CLAP) when available

**Why this matters for Jambox:**
- Dedup at 0.95 Chromaprint found 11.5 GB. MFCC similarity at 0.92 will likely find another significant chunk — sounds that are "basically the same" but different enough recordings to dodge fingerprint matching.
- CLAP embeddings enable the vibe search we actually want: describe a sound in words, find it by what it sounds like, not what it's named.
- All three tiers work from stored features. The expensive part (reading + analyzing audio) happens exactly once.

### Fetch Scoring Updates

After retag, `fetch_samples.py` scoring should be updated:
- `texture` becomes a scored dimension (same weight as vibe keywords)
- `instrument_hint` gets exact-match bonus (+5 when pad description mentions a specific instrument)
- `quality_score` becomes a tiebreaker (between equal-scoring candidates, pick the higher quality one)
- `sonic_description` is stored but NOT used for keyword scoring — it's for human browsing and future embedding search
- **MFCC diversity penalty:** When building the top-N candidates for a pad, penalize candidates whose MFCC vectors are too similar to already-selected candidates (cosine sim >0.92). Prevents "5 copies of the same kick" in the results.
- **CLAP scoring (when available):** If a reference sound or text query has a CLAP embedding, score candidates by embedding cosine similarity. This replaces keyword matching with "sounds like" matching.

### Training Data Export

Every smart-retagged file is a training example:
- Input: audio features + filename + path
- Output: the tag JSON
- User corrections (from editable tag review UI) become gold-standard overrides
- Export format: JSONL compatible with `training/vibe/prepare_dataset.py`
