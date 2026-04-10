# Code Brief: Pattern Generation & Sample Assembly — Revised

## The Old Framing (Wrong)
The original pattern generation feature treated the SP-404 as a sample playback device and Magenta as a "make me a drum loop" machine. That misses the point.

## The Real Framing

The SP-404 has two musical modes, and we need tools for both:

### Mode 1: Pads as Samples (Sample Assembly)
Pads hold audio — breaks, bass loops, vocal chops. A "pattern" here means assembling a rendered loop from library one-shots. The LLM picks the right kick, snare, hat from your library, arranges them in a musical pattern, renders a loop. No Magenta needed.

### Mode 2: Pads as Notes (Pattern Generation)
Pads hold individual notes from a scale. C minor mapped across pads 1–8, bass octave on 9–10, chord voicings on 11–12. A "pattern" here is a sequence of pad triggers that plays a melody, arpeggiation, bass line, or chord progression. THIS is where Magenta shines — it understands musical structure, voice leading, swing, humanized timing, and can generate sequences with real musical intelligence.

Both modes serve different creative purposes. Mode 1 is for building beats. Mode 2 is for songwriting.

---

## Feature A: Scale Mapping & Melodic Patterns (Magenta)

### Concept
Turn the SP-404 into a melodic instrument. Map a scale or chord tones to pads, then use generated patterns to perform melodic content — arpeggios, bass lines, chord progressions, melodic phrases.

### Scale Mapping
A preset can define pads as notes instead of samples:

```yaml
name: Fm Songwriting Kit
slug: fm-songwriting-kit
author: jambox
bpm: 110
key: Fm
vibe: Melodic songwriting palette in F minor
source: curated
tags:
  - songwriting
  - melodic
  - f-minor
  - arpeggiation
scale_mapping:
  root: F3
  scale: minor
  pads:
    1: F3          # Root
    2: Ab3         # Minor third
    3: Bb3         # Fourth
    4: C4          # Fifth
    5: Db4         # Minor sixth
    6: Eb4         # Minor seventh
    7: F4          # Octave
    8: Ab4         # Minor third (octave up)
    9: F2          # Bass root
    10: C3         # Bass fifth
    11: Fm_chord   # Fm triad stab
    12: Bbm_chord  # Bbm triad stab
patterns:
  - name: Rising Arp
    type: arpeggio
    pads: [1, 2, 3, 4, 5, 6, 7, 8]
    direction: up
    rate: 1/8
    swing: 0.6
  - name: Bass Pulse
    type: bass
    pads: [9, 10]
    rate: 1/4
    pattern: [9, 9, 10, 9]
  - name: Chord Prog
    type: progression
    rate: 1bar
    pattern: [11, 11, 12, 11]
```

This is a new preset type — it extends the existing format with `scale_mapping` and `patterns` fields. Regular sample presets work exactly as before.

### What Magenta Does Here
- **GrooVAE**: Takes a basic pattern (like the rigid arp above) and humanizes it — adds swing, velocity variation, micro-timing that feels played, not programmed
- **MusicVAE**: Generates entirely new melodic sequences given a scale, key, and style. "Give me a melancholy bass line in Fm" → a sequence of pad triggers with musical phrasing
- **Interpolation**: Magenta can blend between two patterns — start with a simple arp, end with a complex melody, and generate the in-between. Great for evolving a part over a song section.

### Pattern Output Format
Patterns are stored as sequences of pad triggers with timing and velocity:

```json
{
  "name": "Generated Arp",
  "bpm": 110,
  "key": "Fm",
  "source": "magenta",
  "steps": [
    {"pad": 1, "time": 0.0, "velocity": 0.8, "duration": 0.12},
    {"pad": 3, "time": 0.25, "velocity": 0.6, "duration": 0.12},
    {"pad": 5, "time": 0.5, "velocity": 0.7, "duration": 0.12},
    {"pad": 7, "time": 0.75, "velocity": 0.9, "duration": 0.15}
  ]
}
```

This can be:
- Rendered to audio (trigger the mapped samples at the specified times → bounce to a loop)
- Exported as MIDI for use in a DAW
- Used directly by the SP-404's sequencer if we build a pattern transfer format

### LLM Integration
The LLM doesn't replace Magenta — it translates natural language into Magenta parameters:

```
User: "arpeggiate F minor, rising, eighth notes, jazzy swing"
  → LLM returns: {scale: "Fm", direction: "up", rate: "1/8", swing: 0.72, temperature: 0.6}
    → Magenta generates humanized pattern
      → Pattern stored + optionally rendered to audio
```

The LLM handles the "what do I want" → structured parameters translation. Magenta handles the "make it musical" generation. Same ambient philosophy — user says something natural, music comes out.

---

## Feature B: Sample Assembly (No Magenta)

### Concept
Build rendered drum loops and textural beds from existing library one-shots. The LLM picks the sounds, arranges them in a musical pattern, the system renders a loop.

### How It Works

```
User: "funky drum break, 95 BPM, dusty"
  → LLM generates:
    1. Sound selection: {kick: "dusty warm vinyl", snare: "cracking funk", hat: "loose open sizzle"}
    2. Pattern: a funk break pattern with ghost notes and swing
  → fetch_samples.py finds best matching one-shots for each role
  → Sequencer renders the pattern using those samples
    → Output: a rendered audio loop, tagged and ingested into library
```

### Implementation
- No Magenta dependency — pure Python audio rendering
- Use `soundfile` or `pydub` to load one-shots and place them on a timeline
- Pattern templates: basic rock, four-on-floor, boom-bap, breakbeat, shuffle, etc.
- LLM picks the template and tweaks parameters (swing, ghost note density, velocity variation)
- Rendered loops go through standard ingest → tagged with `source: assembled`

### Why This Is Separate from Magenta
Sample assembly is about the SOUNDS — picking the right kick and snare from your library. Pattern generation is about the NOTES — melodic expression on scale-mapped pads. Different creative modes, different tools, different outputs.

---

## Implementation Plan

### Phase 1: Scale Mapping Foundation
- [ ] Extend preset YAML schema with optional `scale_mapping` and `patterns` fields
- [ ] Build scale-to-pads mapping logic (given root + scale type → note assignments)
- [ ] Support common scales: major, natural minor, harmonic minor, pentatonic major/minor, blues, dorian, mixolydian
- [ ] Web UI: when a preset has `scale_mapping`, show a keyboard/scale visualization instead of sample waveforms
- [ ] Load appropriate note samples: could be from a built-in synth sample set, or user-provided one-shots per note

### Phase 2: Pattern Playback & Basic Generation
- [ ] Pattern sequencer: read a pattern JSON, trigger mapped pads at specified times with velocity
- [ ] Render to audio: bounce a pattern + scale mapping to a WAV/FLAC loop
- [ ] Basic algorithmic patterns (no Magenta yet): arpeggio up/down/random, euclidean rhythms, classic chord progressions in the mapped key
- [ ] Web UI: pattern selector per preset, play/preview button, render-to-pad button

### Phase 3: Magenta Integration
- [ ] Connect to Magenta for humanized timing (GrooVAE) — take a rigid pattern, make it feel human
- [ ] Connect to Magenta for melodic generation (MusicVAE) — generate novel sequences in a given key/scale
- [ ] LLM translates natural language → Magenta parameters
- [ ] Pattern interpolation: blend between two patterns

### Phase 4: Sample Assembly
- [ ] Drum pattern templates (funk, four-on-floor, boom-bap, breakbeat, shuffle, etc.)
- [ ] LLM selects template + library samples based on natural language prompt
- [ ] Render engine: place one-shots on timeline with swing/velocity, bounce to audio
- [ ] Rendered loops auto-ingest with `source: assembled` tag

### Phase 5: Songwriting Presets
- [ ] Chat drafts songwriting preset YAMLs with scale mappings + patterns for common progressions
- [ ] "Songwriter mode" in web UI — scale picker, pattern generator, real-time preview
- [ ] Export patterns as MIDI for DAW integration

---

## First Thing to Try

To get this off the ground without waiting for Magenta:

1. Implement scale mapping in the preset schema
2. Build the basic arp/pattern sequencer (algorithmic, no ML)
3. Wire up the LLM to translate "arpeggiate F minor, rising, eighth notes" into pattern parameters
4. Render to audio and put it on a pad

That gives you a working melodic pattern system with zero Magenta dependency. Magenta becomes a Phase 3 upgrade that adds humanization and novelty — not a blocker.

---

## Questions for Code
1. Does the SP-404 MK2 accept MIDI pattern data via USB, or would patterns always need to be rendered to audio first?
2. What sample format do we want for scale-mapped notes? Built-in simple synth waveforms (sine, saw, square)? Or require the user to provide one-shots per note?
3. Should pattern rendering happen in real-time (preview) or batch (render-to-pad)? Both would be ideal but real-time is harder.
4. Is there a preferred Python audio library for sequencing/rendering? `soundfile` for I/O + numpy for mixing might be simplest.
