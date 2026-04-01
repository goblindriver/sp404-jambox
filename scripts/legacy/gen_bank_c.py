# Bank C: Lo-fi Hip-Hop Jam Kit
exec(open('/sessions/happy-intelligent-edison/synth_core.py').read())

OUT = '/sessions/happy-intelligent-edison/SP-404A-Samples/_BANK-STAGING/C-LofiHipHop'

# Pad 1: Dusty Kick
dur = 0.6
body = sine(55, dur) * env_perc(dur, 0.001, 0.5)
click = noise(dur) * env_perc(dur, 0.0005, 8.0) * 0.3
pitch_env = np.exp(-np.linspace(0, 30, int(SR*dur)))
kick = np.sin(2*np.pi * (55 + 150*pitch_env) * np.cumsum(np.ones(int(SR*dur))/SR))
kick = kick * env_perc(dur, 0.001, 0.4)
kick = kick + click[:len(kick)]
kick = lowpass(kick, 4000)
kick = bitcrush(kick, 12)  # lo-fi character
save_wav(f'{OUT}/01_kick.wav', normalize(kick))
print("C01 kick done")

# Pad 2: Mellow Snare
dur = 0.5
body = sine(200, dur) * env_perc(dur, 0.001, 1.5)
ns = noise(dur) * env_perc(dur, 0.001, 1.0)
ns = bandpass(ns, 1000, 6000)
snare = body * 0.5 + ns * 0.6
snare = lowpass(snare, 5000)
snare = bitcrush(snare, 12)
save_wav(f'{OUT}/02_snare.wav', normalize(snare))
print("C02 snare done")

# Pad 3: Soft Closed Hat
dur = 0.15
hat = noise(dur) * env_perc(dur, 0.0005, 5.0)
hat = highpass(hat, 6000)
hat = lowpass(hat, 12000)
hat = bitcrush(hat, 11)
save_wav(f'{OUT}/03_hat_closed.wav', normalize(hat))
print("C03 hat done")

# Pad 4: Shaker / Perc
dur = 0.3
shaker = noise(dur) * env_perc(dur, 0.005, 2.0)
shaker = bandpass(shaker, 3000, 10000)
shaker = bitcrush(shaker, 10)
save_wav(f'{OUT}/04_shaker.wav', normalize(shaker))
print("C04 shaker done")

# Pad 5: Deep Warm Bass (C2 = ~65Hz, short melodic hit)
dur = 1.2
bass = saw(65, dur) * 0.7 + sine(65, dur) * 0.5
bass_env = env_adsr(dur, 0.005, 0.2, 0.6, 0.3)
bass = lowpass(bass, 800) * bass_env
bass = saturate(bass, 1.5)
bass = lowpass(bass, 600)
save_wav(f'{OUT}/05_bass.wav', normalize(bass))
print("C05 bass done")

# Pad 6: Rhodes-style Keys (FM synthesis)
dur = 2.0
carrier = 330  # E4
mod_ratio = 1.0
mod_idx_env = env_perc(dur, 0.001, 0.3) * 5.0
tt_arr = t(dur)
mod = mod_idx_env * np.sin(2*np.pi * carrier * mod_ratio * tt_arr)
rhodes = np.sin(2*np.pi * carrier * tt_arr + mod)
rhodes = rhodes * env_adsr(dur, 0.005, 0.3, 0.4, 0.5)
rhodes = lowpass(rhodes, 3000)
rhodes = bitcrush(rhodes, 13)
save_wav(f'{OUT}/06_keys.wav', normalize(rhodes))
print("C06 keys done")

# Pad 7: Warm Pad (detuned saws, filtered)
dur = 3.0
p1 = saw(220, dur)
p2 = saw(220.5, dur)  # slight detune
p3 = saw(329.6, dur)  # fifth
pad = (p1 + p2 + p3) / 3.0
pad = lowpass(pad, 1200)
pad = pad * env_adsr(dur, 0.3, 0.2, 0.7, 0.8)
pad = chorus(pad, 0.003, 0.8)
pad = lowpass(pad, 2000)
save_wav(f'{OUT}/07_pad.wav', normalize(pad))
print("C07 pad done")

# Pad 8: Chord Stab (Cm7 - C Eb G Bb)
dur = 1.0
freqs = [261.6, 311.1, 392.0, 466.2]
stab = sum(sine(f, dur) for f in freqs) / len(freqs)
stab = stab * env_perc(dur, 0.003, 0.8)
stab = saturate(stab, 1.3)
stab = lowpass(stab, 3000)
stab = bitcrush(stab, 12)
save_wav(f'{OUT}/08_chord_stab.wav', normalize(stab))
print("C08 chord stab done")

# Pad 9: Vocal Chop (formant synthesis)
dur = 0.6
f0 = 220
formants = [(730, 1.0), (1090, 0.5), (2440, 0.3)]  # "ah" vowel
tt_arr = t(dur)
vox = np.zeros(int(SR*dur))
for ffreq, fgain in formants:
    sig = sine(f0, dur) + saw(f0, dur)*0.3
    sig = bandpass(sig, ffreq-100, ffreq+100)
    vox += sig * fgain
vox = vox * env_adsr(dur, 0.02, 0.1, 0.5, 0.2)
vox = bitcrush(vox, 10)
vox = lowpass(vox, 4000)
save_wav(f'{OUT}/09_vocal_chop.wav', normalize(vox))
print("C09 vocal chop done")

# Pad 10: Lo-fi Beat Loop (~90bpm, 2 bars)
bpm = 88
beat_dur = (60.0/bpm) * 8  # 2 bars of 4/4
n_total = int(SR * beat_dur)
loop = np.zeros(n_total)

def place(sig, beat_pos):
    """Place a sound at a beat position (in beats, 0-indexed)"""
    start = int((beat_pos * 60.0/bpm) * SR)
    end = min(start + len(sig), n_total)
    if start < n_total:
        loop[start:end] += sig[:end-start]

# Recreate short versions for the loop
k = normalize(kick[:int(SR*0.3)]) * 0.9
s = normalize(snare[:int(SR*0.25)]) * 0.7
h = normalize(hat) * 0.5
# kick on 1, 3, 5, 7
for b in [0, 2, 4, 6]:
    place(k, b)
# snare on 2, 6
for b in [2, 6]:
    place(s, b)
# hats on every beat + some offbeats
for b in [0, 0.5, 1, 1.5, 2, 3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 7.5]:
    h_vol = 0.3 if b % 1 == 0.5 else 0.5
    place(normalize(hat) * h_vol, b)

loop = lowpass(loop, 8000)
loop = bitcrush(loop, 12)
loop = saturate(loop, 1.2)
save_wav(f'{OUT}/10_beat_loop.wav', normalize(loop))
print("C10 beat loop done")

# Pad 11: Vinyl Crackle FX
dur = 3.0
crackle = noise(dur) * 0.05
# Add random pops
for _ in range(40):
    pos = np.random.randint(0, int(SR*dur))
    width = np.random.randint(5, 50)
    end_pos = min(pos+width, int(SR*dur))
    crackle[pos:end_pos] += np.random.uniform(-0.3, 0.3)
crackle = highpass(crackle, 200)
crackle = lowpass(crackle, 6000)
crackle = bitcrush(crackle, 8)
save_wav(f'{OUT}/11_vinyl_crackle.wav', normalize(crackle, 0.6))
print("C11 vinyl crackle done")

# Pad 12: Tape Wobble Texture
dur = 4.0
tt_arr = t(dur)
wow_freq = 0.3  # slow wow
flutter_freq = 6.0  # faster flutter  
base_freq = 440
mod = 3.0 * np.sin(2*np.pi*wow_freq*tt_arr) + 0.8*np.sin(2*np.pi*flutter_freq*tt_arr)
tape = np.sin(2*np.pi * base_freq * tt_arr + mod)
tape = tape + saw(220, dur) * 0.2
tape = lowpass(tape, 2000)
tape = tape * env_adsr(dur, 0.5, 0.2, 0.6, 1.0)
tape = bitcrush(tape, 10)
tape = saturate(tape, 1.5)
hiss = noise(dur) * 0.05
hiss = bandpass(hiss, 2000, 8000)
tape = tape + hiss
save_wav(f'{OUT}/12_tape_texture.wav', normalize(tape))
print("C12 tape texture done")
print("=== BANK C COMPLETE ===")
