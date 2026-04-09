# TAGGING SPEC v4

**Version:** 4.0
**Date:** 2026-04-08
**Owner:** Chat
**Canonical source:** `scripts/tag_vocab.py`

---

## How This Doc Works

`tag_vocab.py` is the single source of truth for all tag vocabularies. This document explains the vocabulary — what each dimension means, how to apply it, where the boundaries are, and how tags feed into the scoring and fetch pipelines. If this doc and `tag_vocab.py` disagree, `tag_vocab.py` wins.

Code agent: sync the vocabulary tables in Sections 3–7 mechanically from `tag_vocab.py`. Chat agent: owns the prose, rubrics, and creative guidance.

---

## 1. Dimensions Overview

Every sample in the library is tagged across 7 dimensions. Together they answer: what is this sound, what does it feel like, what does it sound like, what genre is it from, how intense is it, where did it come from, and how should it be used on the SP-404?

| # | Dimension | What It Answers | Selection | Required? |
|---|-----------|----------------|-----------|-----------|
| 1 | type_code | What is it? | Single-select | Yes |
| 2 | vibe | What does it feel like? | Multi-select (1–3) | Yes |
| 3 | texture | What does it sound like? | Multi-select (1–3) | Yes |
| 4 | genre | What style is it from? | Multi-select (1–2) | Yes |
| 5 | energy | How intense? | Single-select | Yes |
| 6 | source | Where did it come from? | Single-select | Yes |
| 7 | playability | How to use it on the SP-404? | Single-select | Yes |

Plus one scalar:

| Field | What It Answers | Range | Required? |
|-------|----------------|-------|-----------|
| quality_score | How good is this sample? | 1–5 integer | Yes (smart retag) |

---

## 2. The Vibe/Texture Boundary

This is the most common source of tagging errors. The rule is simple:

**Vibe = emotional/subjective.** How does the sound make you *feel*? If you close your eyes and someone plays the sample, what mood does it put you in? That's vibe.

**Texture = sonic/physical.** What does the sound *physically sound like*? If you had to describe the waveform's character to a sound engineer, what words would you use? That's texture.

### The Migration

Three terms historically appeared in both dimensions, causing double-scoring in the fetch pipeline. As of v4, they live in texture only:

| Term | Old placement | New placement | Rationale |
|------|--------------|---------------|-----------|
| dusty | vibe + texture | **texture only** | It's a sonic quality — vinyl crackle, bit-crushed, degraded fidelity. The *emotional* response to dusty sounds is nostalgia. |
| raw | vibe + texture | **texture only** | It's a sonic quality — unprocessed, exposed, dry, no effects. The *emotional* response to raw sounds is feeling unfiltered or confrontational. |
| warm | vibe + texture | **texture only** | It's a sonic quality — analog saturation, rounded highs, tube compression. The *emotional* response to warm sounds is comfort. |

### New Vibe Terms

| New vibe | What it covers | Replaces the feeling of |
|----------|---------------|------------------------|
| nostalgic | Longing for the past, bittersweet memory, throwback | dusty (emotional side) |
| unfiltered | Confrontational, honest, nothing-to-hide, punk energy | raw (emotional side) |
| comforting | Safe, held, familiar, like a blanket | warm (emotional side) |

### Backward Compatibility

Existing tags using the old placement still work. The scoring engine is dimension-aware — if a search term matches a tag in multiple dimensions for the same sample, it scores once at the higher weight, not twice. Alias mappings:

```
vibe:"warm" → interpreted as vibe:"comforting"
vibe:"dusty" → interpreted as vibe:"nostalgic"  
vibe:"raw" → interpreted as vibe:"unfiltered"
```

### Quick Test

Not sure if a term is vibe or texture? Ask: "Could a kick drum have this quality?" If yes → texture. Kick drums can be warm, dusty, raw (all texture). Kick drums cannot be nostalgic, dreamy, or melancholy (all vibe).

---

## 3. Type Codes

Type code is the most fundamental dimension. It determines what the sample *is* — its functional role on a pad. Single-select only.

### Full Type Code Table

*Synced from `tag_vocab.py` TYPE_CODES (26 codes)*

#### Drum / Percussion

| Code | Name | Description |
|------|------|-------------|
| KIK | Kick | Low thud — bass drum, 808 kick, boom |
| SNR | Snare | Snap/crack — snare drum, rimshot-snare hybrid |
| HAT | Hi-hat | High metallic — open/closed hi-hats |
| CLP | Clap | Handclap, finger snap |
| CYM | Cymbal | Crash, ride, splash cymbals |
| RIM | Rimshot | Stick-on-rim percussion |
| PRC | Percussion | Other percussion — congas, shakers, tambourine, cowbell |
| BRK | Break / Loop | Full drum pattern or rhythm loop |
| DRM | Drum (full kit) | Complete drum kit hit or multi-element drum sound |

#### Melodic

| Code | Name | Description |
|------|------|-------------|
| BAS | Bass | Bass frequency content — sub bass, bass guitar, 808 bass |
| GTR | Guitar | Electric or acoustic guitar |
| KEY | Keys / Piano | Piano, Rhodes, Wurlitzer, organ, clavinet |
| SYN | Synth | Synthesizer — leads, stabs, arps |
| PAD | Pad / Atmosphere | Sustained chord wash, ambient texture, drone |
| STR | Strings | Bowed/sustained strings — violin, cello, orchestral |
| BRS | Brass | Brass stab or section |
| HRN | Horns | Horn/brass melody or ensemble |
| PLK | Pluck | Plucked string or synth pluck |
| WND | Woodwind | Flute, clarinet, saxophone |

#### Vocal

| Code | Name | Description |
|------|------|-------------|
| VOX | Vocal | Voice — chops, phrases, ad-libs, sung/spoken |

#### Utility / FX

| Code | Name | Description |
|------|------|-------------|
| FX | Sound Effect | Non-musical sound, impact, stinger |
| SFX | Stinger | Short one-shot effect (horn stab, gunshot, cash register) |
| AMB | Ambient | Environmental/atmospheric sound, room tone |
| FLY | Foley | Real-world recorded sound (footsteps, doors, glass) |
| TPE | Tape / Vinyl | Vinyl crackle, tape hiss, analog noise layer |
| RSR | Riser / Sweep | Build-up, sweep, transition effect |

### Decision Tree

```
Is it a drum sound?
├── Yes → Is it a full pattern/loop?
│   ├── Yes → BRK (break/loop)
│   └── No → What part of the kit?
│       ├── Low thud → KIK (kick)
│       ├── Snap/crack → SNR (snare/clap)
│       ├── High metallic → HAT (hi-hat/cymbal)
│       └── Other percussion → PRC (percussion)
│
Is it melodic?
├── Yes → Is it sustained (>1 sec natural decay)?
│   ├── Yes → Is it a chord/wash?
│   │   ├── Yes → PAD (pad/atmosphere)
│   │   └── No → Bowed/sustained string?
│   │       ├── Yes → STR (strings)
│   │       └── No → SYN (synth)
│   └── No → Plucked/struck?
│       ├── Piano/keys → KEY (keys/piano)
│       ├── Guitar → GTR (guitar)
│       ├── Horn/brass → HRN (horns/brass)
│       └── Bass frequency → BAS (bass)
│
Is it a voice? → VOX (vocal)
Is it a non-musical sound? → FX (sound effect)
None of the above → FX (default fallback)
```

---

## 4. Vibe Vocabulary

*Synced from `tag_vocab.py` VIBES (18 terms)*

Vibe tags describe the **emotional/subjective** quality of a sound. Multi-select, 1–3 tags per sample.

### Full Vibe Table

| Vibe | Feeling | When to use |
|------|---------|-------------|
| aggressive | Hostile, confrontational, in-your-face | Distorted kicks, screaming synths, battle-ready drums |
| chill | Relaxed, laid-back, no tension | Smooth loops, mellow pads, Sunday morning vibes |
| comforting | Safe, held, familiar, like a blanket | Warm Rhodes, gentle pads, home-feeling sounds |
| dark | Ominous, shadowy, noir | Minor key content, low-frequency drones, horror textures |
| dreamy | Floaty, surreal, half-asleep | Reverb-heavy pads, ambient washes, ethereal vocals |
| eerie | Unsettling, haunted, off-kilter | Detuned sounds, dissonant textures, horror FX |
| ethereal | Otherworldly, celestial, vast | Shimmering pads, choir-like textures, space sounds |
| gritty | Street-level, rough-edged, unpolished | Lo-fi drums, distorted bass, urban textures |
| hype | Energized, pumped, crowd-moving | Build-ups, festival stabs, party-starting hits |
| melancholic | Sad, wistful, beautiful sadness | Minor key melodies, slow strings, tearful vocals |
| mellow | Gentle, soft, understated | Quiet pads, brushed drums, acoustic intimacy |
| nostalgic | Longing for the past, bittersweet memory | Vinyl-era sounds, retro synths, throwback grooves |
| playful | Fun, bouncy, cheeky | Staccato synths, cartoon FX, quirky rhythms |
| soulful | Deep feeling, groovy, church-to-club | Gospel chords, funk guitar, R&B vocals |
| tense | Anxious, on-edge, suspenseful | Rising tones, staccato pulses, unresolved harmony |
| triumphant | Victorious, anthemic, hands-in-the-air | Major key brass, soaring leads, stadium energy |
| unfiltered | Confrontational, honest, punk energy | Raw vocals, garage recordings, DIY aesthetic |
| uplifting | Positive, ascending, hopeful | Major key progressions, bright arps, joyful melodies |

### Vibe Aliases

*From `tag_vocab.py` VIBE_ALIASES — variant spellings normalized to canonical forms:*

| Input | Maps to | Rationale |
|-------|---------|-----------|
| happy | uplifting | — |
| sad | melancholic | — |
| angry | aggressive | — |
| smooth | chill | — |
| spooky | eerie | — |
| moody | dark | — |
| energetic | hype | — |
| energy | hype | — |
| fun | playful | — |
| relaxed | chill | — |
| calm | mellow | — |
| groovy | soulful | — |
| scary | eerie | — |
| warm | comforting | Vibe/texture migration (see Section 2) |
| raw | unfiltered | Vibe/texture migration (see Section 2) |
| dusty | nostalgic | Vibe/texture migration (see Section 2) |

---

## 5. Texture Vocabulary

*Synced from `tag_vocab.py` TEXTURES (21 terms)*

Texture tags describe the **sonic/physical** character of a sound. Multi-select, 1–3 tags per sample.

### Full Texture Table

| Texture | Sonic character | When to use |
|---------|----------------|-------------|
| airy | Open, spacious, breathy | Wide stereo, lots of reverb/space, breathy vocals |
| bitcrushed | Reduced bit depth, stepped, aliased | 8-bit/12-bit digital distortion, retro game sounds |
| bright | Emphasized highs, sparkly, present | Crisp hats, shimmery pads, trebly leads |
| clean | Unprocessed, transparent, studio-quality | DI recordings, pristine samples, no coloration |
| crispy | High-frequency detail, snappy transients | Tight snares, sizzling hats, punchy attacks |
| crunchy | Mid-range distortion, overdrive character | Driven amps, tube saturation, aggressive compression |
| digital | Precise, synthetic, computer-generated | FM synths, algorithmic textures, pristine digital |
| dusty | Vinyl crackle, bit-crushed, degraded fidelity | Vinyl rips, tape deterioration, lo-fi processing |
| filtered | Frequency-sculpted, resonant, swept | Filter sweeps, wah effects, phaser/flanger |
| glassy | Crystalline, bell-like, transparent harmonics | Bell synths, clean electric piano, glass percussion |
| lo-fi | Low fidelity, degraded, characterful | Tape wobble, reduced bandwidth, vintage recording |
| muddy | Unclear low-mids, boomy, congested | Over-compressed, boxy recordings, needs EQ |
| organic | Natural, acoustic-origin, human-played | Live instruments, room recordings, breath/bow noise |
| raw | Unprocessed, exposed, dry, no effects | Direct signal, no reverb/delay, naked recording |
| saturated | Driven, harmonically rich, hot signal | Tape saturation, analog warmth, driven preamp |
| tape | Tape machine character, flutter, hiss | Reel-to-reel, cassette, tape echo |
| thick | Dense, full-bodied, heavy frequency content | Layered sounds, wide detuning, massive bass |
| thin | Narrow frequency range, lightweight | Single oscillator, filtered low-end, delicate |
| vinyl | Vinyl record character, surface noise | Record crackle, RIAA curve, turntable artifacts |
| warbly | Pitch unstable, wobbly, modulated | Tape wow, chorus, detuned oscillators |
| warm | Analog saturation, rounded highs, tube compression | Analog gear, gentle saturation, smooth top end |

### Texture Aliases

*From `tag_vocab.py` TEXTURE_ALIASES:*

| Input | Maps to |
|-------|---------|
| lofi | lo-fi |
| crisp | crispy |
| wide | airy |
| tape-saturated | tape |
| metallic | crispy |
| metallic-hit | crispy |
| metal-hit | crispy |
| ringy | glassy |

---

## 6. Genre Vocabulary

*Synced from `tag_vocab.py` GENRES (43 genres)*

Genre tags identify the **musical style/tradition** a sample belongs to. Multi-select, 1–2 tags per sample.

### Electronic

| Genre | Description |
|-------|-------------|
| ambient | Atmospheric, non-rhythmic, textural soundscapes |
| breakbeat | Syncopated breaks, big beat, Chemical Brothers energy |
| drum-and-bass | 160–180 BPM, heavy bass, chopped breaks |
| dubstep | Half-time beats, wobble bass, sub-heavy |
| electronic | Broad electronic music (use more specific genre when possible) |
| footwork | 160 BPM, rapid-fire percussion, Chicago juke |
| house | Four-on-the-floor, 120–130 BPM, dance groove |
| industrial | Harsh, mechanical, noise-influenced |
| industrial-techno | Pounding kicks, dark warehouse, Perc/Ansome territory |
| jungle | Chopped amen breaks, ragga vocals, 90s rave bass |
| techno | Repetitive, hypnotic, machine-driven |
| trance | Melodic builds, euphoric breakdowns, arpeggiated synths |
| uk-garage | Shuffled 2-step, chopped vocals, 130 BPM swing |

### Hip-hop / R&B

| Genre | Description |
|-------|-------------|
| boom-bap | Golden age hip-hop, vinyl crackle, hard-hitting drums |
| drill | Dark trap variant, sliding 808s, UK/Chicago drill |
| hiphop | Broad hip-hop (use boom-bap/trap/drill when more specific) |
| lo-fi-hiphop | Chill beats, vinyl texture, study-music aesthetic |
| rnb | Rhythm and blues, smooth vocals, modern R&B production |
| trap | 808 bass, hi-hat rolls, dark synths, Atlanta-rooted |

### Rock / Punk

| Genre | Description |
|-------|-------------|
| breakcore | Hyper-speed chopped breaks, noise, Venetian Snares territory |
| punk | Fast, raw, three-chord energy, DIY aesthetic |
| rock | Guitar-driven, live drums, band energy |
| shoegaze | Wall of guitars, reverb-drenched, dreampop adjacent |

### Pop / Dance

| Genre | Description |
|-------|-------------|
| city-pop | Japanese 80s pop, bright production, Tatsuro Yamashita vibes |
| disco | Four-on-the-floor, string stabs, Nile Rodgers guitar, 70s–80s dance |
| pop | Mainstream, hook-driven, radio-friendly production |

### Soul / Funk

| Genre | Description |
|-------|-------------|
| funk | Tight rhythm, syncopated bass, James Brown to Daft Punk |
| gospel | Church organ, choir, spiritual uplift |
| soul | Deep feeling, Motown/Stax warmth, vocal-driven |

### World / Regional

| Genre | Description |
|-------|-------------|
| afrobeat | West African polyrhythm, Fela Kuti legacy, Afro-fusion |
| baile-funk | Brazilian favela bass, rapid-fire percussion, MC vocal chops |
| dancehall | Jamaican riddim, reggaeton-adjacent, 2000s bounce |
| dub | Echo chamber, deep bass, spacious reverb, King Tubby |
| gqom | South African raw electronic, sparse beats, dark and hypnotic |
| latin | Broad Latin music — salsa, cumbia, bossa nova, reggaeton |
| reggae | Offbeat guitar, deep bass, one-drop rhythm |
| tropical | Warm, sun-drenched, island-influenced production |
| world | Broad world music (use more specific genre when possible) |

### Experimental

| Genre | Description |
|-------|-------------|
| experimental | Genre-defying, avant-garde, unconventional structures |
| psychedelic | Altered consciousness, phaser/flanger, acid-influenced |

### Acoustic / Traditional

| Genre | Description |
|-------|-------------|
| classical | Orchestral, composed, Western art music tradition |
| jazz | Improvisation, swing feel, complex harmony |
| lo-fi | Low-fidelity aesthetic as a genre (not just texture) |

### Genre Aliases

*From `tag_vocab.py` GENRE_ALIASES:*

| Input | Maps to |
|-------|---------|
| hip-hop, hip hop | hiphop |
| lofi, lo fi | lo-fi |
| lo-fi-hip-hop | lo-fi-hiphop |
| r&b | rnb |
| edm | electronic |
| dance | house |
| riddim | dancehall |
| baile funk, favela funk | baile-funk |
| industrial techno | industrial-techno |
| drum n bass, drum and bass, drum & bass, dnb, d&b | drum-and-bass |
| jungle dnb | jungle |
| juke | footwork |
| tech house, tech-house | house |

---

## 7. Energy, Source & Playability

### Energy

*Synced from `tag_vocab.py` ENERGIES (3 levels)*

Single-select. How intense is the sample?

| Energy | Meaning | Examples |
|--------|---------|---------|
| low | Calm, ambient, restful | Soft pads, mellow loops, quiet textures |
| mid | Moderate, grooving, steady | Most drum loops, melodic content, standard grooves |
| high | Intense, driving, peak-time | Hard kicks, fast breaks, aggressive leads, festival stabs |

### Source

Single-select. Where did the sample come from?

| Source | Meaning |
|--------|---------|
| kit | From a sample pack or commercial kit |
| dug | Dug from vinyl, tape, or other found media |
| synth | Synthesized — generated from a synth or sound design tool |
| field | Field recording — real-world captured audio |
| processed | Derived from processing another sample (resample, stem split, effect chain) |

### Playability

*Synced from `tag_vocab.py` PLAYABILITIES (6 modes)*

Single-select. How should this sample be triggered on the SP-404?

| Playability | SP-404 mode | Behavior |
|-------------|-------------|----------|
| one-shot | Gate (default) | Plays once on pad press |
| loop | Loop | Repeats continuously while held or until stopped |
| chop-ready | Gate | Designed to be further chopped on the SP-404 |
| chromatic | Gate | Pitched across pads — playable melodically |
| layer | Gate | Designed to be layered under other samples (ambient/textural) |
| transition | Gate | Risers, sweeps, fills — used between sections |

---

## 8. Quality Score Rubric

The smart retag extracts a quality_score (1–5) for every sample. This score feeds into `scoring_engine.py` as a weighted sub-score — higher quality samples rank higher in fetch results, all else being equal.

### The Scale

| Score | Meaning | What it sounds like | Examples |
|-------|---------|-------------------|----------|
| **5** | Exceptional | Release-quality. Clean recording, intentional character, sits perfectly in a mix. You'd pay for this sample. | A perfectly recorded 808 kick with sub weight and punch. A Rhodes chord with natural tube warmth and zero noise. A vocal chop with pristine isolation and interesting melody. |
| **4** | Good | Solid and usable with no processing needed. Minor imperfections that don't affect usability. | A drum loop with slight room ambience but good groove. A synth pad with a tiny click at the loop point. A bass hit that's slightly hot but not clipping. |
| **3** | Usable | Gets the job done. May need some processing (EQ, trimming, level adjustment) to sit well. The default score for "nothing wrong, nothing special." | A serviceable snare from a free sample pack. A guitar loop that's fine but generic. A pad that works but isn't inspiring. |
| **2** | Below average | Significant issues but potentially salvageable. Would only use if nothing better is available. | A kick with audible clipping. A vocal with background noise that can't be removed. A loop with an awkward edit point. |
| **1** | Poor | Unusable or nearly so. Severe quality issues. Should be flagged for removal from the library. | A sample that's mostly silence. Extreme digital artifacts. A recording so noisy the content is buried. A mis-tagged file (it's a synth, tagged as a kick). |

### How Quality Feeds Into Scoring

In `scoring_engine.py`, quality_score is normalized to 0.0–1.0 and applied as a weighted sub-score:

```
quality_normalized = (quality_score - 1) / 4  # maps 1→0.0, 5→1.0
contribution = quality_normalized * config.dimensions.quality_score.weight
```

Default weight is 2 (from `scoring.yaml`). This means a quality-5 sample gets +2 points over a quality-1 sample — enough to break ties but not enough to override a strong type_code or vibe match.

### Calibration Notes

The smart retag LLM tends to cluster around 3–4. Scores of 1 and 5 are rare. This is acceptable — the distribution should be roughly Gaussian centered on 3. If the retag starts producing >50% scores of 5, the prompt needs recalibration (the model is being too generous). If >20% are 1, it's being too harsh or the library has quality issues to address.

---

## 9. Smart Retag Integration

### What the LLM Sees

The retag prompt sends the LLM:
- The filename (which often contains descriptive terms like "dark_synth_pad_120bpm")
- The file's parent folder path (which encodes category info like "Drums/Kicks/")
- Audio duration
- The full tag vocabulary from `tag_vocab.py` as a constrained output set

The LLM does NOT hear the audio. All tagging is inferred from filename, path, and duration. This is a deliberate design choice — text-based inference is 100x faster than audio analysis and surprisingly accurate for well-named sample libraries.

### What the Model Outputs

Structured JSON with all 7 dimensions plus quality_score:

```json
{
  "type_code": "BRK",
  "vibe": ["hype", "aggressive"],
  "texture": ["raw", "crunchy"],
  "genre": ["punk", "industrial"],
  "energy": "high",
  "source": "kit",
  "playability": "loop",
  "quality_score": 4
}
```

### Known Failure Modes

These are the errors `muscle_tags.py` was built to correct:

| Failure | Frequency | Cause | Fix |
|---------|-----------|-------|-----|
| Kick tagged as BAS | ~5% of kicks | Filename says "bass" or "808" — model conflates bass frequency with bass instrument | muscle_tags rule: if folder contains "Kick", force KIK |
| Pad tagged as SYN | ~8% of pads | Synth pads are ambiguous — is it a synth or a pad? | Rule: if duration >4s and "pad" in filename, force PAD |
| Loops tagged as one-shot | ~3% of loops | Model misreads duration or ignores "loop" in filename | Rule: if duration >2s and "loop" in path, force playability=loop |
| Genre hallucination | ~2% | Model invents genres not in vocabulary (e.g., "chillhop" instead of "lo-fi-hip-hop") | Constrained output validation strips invalid values |
| quality_score inflation | ~15% | Model defaults to 4 when uncertain | Acceptable — 4 is "good," and most curated samples deserve it |

### Error Rate Context

The running retag (qwen3:32b, ~42s/file) shows a ~38% raw error rate. This sounds alarming but breaks down to:
- ~20% are soft errors (vibe/texture borderline calls that are defensible either way)
- ~12% are correctable by muscle_tags rules
- ~6% are genuine errors requiring manual review

The effective error rate after muscle_tags corrections is ~6%, which is acceptable for a 30K-file library.

---

## 10. SP-404 Constraints

Tags exist to serve one purpose: getting the right sample onto the right pad for live performance. Every tagging decision should be made with the SP-404A's hardware constraints in mind.

### Why Mono

The SP-404A plays mono samples. Stereo files work but are converted to mono on playback, which can cause phase cancellation on wide-panned sources. All samples are converted to mono during the fetch pipeline (`ffmpeg -ac 1`). Tags don't need to account for stereo width — it doesn't survive the hardware.

### Why 16-bit/44.1kHz

The SP-404A's DAC is 16-bit/44.1kHz. Higher bit depths and sample rates are downconverted, wasting SD card space with no quality benefit. The RLND chunk in the WAV header is required for the hardware to recognize the file.

### How Tags Map to Pad Placement

The bank config YAML describes each pad with a natural-language description. The scoring engine matches these descriptions against the tag database. The mapping:

| Tag dimension | How it affects pad placement |
|--------------|------------------------------|
| type_code | Primary filter — a pad asking for "kick" will never receive a PAD sample |
| vibe | Ranked matching — "dark kick" prefers kicks tagged with dark/aggressive vibes |
| texture | Ranked matching — "dusty snare" prefers snares tagged with dusty texture |
| genre | Bonus scoring — a funk bank's pads prefer funk-tagged samples |
| energy | Filter + bonus — high-energy banks penalize low-energy samples |
| playability | Critical for SP-404 trigger mode — loops must be tagged as loops, one-shots as one-shots |
| quality_score | Tiebreaker — when two samples match equally, the higher quality one wins |

### Playability and SP-404 Trigger Modes

The playability tag directly informs how a sample should be loaded on the SP-404:

| Playability | SP-404 mode | Behavior |
|------------|-------------|----------|
| one-shot | Gate (default) | Plays once on pad press, stops on release (or plays full sample if gate is off) |
| loop | Loop | Repeats continuously while pad is held or until stopped |
| chop-ready | Gate | Designed to be further chopped using the SP-404's built-in chop function |
| chromatic | Gate | Pitched across pads — playable melodically |
| layer | Gate | Designed to be layered under other samples — usually ambient/textural |
| transition | Gate | Risers, sweeps, fills — used between sections |

The `gen_padinfo.py` script reads playability tags to set the correct mode in `PAD_INFO.BIN`.
