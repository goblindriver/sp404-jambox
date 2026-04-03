# Bank J: Utility/Transitions/FX
import os
exec(open(os.path.join(os.path.dirname(__file__), 'synth_core.py')).read())
OUT = os.path.join(STAGING_BASE, 'J-UtilityFX')

# Pad 1: Riser (pitch sweep up, dramatic)
dur = 3.0
riser = pitch_sweep(80, 6000, dur)
riser_ns = noise(dur) * env_linear(dur, 0.0, 0.4)
riser_ns = highpass(riser_ns, 1000)
riser = riser * env_linear(dur, 0.1, 1.0) * 0.6 + riser_ns * 0.4
riser = saturate(riser, 1.5)
save_wav(f'{OUT}/01_riser.wav', normalize(riser))
print("J01 done")

# Pad 2: Down Sweep (filter sweep down)
dur = 2.0
raw = noise(dur) * 0.5 + saw(200, dur) * 0.5
n = int(SR*dur)
sweep = np.zeros(n)
prev = 0
for i in range(n):
    progress = i / n
    cutoff = 8000 * (1 - progress)**2 + 100
    rc = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc + 1.0/SR)
    sweep[i] = prev + alpha * (raw[i] - prev)
    prev = sweep[i]
sweep = sweep * env_adsr(dur, 0.01, 0.5, 0.5, 0.5)
save_wav(f'{OUT}/02_down_sweep.wav', normalize(sweep))
print("J02 done")

# Pad 3: Impact Hit (big cinematic hit)
dur = 2.0
tt_arr = t(dur)
# Low boom
boom = sine(40, dur) * env_perc(dur, 0.001, 0.3)
# Noise transient
crash = noise(dur) * env_perc(dur, 0.0005, 0.5) * 0.5
crash = bandpass(crash, 100, 8000)
# Ring mod layer
ring = sine(150, dur) * sine(83, dur) * env_perc(dur, 0.002, 0.4) * 0.3
impact = boom + crash + ring
impact = saturate(impact, 2.0)
save_wav(f'{OUT}/03_impact.wav', normalize(impact))
print("J03 done")

# Pad 4: Reverse Cymbal
dur = 2.5
# Forward cymbal: noise with long decay, heavy high content
cym = noise(dur) * env_perc(dur, 0.001, 0.2)
cym = highpass(cym, 3000)
cym = cym + noise(dur) * env_perc(dur, 0.001, 0.4) * 0.3  # body
cym = bandpass(cym, 1000, 14000)
# Reverse it
rev_cym = cym[::-1].copy()
# Add slight fade in
fade = env_linear(dur, 0.0, 1.0)
rev_cym = rev_cym * fade
save_wav(f'{OUT}/04_reverse_cymbal.wav', normalize(rev_cym))
print("J04 done")

# Pad 5: Vinyl Noise (crackle + surface noise, loopable)
dur = 5.0
surface = pink_noise(dur) * 0.08
surface = bandpass(surface, 300, 5000)
# Crackle pops
n = int(SR*dur)
pops = np.zeros(n)
for _ in range(80):
    pos = np.random.randint(0, n - 100)
    width = np.random.randint(3, 40)
    end = min(pos + width, n)
    pops[pos:end] = np.random.uniform(-0.3, 0.3)
pops = highpass(pops, 500)
vinyl = surface + pops * 0.4
vinyl = lowpass(vinyl, 8000)
save_wav(f'{OUT}/05_vinyl_noise.wav', normalize(vinyl, 0.5))
print("J05 done")

# Pad 6: Tape Hiss
dur = 5.0
hiss = noise(dur)
hiss = bandpass(hiss, 2000, 12000)
hiss = hiss * 0.15
# Add subtle wow/flutter modulation
tt_arr = t(dur)
mod = 1.0 + 0.02 * np.sin(2*np.pi*0.5*tt_arr)
hiss = hiss * mod
save_wav(f'{OUT}/06_tape_hiss.wav', normalize(hiss, 0.4))
print("J06 done")

# Pad 7: Glitch Pattern (rhythmic digital artifacts)
dur = 2.0
n = int(SR*dur)
glitch = np.zeros(n)
step = int(SR * 0.04)  # 40ms slices
for i in range(0, n, step):
    end = min(i + step, n)
    length = end - i
    choice = np.random.randint(0, 5)
    if choice == 0:  # sine burst
        freq = np.random.uniform(200, 4000)
        glitch[i:end] = np.sin(2*np.pi*freq*np.arange(length)/SR) * 0.7
    elif choice == 1:  # noise burst
        glitch[i:end] = noise(length/SR)[:length] * 0.5
    elif choice == 2:  # silence
        pass
    elif choice == 3:  # bitcrushed tone
        freq = np.random.uniform(100, 2000)
        sig = np.sin(2*np.pi*freq*np.arange(length)/SR)
        glitch[i:end] = np.round(sig * 4) / 4 * 0.6
    elif choice == 4:  # ring mod burst
        f1 = np.random.uniform(300, 1500)
        f2 = np.random.uniform(500, 3000)
        glitch[i:end] = (np.sin(2*np.pi*f1*np.arange(length)/SR) * 
                          np.sin(2*np.pi*f2*np.arange(length)/SR)) * 0.5
    # Apply window to each slice
    window = np.hanning(length)
    glitch[i:end] *= window
save_wav(f'{OUT}/07_glitch_pattern.wav', normalize(glitch))
print("J07 done")

# Pad 8: Sub Drop (808 style, pitch drops)
dur = 1.5
tt_arr = t(dur)
pitch_env = 200 * np.exp(-tt_arr * 3) + 30
phase = np.cumsum(pitch_env / SR) * 2 * np.pi
drop = np.sin(phase)
drop = drop * env_perc(dur, 0.001, 0.25)
drop = saturate(drop, 2.0)
save_wav(f'{OUT}/08_sub_drop.wav', normalize(drop))
print("J08 done")

# Pad 9: White Noise Burst (short, useful for fills)
dur = 0.5
burst = noise(dur) * env_perc(dur, 0.001, 0.8)
save_wav(f'{OUT}/09_noise_burst.wav', normalize(burst))
print("J09 done")

# Pad 10: Transition Swoosh (stereo feel, panning sim)
dur = 1.5
tt_arr = t(dur)
swish = noise(dur)
n = int(SR*dur)
filtered = np.zeros(n)
prev = 0
for i in range(n):
    p = i/n
    cutoff = 200 + 10000 * np.sin(np.pi * p)
    rc = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc + 1.0/SR)
    filtered[i] = prev + alpha * (swish[i] - prev)
    prev = filtered[i]
vol = np.sin(np.pi * np.linspace(0, 1, n))
swoosh = filtered * vol
save_wav(f'{OUT}/10_swoosh.wav', normalize(swoosh))
print("J10 done")

# Pad 11: Click/Blip (short digital click, good for rhythm)
dur = 0.05
blip = sine(1000, dur) * env_perc(dur, 0.0001, 5.0)
blip = blip + noise(dur) * env_perc(dur, 0.0001, 8.0) * 0.3
save_wav(f'{OUT}/11_click_blip.wav', normalize(blip))
print("J11 done")

# Pad 12: Room Tone (subtle ambience, good for layering)
dur = 6.0
tt_arr = t(dur)
room = pink_noise(dur) * 0.1
room = lowpass(room, 2000)
# Add very subtle resonances (room modes)
room += sine(120, dur) * 0.02
room += sine(240, dur) * 0.01
room += sine(360, dur) * 0.005
room = room * env_adsr(dur, 1.0, 0.5, 0.8, 2.0)
save_wav(f'{OUT}/12_room_tone.wav', normalize(room, 0.3))
print("J12 done")
print("=== BANK J COMPLETE ===")
