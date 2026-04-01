# SP-404 Sample Library — Naming & Tagging Spec

> Reference document for the audio library webapp.

---

## 1. Filename Convention

**Pattern:**
```
[BPM]_[Key]_[Type]_[Descriptor]_[Texture].wav
```

**Rules:**
- Use `00` for BPM when tempo is irrelevant (one-shots, FX, textures)
- Use `XX` for key when pitch is irrelevant (drums, noise, FX)
- All fields separated by underscores, no spaces
- Keep total filename under 32 characters when possible (SP display friendly)

**Examples:**
```
92_Cm_DRM_Boom_Dusty.wav
128_Fs_SYN_Pad_Lush.wav
00_XX_FX_Vinyl_Crackle.wav
85_Am_BAS_Sub_808.wav
```

---

## 2. Type Codes (3-letter)

### Melodic
| Code | Meaning       |
|------|---------------|
| SYN  | Synth         |
| KEY  | Keys / Piano  |
| GTR  | Guitar        |
| STR  | Strings       |
| BAS  | Bass          |
| PAD  | Pad           |
| PLK  | Pluck         |
| BRS  | Brass         |
| WND  | Woodwind      |
| VOX  | Vocal         |
| SMP  | Sampled Phrase|

### Percussive
| Code | Meaning       |
|------|---------------|
| DRM  | Drum (full)   |
| KIK  | Kick          |
| SNR  | Snare         |
| HAT  | Hi-Hat        |
| PRC  | Percussion    |
| CYM  | Cymbal        |
| RIM  | Rimshot       |
| CLP  | Clap          |
| BRK  | Break / Loop  |

### Utility
| Code | Meaning       |
|------|---------------|
| FX   | Sound Effect  |
| AMB  | Ambient       |
| FLY  | Foley         |
| TPE  | Tape / Vinyl  |
| RSR  | Riser / Sweep |
| SFX  | Stinger       |

---

## 3. Tag Dimensions

### 3.1 Vibe / Mood
`dark` · `mellow` · `hype` · `dreamy` · `gritty` · `nostalgic` · `eerie` · `uplifting` · `melancholic` · `aggressive` · `playful` · `soulful` · `ethereal` · `tense` · `chill`

### 3.2 Texture
`dusty` · `clean` · `lo-fi` · `saturated` · `airy` · `crunchy` · `warm` · `glassy` · `warbly` · `bitcrushed` · `tape-saturated` · `bright` · `muddy` · `thin` · `thick` · `filtered` · `raw`

### 3.3 Genre / Style
`boom-bap` · `trap` · `soul` · `jazz` · `funk` · `ambient` · `house` · `afrobeat` · `city-pop` · `gospel` · `psychedelic` · `r&b` · `lo-fi-hiphop` · `footwork` · `dub` · `disco` · `latin` · `world` · `classical` · `electronic` · `rock` · `reggae` · `drill` · `uk-garage`

### 3.4 Source
`dug` · `synth` · `field` · `generated` · `processed` · `kit`

### 3.5 Energy
`low` · `mid` · `high`

### 3.6 Playability
`one-shot` · `loop` · `chop-ready` · `chromatic` · `layer` · `transition`

---

## 4. Key Encoding

| Notation | Meaning     |
|----------|-------------|
| `C`      | C Major     |
| `Cm`     | C Minor     |
| `Fs`     | F# Major    |
| `Fsm`    | F# Minor    |
| `Bb`     | Bb Major    |
| `XX`     | No key      |

---

## 5. Bank Types

| Type       | What it is                                      |
|------------|------------------------------------------------|
| `kit`      | Mixed sounds at one BPM for jamming            |
| `palette`  | All same type for A/B comparison               |
| `dig`      | One source record chopped across pads          |

---

## 6. Pad Color Mapping (MK2)

| Type Code | Color   |
|-----------|---------|
| KIK       | Red     |
| SNR       | Orange  |
| HAT       | Yellow  |
| PRC       | Green   |
| BAS       | Blue    |
| SYN/KEY   | Purple  |
| PAD       | Cyan    |
| VOX       | Pink    |
| FX/SFX    | White   |
| BRK       | Magenta |
