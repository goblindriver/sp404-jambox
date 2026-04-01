# Bank E: Nu-Rave Jam Kit
exec(open('/sessions/happy-intelligent-edison/synth_core.py').read())
OUT = '/sessions/happy-intelligent-edison/SP-404A-Samples/_BANK-STAGING/E-NuRave'

# Pad 1: Punchy 4-on-floor Kick
dur = 0.4
pitch_env = np.exp(-np.linspace(0, 40, int(SR*dur)))
kick = np.sin(2*np.pi * np.cumsum(50 + 200*pitch_env) / SR)
kick = kick * env_perc(dur, 0.0005, 0.6)
kick = saturate(kick, 1.8)
save_wav(f'{OUT}/01_punchy_kick.wav', normalize(kick))
print("E01 kick done")

# Pad 2: Snappy Snare
dur = 0.3
body = sine(250, dur) * env_perc(dur, 0.001, 2.5)
ns = noise(dur) * env_perc(dur, 0.001, 2.0)
ns = bandpass(ns, 2000, 10000)
snare = body * 0.4 + ns * 0.7
snare = saturate(snare, 1.5)
save_wav(f'{OUT}/02_snappy_snare.wav', normalize(snare))
print("E02 snare done")

# Pad 3: Open Hat
dur = 0.5
hat = noise(dur) * env_perc(dur, 0.001, 0.8)
hat = highpass(hat, 5000)
hat = saturate(hat, 1.3)
save_wav(f'{OUT}/03_open_hat.wav', normalize(hat))
print("E03 open hat done")

# Pad 4: Rave Clap (layered)
dur = 0.4
claps = np.zeros(int(SR*dur))
for offset in [0, 0.008, 0.015, 0.02]:
    o = int(offset * SR)
    n = noise(0.03) * env_perc(0.03, 0.0005, 4.0)
    n = bandpass(n, 1000, 8000)
    end = min(o + len(n), len(claps))
    claps[o:end] += n[:end-o]
tail = noise(dur) * env_perc(dur, 0.02, 1.5) * 0.3
tail = bandpass(tail, 800, 5000)
claps += tail
save_wav(f'{OUT}/04_rave_clap.wav', normalize(claps))
print("E04 rave clap done")

# Pad 5: Acid Bass (303-style, saw through resonant filter)
dur = 1.5
tt_arr = t(dur)
bass_saw = saw(65, dur)  # C2
# Simulate resonant filter sweep
n = int(SR*dur)
filt = np.zeros(n)
# Accent envelope for filter
fenv = env_perc(dur, 0.001, 0.5)
prev = 0
prev2 = 0
for i in range(n):
    cutoff = 200 + 3000 * fenv[i]
    rc = 1.0 / (2*np.pi*cutoff)
    alpha = (1.0/SR) / (rc + 1.0/SR)
    # Two-pole for more resonance
    filt[i] = prev + alpha * (bass_saw[i] - prev)
    prev = filt[i]
bass = filt * env_adsr(dur, 0.005, 0.2, 0.6, 0.3)
bass = saturate(bass, 2.5)
save_wav(f'{OUT}/05_acid_bass.wav', normalize(bass))
print("E05 acid bass done")

# Pad 6: Hoover Synth (detuned saws, rave classic)
dur = 2.0
freqs = [130.8, 131.5, 132.2, 65.4, 261.6]  # C3 detuned + octaves
hoover = sum(saw(f, dur) for f in freqs) / len(freqs)
hoover = lowpass(hoover, 3000)
hoover = hoover * env_adsr(dur, 0.05, 0.3, 0.7, 0.4)
hoover = chorus(hoover, 0.004, 2.0)
hoover = saturate(hoover, 1.8)
save_wav(f'{OUT}/06_hoover.wav', normalize(hoover))
print("E06 hoover done")

# Pad 7: Rave Stab (bright, short, major chord)
dur = 0.5
freqs = [523.3, 659.3, 784.0, 1046.5]  # C5 E5 G5 C6
stab = sum(square(f, dur, 0.4) for f in freqs) / len(freqs)
stab = stab * env_perc(dur, 0.002, 1.2)
stab = lowpass(stab, 6000)
stab = saturate(stab, 1.5)
save_wav(f'{OUT}/07_rave_stab.wav', normalize(stab))
print("E07 rave stab done")

# Pad 8: Supersaw Pad
dur = 3.0
base = 220  # A3
saws = []
for detune in [-3, -1.5, -0.5, 0, 0.5, 1.5, 3]:
    saws.append(saw(base + detune, dur))
    saws.append(saw(base*2 + detune*2, dur) * 0.5)  # octave up
pad = sum(saws) / len(saws)
pad = lowpass(pad, 4000)
pad = pad * env_adsr(dur, 0.2, 0.3, 0.7, 0.8)
pad = chorus(pad, 0.003, 1.2)
save_wav(f'{OUT}/08_supersaw_pad.wav', normalize(pad))
print("E08 supersaw pad done")

# Pad 9: Arp Loop (~130bpm, 16th notes, synth arp)
bpm = 130
step = 60.0 / bpm / 4  # 16th note
notes = [262, 330, 392, 523, 392, 330, 262, 196]  # C E G C' G E C low-G
arp_dur = step * len(notes) * 2  # repeat twice
n_total = int(SR * arp_dur)
arp = np.zeros(n_total)
for rep in range(2):
    for i, note in enumerate(notes):
        idx = rep * len(notes) + i
        start = int(idx * step * SR)
        note_len = int(step * SR * 0.8)
        if start + note_len > n_total:
            break
        note_sig = square(note, step*0.8, 0.3) * env_perc(step*0.8, 0.002, 2.0)
        note_sig = lowpass(note_sig, 5000)
        arp[start:start+note_len] += note_sig
arp = saturate(arp, 1.5)
save_wav(f'{OUT}/09_arp_loop.wav', normalize(arp))
print("E09 arp loop done")

# Pad 10: Rave Beat Loop (~130bpm)
beat_dur = (60.0/bpm) * 8
n_total = int(SR * beat_dur)
loop = np.zeros(n_total)
def place(sig, beat_pos):
    start = int((beat_pos * 60.0/bpm) * SR)
    end = min(start + len(sig), n_total)
    if start < n_total:
        loop[start:end] += sig[:end-start]
k = normalize(kick[:int(SR*0.2)]) * 0.9
s = normalize(snare[:int(SR*0.15)]) * 0.7
h_c = noise(0.05) * env_perc(0.05, 0.0005, 5.0)
h_c = highpass(h_c, 6000)
h_c = normalize(h_c) * 0.4
# 4-on-floor kick
for b in range(8):
    place(k, b)
# Snare on 2 and 6
for b in [2, 6]:
    place(s, b)
# Offbeat hats
for b in [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]:
    place(h_c, b)
loop = saturate(loop, 1.3)
save_wav(f'{OUT}/10_rave_loop.wav', normalize(loop))
print("E10 rave loop done")

# Pad 11: Build-up Riser (snare roll + sweep)
dur = 4.0
riser = pitch_sweep(200, 8000, dur) * env_linear(dur, 0.1, 0.8)
# Add accelerating snare hits
n_total = int(SR * dur)
roll = np.zeros(n_total)
hits = 32
for i in range(hits):
    progress = i / hits
    interval = 0.5 * (1 - progress*0.9)  # accelerating
    pos = int(sum(0.5 * (1 - j/hits*0.9) for j in range(i)) * SR)
    if pos < n_total:
        sn = noise(0.05) * env_perc(0.05, 0.0005, 4.0)
        sn = bandpass(sn, 1000, 8000)
        end = min(pos + len(sn), n_total)
        roll[pos:end] += sn[:end-pos] * (0.3 + 0.7*progress)
combo = riser * 0.5 + roll * 0.6
combo = saturate(combo, 1.5)
save_wav(f'{OUT}/11_buildup.wav', normalize(combo))
print("E11 buildup done")

# Pad 12: Siren FX
dur = 2.0
tt_arr = t(dur)
siren_freq = 600 + 400 * np.sin(2*np.pi*3*tt_arr)
siren = np.sin(2*np.pi * np.cumsum(siren_freq) / SR)
siren = siren * env_adsr(dur, 0.05, 0.1, 0.8, 0.3)
siren = saturate(siren, 1.5)
save_wav(f'{OUT}/12_siren.wav', normalize(siren))
print("E12 siren done")
print("=== BANK E COMPLETE ===")
