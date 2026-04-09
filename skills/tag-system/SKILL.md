---
name: tag-system
description: Jambox tag vocabulary, type codes, quality scoring, and fetch logic. Use when the user asks about "type codes", "tag dimensions", "how tagging works", "quality score", "vibe tags", "what makes a good sample", or needs guidance on the tag system, scoring weights, or fetch behavior.
version: 0.2.0
---

# Tag System

## Auto-Tag Commands

- Full library tag: `python scripts/tag_library.py`
- Incremental update: `python scripts/tag_library.py --update`
- LLM smart retag: `python scripts/smart_retag.py` (checkpoint/resume, see ml-pipeline skill)
- Re-vibe pass: `python scripts/smart_retag.py --revibe`

## Tag Dimensions

| Dimension | What it answers | Examples |
|-----------|----------------|---------|
| type_code | What is it? | KIK, SNR, HAT, PRC, BAS, SYN, PAD, VOX, FX, BRK, RSR, GTR, HRN, KEY, STR |
| vibe | What does it feel like? | dark, warm, hype, dreamy, nostalgic, aggressive, mellow, soulful, eerie, playful, gritty, ethereal, triumphant, melancholic, tense |
| texture | What does it sound like? | dusty, lo-fi, raw, clean, warm, saturated, bitcrushed, airy, crispy, glassy, vinyl, tape, digital, organic |
| genre | What style? | funk, soul, disco, house, electronic, hiphop, dub, ambient, jazz, rock, punk, dancehall, latin, pop, rnb, boom-bap, lo-fi, tropical, afrobeat |
| energy | How intense? | low, mid, high |
| source | Where from? | kit, dug, synth, field, processed |
| playability | How to use it? | one-shot, loop, chop-ready, layer, transition |
| instrument_hint | Specific instrument? | rhodes, 808, clavinet, melodica, congas, etc. (from smart retag) |
| quality_score | How good for SP-404? | 1-5 (from smart retag) |
| sonic_description | What would a producer hear? | Free text (from smart retag) |

## Type Codes

| Code | Category | What It Is |
|------|----------|-----------|
| KIK | Drums | Kick drum |
| SNR | Drums | Snare / clap |
| HAT | Drums | Hi-hat (open or closed) |
| PRC | Drums | Percussion (congas, shakers, toms) |
| BRK | Drums | Drum break / loop |
| BAS | Melodic | Bass (any type) |
| SYN | Melodic | Synth (lead, pad, arp) |
| PAD | Melodic | Sustained pad / atmosphere |
| GTR | Melodic | Guitar (any style) |
| KEY | Melodic | Keys / piano |
| HRN | Melodic | Horns / brass |
| STR | Melodic | Strings |
| VOX | Vocal | Vocal sample / chop |
| FX | Utility | Sound effect / transition |
| RSR | Utility | Riser / build |

## Quality Score Rubric

| Score | Meaning | Action |
|-------|---------|--------|
| 5 | Gold — SP-404 ready, unique character | Priority fetch candidate |
| 4 | Strong — clean, usable, good fit | Normal fetch candidate |
| 3 | Decent — usable with some compromise | Fill gaps only |
| 2 | Weak — needs processing or marginal fit | Auto-quarantine |
| 1 | Unusable — wrong format, corrupt, boring | Auto-quarantine |

Files scoring 1-2 are moved to `_QUARANTINE/` for human review.

## Fetch Scoring

`fetch_samples.py` scores every file in the tag database against the query:

| Factor | Points | Notes |
|--------|--------|-------|
| Type code exact match | +10 | Mismatch = -8 |
| Type code related | +3 | e.g., KIK query matching PRC |
| Playability exact | +5 | Mismatch = -4 |
| BPM close (within 5) | +4 | Near (within 15) = +2, far = -2 |
| Key exact match | +3 | Compatible key = +1 |
| Keyword in dimension | +3 | e.g., "warm" matching vibe:warm |
| Keyword in tags | +2 | Partial match |
| Keyword in filename | +1 | Fallback matching |
| One-shot too long | -3 | Penalty for mismatched duration |
| Loop too short | -3 | Penalty for mismatched duration |
| Plex mood bonus | +1 | Personal library mood match |
| Plex play count | +2 | Boost for frequently played tracks |

Weights are tunable via `config/scoring.yaml`.

Global deduplication ensures no file is used twice across any pad.

## Tag Cloud API

- `GET /api/library/tags` — dimension-grouped tag frequencies
- `GET /api/library/by-tag?type_code=KIK&vibe=dark&genre=funk` — dimension filtering (OR within, AND across)

## Pad Description Format

Each pad in `bank_config.yaml` uses: `TYPE_CODE keyword keyword playability`

- Type code first (3 letters, caps)
- 2-3 keywords from any dimension
- Playability last
- **Less is more** — 3-4 total keywords get better matches than 6-7
