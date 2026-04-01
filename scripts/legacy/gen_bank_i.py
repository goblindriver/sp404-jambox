# Bank I: Ambient/Textural Jam Kit
exec(open('/sessions/happy-intelligent-edison/synth_core.py').read())
OUT = '/sessions/happy-intelligent-edison/SP-404A-Samples/_BANK-STAGING/I-AmbientTextural'

# Pad 1: Warm Pad (lush, slow evolving)
dur = 5.0
tt_arr = t(dur)
p1 = sine(220, dur)
p2 = sine(220.7, dur)  # beating
p3 = sine(277.2, dur) * 0.6  # minor third
p4 = sine(329.6, dur) * 0.4  # major third layered
pad = p1 + p2 + p3 + p4
lfo = 0.6 + 0.4 * np.sin(2*np.pi*0.08*tt_arr)
pad = pad * lfo * env_adsr(dur, 1.5, 0.5, 0.7, 2.0)
pad = lowpass(pad, 2500)
pad = chorus(pad, 0.004, 0.6)
save_wav(f'{OUT}/01_warm_pad.wav', normalize(pad))
print("I01 done")

# Pad 2: Deep Drone (fundamental + beating harmonics)
dur = 6.0
tt_arr = t(dur)
d1 = sine(55, dur) * 0.5
d2 = sine(55.2, dur) * 0.4
d3 = sine(82.5, dur) * 0.3  # fifth
d4 = sine(110, dur) * 0.2  # octave
drone = d1 + d2 + d3 + d4
drone = drone * env_adsr(dur, 2.0, 0.5, 0.7, 2.5)
drone = lowpass(drone, 800)
save_wav(f'{OUT}/02_deep_drone.wav', normalize(drone))
print("I02 done")

# Pad 3: Rain/Nature (filtered noise simulation)
dur = 5.0
tt_arr = t(dur)
rain = pink_noise(dur) * 0.5
# Add occasional "droplets" - short bright pings
n = int(SR*dur)
drops = np.zeros(n)
for _ in range(60):
    pos = np.random.randint(0, n - int(SR*0.05))
    freq = np.random.uniform(2000, 6000)
    drop_dur = np.random.uniform(0.01, 0.04)
    drop_n = int(SR*drop_dur)
    drop = np.sin(2*np.pi*freq*np.arange(drop_n)/SR) * np.exp(-np.arange(drop_n)/(SR*0.01))
    end = min(pos+drop_n, n)
    drops[pos:end] += drop[:end-pos] * np.random.uniform(0.05, 0.15)
rain = rain + drops
rain = bandpass(rain, 200, 8000)
rain = rain * env_adsr(dur, 1.0, 0.5, 0.8, 1.5)
save_wav(f'{OUT}/03_rain.wav', normalize(rain))
print("I03 done")

# Pad 4: FM Bell (crystalline, long decay)
dur = 4.0
tt_arr = t(dur)
carrier = 880
mod_idx = 8.0 * np.exp(-tt_arr * 0.8)
bell = np.sin(2*np.pi*carrier*tt_arr + mod_idx * np.sin(2*np.pi*carrier*3.5*tt_arr))
bell = bell * env_perc(dur, 0.002, 0.15)
bell = delay_echo(bell, 0.25, 0.4, 0.4)
save_wav(f'{OUT}/04_bell.wav', normalize(bell))
print("I04 done")

# Pad 5: Atmosphere (wind-like, evolving)
dur = 6.0
tt_arr = t(dur)
wind = pink_noise(dur)
# Slowly modulate filter
n = int(SR*dur)
atmo = np.zeros(n)
prev = 0
for i in range(n):
    progress = i / n
    cutoff = 300 + 1500 * (0.5 + 0.5*np.sin(2*np.pi*0.12*progress*dur))
    rc = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc + 1.0/SR)
    atmo[i] = prev + alpha * (wind[i] - prev)
    prev = atmo[i]
atmo = atmo * env_adsr(dur, 2.0, 0.5, 0.7, 2.5)
save_wav(f'{OUT}/05_atmosphere.wav', normalize(atmo))
print("I05 done")

# Pad 6: Grainy Texture (bitcrushed, lo-fi ambience)
dur = 4.0
tt_arr = t(dur)
tex = sine(330, dur) * 0.3 + pink_noise(dur) * 0.4
tex = lowpass(tex, 2000)
tex = bitcrush(tex, 6)
tex = decimate(tex, 6)
tex = tex * env_adsr(dur, 0.8, 0.3, 0.5, 1.5)
tex = lowpass(tex, 3000)
save_wav(f'{OUT}/06_grainy_texture.wav', normalize(tex))
print("I06 done")

# Pad 7: Reverb Wash (shimmer effect)
dur = 5.0
tt_arr = t(dur)
# Short bright ping into long reverb simulation
ping = sine(1760, 0.05) * env_perc(0.05, 0.001, 5.0) * 0.8
n = int(SR*dur)
wash = np.zeros(n)
wash[:len(ping)] = ping
# Build up reverb with many echoes
for d in np.linspace(0.02, 2.0, 80):
    offset = int(d * SR)
    decay = 0.95 ** (d * 10)
    freq_shift = 1760 * (1 + d * 0.1)  # subtle pitch shift up (shimmer)
    echo_dur = 0.03
    echo_n = int(SR*echo_dur)
    echo = np.sin(2*np.pi*freq_shift*np.arange(echo_n)/SR) * np.exp(-np.arange(echo_n)/(SR*0.02))
    echo = echo * decay * 0.3
    end = min(offset + echo_n, n)
    if offset < n:
        wash[offset:end] += echo[:end-offset]
wash = lowpass(wash, 6000)
wash = wash * env_adsr(dur, 0.01, 0.5, 0.4, 2.0)
save_wav(f'{OUT}/07_shimmer_wash.wav', normalize(wash))
print("I07 done")

# Pad 8: Metallic Chime (tuned percussion, gamelan-like)
dur = 3.0
tt_arr = t(dur)
# Inharmonic partials for metallic quality
freqs = [523, 1320, 1892, 2765, 3410]
chime = np.zeros(int(SR*dur))
for i, f in enumerate(freqs):
    partial = np.sin(2*np.pi*f*tt_arr) * (0.8 ** i)
    decay = np.exp(-tt_arr * (1.0 + i*0.5))
    chime += partial * decay
chime = chime * env_perc(dur, 0.001, 0.15)
chime = delay_echo(chime, 0.3, 0.35, 0.35)
save_wav(f'{OUT}/08_chime.wav', normalize(chime))
print("I08 done")

# Pad 9: Pink Noise Texture (shaped, evolving)
dur = 4.0
tt_arr = t(dur)
pn = pink_noise(dur)
lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.2*tt_arr)
pn = pn * lfo
pn = lowpass(pn, 3000)
pn = pn * env_adsr(dur, 1.0, 0.3, 0.6, 1.5)
save_wav(f'{OUT}/09_pink_texture.wav', normalize(pn))
print("I09 done")

# Pad 10: Evolving Loop (generative-style, phasing tones)
dur = 6.0
tt_arr = t(dur)
# Steve Reich-style phasing
tone1 = sine(440, dur) * 0.3
tone2 = sine(440.3, dur) * 0.3  # very slight detune for phase drift
tone3 = sine(660, dur) * 0.2
tone4 = sine(660.4, dur) * 0.2
evo = tone1 + tone2 + tone3 + tone4
evo = evo * env_adsr(dur, 1.5, 0.5, 0.7, 2.0)
evo = lowpass(evo, 3000)
evo = chorus(evo, 0.005, 0.4)
save_wav(f'{OUT}/10_evolving_loop.wav', normalize(evo))
print("I10 done")

# Pad 11: Sub Bass Drone (deep, felt not heard)
dur = 5.0
tt_arr = t(dur)
sub = sine(35, dur) * 0.7 + sine(70, dur) * 0.3
sub = sub * env_adsr(dur, 1.5, 0.5, 0.8, 2.0)
sub = lowpass(sub, 150)
sub = saturate(sub, 1.5)
save_wav(f'{OUT}/11_sub_drone.wav', normalize(sub))
print("I11 done")

# Pad 12: Glass Pad (bright, ethereal harmonics)
dur = 4.0
tt_arr = t(dur)
# High harmonics with slow attack
glass = np.zeros(int(SR*dur))
for harm in [880, 1320, 1760, 2640, 3520]:
    partial = sine(harm, dur) * (880/harm)
    glass += partial
glass = glass * env_adsr(dur, 1.0, 0.3, 0.5, 1.5)
glass = chorus(glass, 0.003, 0.7)
glass = lowpass(glass, 5000)
save_wav(f'{OUT}/12_glass_pad.wav', normalize(glass))
print("I12 done")
print("=== BANK I COMPLETE ===")
