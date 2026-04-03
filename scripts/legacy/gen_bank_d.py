# Bank D: Witch House Jam Kit
import os
exec(open(os.path.join(os.path.dirname(__file__), 'synth_core.py')).read())
OUT = os.path.join(STAGING_BASE, 'D-WitchHouse')

# Pad 1: Deep 808-style Kick (long, subby, distorted)
dur = 1.2
pitch_env = np.exp(-np.linspace(0, 15, int(SR*dur)))
kick = np.sin(2*np.pi * np.cumsum(35 + 120*pitch_env) / SR)
kick = kick * env_perc(dur, 0.001, 0.2)
kick = saturate(kick, 3.0)
kick = lowpass(kick, 2000)
save_wav(f'{OUT}/01_808_kick.wav', normalize(kick))
print("D01 kick done")

# Pad 2: Reverbed Dark Clap
dur = 1.0
clap_core = noise(0.05) * env_perc(0.05, 0.001, 3.0)
clap_core = bandpass(clap_core, 800, 5000)
# Pad to full length
clap = np.zeros(int(SR*dur))
clap[:len(clap_core)] = clap_core
# Fake reverb with delays
for d in [0.03, 0.07, 0.12, 0.18, 0.25, 0.35, 0.5]:
    offset = int(d * SR)
    decay = 0.5 ** (d / 0.15)
    end = min(offset + len(clap_core), int(SR*dur))
    clap[offset:end] += clap_core[:end-offset] * decay * 0.6
clap = lowpass(clap, 4000)
clap = saturate(clap, 2.0)
save_wav(f'{OUT}/02_dark_clap.wav', normalize(clap))
print("D02 dark clap done")

# Pad 3: Metallic Hat (ring mod + noise)
dur = 0.3
n1 = noise(dur) * env_perc(dur, 0.0005, 3.0)
ring = sine(7500, dur) * sine(5300, dur)  # ring mod
hat = n1 * 0.6 + ring * env_perc(dur, 0.001, 4.0) * 0.5
hat = highpass(hat, 4000)
hat = saturate(hat, 2.0)
save_wav(f'{OUT}/03_metal_hat.wav', normalize(hat))
print("D03 metal hat done")

# Pad 4: Industrial Percussion
dur = 0.5
metal = fm_synth(180, 570, 8, dur) * env_perc(dur, 0.001, 1.5)
click = noise(dur) * env_perc(dur, 0.0005, 6.0) * 0.4
ind = metal + click
ind = saturate(ind, 3.0)
ind = bandpass(ind, 200, 8000)
save_wav(f'{OUT}/04_industrial_perc.wav', normalize(ind))
print("D04 industrial perc done")

# Pad 5: Sub Bass (deep sine, menacing)
dur = 2.0
tt_arr = t(dur)
sub = sine(40, dur) + sine(80, dur) * 0.3
sub = sub * env_adsr(dur, 0.05, 0.3, 0.7, 0.5)
sub = saturate(sub, 2.0)
sub = lowpass(sub, 300)
save_wav(f'{OUT}/05_sub_bass.wav', normalize(sub))
print("D05 sub bass done")

# Pad 6: Dark Synth Lead (detuned squares, heavy filter)
dur = 2.0
tt_arr = t(dur)
s1 = square(196, dur, 0.3)  # G3
s2 = square(196.8, dur, 0.4)  # detuned
lead = (s1 + s2) / 2
# Slow filter sweep down
n = int(SR*dur)
filtered = np.zeros(n)
for i in range(n):
    cutoff = 3000 * np.exp(-i/(SR*0.5)) + 200
    rc = 1.0 / (2*np.pi*cutoff)
    alpha = (1.0/SR) / (rc + 1.0/SR)
    if i == 0:
        filtered[i] = alpha * lead[i]
    else:
        filtered[i] = filtered[i-1] + alpha * (lead[i] - filtered[i-1])
lead = filtered * env_adsr(dur, 0.05, 0.3, 0.6, 0.5)
lead = saturate(lead, 2.5)
save_wav(f'{OUT}/06_dark_synth.wav', normalize(lead))
print("D06 dark synth done")

# Pad 7: Eerie Pad (slow, dissonant, evolving)
dur = 4.0
tt_arr = t(dur)
p1 = sine(220, dur)
p2 = sine(233, dur)  # dissonant
p3 = sine(311, dur)  # tritone area
mod = 0.5 * np.sin(2*np.pi*0.15*tt_arr)  # slow LFO
pad = (p1 + p2*0.7 + p3*0.5) * (0.5 + 0.5*mod)
pad = pad * env_adsr(dur, 1.0, 0.5, 0.6, 1.5)
pad = lowpass(pad, 1500)
pad = delay_echo(pad, 0.3, 0.4, 0.4)
save_wav(f'{OUT}/07_eerie_pad.wav', normalize(pad))
print("D07 eerie pad done")

# Pad 8: Witch Vocal (dark formant synthesis)
dur = 1.5
f0 = 150
tt_arr = t(dur)
# Dark "ooh" formants
src = saw(f0, dur) * 0.5 + square(f0, dur, 0.3) * 0.3
formant1 = bandpass(src, 300, 500)  # dark vowel
formant2 = bandpass(src, 800, 1200) * 0.4
vox = formant1 + formant2
vox = vox * env_adsr(dur, 0.1, 0.2, 0.5, 0.5)
vox = saturate(vox, 2.0)
vox = delay_echo(vox, 0.25, 0.5, 0.5)
vox = lowpass(vox, 3000)
save_wav(f'{OUT}/08_witch_vocal.wav', normalize(vox))
print("D08 witch vocal done")

# Pad 9: Riser FX (dark sweep up)
dur = 3.0
riser = pitch_sweep(60, 4000, dur) * env_adsr(dur, 0.5, 0.1, 0.8, 0.5)
riser_noise = noise(dur) * env_linear(dur, 0.0, 0.5)
riser_noise = highpass(riser_noise, 2000)
riser = riser * 0.6 + riser_noise * 0.4
riser = saturate(riser, 2.0)
save_wav(f'{OUT}/09_dark_riser.wav', normalize(riser))
print("D09 dark riser done")

# Pad 10: Heavy Beat Loop (~70bpm, dragging)
bpm = 70
beat_dur = (60.0/bpm) * 8
n_total = int(SR * beat_dur)
loop = np.zeros(n_total)
def place(sig, beat_pos):
    start = int((beat_pos * 60.0/bpm) * SR)
    end = min(start + len(sig), n_total)
    if start < n_total:
        loop[start:end] += sig[:end-start]
k = normalize(kick[:int(SR*0.5)]) * 0.9
c = normalize(clap[:int(SR*0.4)]) * 0.6
h = normalize(hat[:int(SR*0.15)]) * 0.35
for b in [0, 1.5, 4, 5.5]:
    place(k, b)
for b in [2, 6]:
    place(c, b)
for b in [0, 1, 2, 3, 4, 5, 6, 7]:
    place(h, b)
loop = saturate(loop, 2.0)
loop = lowpass(loop, 6000)
save_wav(f'{OUT}/10_heavy_loop.wav', normalize(loop))
print("D10 heavy loop done")

# Pad 11: Reverse Sweep
dur = 2.5
sweep = pitch_sweep(8000, 80, dur) * env_linear(dur, 0.0, 1.0)
sweep = sweep + noise(dur) * env_linear(dur, 0.0, 0.3)
sweep = lowpass(sweep, 10000)
sweep = saturate(sweep, 1.5)
save_wav(f'{OUT}/11_reverse_sweep.wav', normalize(sweep))
print("D11 reverse sweep done")

# Pad 12: Dark Noise Texture
dur = 4.0
tt_arr = t(dur)
pn = pink_noise(dur)
pn = lowpass(pn, 800)
rumble = sine(30, dur) * 0.3
tex = pn * 0.5 + rumble
tex = tex * env_adsr(dur, 1.0, 0.5, 0.6, 1.5)
tex = saturate(tex, 2.0)
save_wav(f'{OUT}/12_dark_texture.wav', normalize(tex))
print("D12 dark texture done")
print("=== BANK D COMPLETE ===")
