# SCORING ENGINE SPEC

**Version:** 1.0
**Date:** 2026-04-08
**Owner:** Chat (spec) / Code (implementation)
**Implementation:** `scripts/scoring_engine.py` (~320 lines)
**Config:** `config/scoring.yaml` (v7)

---

## What This Is

The scoring engine is the brain of the fetch pipeline. When a pad description says "dark funky drum loop, 112 BPM, Em" and the library has 30,000+ samples, the scoring engine decides which sample wins. It produces a single float score per candidate, and the highest-scoring sample gets assigned to the pad.

There are two scoring paths: CLAP (primary, embedding-based) and legacy (fallback, tag-based). Both flow through a unified interface so that `scoring.yaml` controls all tunable parameters regardless of which path is active.

---

## Architecture

```
Pad description (natural language)
        │
        ▼
  scoring_engine.score_sample(sample, query, config)
        │
        ├── CLAP available? ──► CLAP path
        │                         │
        │                         ├── Cosine similarity (0–1)
        │                         ├── Discogs genre bonus
        │                         ├── Discogs danceability check
        │                         ├── Dimension sub-scores (shared)
        │                         └── Performance bonuses (shared)
        │
        └── No CLAP ──► Legacy path
                          │
                          ├── Tag matching per dimension
                          ├── Keyword scoring
                          ├── Plex play count bonus
                          └── Performance bonuses (shared)
        │
        ▼
  Final score (float) + breakdown (dict)
```

### The Unified Interface

```python
def score_sample(sample, query, config, method="auto"):
    """
    sample: dict with tags, metadata, embeddings
    query: dict with pad description, target BPM/key, bank config
    config: parsed scoring.yaml
    method: "auto" (CLAP if available), "clap", "legacy"
    
    Returns: (float score, dict breakdown)
    """
```

`method="auto"` checks whether CLAP embeddings exist for the sample. If yes → CLAP path. If no → legacy path. This means the library can have a mix of embedded and non-embedded samples, and both get scored correctly.

---

## Scoring Paths

### CLAP Path (Primary)

The CLAP path uses cosine similarity between the pad description's text embedding and the sample's audio embedding as the dominant signal, then adds bonuses from structured metadata.

**Sub-scores (all normalized to 0.0–1.0):**

| Sub-score | Source | Weight (default) | Notes |
|-----------|--------|-------------------|-------|
| CLAP similarity | Cosine sim of text ↔ audio embeddings | 0.6 (via `clap.similarity_weight`) | The big one. Range 0.0–1.0 naturally. |
| Type code match | Tag vs query type | +10 match / -8 mismatch (via `dimensions.type_code`) | Hard filter — mismatch is heavily penalized |
| BPM proximity | Gaussian falloff from target | weight 4 (via `dimensions.bpm`) | See BPM scoring section |
| Key compatibility | Exact or harmonic match | weight 3 (via `dimensions.key`) | Exact = full, compatible = 1/3 |
| Energy match | Tag vs query energy level | +3 match / -2 mismatch | |
| Playability match | Tag vs expected playability | weight 5 | loop ≠ one-shot matters a lot |
| Quality score | Smart retag quality (1–5) | weight 2 | Normalized: (score-1)/4 |
| Discogs genre bonus | Genre token from Discogs ONNX | 0.03 (via `clap.discogs_genre_bonus`) | Applied when genre matches query |
| Discogs keyword bonus | Additional Discogs descriptors | 0.018 (via `clap.discogs_keyword_bonus`) | Per matching keyword |
| Danceability | Discogs danceability score | 0.02 bonus if above threshold | Only for dance/groove/party queries |
| Performance bonuses | SD card intelligence | See performance section | Shared with legacy path |

### Legacy Path (Fallback)

Used when no CLAP embedding exists for a sample. Scores entirely from tags.

**Sub-scores:**

| Sub-score | Source | Weight (default) | Notes |
|-----------|--------|-------------------|-------|
| Type code match | Tag vs query | +10 / -8 | Same as CLAP |
| BPM proximity | Same Gaussian falloff | Same | |
| Key compatibility | Same | Same | |
| Energy match | Same | Same | |
| Playability match | Same | Same | |
| Quality score | Same | Same | |
| Keyword matches | Query terms found in tags | +3 per match | Scans vibe, texture, genre |
| Plex play count | User listening history | +2 bonus (via `legacy.plex_play_bonus`) | Log-scale diminishing returns |
| Plex skip penalty | Skipped tracks | -1 (via `legacy.plex_skip_penalty`) | |
| Performance bonuses | SD card intelligence | Same as CLAP | |

---

## BPM Scoring

BPM uses Gaussian-style falloff instead of hard tiers. This prevents good matches from falling off cliffs at arbitrary boundaries.

```python
def bpm_score(target, actual, tolerance=10):
    diff = abs(target - actual)
    if diff == 0: return 1.0
    if diff <= tolerance: return 0.8
    return max(0, 1.0 - (diff - tolerance) / 30)
```

Visual:

```
Score
1.0  ████
0.8  ████████████████████
0.6            ████████████
0.4                  ████████
0.2                        ████
0.0  ─────────────────────────────
     0    10    20    30    40  BPM difference
     ◄ tolerance ►
```

The tolerance (default 10 BPM) and falloff rate (30 BPM to reach zero) are chosen for Jason's typical bank layout: BPMs cluster 112–130. A 120 BPM bank should score a 122 BPM sample almost as highly as exact match, a 110 BPM sample as moderate, and a 90 BPM sample as near-zero.

Half-time and double-time are NOT automatically detected. A 60 BPM sample scores poorly against a 120 BPM query even though it could be double-timed. This is intentional — the SP-404 doesn't have automatic time-stretching, so BPM needs to be close to usable as-is. Future enhancement: add a half/double-time check with a configurable penalty.

---

## Performance Bonuses (SD Card Intelligence)

`card_intelligence.py` reads the SP-404's SD card to learn what Jason actually uses. Three signals:

| Signal | What it means | Bonus (default) | Config key |
|--------|--------------|-----------------|------------|
| Pad reuse | Sample survived across multiple sessions (still on the card) | +4 | `performance.pad_reuse` |
| BPM stable | User didn't retune the BPM after loading — the BPM match was right | +3 | `performance.bpm_stable` |
| High velocity | Pad was played with high velocity — user hit it hard because they liked it | +2 | `performance.high_velocity` |

These bonuses apply to *future* fetches for the same pad or similar pads. They create a feedback loop: samples that perform well live get ranked higher in future bank builds.

Performance bonuses apply in both CLAP and legacy paths.

---

## Diverse Sampling

The scoring engine doesn't just pick the top N matches. `choose_diverse_match()` adds variety:

- Maintains a fetch history cooldown — recently-used samples get a temporary penalty
- No file can appear on more than one pad in a bank (global dedup)
- Within the top candidates, prefers samples from different source folders to avoid pack bias

This prevents the "all 12 pads are from the same sample pack" problem.

---

## Config Reference: scoring.yaml v7

```yaml
version: 7

dimensions:
  type_code: { match: 10, mismatch: -8 }
  bpm: { exact: 4, close: 2, range: 10 }
  key: { exact: 3, compatible: 1 }
  energy: { match: 3, mismatch: -2 }
  playability: { match: 5 }
  keyword: { per_match: 3 }
  quality_score: { weight: 2 }

clap:
  similarity_weight: 0.6
  discogs_genre_bonus: 0.03
  discogs_keyword_bonus: 0.018
  danceability_threshold: 0.5
  danceability_bonus: 0.02

performance:
  pad_reuse: 4
  bpm_stable: 3
  high_velocity: 2

legacy:
  plex_play_bonus: 2
  plex_skip_penalty: -1
```

### Tuning Guide

**Want punchier fetch results?** Increase `type_code.match` — makes type filtering more dominant over vibe/texture nuance.

**Want more vibe-accurate results?** Increase `clap.similarity_weight` toward 0.8 — lets the CLAP embedding drive more of the decision.

**Want BPM to matter more?** Decrease `bpm.range` (tighter tolerance) and increase `bpm.exact` weight.

**Want to reward quality?** Increase `quality_score.weight` — currently 2, could go to 4–5 to make quality a strong signal.

**Want performance learning to matter more?** Increase `performance.*` values — currently modest (+2 to +4). Could go to +6–8 to make live performance history a dominant signal.

**Want to tune CLAP vs legacy balance?** You can't directly — the path is auto-selected based on embedding availability. But you can ensure more samples get CLAP embeddings by running the CLAP embedding batch process.

---

## Tag Abstraction Layer

The scoring engine reads tags through an abstraction:

```python
def get_tags(filepath):
    """Read tags for a file. Today: _tags.json. Tomorrow: SQLite."""
```

This is designed for the ARCH-1 migration (`_tags.json` → SQLite). When ARCH-1 lands, swap the implementation inside `get_tags()` — the rest of the scoring engine doesn't change.

---

## Score Cache

The scoring engine caches the top 200 results per query (LRU eviction). Cache key is a hash of the query parameters. Cache is invalidated when:
- `scoring.yaml` is modified (version bump)
- Tag database is updated (retag, muscle_tags)
- CLAP embeddings are regenerated

Default size 200 entries (reduced from 500 during the blackout cleanup — 500 was unjustified memory growth with no measured cache hit improvement).
