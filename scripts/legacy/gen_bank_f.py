# Bank F: Electroclash Jam Kit
import os
exec(open(os.path.join(os.path.dirname(__file__), 'synth_core.py')).read())
OUT = os.path.join(STAGING_BASE, 'F-Electroclash')

# Pad 1: 808 Kick (tight, punchy)
dur = 0.5
pitch_env = np.exp(-np.linspace(0, 35, int(SR*dur)))
kick = np.sin(2*np.pi * np.cumsum(45 + 180*pitch_env) / SR)
kick = kick * env_perc(dur, 0.0005, 0.5)
kick = saturate(kick, 2.0)
save_wav(f'{OUT}/01_808_kick.wav', normalize(kick))
print("F01 done")

# Pad 2: Electronic Clap (sharp, dry)
dur = 0.3
claps = np.zeros(int(SR*dur))
for offset in [0, 0.005, 0.012, 0.018]:
    o = int(offset * SR)
    n = noise(0.02) * env_perc(0.02, 0.0005, 5.0)
    n = bandpass(n, 1500, 9000)
    end = min(o + len(n), len(claps))
    claps[o:end] += n[:end-o]
claps = claps * env_perc(dur, 0.02, 2.0)
claps = saturate(claps, 1.8)
save_wav(f'{OUT}/02_clap.wav', normalize(claps))
print("F02 done")

# Pad 3: Tight Closed Hat
dur = 0.08
hat = noise(dur) * env_perc(dur, 0.0003, 6.0)
hat = highpass(hat, 7000)
save_wav(f'{OUT}/03_tight_hat.wav', normalize(hat))
print("F03 done")

# Pad 4: Cowbell (808-style)
dur = 0.4
cb1 = sine(540, dur) * 0.6
cb2 = sine(800, dur) * 0.4
cowbell = (cb1 + cb2) * env_perc(dur, 0.001, 1.5)
cowbell = bandpass(cowbell, 400, 2000)
cowbell = saturate(cowbell, 1.5)
save_wav(f'{OUT}/04_cowbell.wav', normalize(cowbell))
print("F04 done")

# Pad 5: Distorted Bass (dirty analog-style)
dur = 1.5
bass = square(55, dur, 0.35) * 0.7 + saw(55, dur) * 0.4
bass = lowpass(bass, 600)
bass = bass * env_adsr(dur, 0.005, 0.15, 0.5, 0.3)
bass = saturate(bass, 4.0)
bass = lowpass(bass, 1200)
save_wav(f'{OUT}/05_dirty_bass.wav', normalize(bass))
print("F05 done")

# Pad 6: Analog Lead (square wave, portamento feel)
dur = 2.0
tt_arr = t(dur)
# Pitch slides from C3 to E3
freq_env = 130.8 + (164.8-130.8) * (1 - np.exp(-tt_arr*5))
phase = np.cumsum(freq_env / SR) * 2 * np.pi
lead = np.sign(np.sin(phase)) * 0.8  # square
lead = lowpass(lead, 2500)
lead = lead * env_adsr(dur, 0.02, 0.2, 0.6, 0.4)
lead = saturate(lead, 2.0)
save_wav(f'{OUT}/06_analog_lead.wav', normalize(lead))
print("F06 done")

# Pad 7: Robot Vocal (ring modulated formants)
dur = 1.5
f0 = 180
src = saw(f0, dur)
# Ring modulate with carrier
carrier = sine(300, dur)
robot = src * carrier
robot = bandpass(robot, 200, 4000)
robot = robot * env_adsr(dur, 0.02, 0.2, 0.5, 0.3)
robot = saturate(robot, 2.0)
save_wav(f'{OUT}/07_robot_vocal.wav', normalize(robot))
print("F07 done")

# Pad 8: Synth Stab (harsh, bright)
dur = 0.4
freqs = [261.6, 329.6, 392.0]  # C E G
stab = sum(square(f, dur, 0.3) + saw(f, dur)*0.3 for f in freqs) / len(freqs)
stab = stab * env_perc(dur, 0.001, 1.5)
stab = saturate(stab, 2.5)
stab = lowpass(stab, 5000)
save_wav(f'{OUT}/08_harsh_stab.wav', normalize(stab))
print("F08 done")

# Pad 9: Sweep FX (filter sweep)
dur = 2.5
raw = noise(dur) * 0.5 + saw(100, dur) * 0.5
n = int(SR*dur)
sweep = np.zeros(n)
prev = 0
for i in range(n):
    progress = i / n
    cutoff = 100 + 8000 * progress**2
    rc = 1.0 / (2*np.pi*cutoff)
    alpha = (1.0/SR) / (rc + 1.0/SR)
    sweep[i] = prev + alpha * (raw[i] - prev)
    prev = sweep[i]
sweep = sweep * env_adsr(dur, 0.1, 0.1, 0.8, 0.5)
save_wav(f'{OUT}/09_filter_sweep.wav', normalize(sweep))
print("F09 done")

# Pad 10: Electroclash Beat Loop (~120bpm)
bpm = 120
beat_dur = (60.0/bpm) * 8
n_total = int(SR * beat_dur)
loop = np.zeros(n_total)
def place(sig, beat_pos):
    start = int((beat_pos * 60.0/bpm) * SR)
    end = min(start + len(sig), n_total)
    if start < n_total:
        loop[start:end] += sig[:end-start]
k = normalize(kick[:int(SR*0.2)]) * 0.9
cl = normalize(claps[:int(SR*0.15)]) * 0.65
h = normalize(hat) * 0.45
cb = normalize(cowbell[:int(SR*0.15)]) * 0.3
for b in range(8): place(k, b)
for b in [2, 6]: place(cl, b)
for b in [0.5,1.5,2.5,3.5,4.5,5.5,6.5,7.5]: place(h, b)
for b in [1, 3, 5, 7]: place(cb, b)
loop = saturate(loop, 1.3)
save_wav(f'{OUT}/10_ec_loop.wav', normalize(loop))
print("F10 done")

# Pad 11: Transition Whoosh
dur = 1.5
whoosh = noise(dur)
n = int(SR*dur)
filtered = np.zeros(n)
prev = 0
for i in range(n):
    p = i/n
    # Sweep up then down
    cutoff = 200 + 8000 * np.sin(np.pi * p)
    rc = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc + 1.0/SR)
    filtered[i] = prev + alpha * (whoosh[i] - prev)
    prev = filtered[i]
vol_env = np.sin(np.pi * np.linspace(0, 1, n))
filtered = filtered * vol_env
save_wav(f'{OUT}/11_whoosh.wav', normalize(filtered))
print("F11 done")

# Pad 12: Static Noise Burst
dur = 0.8
static = noise(dur)
static = bitcrush(static, 4)
static = decimate(static, 8)
static = static * env_perc(dur, 0.001, 1.0)
static = lowpass(static, 6000)
save_wav(f'{OUT}/12_static.wav', normalize(static))
print("F12 done")
print("=== BANK F COMPLETE ===")
