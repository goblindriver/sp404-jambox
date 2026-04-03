# Bank G: Funk & Horns Jam Kit
import os
exec(open(os.path.join(os.path.dirname(__file__), 'synth_core.py')).read())
OUT = os.path.join(STAGING_BASE, 'G-FunkHorns')

# Pad 1: Funky Kick (tight, punchy, James Brown style)
dur = 0.25
pitch_env = np.exp(-np.linspace(0, 50, int(SR*dur)))
kick = np.sin(2*np.pi * np.cumsum(60 + 150*pitch_env) / SR)
click = noise(0.005) * env_perc(0.005, 0.0001, 10.0) * 0.5
kick = kick * env_perc(dur, 0.0005, 1.0)
kick_full = np.zeros(int(SR*dur))
kick_full[:len(kick)] = kick
kick_full[:len(click)] += click
kick = kick_full
save_wav(f'{OUT}/01_funk_kick.wav', normalize(kick))
print("G01 done")

# Pad 2: Crispy Funk Snare (lots of body + snap)
dur = 0.35
body = sine(220, dur) * env_perc(dur, 0.001, 2.0) * 0.5
snap = noise(dur) * env_perc(dur, 0.001, 2.5) * 0.6
snap = bandpass(snap, 2000, 12000)
wire = noise(dur) * env_perc(dur, 0.01, 0.8) * 0.3
wire = bandpass(wire, 3000, 7000)
snare = body + snap + wire
save_wav(f'{OUT}/02_funk_snare.wav', normalize(snare))
print("G02 done")

# Pad 3: Funky Hi-Hat (16th note friendly, tight)
dur = 0.1
hat = noise(dur) * env_perc(dur, 0.0003, 4.0)
hat = highpass(hat, 7000)
hat = lowpass(hat, 14000)
save_wav(f'{OUT}/03_funk_hat.wav', normalize(hat))
print("G03 done")

# Pad 4: Conga Hit
dur = 0.6
conga = sine(300, dur) * env_perc(dur, 0.001, 1.2)
# Pitch sweep for conga character
tt_arr = t(dur)
pitch_env = np.exp(-tt_arr * 20) * 200 + 300
conga = np.sin(2*np.pi * np.cumsum(pitch_env) / SR)
conga = conga * env_perc(dur, 0.001, 1.0)
conga = saturate(conga, 1.3)
save_wav(f'{OUT}/04_conga.wav', normalize(conga))
print("G04 done")

# Pad 5: Funk Bass (plucky, bright, slap-style)
dur = 1.0
tt_arr = t(dur)
bass = saw(82.4, dur) * 0.6 + square(82.4, dur, 0.3) * 0.4  # E2
# Filter envelope for pluck
n = int(SR*dur)
filtered = np.zeros(n)
fenv = env_perc(dur, 0.001, 0.6)
prev = 0
for i in range(n):
    cutoff = 300 + 4000 * fenv[i]
    rc = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc + 1.0/SR)
    filtered[i] = prev + alpha * (bass[i] - prev)
    prev = filtered[i]
filtered = filtered * env_adsr(dur, 0.003, 0.15, 0.4, 0.2)
filtered = saturate(filtered, 1.8)
save_wav(f'{OUT}/05_funk_bass.wav', normalize(filtered))
print("G05 done")

# Pad 6: Horn Stab (brass-like FM, short punchy)
dur = 0.4
tt_arr = t(dur)
# Brass-like: high mod index, quick decay
carrier = 440  # A4
mod_freq = 440
mod_idx = env_perc(dur, 0.005, 0.8) * 6
mod = mod_idx * np.sin(2*np.pi*mod_freq*tt_arr)
horn = np.sin(2*np.pi*carrier*tt_arr + mod)
# Add harmonics for brass quality
horn += np.sin(2*np.pi*carrier*2*tt_arr + mod*0.5) * 0.3
horn += np.sin(2*np.pi*carrier*3*tt_arr + mod*0.3) * 0.15
horn = horn * env_perc(dur, 0.01, 1.2)
horn = saturate(horn, 1.5)
horn = lowpass(horn, 6000)
save_wav(f'{OUT}/06_horn_stab.wav', normalize(horn))
print("G06 done")

# Pad 7: Horn Phrase (quick brass run, 3 notes)
dur = 0.8
n_total = int(SR*dur)
phrase = np.zeros(n_total)
notes = [(440, 0.0, 0.2), (523, 0.2, 0.2), (587, 0.4, 0.35)]
for freq, start_t, note_dur in notes:
    start = int(start_t * SR)
    nd = int(note_dur * SR)
    tt_note = np.arange(nd) / SR
    mi = env_perc(note_dur, 0.005, 0.8)[:nd] * 5
    m = mi * np.sin(2*np.pi*freq*tt_note)
    note = np.sin(2*np.pi*freq*tt_note + m)
    note += np.sin(2*np.pi*freq*2*tt_note + m*0.5) * 0.25
    note = note * env_perc(note_dur, 0.008, 1.5)[:nd]
    end = min(start+nd, n_total)
    phrase[start:end] += note[:end-start]
phrase = lowpass(phrase, 5000)
phrase = saturate(phrase, 1.5)
save_wav(f'{OUT}/07_horn_phrase.wav', normalize(phrase))
print("G07 done")

# Pad 8: Clavinet-style Keys (bright, percussive)
dur = 1.0
clav = square(330, dur, 0.2)  # E4, narrow pulse
clav += square(660, dur, 0.15) * 0.3  # harmonics
n = int(SR*dur)
filtered = np.zeros(n)
fenv = env_perc(dur, 0.001, 0.5)
prev = 0
for i in range(n):
    cutoff = 500 + 5000 * fenv[i]
    rc = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc + 1.0/SR)
    filtered[i] = prev + alpha * (clav[i] - prev)
    prev = filtered[i]
filtered = filtered * env_adsr(dur, 0.002, 0.1, 0.3, 0.2)
save_wav(f'{OUT}/08_clavinet.wav', normalize(filtered))
print("G08 done")

# Pad 9: Wah Guitar Hit (filtered saw, envelope wah)
dur = 1.5
tt_arr = t(dur)
gtr = saw(196, dur) * 0.6 + square(196, dur, 0.4) * 0.3  # G3
# Wah envelope: sweep up then down
n = int(SR*dur)
filtered = np.zeros(n)
prev = 0
for i in range(n):
    p = i/n
    # Wah sweep: up and down
    cutoff = 400 + 3000 * np.sin(np.pi * p * 2)
    if cutoff < 200: cutoff = 200
    rc = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc + 1.0/SR)
    filtered[i] = prev + alpha * (gtr[i] - prev)
    prev = filtered[i]
filtered = filtered * env_adsr(dur, 0.005, 0.2, 0.5, 0.3)
filtered = saturate(filtered, 2.0)
save_wav(f'{OUT}/09_wah_guitar.wav', normalize(filtered))
print("G09 done")

# Pad 10: Funk Beat Loop (~105bpm)
bpm = 105
beat_dur = (60.0/bpm) * 8
n_total = int(SR * beat_dur)
loop = np.zeros(n_total)
def place(sig, beat_pos):
    start = int((beat_pos * 60.0/bpm) * SR)
    end = min(start + len(sig), n_total)
    if start < n_total:
        loop[start:end] += sig[:end-start]
k = normalize(kick) * 0.9
s = normalize(snare[:int(SR*0.2)]) * 0.7
h = normalize(hat) * 0.4
cg = normalize(conga[:int(SR*0.2)]) * 0.3
# Funky kick pattern
for b in [0, 0.75, 2, 3.5, 4, 4.75, 6, 7.5]: place(k, b)
for b in [2, 6]: place(s, b)
# 16th hat pattern with accents
for b_16 in range(32):
    b = b_16 * 0.5
    vol = 0.45 if b_16 % 2 == 0 else 0.25
    place(normalize(hat)*vol, b)
for b in [1, 3, 5, 7]: place(cg, b)
loop = saturate(loop, 1.2)
save_wav(f'{OUT}/10_funk_loop.wav', normalize(loop))
print("G10 done")

# Pad 11: Scratch FX (simulated vinyl scratch)
dur = 0.8
tt_arr = t(dur)
# Modulated noise to simulate scratch
scratch_freq = 200 + 1500 * np.abs(np.sin(2*np.pi*8*tt_arr))
phase = np.cumsum(scratch_freq / SR) * 2 * np.pi
scratch = np.sin(phase) * noise(dur)
scratch = bandpass(scratch, 300, 6000)
scratch = scratch * env_adsr(dur, 0.01, 0.1, 0.5, 0.1)
scratch = saturate(scratch, 2.0)
save_wav(f'{OUT}/11_scratch.wav', normalize(scratch))
print("G11 done")

# Pad 12: Funk Cowbell
dur = 0.25
cb1 = sine(587, dur) * 0.6
cb2 = sine(845, dur) * 0.4
cowbell = (cb1 + cb2) * env_perc(dur, 0.001, 2.0)
cowbell = saturate(cowbell, 1.3)
save_wav(f'{OUT}/12_cowbell.wav', normalize(cowbell))
print("G12 done")
print("=== BANK G COMPLETE ===")
