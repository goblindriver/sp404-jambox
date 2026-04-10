# Reinforcement Learning Training Pipeline — Pitch for Chat

## The Vision

Turn Jambox into a system that **learns from everything Jason owns**. Not just audio — every movie, book, audiobook, game, multitrack session, field recording, and personal film becomes training data for what "good" means. The model doesn't just tag samples generically — it understands that "dark" for someone who owns Cormac McCarthy, Berserk, The Thing, NIN multitracks, and an occult library is a very specific flavor of dark.

Right now the LLM (qwen3:32b) tags samples based on audio features + a static system prompt. It's good but generic. An RL-trained model would understand *our* taste fingerprint — built from 2,402 movies, 33K music tracks, 4,800 TV/anime episodes, 38 audiobook authors, 197 retro game collections, multitrack sessions from Marvin Gaye to Nine Inch Nails, and an occult/psychedelia research library.

## What Already Exists

We're not starting from zero. The infrastructure is substantial:

| Component | Status | What It Does |
|-----------|--------|-------------|
| QLoRA training | Working | `training/vibe/train_lora.py` — fine-tunes Qwen on JSONL |
| Session store | Working | `vibe_training_store.py` — SQLite captures prompt → LLM parse → user review → applied preset |
| Data export | Working | `prepare_dataset.py` — sessions → JSONL training examples |
| Eval suite | Working (small) | 25 seed evals across parse, draft, and ranking tasks |
| Model serving | Working | `serve_model.py` — GGUF via llama.cpp at its own endpoint |
| Smart retag | Running now | qwen3:32b tagging 30K files with audio features + LLM |
| Plex music | Working | 298 moods, 412 styles, 33K tracks with play counts |
| Plex movies/TV | **NEW** | 2,402 movies, 88 shows, taste profiling, clip extraction |
| Multitrack ingest | **NEW** | 4,336 session stems from QNAP (Marvin Gaye, Stevie Wonder, NIN, Phoenix, etc.) |
| Clip extraction | **NEW** | ffmpeg silence detection → auto-classified audio clips from movies/TV |
| Cross-media taste profiler | **NEW** | Reads ALL media to build unified vibe fingerprint |
| Review UI | Working | Editable parsed tags in vibe prompt flow |

## The Full Media Inventory

Everything on Jason's drives is training data:

### Directly Sampleable (audio already extracted or extractable)

| Source | Count | Location | Status |
|--------|-------|----------|--------|
| Sample library (FLAC) | 30,700+ | ~/Music/SP404-Sample-Library | Smart retag running |
| Multitrack session stems | 4,336 WAVs | QNAP: Video Production/Multitrack Sessions | **500+ ingested** |
| H4N field recordings | 16+ WAVs (1GB+) | QNAP: Video Production/H4N | Ready to ingest |
| Movies (clip extraction) | 2,402 films | Drobo: Multimedia/Movies | **Pipeline built** |
| TV/Anime episodes | 4,801 | Drobo: Multimedia/TV Shows + Anime | **Pipeline built** |
| Personal films | 23 files | QNAP: Video Production/Finished Movies | Ready |
| Oddcast recordings | 4+ sessions | QNAP: oddcast/ | Ready |
| Frosthelm mix | 1 WAV (45MB) | QNAP: Video Production/ | Ready |
| 4CH field recordings | 4 WAVs (770MB+) | QNAP: Video Production/ | Ready |

### Multitrack Session Artists (already separated — no Demucs needed)

| Artist | Stems | Songs | Vibe Signal |
|--------|-------|-------|-------------|
| Marvin Gaye | 78 | What's Going On, Grapevine, Ain't No Mountain, Mercy Mercy Me | soulful, warm, nostalgic |
| Stevie Wonder | 16 | Superstition | soulful, funk |
| Bob Marley | 62 | No Woman No Cry, Is This Love, Lively Up Yourself | soulful, mellow |
| Phoenix | 206 | Full Wolfgang Amadeus album (1901, Lisztomania, Countdown, etc.) | hype, playful |
| Nine Inch Nails | 256 | The Hand That Feeds (full multitrack) | aggressive, dark, industrial |
| Nirvana | 96 | Pennyroyal Tea, Polly, Sappy, Marijuana | gritty, aggressive |
| Queen | 24 | Bohemian Rhapsody, Killer Queen | hype, nostalgic |
| Def Leppard | 22 | Rock of Ages | aggressive, hype |
| Doobie Brothers | 25 | 1973 session | funk, nostalgic |
| The Beatles | 14 | Sgt Pepper | nostalgic, dreamy |
| Counting Crows | 63 | Mr Jones (Live), Hard Candy (Live) | nostalgic, soulful |
| + 18 more artists | ~1,500 | Various sessions | Various |

### Taste Signal (non-audio — trains the vibe model)

| Source | Count | What It Tells The Model |
|--------|-------|------------------------|
| **Movies** (Plex) | 2,402 | Genre distribution (Drama/Thriller/Horror/Sci-Fi), director taste (Spielberg/Scorsese/Coen Bros/Kubrick/Wes Anderson), decade preferences |
| **TV Shows** | 69 | Long-form taste signal — Breaking Bad, Archer, Daria, American Gods |
| **Anime** | 19 | Cowboy Bebop, Evangelion, Berserk, FLCL, Samurai Champloo, Vinland Saga — specific aesthetic |
| **Music** (Plex) | 33,408 tracks | 298 mood tags, 412 style tags, play counts, loudness analysis |
| **Audiobooks** | 38 authors | Palahniuk, McCarthy, Barker, Jung, Hofmann, Gibson, Gaiman, Herbert — dark/psychological taste |
| **Books** | 20+ categories | Dark Arts/occult, screenprinting, fiction (300 horror ebooks), psychedelia research |
| **MYanonamouse** | ~100 items | Occult/psychedelia collection (Austin Osman Spare, peyote research, Aleister Crowley) |
| **Retro Games** | 197 collections | Atari through Dreamcast, Neo Geo — nostalgic/playful aesthetic |
| **Personal Films** | 23 | Prairie documentaries, urban exploration, music videos — what he chose to *make* |
| **Multitrack choices** | 29 artists | Which artists he wanted to mix = strongest taste signal |

## Cross-Media Taste Fingerprint

The taste profiler (`scripts/taste_profiler.py`) reads across ALL sources and produces a unified vibe weighting:

```
Combined vibe fingerprint:
  nostalgic       0.250  ####################
  dark            0.231  ##################
  dreamy          0.201  ################
  eerie           0.097  #######
  playful         0.052  ####
  soulful         0.042  ###
  gritty          0.034  ##
  hype            0.030  ##
  aggressive      0.025  #
  tense           0.018  #
```

**Key insight:** This is fundamentally different from the Plex-only music profile (which was soulful > tense > eerie). The books, games, films, and multitrack choices shift the fingerprint toward **nostalgic-dark-dreamy** — which is the real aesthetic.

This fingerprint should weight how the model tags samples:
- A sample tagged "dark" by a model trained on this profile understands McCarthy-dark, not just "low spectral centroid"
- "Nostalgic" means Atari + prairie films + Marvin Gaye stems, not just "sounds old"
- quality_score 5 means "this is the kind of sound that fits the media world I live in"

## Five Training Data Sources (expanded from three)

### Source 1: Retag Corrections (NEW — needs building)
When the user reviews smart retag output and corrects tags.
**Signal strength:** HIGHEST — explicit, per-field, ground truth.

### Source 2: Plex Music Metadata (33K tracks)
298 mood tags, 412 style tags, play counts as preference signal.
**Signal strength:** HIGH — professional labels, massive volume.

### Source 3: Plex Movie/TV Metadata (7K+ items)
Genre distributions, ratings, viewing history → vibe vocabulary grounding.
**Signal strength:** MEDIUM — indirect but shapes what vibes mean.

### Source 4: Cross-Media Taste Profile
Books, games, audiobooks, personal films, multitrack choices → unified vibe fingerprint.
**Signal strength:** MEDIUM — contextual, shapes model personality.

### Source 5: Fetch Outcomes (implicit)
Which samples stick vs. get replaced when fetched for pads.
**Signal strength:** LOW-MEDIUM — implicit and delayed, but captures real usage.

## Architecture: The Feedback Loop

```
    ┌────────────────────────────────────────────────────────┐
    │                 MEDIA COLLECTION                        │
    │  Movies · Music · TV · Books · Games · Films · Sessions │
    └───────────────────────┬────────────────────────────────┘
                            │
                 taste_profiler.py
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │              TASTE FINGERPRINT                          │
    │  nostalgic > dark > dreamy > eerie > playful            │
    │  (weights vibe vocabulary for this specific user)       │
    └───────────────────────┬────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
    ┌──────────┐    ┌──────────────┐    ┌──────────────┐
    │  Retag   │    │  Vibe Prompt │    │   Fetch      │
    │ Review   │    │   Review     │    │  Outcomes    │
    │(tag edits)│   │(parse edits) │    │(keep/replace)│
    └────┬─────┘    └──────┬───────┘    └──────┬───────┘
         │                 │                   │
         └────────────┬────┘───────────────────┘
                      ▼
    ┌─────────────────────────────────────────┐
    │         Correction Store (SQLite)        │
    │  - original LLM output                   │
    │  - user correction                       │
    │  - error type + taste context            │
    └──────────────────┬──────────────────────┘
                       │
    ┌──────────────────▼──────────────────────┐
    │         Training Data Export              │
    │  - Preference pairs (correct > incorrect)│
    │  - Plex metadata pairs (33K+ music)      │
    │  - Taste-weighted examples               │
    │  - Fetch outcome pairs                   │
    └──────────────────┬──────────────────────┘
                       │
    ┌──────────────────▼──────────────────────┐
    │         DPO Training                     │
    │  Base: qwen3:32b → 7B LoRA distillation │
    │  Taste fingerprint as system context     │
    └──────────────────┬──────────────────────┘
                       │
    ┌──────────────────▼──────────────────────┐
    │         Serve Fine-Tuned Model           │
    │  SP404_FINE_TUNED_LLM_ENDPOINT          │
    │  (knows the user's taste DNA)            │
    └─────────────────────────────────────────┘
```

## Why DPO Instead of PPO

PPO needs a reward model and online environment — complex and compute-heavy. **DPO (Direct Preference Optimization)** learns directly from preference pairs:

- Input: `(prompt, chosen_response, rejected_response)`
- The model learns to prefer the chosen response
- Works with small datasets (100+ pairs), scales with more
- Can run on M3 24GB with QLoRA

For our use case: `(audio_features + taste_context, user_corrected_tags, original_llm_tags)` — the correction is "chosen," the LLM's original output is "rejected." The taste fingerprint becomes part of the prompt context, so the model learns what "good" means for this specific user.

## Phased Rollout

### Phase 1: Capture Infrastructure (Code builds)
- Add retag review UI to web app (browse samples, edit tags inline, approve/reject)
- Create `retag_corrections` SQLite table (mirrors `vibe_sessions` pattern)
- Log original vs. corrected for each field
- Add error type classification
- Inject taste fingerprint into smart retag system prompt

### Phase 2: Training Data Assembly (Code builds)
- `training/retag/prepare_plex_dataset.py` — export Plex mood→vibe pairs (33K+)
- `training/retag/prepare_taste_dataset.py` — export cross-media taste examples
- `training/retag/prepare_multitrack_dataset.py` — use known-artist stems as labeled examples (Marvin Gaye bass = BAS + soul + warm + nostalgic)
- Target: 40,000+ training pairs across all sources

### Phase 3: DPO Training (Code builds, Chat reviews)
- `training/retag/train_dpo.py` — DPO on combined preference pairs
- Distill 32b → 7B LoRA for inline inference speed
- Eval against expanded test suite
- Quantize to GGUF, serve at its own endpoint

### Phase 4: Online Learning Loop (stretch)
- A/B testing: base model vs. fine-tuned
- Auto-export corrections weekly
- Scheduled retraining
- Scoring weight learning from fetch outcomes
- Taste profile auto-refresh as media collection grows

## What Code Needs from Chat

1. **Retag review UX spec** — How should the tag review interface work? Table of samples with inline editable fields? Approval queue with accept/reject/edit? Batch review or one-at-a-time?

2. **Error taxonomy** — What categories of LLM mistakes matter most? Proposed:
   - `wrong_type_code` — called a kick a snare (highest priority)
   - `wrong_playability` — called a loop a one-shot
   - `hallucinated_tag` — invented a vibe that doesn't fit
   - `missing_tag` — left out an obvious genre/vibe
   - `bad_quality_score` — quality too high or too low
   - `wrong_instrument` — misidentified the instrument

3. **Taste fingerprint review** — The cross-media profiler produces: nostalgic > dark > dreamy > eerie > playful. Does this feel right? Should any sources be weighted differently? Are there vibe dimensions missing?

4. **Multitrack labeling** — The 29 multitrack session artists are high-confidence training examples (we KNOW Marvin Gaye's isolated conga is PRC + soul + warm). Chat should review the artist→genre/vibe mappings for training data quality.

5. **Plex mapping review** — The `MOOD_TO_VIBE` mapping covers 120 moods → 15 vibes. Chat should review and expand for training data quality.

6. **Eval set expansion** — Current eval sets have 25 examples. Need 50-100 real-library examples. Chat could curate these from genre presets.

7. **Movie clip curation guidance** — We can auto-extract dialog/SFX/ambient/score from any of 2,402 movies. Which movies should we prioritize? Genre-based? Director-based? Should clips get their own bank preset (e.g. "cinema-samples")?

## Hardware Reality

M3 iMac, 24GB unified memory:
- **Inference**: qwen3:32b at ~10s/sample (batch retag), 7B fine-tuned at ~3s (inline)
- **Training**: QLoRA on 7B fits in 24GB. 32B needs offloading.
- **Recommendation**: 32b as teacher (batch quality), fine-tuned 7B as student (inline speed)
- **Taste profile**: builds in <1 second from all sources

## Success Metrics

1. **Type code accuracy**: 60% → 90% (measured against user corrections)
2. **Vibe tag precision**: LLM vibes that users keep vs. change
3. **Taste alignment**: model's vibe distribution correlates with cross-media fingerprint
4. **Fetch hit rate**: % of fetched samples that stay (not replaced)
5. **Quality score calibration**: LLM quality_score correlates with user rating
6. **Speed**: fine-tuned 7B matches 32b quality at 3x speed

## What's Already Built (this session)

- `scripts/taste_profiler.py` — Cross-media taste fingerprint (movies + books + games + audio + films)
- `scripts/extract_clips.py` — Movie/TV audio clip extraction pipeline
- `scripts/ingest_multitracks.py` — QNAP multitrack session stem ingester (copy-only, originals safe)
- `web/api/media.py` — Movie/TV browse + clip extraction web API
- `PlexMediaDB` class in `plex_client.py` — Full Plex media library queries
- `data/taste_profile.json` — Exported taste fingerprint for training
- 500+ multitrack stems already ingested (Marvin Gaye, Stevie Wonder, Bob Marley, Phoenix, NIN, Nirvana, Queen, Doobie Brothers)
- 35 movie clips extracted (Aliens, Cowboy Bebop) with auto-classification and tagging
- Smart retag running with qwen3:32b on full 30K library

---

*This is a Code → Chat handoff for creative direction and spec review. Code will build whatever architecture Chat approves. The media inventory is massive — Chat's job is to help us decide what to prioritize and how the taste model should weight different signals.*
