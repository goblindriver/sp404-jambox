---
name: bank-design
description: SP-404A bank layout design, pad conventions, and preset system. Use when the user asks to "design a bank", "create a preset", "lay out pads", "what goes where on the sampler", "Tiger Dust Block Party", or needs guidance on bank architecture, genre presets, energy arcs, or pad assignment conventions.
version: 0.2.0
---

# Bank Design — SP-404A

## Hardware Constraints

- **10 banks** (A through J), **12 pads per bank** = 120 total pad slots
- Banks A-B are **internal memory** — survive SD card swaps. Put always-need-it sounds here.
- Banks C-J live on the SD card — use for genre-specific or session-specific content.
- **Sub Pad** is a hardware retrigger button (rapid-repeat of last-pressed pad for rolls/fills). It is NOT a sample slot.
- File naming on card: `{BANK_LETTER}0000{PAD_NUMBER}.WAV` in `ROLAND/SP-404SX/SMPL/`

## Pad Convention (12 pads per bank)

| Pads | Role | Examples |
|------|------|---------|
| 1-4 | Drum one-shots | Kick, snare, hat, perc |
| 5-8 | Loops & breaks | Choppable rhythm, melodic loops |
| 9-10 | Melodic content | Bass, chords, leads |
| 11-12 | Texture/FX | Risers, transitions, ambient, vocal chops |

## Tiger Dust Block Party (Default Performance Set)

| Bank | Name | BPM | Key | Energy | Purpose |
|------|------|-----|-----|--------|---------|
| A | Soul Kitchen | 98 | G | Low | Golden hour opener. Dusty soul grooves. |
| B | Funk Muscle | 112 | Em | High | James Brown tight, Parliament nasty. |
| C | Disco Inferno | 118 | Am | High | Four-on-the-floor, lush strings. |
| D | Boom Bap Cipher | 90 | Dm | Mid | Golden age hip-hop, vinyl crackle. |
| E | Caribbean Heat | 108 | Cm | High | Dancehall riddims, soca drums. |
| F | Electro Sweat | 120 | Dm | High | Dance-punk, dirty synths, LCD energy. |
| G | Neon Rave | 128 | F | High | Blog-house filters, rave stabs. |
| H | Peak Hour | 125 | Gm | High | THE MOMENT. Maximum intensity. The drop. |
| I | Dub Cooldown | 100 | Am | Low | Echo chamber bass, melodica, reverb. |
| J | Weapons Cache | 120 | XX | Mid | Air horns, sirens, scratches, impacts. |

**Energy arc:** warm up → groove → full dance floor → change pace → summer → get weird → build → PEAK → breathe → weapons anytime

### Harmonic Design
Default set keys (Am, Dm, Em, F, G) are diatonic to C major — everything harmonizes across banks.

### Tempo Design
112/120/128/130 BPM cluster — all mix cleanly. Outliers (90, 98, 100, 108) provide deliberate gear changes.

## Internal Memory Strategy

Banks A-B survive SD card swaps. Use for:
- Core drum kit that you always want
- Essential transitions and utility sounds
- Your personal signature samples

Banks C-J change with the card — use for genre-specific or session-specific content.

## Preset System

Bank configurations are standalone YAML files in `presets/`, organized by category:
- `genre/` — genre-specific banks
- `utility/` — drum kits, transitions, SFX
- `song-kits/` — banks built around specific tracks
- `palette/` — mood/texture banks
- `community/` — shared presets
- `auto/` — daily auto-generated presets

**Sets** group 10 presets into complete configurations for different session types.

### Pad Description Format

Each pad in `bank_config.yaml` uses: `TYPE_CODE keyword keyword playability`
- Type code first (3 letters, caps): KIK, BRK, SYN, VOX, etc.
- 2-3 keywords from any dimension (vibe, texture, genre)
- Playability last: one-shot, loop, chop-ready, layer, transition
- **Less is more** — 3-4 total keywords get better matches than 6-7

Examples:
- `BAS funk warm loop` — finds a warm funk bass loop
- `KIK hard aggressive one-shot` — finds a hard aggressive kick
- `PAD dreamy ethereal layer` — finds a dreamy pad for layering

## Genre Presets

See `references/genre-presets.md` for the full list of available genre presets with BPM, key, and vibe descriptions.
