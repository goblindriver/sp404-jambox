# Bank H: IDM Jam Kit
import os
exec(open(os.path.join(os.path.dirname(__file__), 'synth_core.py')).read())
OUT = os.path.join(STAGING_BASE, 'H-IDM')

# Pad 1: Glitchy Kick (processed, weird pitch)
dur = 0.5
pitch_env = np.exp(-np.linspace(0, 25, int(SR*dur)))
# Add glitch: rapid pitch flutter
tt_arr = t(dur)
flutter = 30 * np.sin(2*np.pi*45*tt_arr) * np.exp(-tt_arr*10)
kick = np.sin(2*np.pi * np.cumsum(50 + 180*pitch_env + flutter[:len(pitch_env)]) / SR)
kick = kick * env_perc(dur, 0.0005, 0.4)
kick = saturate(kick, 2.5)
# Bitcrush the tail
n = int(SR*dur)
for i in range(n//3, n):
    kick[i] = np.round(kick[i] * 16) / 16
save_wav(f'{OUT}/01_glitch_kick.wav', normalize(kick))
print("H01 done")

# Pad 2: Broken Snare (layered, mangled)
dur = 0.4
body = sine(180, dur) * env_perc(dur, 0.001, 2.0) * 0.4
ns = noise(dur) * env_perc(dur, 0.001, 1.5) * 0.6
ns = bandpass(ns, 1500, 10000)
# Ring modulate for weirdness
ring = sine(1200, dur) * sine(780, dur)
ring = ring * env_perc(dur, 0.002, 3.0) * 0.3
snare = body + ns + ring
snare = saturate(snare, 2.0)
save_wav(f'{OUT}/02_broken_snare.wav', normalize(snare))
print("H02 done")

# Pad 3: Metallic Hat (ring modulated, complex)
dur = 0.25
h1 = sine(6731, dur) * sine(4523, dur)
h2 = sine(8234, dur) * sine(3127, dur)
hat = (h1 + h2*0.7) * env_perc(dur, 0.0005, 3.0)
hat = hat + noise(dur) * env_perc(dur, 0.0005, 5.0) * 0.2
hat = highpass(hat, 3000)
hat = saturate(hat, 1.5)
save_wav(f'{OUT}/03_metal_hat.wav', normalize(hat))
print("H03 done")

# Pad 4: Glitch Percussion (granular-style, stuttered)
dur = 0.8
# Create a tone then chop it up
base = fm_synth(400, 730, 5, dur) * env_perc(dur, 0.001, 0.8)
n = int(SR*dur)
glitch = np.zeros(n)
# Random grain placement
grain_size = int(SR * 0.015)
for i in range(0, n - grain_size, grain_size * 2):
    src_pos = np.random.randint(0, max(1, n - grain_size))
    length = min(grain_size, n - i, n - src_pos)
    window = np.hanning(length)
    glitch[i:i+length] = base[src_pos:src_pos+length] * window
glitch = saturate(glitch, 2.0)
save_wav(f'{OUT}/04_glitch_perc.wav', normalize(glitch))
print("H04 done")

# Pad 5: Morphing Bass (modulated, evolving)
dur = 2.0
tt_arr = t(dur)
# Bass with FM that evolves
mod_env = np.sin(2*np.pi*0.5*tt_arr) * 3 + 2  # oscillating mod index
bass = np.sin(2*np.pi*55*tt_arr + mod_env * np.sin(2*np.pi*55*tt_arr))
bass += saw(55, dur) * 0.3
bass = lowpass(bass, 1500)
bass = bass * env_adsr(dur, 0.005, 0.2, 0.6, 0.4)
bass = saturate(bass, 2.0)
save_wav(f'{OUT}/05_morph_bass.wav', normalize(bass))
print("H05 done")

# Pad 6: Complex FM Synth (evolving, bell-like but twisted)
dur = 2.5
tt_arr = t(dur)
carrier = 440
mod1 = 7.0 * np.exp(-tt_arr*1.5) * np.sin(2*np.pi*440*1.41*tt_arr)
mod2 = 3.0 * np.sin(2*np.pi*440*2.76*tt_arr + mod1)
sig = np.sin(2*np.pi*carrier*tt_arr + mod2)
sig = sig * env_adsr(dur, 0.01, 0.5, 0.3, 0.8)
sig = delay_echo(sig, 0.17, 0.35, 0.35)
save_wav(f'{OUT}/06_complex_fm.wav', normalize(sig))
print("H06 done")

# Pad 7: Digital Texture (harsh, evolving noise)
dur = 3.0
tt_arr = t(dur)
n = int(SR*dur)
tex = np.zeros(n)
# Layered ring-modulated noise bands
for freq in [1200, 2800, 5600, 7300]:
    band = noise(dur)
    band = bandpass(band, freq-200, freq+200)
    mod = sine(freq * 0.13, dur)
    tex += band * mod * 0.3
tex = tex * env_adsr(dur, 0.5, 0.3, 0.5, 1.0)
tex = saturate(tex, 1.5)
save_wav(f'{OUT}/07_digital_texture.wav', normalize(tex))
print("H07 done")

# Pad 8: Granular-style Pad
dur = 4.0
tt_arr = t(dur)
n = int(SR*dur)
pad = np.zeros(n)
base_tone = sine(220, dur) + sine(330, dur)*0.5 + sine(440, dur)*0.3
grain_size = int(SR * 0.05)
window = np.hanning(grain_size)
for i in range(0, n - grain_size, int(grain_size * 0.3)):
    # Read from slightly random position with slight pitch shift
    src_pos = int(i + np.random.uniform(-SR*0.1, SR*0.1))
    src_pos = max(0, min(src_pos, n - grain_size))
    grain = base_tone[src_pos:src_pos+grain_size] * window
    end = min(i + grain_size, n)
    pad[i:end] += grain[:end-i]
pad = pad * env_adsr(dur, 0.8, 0.3, 0.5, 1.5)
pad = lowpass(pad, 4000)
pad = delay_echo(pad, 0.2, 0.3, 0.3)
save_wav(f'{OUT}/08_granular_pad.wav', normalize(pad))
print("H08 done")

# Pad 9: Stutter FX (rhythmic glitch pattern)
dur = 1.5
tt_arr = t(dur)
n = int(SR*dur)
base = saw(330, dur) * 0.5 + noise(dur) * 0.3
# Apply rhythmic gate
gate = np.zeros(n)
step = int(SR * 0.05)  # 50ms steps
for i in range(0, n, step):
    if np.random.random() > 0.35:  # 65% chance of gate open
        end = min(i + int(step * np.random.uniform(0.3, 0.9)), n)
        gate[i:end] = 1.0
stutter = base * gate
stutter = saturate(stutter, 2.0)
stutter = bandpass(stutter, 200, 8000)
save_wav(f'{OUT}/09_stutter_fx.wav', normalize(stutter))
print("H09 done")

# Pad 10: IDM Beat Loop (~140bpm, complex rhythm)
bpm = 140
beat_dur = (60.0/bpm) * 8
n_total = int(SR * beat_dur)
loop = np.zeros(n_total)
def place(sig, beat_pos):
    start = int((beat_pos * 60.0/bpm) * SR)
    end = min(start + len(sig), n_total)
    if start < n_total:
        loop[start:end] += sig[:end-start]
k = normalize(kick[:int(SR*0.2)]) * 0.85
s = normalize(snare[:int(SR*0.15)]) * 0.6
h = normalize(hat[:int(SR*0.1)]) * 0.4
gp = normalize(glitch[:int(SR*0.1)]) * 0.35
# Irregular kick pattern
for b in [0, 1.25, 2.5, 3, 4.5, 5.75, 7]: place(k, b)
# Off-kilter snare
for b in [1.75, 3.5, 5.25, 7.5]: place(s, b)
# Scattered hats
for b in [0, 0.5, 1, 1.5, 2.25, 3.25, 3.75, 4, 4.75, 5.5, 6, 6.5, 7, 7.25]: place(h, b)
# Glitch hits
for b in [0.25, 2.75, 4.25, 6.75]: place(gp, b)
loop = saturate(loop, 1.3)
save_wav(f'{OUT}/10_idm_loop.wav', normalize(loop))
print("H10 done")

# Pad 11: Buffer Override FX (simulated buffer repeat)
dur = 2.0
src = fm_synth(300, 500, 4, dur) * env_adsr(dur, 0.01, 0.2, 0.6, 0.5)
n = int(SR*dur)
buffer_fx = np.zeros(n)
buf_size = int(SR * 0.08)  # 80ms buffer
pos = 0
while pos < n:
    # Grab a buffer chunk
    chunk_end = min(pos + buf_size, n)
    chunk = src[pos:chunk_end]
    # Repeat it a random number of times
    repeats = np.random.choice([1, 2, 3, 4, 6])
    for r in range(repeats):
        start = pos + r * len(chunk)
        end = min(start + len(chunk), n)
        if start < n:
            buffer_fx[start:end] = chunk[:end-start]
    pos += len(chunk) * repeats
    # Occasionally change buffer size
    buf_size = int(SR * np.random.choice([0.04, 0.06, 0.08, 0.12, 0.16]))
buffer_fx = saturate(buffer_fx, 1.5)
save_wav(f'{OUT}/11_buffer_fx.wav', normalize(buffer_fx))
print("H11 done")

# Pad 12: Ambient Drone Pad (slowly evolving)
dur = 5.0
tt_arr = t(dur)
d1 = sine(110, dur) * 0.4
d2 = sine(110.3, dur) * 0.3  # beating
d3 = sine(165, dur) * 0.2  # fifth
lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.1*tt_arr)
drone = (d1 + d2 + d3) * lfo
drone = drone * env_adsr(dur, 1.5, 0.5, 0.6, 2.0)
drone = lowpass(drone, 2000)
drone = delay_echo(drone, 0.3, 0.4, 0.4)
save_wav(f'{OUT}/12_ambient_drone.wav', normalize(drone))
print("H12 done")
print("=== BANK H COMPLETE ===")
