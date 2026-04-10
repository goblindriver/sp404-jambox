# Jambox Optimization & Refinement Plan

**Date:** April 3, 2026
**Context:** Infrastructure phase complete. All systems green. Focus shifts from "does it work" to "does it sound right."

---

## Tier 1: Fetch Quality (Sound Accuracy)

**Goal:** When you load a preset and hit Fetch, every pad should sound like it belongs.

### 1A. Fetch Quality Audit

**What:** Load Tiger Dust Block Party. Run Fetch All (or bank-by-bank). Listen to every pad. Score each:
- **Hit** — right vibe, right energy, immediately usable
- **Close** — right category but wrong character (a kick, but too clean for funk)
- **Miss** — wrong sound entirely

**Output:** Hit rate percentage per bank and overall. Target: 75%+ hits.

**Diagnosis from results:**
- Low hit rate + correct type_codes → scoring weights need tuning (`config/scoring.yaml`)
- Low hit rate + wrong type_codes → tagger is mislabeling files
- Empty/fallback results → library coverage gap (no matching files exist)
- Hits but wrong energy → energy/vibe tags are unreliable

### 1B. Scoring Weight Tuning

Current weights (from `config/scoring.yaml`):
- Type code match: +10 / mismatch: -8
- Playability match: +5
- BPM proximity: +3-4
- Key match: +3
- Keyword match: +3 each

**Potential adjustments to test:**
- Increase vibe keyword weight (currently same as genre — but vibe is more subjective and harder to get right)
- Add energy tier matching (high/mid/low as a scored dimension, not just a keyword)
- Penalize BPM mismatches more aggressively for loop pads (a 90 BPM loop in a 128 BPM bank is unusable)
- Boost Plex play count influence for personal library matches (if you listen to it a lot, it's probably good)

### 1C. Pad Description Refinement

After the audit, rewrite pad descriptions that consistently miss. Rules of thumb:
- 3-4 keywords max — more isn't better, it fragments the search
- Lead with the most distinctive keyword (the one that narrows the field most)
- Use texture words (dusty, crispy, warm) over genre words when genre is already set by the bank
- Playability tag matters more for loops than one-shots

---

## Tier 2: Library Health

### 2A. Multi-Resolution Dedup

Three tiers of duplicate detection, each using features stored during the smart retag. Extract once, query at increasing resolution.

**Tier 1 — Chromaprint (done):** 11.5 GB found at 0.95 threshold. Catches exact/near-exact dupes.

**Tier 2 — MFCC Similarity (free after retag):** Cosine similarity on stored MFCC vectors. Catches "same sound, different recording" — two snare recordings from different sessions, same synth preset in different packs. Threshold: 0.92 for "likely same sound." Run this pass after retag completes — no audio I/O needed, pure vector math.

**Tier 3 — CLAP Embeddings (future):** Semantic audio similarity. Catches "these pads serve the same musical purpose even though they sound different." Requires LAION-CLAP model. One additional overnight pass to compute embeddings, then similarity is instant.

**Review process (same for all tiers):**
1. Code generates dupe pairs with similarity scores
2. Spot-check 25 pairs — true dupe rate?
3. If >90% true → bulk action, reclaim space
4. If false positives → raise threshold, re-query stored features (no re-extraction)

### 2B. Tag Accuracy Audit

**What:** Random sample of 50 files from the library. For each, check:
- Is the `type_code` correct? (Is the thing labeled KIK actually a kick?)
- Is the `playability` correct? (Is the thing labeled "loop" actually a loop?)
- Is the `bpm` correct? (Does librosa's detection match the actual tempo?)
- Is the `key` correct? (Does librosa's key match the actual key?)
- Are the `vibe` and `genre` tags reasonable?

**Output:** Accuracy percentages per field. Identify systematic errors.

**Expected problems:**
- BPM detection unreliable on breaks with heavy swing
- Key detection unreliable on one-shots and percussion
- Type code confusion between similar categories (SYN vs PAD, BRK vs BAS)
- Vibe tags too generic ("dark" applied to everything minor key)

**Fixes:**
- Add rules: don't attempt key detection on type_codes KIK, SNR, HAT, PRC
- Add rules: don't attempt BPM detection on one-shots (playability = one-shot)
- Retrain type_code classification if error rate >15%

### 2C. Library Coverage Analysis

**What:** Generate a coverage report showing tag distribution across the full library.

**Dimensions to analyze:**
- `type_code` distribution — how many of each? (expect: lots of KIK/SNR/HAT, few VOX/FX)
- `genre` distribution — what genres are well-covered vs sparse?
- `vibe` distribution — same question for vibes
- `energy` distribution — is the library skewed toward high energy?
- `bpm` distribution — histogram showing tempo coverage
- `key` distribution — are we missing entire keys?

**Output:** Coverage report with gaps highlighted. Directly informs Cowork download priorities.

**Expected gaps (based on Tiger Dust needs):**
- Caribbean instruments (steel pan, soca drums, dancehall riddims)
- Dub elements (melodica, echo-heavy bass, dub delay FX)
- Soul instruments (Rhodes, organ, tambourine, horn sections)
- Funk-specific elements (clavinet, wah guitar, slap bass)
- Crowd noise, air horns, and performance SFX

### 2D. Cowork Download Prioritization (from coverage gaps)

After 2C, rank download priorities by which gaps most affect the active presets:
1. Gaps that affect Tiger Dust Block Party (the default set)
2. Gaps that affect multiple presets (cross-cutting needs)
3. Gaps in pending preset banks (Riot Mode, Minneapolis Machine)
4. General library diversity

---

## Tier 3: LLM Parse Quality

### 3A. Base vs RAG Comparison (GATE)

**What:** Run the eval suite in both modes. Compare parse accuracy, draft quality, and ranking correctness.

**Action:**
```bash
python training/vibe/eval_model.py --mode base
python training/vibe/eval_model.py --mode rag
python training/vibe/compare_modes.py
```

**Decision tree:**
- RAG significantly better → keep investing in RAG pipeline (ChromaDB, embeddings)
- RAG marginally better → RAG not worth the complexity, stick with base + better prompts
- RAG worse → something's broken in retrieval, debug before proceeding
- Either way → this gates QLoRA. Don't fine-tune until base vs RAG is understood.

### 3B. Prompt Coverage Test

**What:** Feed every pad description from Tiger Dust through the parser. Check:
- Does it produce valid structured output?
- Are the type_codes preserved correctly?
- Are distinctive keywords (melodica, clavinet, 808) passed through or lost?
- Does it handle compound concepts ("dub echo loop" = dub genre + echo texture + loop playability)?

**Expected problems:**
- Instrument-specific keywords (melodica, clavinet, cowbell) not in the parser's vocabulary
- Compound texture words parsed as genre or vice versa
- Energy level not inferred from context (a "massive" bass should be high energy)

### 3C. Parser Vocabulary Expansion

After 3B, expand `config/vibe_mappings.yaml` with:
- Missing instrument keywords → type_code mappings
- Genre-specific vocabulary (riddim, soca, dub, boom-bap)
- Texture words that imply energy (massive → high, delicate → low, dusty → mid)

---

## Tier 4: Workflow & Performance

### 4A. Preview Latency

**What:** Time the end-to-end flow: click pad → hear audio preview.

**Target:** <500ms from click to sound.

**If slow:** Profile where time is spent — file I/O, FLAC decode, network, UI rendering.
Consider pre-converting preview files to low-bitrate WAV/MP3 for instant playback.

### 4B. Single-Pad Re-fetch

**What:** When one pad doesn't hit right, how fast can you get a different sample?

**Current flow:** Edit pad description → re-fetch single pad → preview
**Ideal flow:** Click pad → "Next" button cycles through top-N candidates without re-fetching
**Requires:** Fetch returns ranked candidates, UI stores the list, "Next" just loads the next one

### 4C. Bank Switching

**What:** How fast does the UI update when switching between banks or loading a new preset?

**Target:** <1s for full bank load including pad previews.

### 4D. Fetch All Performance

**What:** Time a full 120-pad fetch (all 10 banks in Tiger Dust).

**Target:** <30s for the full set.

**If slow:** Profile scoring algorithm. Consider pre-computing type_code indexes for O(1) lookup instead of scanning all 20,925 files per pad.

---

## Execution Order

### Phase 0: Smart Retag (MUST HAPPEN FIRST)
Nothing else in this plan works without real tags. 108 tagged files out of 30,511 means the fetch system is fundamentally broken.

0a. **Validate retag pipeline on 100 files** — Code builds `scripts/smart_retag.py`, Chat reviews output and tunes the prompt. See `SMART_RETAG_SPEC.md` for system prompt, quality rubric, trim policy, vocabulary.
0b. **Retag Phase 1: Tiger Dust demand** — Process files in type_code priority order (KIK → SNR → HAT → PRC → BRK → BAS → SYN/PAD/KEY → VOX/FX/RSR → GTR/HRN/STR). Run fetch dry-runs after each batch to watch accuracy improve.
0c. **Retag Phase 2: Everything else** — Full overnight pass on remaining untagged files.
0d. **Quarantine pass** — Move quality 1-2 files to `_QUARANTINE/`. Generate quarantine report for human review.

### Phase 1: Measure (after retag — tags are now real)
1. Fetch Quality Audit on Tiger Dust (Tier 1A) — **you do this, ears required**
2. Library Coverage Analysis (Tier 2C) — **Code agent**
3. Tag Accuracy Audit (Tier 2B) — **Code agent generates sample, you spot-check**
4. Base vs RAG comparison (Tier 3A) — **Code agent**

### Phase 2: Fix (based on measurements)
5. Scoring weight tuning (Tier 1B) — **Code agent, guided by audit results**
6. Pad description refinement (Tier 1C) — **Chat, based on audit results**
7. Dedupe review (Tier 2A) — **Code agent spot-check, you approve**
8. Parser vocabulary expansion (Tier 3C) — **Chat updates vibe_mappings.yaml**

### Phase 3: Fill (library gaps)
9. Coverage gap download briefs (Tier 2D) — **Chat writes briefs**
10. Cowork executes downloads — **Cowork** (new files auto-retag on ingest)
11. Re-run Fetch Quality Audit — **you, ears again**

### Phase 4: Polish (workflow)
12. Preview latency optimization (Tier 4A) — **Code agent**
13. Single-pad re-fetch / candidate cycling (Tier 4B) — **Code agent**
14. Fetch All performance (Tier 4D) — **Code agent**

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Files with real dimensional tags | 108 / 30,511 (0.3%) | 30,511 / 30,511 (100%) |
| Fetch hit rate (Tiger Dust) | Unmeasurable (no tags) | >75% |
| Type code accuracy | Unknown | >90% |
| BPM detection accuracy (loops) | Unknown | >85% |
| Key detection accuracy (melodic) | Unknown | >80% |
| Tag coverage (no empty categories) | Unknown | 0 empty genre/vibe combos needed by presets |
| Library after trim | 30,511 files | ~20-25k (cut the dead weight) |
| Dedupe false positive rate | Unknown | <5% |
| Preview latency | Unknown | <500ms |
| Full set fetch time | Unknown | <30s |
| RAG vs base improvement | Unknown | >10% to justify RAG complexity |
| Training examples from retag | 0 | ~25-30k (every tagged file) |
