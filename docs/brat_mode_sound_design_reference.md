# BRAT MODE: Comprehensive Sound Design Reference Document

**Target Aesthetic:** Charli XCX (Brat album), M.I.A., Slayyyter, 100 gecs, SOPHIE, AG Cook
**Genres:** Hyperpop, PC Music, Detuned Maximalism, Hard Pop, Glitch Textures
**Purpose:** Personal music production reference for hyperpop/experimental pop sound design

---

## 1. DETUNED SUPERSAWS & SYNTHS

### 1.1 Hypersaw / Supersaw Construction

**Basic Supersaw Architecture:**
- Load default sawtooth wave
- Unison: 16 voices (expandable to 32 for wider, phasey effects)
- Detune knob: Bring down gradually from max until the sound feels wide without phasing (typically 0.1–0.3)
- Pan: Slight left pan for initial layer (-5 to -15%)
- Strategy: Use two supersaw layers—one with aggressive detune (0.2–0.4), one cleaner with subtle detune (0.05–0.1)

**Serum-Specific Supersaw Parameters:**
- **Range:** Set to control maximum semitone deviation (5–12 semitones for aggressive "Brat" character)
- **Width:** Controls stereo spread between unison voices (0.5–1.0 for maximum width)
- **Unison (per OSC):** Can enable independently on OSC A and B
- **Stack function (hidden in Global tab):** Transpose some unison voices up/down for rich harmonics
  - Example: Stack down 1 octave (0–3 voices), stack up 5 semitones (2–4 voices) = harmonic richness without muddiness

**Vital Synth Parameters (Lighter but Capable):**
- Simpler unison control vs. Serum (fewer tweaks)
- Unison voices: 8–16 range
- Phase randomization: 40–70% for detuning variation
- Better for clean layers; pair with Serum for aggressive leads

### 1.2 "Brat" Synth Tone Design

**The Signature Sound:**
- Deliberately ugly, detuned, bright
- Slightly overdriven but not distorted at source
- Presence peak around 3–5 kHz (presence element)
- Slight high-pass filter roll-off at ~200–300 Hz to remove muddiness
- Aggressive unison detune creating "shimmer" with beating/wobble

**Construction:**
1. Start with sawtooth or square wave
2. Apply unison with 0.15–0.25 detune
3. Layer two instances: one octave apart (creates hollow quality)
4. Add 10–15% FM modulation from slow LFO (0.3–0.8 Hz) for subtle movement
5. EQ: Boost 4 kHz by 6–9 dB, cut 300 Hz by 3–4 dB
6. Light saturation (10–20% drive) for attitude without losing clarity

### 1.3 PC Music-Style Crystalline Synths

**Characteristics:**
- High-pass filtered aggressively (cutoff 1–2 kHz minimum)
- Thin, metallic, almost synthetic sounding
- Often played in staccato/short note bursts
- Multiple harmonic layers create "crystalline" texture

**FM Synthesis for Metallic Quality:**
- Use FM synthesis with high modulation index (C:M ratio 1:4 to 1:8)
- Carrier frequency: 1–4 kHz (where metallic tones live)
- Modulator LFO: 0.5–3 Hz for slow morphing, 8–15 Hz for bell/metallic artifacts
- Filter envelope: Sharp attack (1–5 ms), fast decay (50–150 ms), minimal sustain

**Frequency Ranges for "Thin" Texture:**
- Focus fundamental around 2–4 kHz
- Remove everything below 500 Hz entirely (high-pass filter)
- Keep presence at 8–12 kHz for air/sparkle
- Notch out muddiness at 400–600 Hz and 1–1.5 kHz

**Tools:** Additive synthesis creates crystalline effect when using sine wave stacking at octaves + fifths + thirds

### 1.4 Bitcrushed and Degraded Synth Textures

**Bitcrushing Fundamentals:**
- **Bit depth reduction:** 8–12 bits (lower = grittier) for "Brat" attitude
- **Sample rate reduction:** 8–16 kHz (creates aliasing that adds upper-frequency distortion)
- **Combination:** Use both simultaneously for extreme degradation

**Creative Application:**
- Automate bit depth across a synth lead: Start at 16-bit (clean), sweep to 6-bit by drop
- Layer bitcrushed version 20% under main synth for texture
- Bitcrush only the high-frequency content (above 3 kHz) to preserve bass clarity

**Specific Effect Settings (Xfer Destructo or Native Instruments Bit Shifter):**
- Bit depth: 8–10 bits for "Brat" sounds
- Sample rate: 12–16 kHz range (creates aliasing distortion)
- Mix/Wet: 30–60% (not full saturation) to maintain note definition
- Automate for dynamic texture changes within a single note

### 1.5 Pitch-Bent Stab Techniques

**Creating Pitch Bends as Performance Element:**
1. Play staccato synth stabs (50–200 ms duration)
2. Modulate pitch downward using LFO or envelope during note
3. **Pitch bend wheel:** 2–4 semitones, quick downward motion (200–400 ms duration)
4. Layer multiple pitch-bent stabs at different start times for rich texture
5. Add slight distortion during pitch bend for "zip" effect

**Envelope Pitch Modulation (Per-Note):**
- Pitch envelope: +2 to +5 semitones at attack, drops over 100–300 ms to 0
- Creates "stab" character without manual pitch wheel
- Stack 2–3 instances with slightly different envelope times for complexity

### 1.6 Synth Recommendations & Specific Settings

#### Xfer Serum (Most Versatile)

**Supersaw Setup for "Brat":**
- Osc A: Saw wave, Unison 16, Detune 0.25, Pan 0
- Osc B: Saw wave, Unison 8, Detune 0.05, Blend 50%, Pan +15%
- Filter 1: High-pass, Cutoff 300 Hz, Res 0, Env to filter -0.3 (subtle opening)
- Filter 2: Low-pass, Cutoff 8 kHz, Res 0.4 (slight sheen)
- Amp Env: A 10 ms, D 200 ms, S 0.7, R 100 ms
- LFO 1 (to Osc pitch): Rate 0.6 Hz, Depth 0.05 semitones (subtle modulation)

**Metallic Pad:**
- Osc A: Square, Unison 12, Detune 0.15, WT Position 30% (moves through wavetable)
- Osc B: Sine, Unison 1, coarse tuning +12 semitones
- Filter: Bandpass, Cutoff 3 kHz, Res 0.8 (peak at 3 kHz)
- Env: A 50 ms, D 400 ms, S 0.5, R 200 ms
- Reverb: 20% wet, 1.5 sec decay (crystalline space)

#### Vital (Modern Alternative)

**Advantages for Hyperpop:**
- Excellent unison control with phase randomization
- CPU-efficient (multiple instances possible)
- Strong wavetable morphing for evolving textures
- Superior filter modulation options

**Brat Supersaw:**
- Osc 1: Sawtooth, Unison 12, Phase randomize 50%, Detune spread 0.2
- Osc 2: Square, Unison 8, Phase randomize 30%, Detune 0.08
- Filter: High-pass, Cutoff 400 Hz, then Low-pass Cutoff 7 kHz, Res 0.3
- LFO 1: Morphs wavetable position, Rate 0.4 Hz, Depth 30%
- Master: Add 15% saturation for grit

#### Sylenth1 (Punchy, Focused)

**Good for clean PC Music sounds:**
- Osc A: Sawtooth, Detune +30 cents
- Osc B: Sawtooth, Detune -25 cents (creates intentional beating)
- Filter: High-pass 350 Hz, Low-pass 6 kHz, Res 2.0 (focused peak)
- Filter envelope: Fast attack (5 ms), short decay (150 ms), minimal sustain
- Reverb: 15% for sense of space without washing out

---

## 2. HARD POP DRUMS

### 2.1 Hyperpop Drum Design Philosophy

**Core Principle:** "Intentional Overcompression"
- Transients are crushed deliberately
- Kick and snare dominate frequency spectrum
- Hi-hat rolls and stutters create rhythmic texture
- No drum is "natural" or "sampled authentically"—everything processed aggressively

**Distorted 808 Kicks:**
- Layer 1 (sub): Pure sine wave, low-pass filtered at 80 Hz, no distortion (45–50% volume)
- Layer 2 (punch): 808 sample or square wave with quick decay, distort heavily (see below)
- Layer 3 (attack click): Very short pitched noise (100–200 Hz), 5–10 ms duration (10–15% volume)

**Heavy 808 Distortion Settings:**
- Saturation: 40–60% (adds harmonics, makes 808 audible on small speakers)
- Distortion type: Soft clipping preferred over hard clipping (more musical)
- Frequency focus: Boost 200–300 Hz (sub-kick clarity), add presence at 1.5–2 kHz
- Post-distortion EQ: High-pass at 30 Hz (remove sub rumble), peak at 250 Hz (+6 dB)

### 2.2 Charli XCX / AG Cook Drum Programming Style

**Aesthetic Signature:**
- Aggressive stereo compression (L/R channels processed independently, then crushed together)
- Pitched drums (pitch-shift hi-hats and snares for textural variety)
- Mixed resolutions: Straight snares + 16th-note rolls simultaneously
- Off-grid hi-hat placement for "drunk" feel while maintaining groove pocket

**Snare / Clap Design:**
- Layer 1: Acoustic snare sample, 4 kHz peak, short decay (150 ms)
- Layer 2: Clap sample, higher pitched (brighter), overlapped by 20 ms for thickness
- Layer 3: Pitched noise burst (white noise, heavily filtered 2–4 kHz, 50 ms duration)
- Compression on snare bus: Ratio 8:1, Attack 0 ms, Release 20 ms, makeup gain +6 dB
- Distortion on snare: 15–25% saturation for attitude

**Charli-Specific Programming Details:**
- Kick hits on 1 and 3 (straight beats)
- Snare: Standard trap positioning (off-beat 2 and 4, but with ghost notes 16ths between)
- Hi-hat: Syncopated 16th-note rolls with occasional 32nd stutters
- Example pattern: Kick (1), Hi-hat x8 (16ths), Snare (3), Hi-hat stutter x6 (32nds), Kick (4 early)

### 2.3 Trap-Influenced Hi-Hat Patterns with Rolls and Stutters

**Hi-Hat Programming Techniques:**

**Basic Trap Hi-Hat Pattern:**
- Straight 16th notes: Kick, HH, HH, HH, Snare, HH, HH, HH, Kick, HH, HH, HH, Snare, HH, HH, HH
- Velocity variation: 40%, 65%, 40%, 55% (natural humanization)
- Pan variation: Center, -5%, Center, +5% (slight motion)

**Roll Effects:**
- Roll speed: 32nd notes (8 hats per beat at 4/4 tempo)
- Duration: 1/2 beat to full beat (8 to 16 32nd notes)
- Placement: Before snare hits, at drop, during transitions
- Velocity curve: Starts soft (40%), crescendos to loud (80%) over roll duration

**Stutter Effects:**
- Triggered by muting every other hi-hat note in a pattern
- Example: Enable notes 1, 3, 5, 7, skip 2, 4, 6, 8 = syncopated stutter
- Or: Reduce note duration to 30% of grid length = percussive stutter (gated effect)
- Automate hi-hat pitch down 2–4 semitones during stutters for "zipping" effect

**Triplet Hi-Hat Stutters:**
- Set 1/24 note length = triplet 16ths
- Create pattern at triplet resolution: 1, 2, skip, 3, 4, skip, 5, 6, skip
- Results in off-grid, glitchy hi-hat feel without sounding random
- Layer with straight 16ths at lower velocity (30%) for pocket

### 2.4 Drum Bus Processing (Heavy Compression, Saturation, Limiting)

**Drum Bus Chain Architecture:**

1. **EQ (First Stage - Tone Shaping)**
   - High-pass filter: 40 Hz (remove sub rumble not from kick)
   - Boost: +4 dB at 100 Hz (sub punch), +6 dB at 3 kHz (attack/presence)
   - Cut: -3 dB at 500 Hz (mud), -2 dB at 7 kHz (harshness)

2. **Compression (Main Glue)**
   - Ratio: 4:1 to 8:1 (aggressive for "Brat" vibe)
   - Threshold: -15 dB (light detection, lots of gain reduction)
   - Attack: 2–5 ms (preserves transients slightly)
   - Release: 50–100 ms (fast for punchy sound)
   - Makeup gain: +6 to +12 dB (compensate for reduction)
   - Result: Drums "pump" with beat, creating energy

3. **Saturation (Harmonic Character)**
   - Type: Soft saturation preferred (tube emulation or analog model)
   - Drive: 20–35% (adds harmonics without murk)
   - Output compensation: Keep output at unity or -1 dB
   - Tone/Color: Warm setting if available (adds body)

4. **Multiband Compression (Optional - For Frequency-Specific Control)**
   - Sub (30–100 Hz): Ratio 2:1, loose control (protect kick)
   - Low-mids (100–500 Hz): Ratio 6:1, snappier control
   - Mids (500 Hz–2 kHz): Ratio 8:1, aggressive (tame snare mud)
   - Presence (2–8 kHz): Ratio 4:1, moderate (keep attack)
   - Air (8+ kHz): Ratio 2:1, light (preserve hi-hat crispness)

5. **Limiter (Final Safety)**
   - Type: Hard limiter (digital clipping preferred for "Brat" sound)
   - Threshold: -3 to -2 dBFS (allow slight clipping)
   - Attack: 0.1 ms (catch peaks instantly)
   - Release: 50 ms (fast recovery)
   - Note: This is intentional clipping for attitude, not loudness control

### 2.5 Layering Electronic and Processed Acoustic Drums

**Three-Layer Kick Approach:**
- Layer 1 (Sub, 50%): Pure sine wave 40–60 Hz, no processing
- Layer 2 (Body, 40%): Acoustic kick or 808 sample, boost 200 Hz by 6 dB, distort 25%
- Layer 3 (Click, 10%): Pitched click (500–1 kHz), very short (20 ms), add 40% saturation
- Pan: All center for mono compatibility
- Individual compression on Layer 2: Ratio 4:1, Attack 0 ms, Release 150 ms (shape attack)

**Three-Layer Snare:**
- Layer 1 (Acoustic, 50%): Real snare sample, natural decay
- Layer 2 (Clap, 40%): Bright clap sample, overlapped 10 ms early, adds brightness
- Layer 3 (Noise, 10%): White noise burst (pitched 2–4 kHz), short (80 ms), adds texture
- Compress all three together: Ratio 6:1, Attack 2 ms, Release 50 ms
- Add 20% saturation to snare bus for attitude

**Hybrid Hi-Hat Design:**
- Electronic: Synthesized hi-hat from filtered white noise (1–8 kHz bandpass, resonance 0.4)
- Acoustic: Real hi-hat sample, layered underneath at 30% volume
- Electronic dominates (70% volume, panned slightly left)
- Distort electronic layer 15% for edge
- Keep acoustic layer clean for "realness"

### 2.6 "Too Loud" Aesthetic—Intentional Clipping and Distortion

**Clipping Strategy:**
- Mix to -3 dBFS on the master (intentionally hot)
- Allow drums to clip softly against limiter (creates harmonic saturation)
- Soft clipping preferred over hard clipping (less harsh artifacts)
- Clipping adds presence without losing transient clarity

**Distortion Layering:**
- Drum track distortion: 15–30% (adds harmonics, makes drums "sit" in mix without volume increase)
- Bus distortion: 25–40% (glues everything together with aggressive character)
- Use tape saturation model if available (sounds more musical than digital distortion)
- Always EQ after distortion to control artifacts (boost 3–5 kHz, cut 500 Hz)

**Loudness Without Headroom:**
- Accept -1 to -0.5 dBFS peaks (intentional clipping for "Brat" sound)
- Use multiple stages of compression (drum bus compression + sidechain compression + limiter) to control dynamics while maintaining perceived loudness
- Parallel compression: Route drums to separate compressor bus at 0dB gain reduction, blend 20–30% back into main mix (preserves transients while adding thickness)

---

## 3. GLITCH & TEXTURE

### 3.1 Granular Synthesis for Glitch Effects

**Basic Granular Concept:**
- Slice audio into micro-grains (5–50 ms each)
- Reassemble grains in new order/timing for glitchy texture
- Grain parameters: Position (start time), Duration, Pan, Pitch

**Granular Effect Settings:**
- Grain size: 10–30 ms for noticeable glitch, 50–100 ms for subtle texture
- Density: 40–80 grains per second (higher = denser texture)
- Grain jitter: 20–40% randomization (prevents mechanical sound)
- Pitch shift per grain: +/- 2 to 5 semitones randomized (creates harmonic chaos)
- Playback speed: 0.5x to 2x original (time-stretching without pitch shift)

**Tools:**
- Native Instruments Granulator 2 (excellent for real-time control)
- Arturia eFX Fragments (musical granular processor)
- Ableton's Spectral Resonator (creative granular reimagining)

**Practical "Brat" Application:**
- Use on synth lead: Apply granular effect during drop moment for disintegration effect
- Grain size: 20 ms, Density 60 grains/sec, Jitter 30%
- Pitch randomization: +/- 3 semitones
- Creates impression of vocal/synth breaking apart into particles

### 3.2 Buffer/Stutter Effects (Glitch2, Effectrix, HalfTime, Gross Beat)

#### **Glitch2 (Voxengo) - Architecture**

**Step Sequencer Grid:**
- 16 steps (adjustable to 32/64 steps)
- 16 effects available: Stretch, Reverse, Filter, Echo, Shuffle, Repeat, Grain, Scatter, and more
- Each step can trigger one or multiple effects
- Tempo-synced to host

**Signature Glitch2 Sound Design:**
- Use "Repeat" effect: 4–8 repeats, spread across 4–8 steps (creates stutter)
- Automation: Apply Repeat to 1/4 beat sections, creating rhythmic chopping
- "Scatter" effect: Randomizes grain order, 40–60% scatter amount
- "Pitch" effect: Down 3–5 semitones, applied selectively to create "robot" stutters
- Combine multiple effects: Stretch + Repeat + Reverse for maximum glitch

**Effectrix 2 (Sugar Bytes) - Superior for Performance**

**14 Built-In Effects:**
- **Repeat:** Creates percussion stutter, 4–8 repetitions over 1/16 beat typical
- **Stutter:** Different from Repeat—gates audio at variable rate (useful for vocal chopping)
- **Stretch:** Time-stretches audio without pitch change, 50–150% stretch typical
- **Filter:** Automates filter cutoff/resonance, can sweep 100 Hz to 8 kHz over 1 beat
- **Echo:** Multi-tap delay, 3–5 taps spaced rhythmically
- **Shuffle:** Reorders audio grains, variable shuffle amount (30–70%)
- **Pitch:** Shifts pitch down typically (-2 to -7 semitones for demon effect), up for chipmunk
- **BPM:** Resamples audio at different tempos (creates rhythmic speedup/slowdown)
- **Bitcrush:** Reduces bit depth (6–10 bits typical)

**Effectrix Grid Programming:**
- 32-step sequencer
- Paint effects into grid lanes to create complex stutters
- Example pattern: Kick hit, Repeat (2 steps), Stutter (2 steps), Pitch Down (1 step), Stretch (2 steps)
- Steptrain mode: Special variant for creating smooth stutter automation

#### **HalfTime and Gross Beat (Native Instruments / iZotope)**

**HalfTime:**
- Not a stutter plugin but creates rhythmic glitch through time-stretching
- Halves playback speed while maintaining pitch (creates "floating" effect)
- Sync to host for rhythmic moments
- Use on synth lead: Enable HalfTime for 1/2 bar during build-up (creates tension)

**Gross Beat:**
- Rhythmic time-stretching effect, extremely powerful
- Preset curves: Can create "swing," "reverse," "stutter," "pitchshift" in rhythmic patterns
- Custom curves allow drawing exact timing/stretching curve per beat
- Example: Linear curve down 50% creates deceleration effect over 1 beat

### 3.3 Bitcrushing and Sample Rate Reduction Techniques

**Bitcrushing Fundamentals (Revision):**
- Bitcrusher reduces digital resolution, creating quantization distortion
- Audible artifacts: Higher frequencies become harsh/metallic, lower frequencies become "grainy"
- Not the same as distortion—creates specific digital character

**Bit Depth Settings for Different Effects:**
- 16-bit: Subtle grit, barely noticeable
- 12-bit: Clear degradation, lo-fi character, musical
- 8-bit: Extreme degradation, "video game" sound
- 4-bit: Extreme noise, almost unusable alone but great layered

**Sample Rate Reduction Settings:**
- 44.1 kHz (standard, no change)
- 22.05 kHz: Introduces subtle aliasing above 11 kHz
- 11.025 kHz: Clear aliasing (frequencies above 5.5 kHz distort)
- 8 kHz: Severe aliasing, "phone quality" sound
- 4 kHz: Extreme lo-fi, almost all high-frequency content becomes noise

**Combined Bitcrushing + Sample Rate Reduction:**
- Typical "Brat" setting: 10-bit + 16 kHz sample rate
- Creates aliasing artifacts + quantization = complex digital texture
- Automate bit depth across a synth lead: Start 16-bit (clean), end 6-bit (grainy)
- Apply selectively to high-frequency content (above 4 kHz) to preserve bass clarity

### 3.4 Digital Artifacts as Musical Elements

**White Noise / Digital Static:**
- Filter white noise to create texture: 2–8 kHz bandpass (metallic), 8–15 kHz (air/fizz)
- Layer underneath synths at -20 to -15 dB (noticeable but not dominant)
- Automate filter cutoff for dynamic texture

**Aliasing as Feature (Not Bug):**
- Intentional aliasing from extreme pitch-shifting or extreme sample rate reduction
- Creates "digital bells" / metallic harmonics
- High-pass alias artifacts (fold-back distortion above Nyquist frequency) into presence range (3–8 kHz)
- Layer at -15 dB under main sound for sheen

**DC Offset / Digital Clipping Artifacts:**
- Record a synth with intentional clipping (push gain into limiter)
- Slight DC offset from clipping creates "digital warmth"
- Soften hard clipping with soft-clipping emulation for more musical sound

### 3.5 Micro-Editing and Audio Chopping Techniques

**Vocal Chopping (Classic Hyperpop):**
1. Record vocal or dialogue (aim for 2–4 syllables)
2. Slice into phonemes / syllables (1 slice per 50–150 ms)
3. Create grid-based pattern: Play back slices in non-linear order
4. Example pattern: Slice A, Slice B, Slice A, Silence (50 ms gap), Slice C, Slice B
5. Repeat pattern 4–8 times for hook-like texture
6. Pitch shift every other slice up +3 semitones for variety
7. Add slight reverb (-2 dB, 0.3 sec) to blur transitions

**Synth Micro-Editing:**
- Record 2–4 bar synth pad
- Slice every 50 ms (creates grain-like texture)
- Reorder slices randomly, remove 30–50% of slices (creates stuttering)
- Pitch shift alternating slices +/- 2 semitones (creates harmonic interest)
- Play back at different speeds for chopped/glitchy texture

**Effective Slicing Points:**
- Slice at transient peaks (cleaner cuts)
- Fade slices slightly at edges (prevent clicks): 5 ms fade in, 5 ms fade out
- Keep slices 30–200 ms for noticeable glitch, 200–500 ms for subtle texture

---

## 4. BASS DESIGN

### 4.1 Distorted 808 Bass

**808 Foundation (Pure Element):**
- Sine wave fundamental 40–60 Hz (sub-bass range)
- Quick pitch ramp at attack (pitch down to final note): 80 Hz down to 50 Hz over 50–100 ms
- Decay envelope: Long sustain (1–3 seconds) for melodic bass lines
- Natural 808 character: Decay from strong attack to quiet tail over 2–4 seconds

**Heavy Distortion Layer:**
- Add saturation/distortion to 808 to make it audible on small speakers
- Distortion type: Soft clipping (tape saturation model preferred)
- Drive amount: 30–50% for noticeable harmonics
- Post-distortion EQ: Boost 250 Hz by +5 dB (adds thump), add presence at 1–2 kHz (+3 dB)

**Frequency-Specific Distortion:**
- Use multiband distortion: Apply distortion only to 200–500 Hz range
- Preserves clean low-end sub, adds grit to upper-bass body
- Mid distortion (500 Hz–1.5 kHz): Heavy distortion 40% (adds presence)
- Keep super-low (30–100 Hz) completely clean (no distortion)

**Sidechain Compression (Bass to Kick):**
- Apply compressor to 808 bass track
- Sidechain source: Kick drum track
- Ratio: 4:1, Attack 0 ms, Release 150–200 ms
- Threshold set so kick causes -3 to -6 dB gain reduction on bass
- Creates "pumping" pocket between kick and bass

### 4.2 Reese Bass Variations for Hyperpop

**Classic Reese Architecture:**
- Oscillator 1: Sawtooth wave, detuned -15 cents
- Oscillator 2: Sawtooth wave, detuned +15 cents (creates beating at ~4–5 Hz)
- Both oscillators: Same amplitude, no filters initially
- Filter: Low-pass resonant filter, Cutoff 500–800 Hz, Resonance 0.6–0.8
- Envelope: Fast attack (5 ms), medium decay (400 ms), minimal sustain (0.3), release 200 ms

**"Brat" Reese Variation:**
- Same detuning but add FM modulation: LFO modulates filter cutoff at 2–4 Hz
- Filter sweeps up and down, creating morphing texture
- Add distortion (20%) to make it aggressive/attitude-filled
- Automate resonance (0.3 to 0.8) for dynamic filtering effect

**Hyperpop Reese Layer:**
- Create two Reese instances:
  - Reese 1 (Clean, 60%): No distortion, gentle filter movement
  - Reese 2 (Distorted, 40%): Heavy distortion (40%), bitcrushed (10-bit), aggressively filtered
- Combine for rich/aggressive hybrid bass
- Pan Reese 1 center, pan Reese 2 left 10% (slight width without losing mono compatibility)

### 4.3 FM Bass Techniques (Aggressive, Metallic)

**FM Bass Fundamentals:**
- Carrier frequency: Sets fundamental pitch (bass range 40–80 Hz typical)
- Modulator frequency: Determines harmonic content
- Modulation index/depth: Controls how much modulator affects carrier (intensity)

**Aggressive FM Bass Settings:**
- Carrier: 55 Hz sine wave
- Modulator: 220 Hz sine wave (4x carrier = aggressive harmonics)
- Modulation depth: 200–400 cents (creates complex timbre)
- Envelope on modulation: Fast attack, longer decay (creates evolving character)
- Filter: Low-pass 1 kHz, resonance 0.3 (tames harshness)
- Distortion: 25% to blend harmonics together

**Metallic FM Bass:**
- Use square wave or sawtooth for modulator (instead of sine) to increase harmonic complexity
- Modulator frequency: 440 Hz (8x carrier) for bright metallic character
- Modulation depth: 300–500 cents (extreme)
- Filter: Bandpass around 500 Hz, resonance 0.7 (emphasizes specific harmonic)
- Result: Ringing, bell-like metallic bass (more synth than traditional bass)

### 4.4 Bass Layering Strategies (Sub + Mid + Distortion)

**Three-Layer Bass Architecture:**

**Layer 1 - Sub (50% volume, fundamental integrity):**
- Pure sine wave 35–50 Hz (true sub)
- No processing: No distortion, no filtering, no modulation
- Mono output (both L/R channels identical)
- Purpose: Weight and low-end presence

**Layer 2 - Mid Body (35% volume, character):**
- 808 or Reese bass, 60–150 Hz focus
- Slight distortion (15–25%) to add harmonics
- Filter: Low-pass 1 kHz, subtle resonance (0.2)
- Slight sidechain: -2 to -3 dB reduction on kick hit
- Purpose: Thickness and tone

**Layer 3 - Distortion / Attitude (15% volume, presence):**
- Heavily distorted bass sound, 200–400 Hz focus
- Bitcrushed (8–10 bits) for grit
- High-pass filtered at 150 Hz (removes sub conflict)
- Loud and aggressive in its own frequency range
- Purpose: Cut through mix, add attitude/aggression

**Blending Strategy:**
- All three layers play simultaneously
- Pan: Sub center, Mid center, Distortion center (mono compatibility)
- EQ total blend: Aim for smooth frequency response 40 Hz–1.5 kHz
- Use multiband compression to glue layers together at 100–300 Hz range (ratio 4:1, gentle control)

### 4.5 Sidechain and Ducking Approaches

**Sidechain Bass to Kick:**
- Compressor on bass track
- Sidechain input: Kick drum
- Ratio: 4:1 (moderate reduction)
- Attack: 0 ms (instant response to kick)
- Release: 150 ms (moderate, not too quick)
- Threshold: Set to -3 to -5 dB gain reduction on bass when kick hits
- Creates "pocket" for kick, bass fills space after kick release

**Advanced Sidechain - Multi-Band:**
- Apply sidechain only to low frequencies (below 300 Hz) of bass
- Keep mid frequencies (300 Hz–1.5 kHz) uncompressed
- Preserves bass character while clearing space for kick fundamentals

**Ducking (Sidechaining Reverses):**
- Use gate/expander instead of compressor for "hard" ducking
- Threshold set so bass completely silences during kick hit
- Creates more aggressive "clearing" effect than compression
- Use sparingly (only on aggressive sections)

**Kick-Side-Kick Interaction (Pro Technique):**
- Sidechain kick to bass (as described above)
- Also sidechain bass to kick using gentle ratio (2:1)
- Creates dialogue between kick and bass, both moving in pocket
- Results in more cohesive low-end groove

---

## 5. VOCAL PROCESSING

### 5.1 Extreme Auto-Tune (Zero Retune Speed, Formant Shifting)

**Auto-Tune Settings for Extreme Effect:**

**Zero Retune Speed (The "Robot" Sound):**
- Retune Speed: 0 ms (instantaneous)
- Fine Tuning: Set to max to minimize natural vibrato/glide
- Humanize: 0% (disable) for maximum artificial character
- Vibrato amount: Minimum (remove natural variation)
- Result: Every pitch change is snapped instantly, creating robotic, artificial effect

**Typical Settings for "Brat" Aesthetic:**
- Retune Speed: 1–3 ms (very fast but not perfectly instant)
- Humanize: 10–20% (maintains slight naturalness while sounding "fixed")
- Target scale: Set to key of song (allows intentional off-key pitches)
- Vibrato suppression: 80–100%

**Formant Shifting (Advanced Auto-Tune):**
- Formant controls adjust perceived vocal gender/throat shape
- Moving formant up creates "child" or "chipmunk" effect
- Moving formant down creates "demon" or "mature" effect
- Typical range: -3 to +3 octaves (extreme shifts)
- Use formant shift while keeping pitch unchanged for weird vocal texture

**Formant Preserve Option:**
- When pitch-shifting vocals, enable formant correction
- Prevents "chipmunk" effect at higher pitches, "demon" effect at lower pitches
- Tradeoff: More natural but less weird
- Disable for intentional artifact (especially on backing vocals)

### 5.2 Pitch-Shifted Vocals (Chipmunk vs. Demon)

**Chipmunk Effect (Pitched Up):**
- Pitch shift up +12 to +24 semitones (1–2 octaves)
- Formant preservation: Disable (create artificial character)
- Maintain original vocal duration (use time-stretching, not speed change)
- Layer under lead vocal at -8 to -15 dB for texture
- Use selectively on hook/chorus for memorability

**Practical Implementation:**
- Record lead vocal
- Duplicate track, pitch shift up +18 semitones
- Add slight reverb (-4 dB, 0.5 sec) to blur high pitch
- Pan slightly left/right (subtle width)
- Creates "ethereal" doubled vocal effect

**Demon Effect (Pitched Down):**
- Pitch shift down -24 to -36 semitones (2–3 octaves)
- Formant preservation: Disable
- Use on aggressive/attitude-filled lyrics
- Layer at -12 to -18 dB (less present than chipmunk)
- Often used as drop moment or ad-lib

**Example Usage:**
- Lead vocal: Standard (octave 1)
- Chipmunk layer: +18 semitones (during first chorus)
- Demon layer: -24 semitones (during drop moment)
- Stacked effect creates wealth/confidence texture

### 5.3 Vocal Chop / Stutter Techniques

**Chopping Process:**
1. Record vocal phrase (2–4 syllables or words)
2. Slice audio into grid: 50 ms slices typical (divides phrase into phoneme-like pieces)
3. Rearrange slices in sequence using DAW's drum rack or sampler
4. Create melodic pattern from rearranged slices

**Pattern Example:**
- Original phrase: "I'm the best"
- Slice 1: "I'm" (250 ms)
- Slice 2: "the" (150 ms)
- Slice 3: "best" (300 ms)
- New pattern: Slice 1, Silence (50 ms), Slice 2, Slice 1, Slice 3, Slice 2
- Play pattern as 1-bar loop over drums

**Stutter Effect:**
- Take single slice (e.g., first 100 ms of vocal)
- Repeat slice 4–8 times, each time slightly pitch-shifted
- Add slight panning variation (L, C, R, C, L, C)
- Create "vocal stutter" that sounds glitchy but musical

**Tools:**
- Effectrix (grid-based): Design chop patterns visually
- Glitch2 (step sequencer): Paint vocal chops into sequence
- Sampler/Drum Rack (manual): Slice and arrange manually in DAW

### 5.4 Layered Vocal Stacking (SOPHIE / AG Cook Vocal Wall)

**The "Vocal Wall" Concept:**
- SOPHIE and AG Cook create "walls" of vocals by stacking many layers
- Each layer is processed differently (pitch, distortion, reverb, pan)
- Combined effect: Single vocal becomes a choir of altered versions

**Vocal Stack Architecture (Example for Hook):**

**Layer 1 - Lead (Center, 0 dB):**
- Original vocal, minimal processing
- Auto-tune: Moderate (10 ms retune speed, 30% humanize)
- Reverb: -6 dB, 1.2 sec decay
- Distortion: 5% (subtle attitude)

**Layer 2 - Chipmunk Harmony (+12 semitones, Pan Left -25%):**
- Pitched up 1 octave
- Auto-tune: Aggressive (3 ms retune speed, 0% humanize)
- Reverb: -8 dB, 0.8 sec decay
- Distortion: 15% (more present than lead)
- Volume: -6 dB relative to lead

**Layer 3 - Demon Harmony (-12 semitones, Pan Right +25%):**
- Pitched down 1 octave
- Auto-tune: Aggressive (3 ms retune speed, 0% humanize)
- Reverb: -8 dB, 0.8 sec decay
- Distortion: 20% (more aggressive)
- Volume: -8 dB relative to lead (less present)

**Layer 4 - Texture / Atmosphere (Center, -15 dB):**
- Heavily pitch-shifted (+7 semitones + -5 semitones simultaneously, creating harmony)
- Extreme bitcrushing (8-bit, 8 kHz sample rate)
- Reverb: -4 dB, 2.5 sec decay (washed out)
- Distortion: 30% (aggressively degraded)
- Purpose: Adds texture, not melody

**Combined Effect:**
- Creates sense of vocal "choir" from single source
- Each layer occupies different frequency range and spatial position
- Together they create fuller, more confident sound (SOPHIE/AG Cook signature)

**SOPHIE-Specific Technique:**
- Record vocal normally
- Use varispeed in Logic: Play back track at 88% speed, record vocal (becomes pitched up when restored)
- Creates natural-sounding chipmunk effect (not artificial plugin pitch-shift)
- Record multiple takes at different varispeed amounts (-10%, +10%, -5%) for natural variation

### 5.5 Vocoder and Talk-Box Processing for Attitude

**Vocoder Basics:**
- Analyze incoming vocal to extract formants (spectral shape)
- Apply those formants to a synth source
- Result: Vocal tone with synth character (or vice versa)
- Creates "robotic but musical" effect

**Vocoder Settings for "Brat":**
- Carrier: Sawtooth synthesizer (bright, aggressive)
- Modulator: Lead vocal
- Bands: 16–32 bands (higher = more detailed vocal shape preserved)
- Mix: 80% wet vocoder, 20% dry vocal (hear both)
- Filter: Pre-filter carrier at 2–6 kHz (emphasize presence)
- Distortion on carrier: 25% before vocoder (adds grit)

**Talk-Box Effect (Extreme Vocoder):**
- Similar to vocoder but more aggressive
- Synth "talks" through vocal source
- Effect: Sounds like vocal is being modulated by synthesizer
- Creates extreme robot/attitude sound
- Use sparingly (only on specific moments for impact)

**Implementation:**
- Send vocal to talk-box processor
- Carrier: Synth bass line or melody
- Wet: 100% (full robot effect)
- Use only on second half of hook or specific attitude moment

### 5.6 Distorted / Bitcrushed Vocals

**Light Vocal Distortion (Attitude Layer):**
- Add saturation to lead vocal: 10–15% drive
- Type: Soft saturation (tape model preferred)
- Post-distortion EQ: Boost 3 kHz by +3 dB (add presence)
- Apply to whole vocal or specific words for emphasis
- Creates grittier, more aggressive vocal tone without destroying intelligibility

**Heavy Vocal Distortion (Backing/Effects Layer):**
- Duplicate vocal track
- Apply heavy distortion: 40–60% drive
- Bitcrushing on top: 8–10 bits
- Pitch shift down: -5 to -7 semitones (demon effect)
- High-pass filter at 500 Hz (remove mud)
- Use as textural element underneath lead vocal (-12 to -15 dB)
- Creates aggressive, attitude-filled harmony

**Bitcrushed Vocal Texture:**
- Apply bitcrusher to backing vocal
- Bit depth: 8 bits (strong effect) or 6 bits (extreme)
- Sample rate: 16 kHz (creates aliasing above 8 kHz)
- Keep original vocal underneath at -3 dB for clarity
- Creates "digital ghost" effect

---

## 6. ATTITUDE & ENERGY ELEMENTS

### 6.1 M.I.A.-Style World Music Sample Integration

**Sample Selection Philosophy:**
- Non-Western percussion and instrumentation (Indian, African, Asian influences)
- Unexpected juxtaposition with Western pop structure
- Samples often triggered on beat points (kick or snare hits)

**Typical M.I.A. Approach:**
- Sitar or dhol percussion sample: 1–2 second loop
- Triggered on drops or breaks (every 4–8 bars)
- Heavy distortion/compression applied to sample (makes it sit aggressively in mix)
- Often layered with electronic drums, creating East-meets-West texture

**Implementation (Example):**
- Source: Sitar or tabla sample (can be from sample packs or recorded)
- Processing:
  - High-pass filter at 100 Hz (remove sub rumble)
  - Bitcrushing: 10 bits, 12 kHz sample rate (degrades quality intentionally)
  - Saturation: 30% (makes sample sit forward in mix)
  - Distortion: 15% (adds aggression)
- Panning: Slightly left/right for width
- Placement: Triggered on drop moment, layered under kick/snare
- Volume: -8 to -10 dB (noticeable but not dominant)

**World Sample Layering:**
- Create two instances of world sample: One clean, one heavily processed
- Clean layer: 60% volume, gentle reverb
- Processed layer: 40% volume, heavy distortion/bitcrushing
- Together create "world meets hyperpop" collision

### 6.2 Gunshot, Cash Register, and Attitude SFX Design

**Gunshot Samples:**
- Source: Sample pack or record own gunshot-like percussive sound
- Processing: Heavy compression (ratio 8:1, attack 0 ms) preserves transient
- EQ: Boost 1–2 kHz (adds "snap"), cut 300 Hz (removes muddiness)
- Distortion: 10% (slight attitude)
- Reverb: Very short (50–100 ms) or none (keep tight)
- Placement: On snare hit or specific emphasis points
- Volume: Peak at -6 to -3 dBFS (very loud, attention-grabbing)

**Cash Register Sound:**
- Source: Cash register sample (traditional "ding" sound)
- Processing: High-pass filter at 500 Hz (remove low rumble)
- Bitcrushing: 12 bits, 16 kHz (degrades slightly)
- Saturation: 20% (adds texture)
- Reverb: Medium (1 sec decay) to add shimmer
- Pitch shift: Can shift +/- 3–5 semitones for tonal variety
- Placement: End of phrases or drop moments (money/confidence metaphor)
- Volume: -8 dB (noticeable but not overwhelming)

**Attitude SFX - Vocal Ad-Libs:**
- "Uh," "Yuh," "Brat," "OK" samples (can record own or use samples)
- Process heavily: Auto-tune (aggressive), distort (25%), bitcrush (10 bits)
- Layer: 2–3 ad-lib phrases at different pitches (harmony stack)
- Reverb: Short (0.3 sec) to keep punchy
- Trigger on specific beats (usually drop moment or before hook)

### 6.3 Crowd/Chant Samples and Processing

**Crowd Sample Integration:**
- Source: Crowd cheer, crowd chant, or record own (vocal group)
- Processing:
  - Compress aggressively: Ratio 6:1, attack 5 ms, release 150 ms (even out dynamics)
  - EQ: Boost 2 kHz (vocals presence), cut 300 Hz (muddiness)
  - Distortion: 15–25% (make sit forward, add attitude)
  - Reverb: 0.5–0.8 sec (sense of space, but not washed out)
- Pitch: Can be pitch-shifted for tonal variety or left natural
- Placement: Under drop moment, during chorus for energy boost
- Volume: -10 to -8 dB (supporting element, not lead)

**Chant Creation (DIY):**
- Record vocal phrase (4–8 words): "Yeah," "Brat," "Let's go," etc.
- Layer 3–5 versions with slight pitch variations (+/- 3 semitones each)
- Pan: Spread across stereo field (L, C, R positioning)
- Process same as crowd sample above
- Creates "crowd" effect from single voice

**Call-and-Response Pattern:**
- First phrase: Lead vocal (clean, minimal processing)
- Second phrase: Crowd/backing vocal (distorted, processed, lower pitch)
- Repeat: Creates dialogue between lead and "crowd" energy
- Used in M.I.A. and hyperpop for confidence/attitude building

### 6.4 Confidence Sonic Signature (How Producers Create Swagger)

**Swagger Creation Techniques:**

**1. Frequency Presence Peaks:**
- Boost 3–4 kHz: Gives "forward" vocal character
- Boost 1.5–2 kHz: Adds body/confidence to synth leads
- Presence translates as "loud even when not loud" = confidence

**2. Sidechain Pumping:**
- Aggressive sidechain on instruments to kick creates "bouncing" pocket
- Makes beat feel locked/confident (vs. floating)
- Confident beat = confident song

**3. Snappy Transients:**
- Fast attack compression on drums (0–2 ms): Makes every hit snap with confidence
- Crushed snare transient = aggressive attitude
- Preserved kick transient = powerful presence

**4. Distortion/Saturation:**
- Aggressive processing (25–40% distortion) signals "we don't care about perfection"
- Distortion = attitude, confidence, not afraid to be rough
- Clean production = polite; distorted production = braggadocious

**5. Volume Confidence:**
- Drum bus at -3 to -2 dBFS (intentional clipping) signals "we're loud and proud"
- Kick peak at -1 dBFS: Maximizes perceived power
- No headroom = no apologizing

**6. Synth Unison/Detune:**
- Heavy unison detune creates "thick" synth character
- Thickness feels powerful/confident vs. thin/weak
- Detuned synth = attitude, PC Music/hyperpop swagger

**7. Reversed Reverb (Swell Effect):**
- Lead into moment: Reverse reverb creates build-up tension
- Drop moment hits with maximum confidence/impact
- Confidence = planned, powerful moments

### 6.5 Spoken Word and Ad-Lib Processing

**Spoken Word Integration:**
- Source: Record own dialogue or use vocal samples
- Content: Confident statements ("I'm the best," "No cap," "Slay," etc.)
- Processing:
  - Auto-tune: Light (30% humanize) to keep some naturalness
  - Pitch shift: Can shift down 5 semitones for deeper confidence
  - Distortion: 10–20% (attitude)
  - Reverb: Very short (100–200 ms) to keep present
  - Compression: Ratio 4:1 to even out dynamics
- Placement: Start of verse, before drop, or as hook replacement
- Volume: -6 to -8 dB (noticeable, authoritative)

**Ad-Lib Layering:**
- Multiple short vocal sounds ("Uh," "Yeah," "OK," "Brat")
- Each processed differently (pitch shift, distortion levels vary)
- Stack 2–4 ad-libs on specific beat points (usually drop)
- Creates cacophony of confidence/attitude
- Example: Original ad-lib + pitched version (-5 semitones) + heavily distorted version = vocal trio

**Call-Out Strategy:**
- Spoken word "call" over beat
- Crowd/backing vocal response
- Back-and-forth creates energy and engagement
- Confidence comes from dialogue/interaction

---

## 7. EFFECTS & MIXING

### 7.1 "Loud and Proud" Mixing Approach (Intentional Overcompression)

**Philosophy:**
- Embrace clipping as aesthetic choice
- Use multiple compression stages to control dynamics while maintaining perceived loudness
- Distortion is friend, not enemy

**Compression Chain Architecture:**

**Stage 1: Drum Bus Compression (Glue)**
- Ratio: 4:1 to 6:1
- Threshold: -15 dB (significant gain reduction)
- Attack: 2–5 ms (preserves transient slightly)
- Release: 50–100 ms (fast for punchy recovery)
- Makeup gain: +6 to +10 dB (compensates for reduction, adds loudness)

**Stage 2: Parallel Compression (Thickness)**
- Setup: Route all tracks to parallel "New York Compression" bus
- Compressor settings: Ratio 8:1, Attack 0 ms, Release 50 ms, threshold aggressive
- Wet compression bus: At -3 dB gain reduction
- Blend parallel bus back at 20–30% volume under original mix
- Result: Original transients preserved, compressed thickness added underneath

**Stage 3: Sidechain Compression (Pocket)**
- Drums sidechain: Hi-hat/kick dynamics control bass and synth
- Ratio: 2:1 (gentle)
- Attack: 5 ms
- Release: 150 ms
- Keeps beat tight and syncopated

**Stage 4: Master Limiter (Safety/Clipping)**
- Threshold: -2 to 0 dBFS (allow slight clipping)
- Attack: 0.1 ms (catch peaks instantly)
- Release: 50 ms (fast recovery)
- Character: Soft clipping preferred for musicality

**Result:**
- Drums feel cohesive and punchy (Stage 1)
- Overall mix feels thick and loud without losing transients (Stage 2)
- Pocket is tight and groovy (Stage 3)
- Peaks controlled without sounding limited (Stage 4)

### 7.2 Stereo Width Manipulation (Extreme Widening then Mono Collapse)

**Extreme Widening Technique:**

**Full Widening:**
- Take synth lead or textural element
- Apply stereo widener: 200–300% width (maximum)
- Alternative: Pan copies of sound hard left/right, delay one by 20–30 ms
- Result: Synth feels HUGE, separated far across stereo field

**Mono Collapse:**
- Same sound: Hard-pan left and right at 100%
- Then: Apply another effect that sums to mono partially
- Collapse creates: "It was wide, now it's dead center" effect = tension/impact
- Time this to drop moment for maximum impact

**Implementation:**
- Intro: Synth at normal width (centered)
- Build: Gradually increase stereo width over 4–8 bars (automate panning)
- Drop: Instant mono collapse (automate stereo width back to 0)
- Creates excitement through spatial manipulation

**Stereo Width Plugin Settings:**
- Mid-side processing: Increase side component 200%, maintain mid at 100%
- Results in extreme width
- Watch mono compatibility: Check mix in mono mode
- Avoid phase cancellation (listen in mono to ensure nothing disappears)

### 7.3 Creative Sidechain and Pumping Effects

**Traditional Sidechain (Kick-Based):**
- Applied to: Synth leads, bass, pads, all elements except drums
- Compressor on each track
- Sidechain source: Kick drum
- Creates pump/bounce where everything ducks to kick

**Sidechain Settings for Aggressive Pump:**
- Ratio: 8:1 (extreme ducking)
- Attack: 0 ms (instant response)
- Release: 200–300 ms (slow recovery, noticeable pump)
- Threshold: High so even quiet kicks trigger ducking
- Result: Obvious "pump" that listener feels as dance/motion

**Rhythmic Sidechain (Non-Kick):**
- Create sidechain source: Hi-hat pattern or custom drum hit
- Apply sidechain to bass/synth: Creates rhythmic stuttering without audio chop
- Makes elements bob/pump in time with beat in non-obvious way

**Multi-Band Sidechain:**
- Sidechain only bass frequencies (sub range): Lets kick carry low-end
- Sidechain only mid frequencies (1–3 kHz): Lets snare presence shine
- Sidechain presence frequencies (3–8 kHz): Preserves lead vocal/synth presence
- Creates controlled pumping without losing element character

### 7.4 Reverb Used Sparingly but Dramatically

**Reverb Philosophy:**
- Most elements: Very little/no reverb (keep punch and attack)
- Specific moments: Big, dramatic reverb for impact and space

**Settings for Minimalist Reverb Approach:**

**Lead Vocal Reverb:**
- Reverb amount: -4 to -6 dB (noticeable but not washed out)
- Decay time: 1.0–1.5 sec (moderate space, not huge room)
- Pre-delay: 20–50 ms (separation from dry signal)
- High-pass filter on reverb: Cut below 200 Hz (no bass rumble in reverb)
- Early reflections: Moderate (provides space without muddiness)

**Synth Lead Reverb:**
- Sparingly: Use only on specific moments (build-up or transition)
- Decay: 0.5–1.2 sec (not huge)
- Mix: -8 to -10 dB (just a hint of space)
- Automate in: Gradually increase reverb amount leading into drop, then cut on drop

**Reverse Reverb (Dramatic Effect):**
- Record sound (vocal, synth, drum hit)
- Reverse the sound in DAW
- Apply heavy reverb (2–3 sec decay, 100% wet)
- Reverse back
- Result: Reverb tail comes before the sound (swell effect)
- Use: Lead into drop moment for maximum impact

**Snare/Clap Reverb:**
- Very little (barely noticeable)
- Purpose: Add space without losing snare snap
- Typical: -12 to -15 dB, 0.4–0.6 sec decay
- Alternative: No reverb on snare, use side-chain compression from snare instead

### 7.5 Delay Throws and Tape Stop Effects

**Delay Throw (Classic Production Technique):**
- Setup: Create separate reverb/delay bus
- Send lead vocal to this bus: Specific words/phrases only (via automation)
- Settings: Delay time = 1/4 note or 1/8 note, 2–3 repeats, feedback 30%
- Mix: 80% wet delay, 20% dry vocal
- Effect: Last word of phrase echoes into next line, creating space and interest
- Example: "I'm the best" → "best-est-est" (echo repeats)

**Automation for Throw Effect:**
- Keep vocal dry through verse
- Increase send to delay bus on last word of phrase
- Creates emphasis without sounding artificial

**Tape Stop Effect (Retro/Dramatic):**
- Plugin: Native Instruments Tape Stop, Kilohearts Tape Stop, or manual pitch-down
- Speed reduction: 100% down to 50% over 0.5–1 second
- Applied to: Entire mix or specific element (kick, synth, vocal)
- Timing: Use before drop moment or at section transition
- Effect: Song "slows down" dramatically, building tension

**Automated Tape Stop:**
- Engage tape stop on transition between sections
- Gradual slowdown = tension building
- Release tape stop at drop = explosion of energy
- Volume: Automation pitch doesn't change volume, so audio gets quieter naturally as "tape slows"

### 7.6 Master Bus Destruction (Soft Clipping, Limiting, Saturation)

**Master Bus Chain (Final Stage):**

**1. EQ (Tone Shaping - First)**
- High-pass filter: 30 Hz (remove sub rumble)
- Presence peak: Boost 2–3 kHz by +2 to +3 dB (adds clarity to final mix)
- High-frequency air: Boost 10–12 kHz by +1 to +2 dB (adds sparkle)
- Cut muddiness: -2 dB at 500 Hz

**2. Compression (Glue - Second)**
- Ratio: 2:1 (conservative, not aggressive)
- Threshold: -20 dB (light detection, few dB of gain reduction)
- Attack: 10–20 ms (preserves transients)
- Release: 100 ms (moderate recovery)
- Purpose: Master glue, not loudness control

**3. Saturation (Character - Third)**
- Type: Soft saturation / tape emulation
- Drive: 15–25% (adds harmonics without distortion)
- Tone: Warm if available (adds body)
- Output: Keep at unity or -0.5 dB

**4. Soft Clipping (Loudness/Attitude - Fourth)**
- Plugin: Soft clipping emulation or analog-modeled limiter
- Threshold: -3 to -2 dBFS (allow slight clipping intentionally)
- Curve: Soft knee preferred (musical clipping)
- Attack: 0.5–1 ms (fast enough to catch peaks)
- Release: 30–50 ms (quick recovery)
- Output compensation: -1 to -2 dB (prevent excessive boost from clipping)

**5. Limiter (Safety - Fifth)**
- Hard limiter as absolute ceiling
- Threshold: -0.3 dBFS (catches anything over digital limit)
- Attack: 0.1 ms (instant)
- Release: 50 ms (fast)
- Purpose: Prevents digital clipping artifacts

**Final Mix Levels:**
- Target: Peak at -1 to -0.5 dBFS (loud, confident, slightly clipped)
- Loudness: -14 to -12 LUFS (perceived loudness)
- Headroom: 0–1 dB (very little, "Brat" aesthetic)

---

## 8. KEY REFERENCE TRACKS (Production Notes)

### 8.1 Charli XCX - Brat Era

#### "360"
- **Producer:** AG Cook, others
- **Key Elements:**
  - Detuned supersaw synth (bright, presence at 4 kHz)
  - Distorted 808 bass with heavy sidechain to kick
  - Trap hi-hat patterns with stutters and 32nd-note rolls
  - Vocal processing: Light auto-tune, no extreme formant shifting
  - Drum bus compression: Aggressive (ratio 6:1+), creates pumping motion
- **Sound Design Notes:**
  - Synth lead: 16-voice unison supersaw, detune 0.2, high-pass filtered 500 Hz
  - 808 bass: Sine wave 55 Hz, pitch ramp 50 ms, distorted 35% post-gain
  - Snare: Layered acoustic + digital noise, compressed aggressively
  - Reverb: Minimal on drums, 0.8 sec on vocal
- **M.I.A. Influence:** Percussive element in middle section (melodic rhythm)

#### "Von Dutch"
- **Producer:** Finn Keane (original), AG Cook (remix)
- **Key Elements:**
  - Metallic synth (high-passed, crystalline PC Music style)
  - Hard-hitting trap drums with over-compressed transients
  - Pitched vocal ad-libs (stacked harmonies)
  - Heavy master bus compression for "locked" feel
- **Sound Design Notes:**
  - Synth: FM-style modulation, carrier 3 kHz, modulator 9 kHz, mod depth 150%
  - Kick: Layered 40 Hz sub + 100 Hz pitched punch + click (total 3 layers)
  - Clap: Heavily compressed (ratio 8:1, attack 0 ms), includes pitched noise layer
  - Master: Ratio 4:1 compression, attack 5 ms, release 100 ms + soft clipping

#### "Guess" (feat. Bladee)
- **Producers:** A.G. Cook, Finn Keane
- **Key Elements:**
  - Sparse production (hyperpop minimalism)
  - Detuned pad (thick, lush)
  - Pitched vocal sections (formant shifted, chipmunk effect)
  - Glitch stutters on synth (Effectrix-style)
- **Sound Design Notes:**
  - Pad: Sawtooth supersaw (12-voice unison, detune 0.15), layer with sine wave +octave
  - Vocal processing: Auto-tune aggressive, pitched +12 semitones on second half
  - Glitch effect: Applied to lead synth, stutter repeat 4 times, scatter 50%
  - Reverb on vocal: 1.5 sec decay, pre-delay 30 ms

#### "Talk Talk"
- **Key Elements:**
  - House-influenced 4-on-the-floor kick (very different from hyperpop)
  - Pitched synth leads (shifted up/down throughout)
  - Vocal stacking and layering
  - Stereo width manipulation (widening during build)
- **Sound Design Notes:**
  - Kick: Punchy 808, 80 Hz fundamental, quick decay (1.5 sec), sidechain aggressive
  - Synth: Two instances—one at 0 semitones (lead), one pitched +3 semitones (harmony)
  - Master: Less compression than other Brat tracks (more spacious feel)

### 8.2 Charli XCX - PC Music Era

#### "Vroom Vroom" (prod. SOPHIE)
- **Key Elements:**
  - Extreme glitch and stutter effects throughout
  - Minimalist arrangement (few sounds, but all processed heavily)
  - Pitched vocal (tuned, formant-shifted)
  - SOPHIE's signature: Every element sounds processed/created from scratch
- **Sound Design Notes:**
  - Synth bass: FM synthesis (carrier 60 Hz, modulator 240 Hz, mod depth 250%)
  - Stutter effect: Applied to all elements, granular glitch every 1/4 beat
  - Vocal: Extreme auto-tune (0 ms retune speed), pitch shifted +7 semitones on chorus
  - Master: Soft clipping for "Brat" attitude (allowed clipping)

#### "Click" (feat. Kim Petras, Tommy Cash; prod. SOPHIE, Umru)
- **Key Elements:**
  - Industrial glitch production
  - Hard distorted synths (detuned, "ugly")
  - Glitch hits and texture elements
  - Heavy compression on all tracks
- **Sound Design Notes:**
  - Lead synth: Detuned sawtooth (16-voice, detune 0.25), distorted 40%, bitcrushed (10-bit)
  - Drums: Highly compressed transients (ratio 8:1, attack 0 ms)
  - Effects: Stutter and glitch applied to synth hits for momentum
  - Bass: Reese bass with FM modulation (wobbling texture)

### 8.3 M.I.A.

#### "Paper Planes" (prod. Diplo, Switch)
- **Key Elements:**
  - Minimal beat (Clash sample interpolation)
  - Gunshot samples as rhythm
  - East-meets-West world sample integration
  - Raw, confident production aesthetic
- **Sound Design Notes:**
  - Kick: Very simple, pitched "boom" sound
  - Gunshots: Real gunshot samples, layered, compressed to sit in mix
  - Bass: Synth bass (simple sine wave movement), melodic line
  - Hi-hat: Panned stereo, subtle 16th-note hi-hat line with motion
  - Overall: Minimal compression, confidence through simplicity not complexity

#### "Bad Girls" (prod. Danja)
- **Key Elements:**
  - Eastern-influenced synth sounds (sitar-like, world percussion)
  - SOS signal rhythm (iconic pattern)
  - Multiple world samples layered
  - Attitude-filled vocal performance
- **Sound Design Notes:**
  - Synth: Bright, slightly detuned (not PC Music, but attitude-filled)
  - Percussion: Layered world instruments (tabla, others), processed with distortion
  - Signal rhythm: Synth stabs, rhythmic pattern carries song
  - Vocal processing: Pitch-shifted sections, call-and-response with backing vocals

#### "Born Free" (prod. Rusko)
- **Key Elements:**
  - Dubstep-influenced production
  - Heavy bass (wobble bass)
  - Minimal melodic content
  - Attitude through heaviness, not processing complexity
- **Sound Design Notes:**
  - Bass: Reese-style wobbling bass, long sustain
  - Filter: Automated filter sweep (LFO modulation, 2–4 Hz)
  - Drums: Trap snares, pitched kick, minimal hi-hats
  - Master: Hard compression for aggression

### 8.4 SOPHIE

#### "Bipp"
- **Producer:** SOPHIE (entirely created from scratch using Monomachine)
- **Key Elements:**
  - Every sound is created/synthesized, no samples
  - Glitchy, stuttering rhythm (inspired by glitch music)
  - Bright, crystalline synth character
  - Extreme vocal processing (pitched, formant-shifted, stacked)
- **Sound Design Notes:**
  - Synth: FM synthesis (on Monomachine), metallic character
  - Vocal: Pitched up +18 semitones, formant shifted, extreme auto-tune
  - Reverb: Dramatic, used on specific moments (swell effect)
  - Glitch: Applied to vocal and synth, creating stuttering texture
  - Master: Soft clipping, loud and proud aesthetic

#### "Lemonade"
- **Key Elements:**
  - Playful, sparkly synths (opposite of dark/heavy)
  - Popping, bubbling sound design (creative synthesis)
  - Pitched vocal (talkative, narrative)
  - Minimal but effective arrangement
- **Sound Design Notes:**
  - Synth: Plucked/percussive quality (very short attack, long decay with resonance)
  - Distortion: Minimal, allows clarity to shine
  - Vocal: Light auto-tune (retune speed 10 ms), pitch-shifted variations
  - Reverb: Strategic, used for specific bright moments
  - Master: Not as crushed as "Bipp"—allows dynamics to shine

#### "Immaterial"
- **Key Elements:**
  - Experimental vocal layering and processing
  - Pitch-shifted harmonies creating choir effect
  - Minimal synth accompaniment
  - Formant manipulation extensively used
- **Sound Design Notes:**
  - Vocal layer 1 (lead): Original, minimal processing
  - Vocal layer 2: Pitched +12 semitones (chipmunk)
  - Vocal layer 3: Pitched -12 semitones (demon)
  - Vocal layer 4: Heavily distorted, bitcrushed background texture
  - Synth: Simple, bell-like tone (FM synthesis or wavetable)
  - Master: Soft clipping, loud aesthetic but less aggressive than "Bipp"

### 8.5 100 Gecs

#### "money machine" (prod. Dylan Brady)
- **Key Elements:**
  - Trap-influenced drums (distorted 808, crushed claps)
  - Detuned synth melodies (hyperpop signature)
  - Country guitar samples (unexpected collision)
  - Playful, confident vocal performance
- **Sound Design Notes:**
  - 808: Heavy distortion (40%), sidechain aggressive (ducks 5 dB to kick)
  - Synth: 16-voice unison detune (0.2), bright presence (4 kHz peak)
  - Clap: Layered acoustic + digital noise, compressed ratio 8:1
  - Master: Soft clipping (-1 dBFS), aggressive compression (ratio 4:1)

#### "ringtone" (prod. Dylan Brady)
- **Key Elements:**
  - Fuzzy, distorted guitar bridge (emo element)
  - Hard electronic drums
  - Glitchy production moments
  - Emotional vocal + hard production contrast
- **Sound Design Notes:**
  - Distorted synth: Heavy distortion (50%), bitcrushed (10-bit)
  - Drums: Trap-influenced with glitch stutters during pre-chorus
  - Guitar: Heavily distorted (guitar pedal distortion, not plugin)
  - Vocal processing: Auto-tune moderate, emotional performance prioritized
  - Master: Less crushed than "money machine"—allows emotional dynamics

### 8.6 Slayyyter

#### "Mine"
- **Producer:** AOBeats, Robokid
- **Key Elements:**
  - House-influenced 4-on-the-floor (less glitchy than hyperpop)
  - Detuned synths (attitude)
  - Heavy distortion throughout
  - Confident, swagger-filled vocal
- **Sound Design Notes:**
  - Synth: Bright sawtooth supersaw (12-voice, detune 0.15), distorted 30%
  - Kick: Punchy house kick (80 Hz sine, 1 sec decay)
  - Master: Compressed (ratio 4:1) for cohesion

#### "Daddy AF"
- **Producer:** AOBeats, Robokid
- **Key Elements:**
  - Trap-influenced glitch drums
  - Abrasive synthesizers (deliberately ugly/detuned)
  - Experimental trap-pop fusion
  - Aggressive, confident attitude
- **Sound Design Notes:**
  - Synth: Detuned supersaw (16-voice, detune 0.25), high-passed 300 Hz
  - Distortion: 40% on synth, 35% on master
  - Drums: Heavily crushed transients (ratio 10:1), glitch effects
  - Master: Aggressive soft clipping (-0.5 dBFS), very loud aesthetic

#### "Celebrity"
- **Key Elements:**
  - Sparse, confident production
  - Detuned synth (minimal but present)
  - Hard-hitting trap drums
  - Attitude through simplicity
- **Sound Design Notes:**
  - Synth: Single detuned note/chord, sparse placement
  - Kick: Simple but distorted (25%)
  - Snare: Heavily compressed, cracked sound
  - Master: Soft limiting (-2 dBFS)

### 8.7 AG Cook (Solo/Production)

#### "Digitalism" or typical PC Music production
- **Signature Techniques:**
  - Obsessive chord arrangements (built from basic MIDI sounds initially)
  - Multiband compression (OTT on every layer)
  - Shiny, detailed production aesthetic
  - Glitchy, experimental sound design mixed with pop sensibility
- **Sound Design Notes:**
  - Start with boring MIDI sound, design through chords/arrangement
  - OTT compression: Heavy makeup gain, aggressive multiband compression
  - EQ: Boost presence peaks at 3 kHz, add air at 12 kHz
  - Master: Soft clipping, confidence-driven aesthetic
  - Every element: High-passed and limited to emphasize presence

---

## 9. PRODUCTION CHECKLIST & SUMMARY

### Pre-Production / Concept
- [ ] Target "Brat" attitude: Loud, confident, aggressive, unapologetic
- [ ] Establish detuned synth sound (supersaw with 0.15–0.25 detune)
- [ ] Plan drum character: Which drums distorted? Which compressed? Which glitched?
- [ ] Identify world sample or attitude SFX to integrate

### Synth Design
- [ ] Build supersaw: 12–16 voices, detune 0.15–0.25, layer multiple instances
- [ ] Apply PC Music crystalline effect: High-pass 500 Hz+, thin metallic character
- [ ] Add bitcrushing / degradation: 10-bit depth typical for glitch texture
- [ ] Set FM modulation for metallic attitude (optional but effective)
- [ ] EQ: Boost 3–4 kHz presence, cut 300 Hz muddiness

### Drums
- [ ] Construct layered kick: Sub (sine 45 Hz) + body (distorted 25%) + click (pitch noise 10%)
- [ ] Design snare: Acoustic layer + clap layer + noise layer, compress 8:1
- [ ] Program hi-hats: Trap pattern with 32nd-note rolls and stutters
- [ ] Drum bus compression: Ratio 6:1, attack 2 ms, release 50 ms
- [ ] Add master drum distortion: 25–35% soft saturation

### Bass
- [ ] Layer bass: Sub (clean sine) + mid-body (distorted 808) + attitude (heavy distortion 40%)
- [ ] Apply sidechain from kick: Ratio 4:1, attack 0 ms, release 150 ms
- [ ] EQ bass layers: Smooth blend across 40 Hz–1.5 kHz

### Vocal Processing
- [ ] Set auto-tune: Moderate retune speed (3–5 ms) for "Brat" effect
- [ ] Layer vocals: Lead + chipmunk (+12 semitones) + demon (-12 semitones)
- [ ] Add saturation to lead: 10–15% for attitude
- [ ] Apply formant shifting selectively (optional for extreme effect)
- [ ] Add reverb minimal on lead: -4 to -6 dB, 1.0 sec decay

### Glitch / Texture Elements
- [ ] Add stutter effect: Use Glitch2 or Effectrix, stutter 4–8 times
- [ ] Layer bitcrushed elements: 8–10 bits, sample rate 12–16 kHz
- [ ] Include vocal chops or micro-edits: Slice and rearrange vocals
- [ ] Apply granular effects selectively: Grain size 20 ms, density 60 grains/sec

### Attitude / Energy
- [ ] Add gunshot or cash register SFX on specific beats
- [ ] Layer world music sample (if using M.I.A. influence)
- [ ] Include vocal ad-libs with pitch stacking
- [ ] Create confidence through: Presence peaks (3–4 kHz boost), sidechain pumping, intentional clipping

### Final Mixing & Mastering
- [ ] Drum bus compression: 4:1 ratio, aggressive attack/release
- [ ] Parallel compression (New York style): 20–30% blend for thickness
- [ ] Master EQ: Boost 2–3 kHz presence, 10–12 kHz air, cut 300 Hz mud
- [ ] Saturation on master: 15–25% soft saturation
- [ ] Soft clipping on master: Threshold -3 to -2 dBFS (intentional clipping)
- [ ] Final limiter: Threshold -0.3 dBFS (safety)
- [ ] Target loudness: -14 to -12 LUFS, peaks -1 to -0.5 dBFS
- [ ] Check mono compatibility: Stereo mixes should collapse to mono without phase issues
- [ ] Final check: Does the mix feel confident, loud, and attitude-filled?

---

## 10. PLUGIN RECOMMENDATIONS

### Essential Synths
- **Xfer Serum:** Best for supersaw, FM, granular synthesis
- **Vital:** Excellent unison control, CPU-efficient, free/affordable
- **Sylenth1:** Clean, punchy synth, good for PC Music sounds
- **Wavetable (Ableton):** Built-in, capable, especially for wavetable morphing

### Essential Effects
- **Glitch2 (Voxengo):** Step-sequenced glitch/stutter effects
- **Effectrix 2 (Sugar Bytes):** 14 effects, excellent for vocal chopping
- **Native Instruments Reaktor:** Granular synthesis, custom glitch design
- **Arturia eFX Fragments:** Granular processor, musical and creative
- **Kilohearts Tape Stop:** Retro tape effect for transitions

### Drum Processing
- **Native Instruments Massive:** Excellent bass design (distorted 808s, FM bass)
- **Output Arcade:** Drum synth with character controls (distortion, saturation)
- **Sonible Smart:COMP:** AI compression, works great for aggressive drum bus settings

### Vocal Processing
- **Antares Auto-Tune:** Industry standard, essential for extreme auto-tune effects
- **Waves Vocal Rider:** Automatic vocal leveling, good for stacking
- **SoundToys PitchMorphesis:** Pitch shifting, formant manipulation

### Reverb & Delay
- **Valhalla VRoom:** Excellent reverb, controllable for dramatic/minimal use
- **Native Instruments Reaktor:** Granular reverb, experimental possibilities
- **Eventide H990:** Professional reverb/effects (expensive but legendary)

### Compression & Limiting
- **FabFilter Pro-C:** Visual compression, excellent for learning/tweaking
- **Native Instruments Solid Bus Comp:** Analog-modeled bus compression
- **IK Multimedia T-RackS:** Soft clipping, analog-modeled mastering chain

### Distortion & Saturation
- **Softube Saturation Knob:** Simple, effective saturation (free or paid)
- **Soundtoys Decapitator:** Creative distortion with character options
- **Universal Audio Neve 1073:** Analog-modeled saturation/EQ

### Bitcrushing & Lo-Fi
- **Native Instruments Bit Shifter:** Bitcrushing and sample rate reduction
- **SoundToys Decapitator:** Includes bitcrushing alongside distortion
- **Xfer Destructo:** Comprehensive degradation processor

### Master Bus / Loudness
- **FabFilter Pro-L:** Linear phase limiting, essential for loudness
- **Nugen Visualizer:** LUFS metering, loudness standards compliance
- **Softube FET Compressor:** Analog-modeled fast compressor (classic 1176)

---

## CONCLUSION

The "Brat Mode" sound combines Charli XCX's hypercompressed attitude with PC Music's crystalline experimental character, M.I.A.'s world-influenced aggression, SOPHIE's extreme vocal processing, and 100 gecs' glitchy emotionality. Success requires:

1. **Intention:** Distortion and clipping are deliberate aesthetic choices, not mistakes
2. **Layering:** Every sound should have multiple processed versions contributing different frequencies/character
3. **Processing:** Aggressive compression, saturation, and bitcrushing on every element
4. **Attitude:** Presence peaks (3–4 kHz), sidechain pumping, and confident peak levels create swagger
5. **Cohesion:** Drum bus and master compression/saturation glue disparate sounds into unified aesthetic

The goal is not perfection or naturalness, but bold, unapologetic self-expression through sound. Maximum loudness, intentional distortion, and refusal to apologize for harshness = Brat attitude.

---

## SOURCES & REFERENCES

- [A. G. Cook on New Album 'Britpop' and Producing Charli XCX's 'Brat' — Variety](https://variety.com/2024/music/global/ag-cook-britpop-charli-xcx-brat-1235994011/)
- [Brat (album) - Wikipedia](https://en.wikipedia.org/wiki/Brat_(album))
- ["Brat" Is The Sound Of Something Fighting Itself: Charli xcx Collaborators A. G. Cook, Finn Keane & George Daniel On The Album's Massive Impact — GRAMMY.com](https://www.grammy.com/news/charli-xcx-brat-explainer-ag-cook-finn-keane-george-daniel-roundtable)
- [Hyperpop production 101: How to make hyperpop that pushes the limits — Native Instruments Blog](https://blog.native-instruments.com/hyperpop/)
- [10 Best Plugins for Hyperpop Production in 2026 — Output](https://output.com/blog/best-plugins-for-hyperpop)
- [How to use digital synthesis techniques to create metallic sounds — MusicRadar](https://www.musicradar.com/how-to/how-to-use-digital-synthesis-techniques-to-create-metallic-sounds)
- [How Experimental Pop Producer SOPHIE Pushed the Envelope — Google Arts & Culture](https://artsandculture.google.com/story/how-experimental-pop-producer-sophie-pushed-the-envelope-musikinstrumenten-museum/2wWx4L63W07OIQ?hl=en)
- [10 Supersaw tips for Xfer SERUM - Get a big & lush sound — Production Music Live](https://www.productionmusiclive.com/blogs/news/10-supersaw-tips-for-xfer-serum-get-a-big-lush-sound-without-layering)
- [Serum VST 101: The Ultimate Guide & Advanced Tips/Tricks — Unison](https://unison.audio/serum-vst/)
- [Glitch VST Plugins: 15 Of The Best In 2022 — Cymatics.fm](https://cymatics.fm/blogs/production/best-glitch-vst-plugins)
- [Best 808 Sound Design Tricks, Techniques & Secrets (2025) — Unison](https://unison.audio/808-sound-design/)
- [How to Synthesize and Process 808s Like Tropkillaz (from Scratch in Operator) — Soniklash Sounds](https://soniklash.com/2025/03/14/808tropkillaz/)
- [Synth Bass: 7 Bass Types and How to Build Them — LANDR Blog](https://blog.landr.com/synth-bass/)
- [How to use Auto-Tune as a Pro — Major Mixing](https://majormixing.com/how-to-use-auto-tune-as-a-pro/)
- [Bitcrushing and Downsampling 101 (The Best Producer's Guide) — Unison](https://unison.audio/bitcrushing-and-downsampling/)
- [What is bitcrushing? How to add grit and texture to your tracks — Native Instruments Blog](https://blog.native-instruments.com/bitcrushing/)
- [Vocal Layering: 5 Techniques for Better Vocal Stacks — Synchro Arts](https://www.synchroarts.com/posts/vocal-layering)
- [Vocal Layering: 7 Ways To Stack Vocals For Powerful Sound — LANDR](https://blog.landr.com/vocal-layering/)
- [5 Best Trap Hi Hat Patterns — emastered](https://emastered.com/blog/trap-hi-hat-patterns)
- [Trap Hats: 4 Hi-Hat Techniques Every Trap Producer Uses — LANDR Blog](https://blog.landr.com/trap-hats/)
- [How To Improve Your Mixes With Master Bus Compression And Saturation — Sonarworks Blog](https://www.sonarworks.com/blog/learn/from-the-general-to-the-specific-master-bus-processing-analog-color)
- [Master Bus - How to Process Your Master Bus — Music Guy Mixing](https://www.musicguymixing.com/master-bus/)
- [5 Tips for Taking Control of Stereo Width — Audient](https://audient.com/tutorial/5-tips-for-taking-control-of-stereo-width/)
- [The Science of Stereo Width: How to Widen Your Mix Without Ruining It — Mix Master Pro](https://mixmasterpro.io/articles/stereowidth/)
- [Creative Tape Stop Effects — Attack Magazine](https://www.attackmagazine.com/technique/tutorials/creative-tape-stop-effects/)
- [These are the Plugins Behind A.G. Cook's Hyperpop Sound — Internet Tattoo](https://www.internettattoo.com/blog/ag-cook-hyperpop-plugin-svst)
- [How to Create Hyperpop Music with Pro Tools (PRO techniques) — Sample Focus Blog](https://blog.samplefocus.com/blog/make-hyperpop-music-pro-tools/)
- [Paper Planes - Learn Mix, Drum, Bass, & Beat Production — Modern Beats](http://www.modernbeats.com/hit-talk/mia-paper-planes-learn-mix-beat-production/)
- [Bad Girls (M.I.A. song) - Wikipedia](https://en.wikipedia.org/wiki/Bad_Girls_(M.I.A.)_song))
- [Slayyyter may be the 'WOR$T GIRL IN AMERICA,' but she's thrilling — Riff Magazine](https://riffmagazine.com/album-reviews/slayyyter-worst-girl-in-america/)
- [Recreating The Sound Of Immaterial By Sophie Using Wavetable — Attack Magazine](https://www.attackmagazine.com/technique/synth-secrets/recreating-the-sound-of-immaterial-by-sophie-using-wavetable/)
- [How to Make a Reese Bass in Xfer Serum 2 – Sound Design Techniques — ADSR](https://www.adsrsounds.com/serum-tutorials/how-to-create-a-reese-bass-more-unique-in-serum/)
- [How to Design Bass Sounds – From Sub to Reese — The Ghost Production](https://theghostproduction.com/producer-resources/how-to-design-bass/)
- [Formant Shifting 101: Manipulating Vocals In Creative Ways — Unison](https://unison.audio/formant-shifting/)
- [Formant Shifting: 4 Creative Techniques To Alter Your Voice — Baby Audio](https://babyaud.io/blog/formant-shifting)
