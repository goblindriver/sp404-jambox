import os
exec(open(os.path.join(os.path.dirname(__file__), 'loop_core.py')).read())

# ============================================
# BANK C: LO-FI HIP-HOP LOOPS (88bpm)
# ============================================
OUT_C = os.path.join(STAGING_BASE, 'C-LofiHipHop')
BPM = 88

# --- Make quick drum sounds for loops ---
def lofi_kick(dur=0.3):
    pe = np.exp(-np.linspace(0, 30, int(SR*dur)))
    k = np.sin(2*np.pi * np.cumsum(55 + 150*pe) / SR)
    k = k * env_perc(dur, 0.001, 0.4)
    return normalize(lowpass(bitcrush(k, 12), 4000))

def lofi_snare(dur=0.25):
    b = sine(200, dur) * env_perc(dur, 0.001, 1.5)
    n = bandpass(noise(dur) * env_perc(dur, 0.001, 1.0), 1000, 6000)
    return normalize(lowpass(bitcrush(b*0.5 + n*0.6, 12), 5000))

def lofi_hat(dur=0.08):
    h = highpass(noise(dur) * env_perc(dur, 0.0005, 5.0), 6000)
    return normalize(bitcrush(h, 11))

def lofi_shaker(dur=0.1):
    s = bandpass(noise(dur) * env_perc(dur, 0.005, 3.0), 3000, 10000)
    return normalize(s)

k = lofi_kick()
s = lofi_snare()
h = lofi_hat()
sh = lofi_shaker()

# Pad 5: Bass Line Loop (Cm pentatonic, laid back)
bass_notes = [
    (0, NOTE['C2'], 1.5, 0.9, 'saw'),
    (2, NOTE['Eb2'], 1.0, 0.8, 'saw'),
    (3.5, NOTE['G2'], 0.5, 0.7, 'saw'),
    (4, NOTE['C2'], 1.5, 0.9, 'saw'),
    (6, NOTE['Bb2']*0.5, 1.0, 0.85, 'saw'),  # Bb1
    (7, NOTE['G2']*0.5, 0.75, 0.7, 'saw'),   # G1
]
bass = make_bass_loop(BPM, 2, bass_notes)
bass = lowpass(bass, 600)
bass = saturate(bass, 1.5)
bass = bitcrush(bass, 12)
n = bar_samples(BPM, 2)
save_wav(f'{OUT_C}/05_bass_loop.wav', normalize(bass[:n]))
print("C05 bass loop done")

# Pad 6: Rhodes Keys Loop (jazzy Cm7 changes)
keys_notes = [
    # Cm7 chord hits
    (0, NOTE['C4'], 1.5, 0.7),
    (0, NOTE['Eb4'], 1.5, 0.5),
    (0, NOTE['G4'], 1.5, 0.5),
    (0, NOTE['Bb4'], 1.5, 0.4),
    # Ab maj
    (2, NOTE['Ab3'], 1.5, 0.7),
    (2, NOTE['C4'], 1.5, 0.5),
    (2, NOTE['Eb4'], 1.5, 0.5),
    # Fm
    (4, NOTE['F3'], 1.0, 0.6),
    (4, NOTE['Ab3'], 1.0, 0.5),
    (4, NOTE['C4'], 1.0, 0.5),
    # G7
    (5.5, NOTE['G3'], 1.5, 0.7),
    (5.5, NOTE['B3'], 1.5, 0.5),
    (5.5, NOTE['D4'], 1.5, 0.5),
    (5.5, NOTE['F4'], 1.5, 0.4),
    # Little fill
    (7, NOTE['Eb4'], 0.5, 0.5),
    (7.5, NOTE['D4'], 0.5, 0.4),
]
keys = make_melodic_loop(BPM, 2, keys_notes, wave='fm', filter_cutoff=3000, attack=0.01, release=0.15)
keys = bitcrush(keys, 13)
keys = lowpass(keys, 3500)
save_wav(f'{OUT_C}/06_keys_loop.wav', normalize(keys[:n]))
print("C06 keys loop done")

# Pad 7: Warm Pad Loop (Cm -> Ab, slowly evolving)
pad_chords = [
    (0, [NOTE['C3'], NOTE['Eb3'], NOTE['G3'], NOTE['Bb3']], 4, 0.7),  # Cm7
    (4, [NOTE['Ab3']*0.5, NOTE['C3'], NOTE['Eb3']], 4, 0.7),  # Ab
]
pad = make_pad_loop(BPM, 2, pad_chords, wave='saw', detune=0.5)
pad = lowpass(pad, 1500)
pad = chorus(pad, 0.003, 0.8)
pad = bitcrush(pad, 13)
save_wav(f'{OUT_C}/07_pad_loop.wav', normalize(pad[:n]))
print("C07 pad loop done")

# Pad 8: Melodic Riff Loop (lo-fi melody, pentatonic)
mel_notes = [
    (0, NOTE['C4'], 0.75, 0.7),
    (1, NOTE['Eb4'], 0.5, 0.6),
    (1.75, NOTE['G4'], 0.75, 0.65),
    (2.5, NOTE['Eb4'], 0.5, 0.6),
    (3.5, NOTE['C4'], 0.5, 0.55),
    (4, NOTE['Bb3'], 1.0, 0.7),
    (5.5, NOTE['G3'], 0.75, 0.6),
    (6.5, NOTE['Ab3'], 0.5, 0.5),
    (7, NOTE['G3'], 0.75, 0.6),
]
mel = make_melodic_loop(BPM, 2, mel_notes, wave='fm', filter_cutoff=2500, attack=0.02, release=0.1, detune=0)
mel = bitcrush(mel, 11)
mel = delay_echo(mel, 0.25, 0.3, 0.3)
save_wav(f'{OUT_C}/08_melody_loop.wav', normalize(mel[:n]))
print("C08 melody loop done")

# Pad 9: Main Drum Loop (boom bap, swung)
kick_pat = [(0, 0.9), (1.75, 0.7), (4, 0.9), (4.75, 0.6), (6.5, 0.7)]
snare_pat = [(2, 0.8), (6, 0.8)]
hat_pat = [(i*0.5, 0.5 if i%2==0 else 0.3) for i in range(16)]
drum1 = make_drum_loop(BPM, 2, kick_pat, snare_pat, hat_pat, 
                        kick_sound=k, snare_sound=s, hat_sound=h, swing=0.15)
drum1 = bitcrush(drum1, 12)
drum1 = lowpass(drum1, 8000)
save_wav(f'{OUT_C}/09_drum_loop1.wav', normalize(drum1[:n]))
print("C09 drum loop 1 done")

# Pad 10: Drum Loop Variation (more ghost notes, busier hat)
kick_pat2 = [(0, 0.9), (0.75, 0.4), (2.5, 0.6), (4, 0.9), (5.5, 0.5), (7, 0.6)]
snare_pat2 = [(2, 0.8), (5.75, 0.4), (6, 0.8), (7.5, 0.35)]
hat_pat2 = [(i*0.25, 0.4 if i%4==0 else 0.2) for i in range(32)]
drum2 = make_drum_loop(BPM, 2, kick_pat2, snare_pat2, hat_pat2,
                        kick_sound=k, snare_sound=s, hat_sound=h, swing=0.15)
drum2 = bitcrush(drum2, 12)
save_wav(f'{OUT_C}/10_drum_loop2.wav', normalize(drum2[:n]))
print("C10 drum loop 2 done")

# Pad 11: Vinyl Texture Loop (crackle + warmth, loopable)
tex_dur = n / SR
crackle = noise(tex_dur) * 0.04
nn = int(SR*tex_dur)
pops = np.zeros(nn)
for _ in range(50):
    pos = np.random.randint(0, nn-100)
    w = np.random.randint(5, 40)
    end = min(pos+w, nn)
    pops[pos:end] += np.random.uniform(-0.2, 0.2)
vinyl = crackle + pops * 0.3
vinyl = bandpass(vinyl, 300, 5000)
# Add warm hum
vinyl += sine(60, tex_dur) * 0.02
vinyl = bitcrush(vinyl, 8)
save_wav(f'{OUT_C}/11_vinyl_loop.wav', normalize(vinyl[:n], 0.5))
print("C11 vinyl loop done")

# Pad 12: Ambient Pad Texture Loop (dreamy, long)
tt_arr = np.arange(n) / SR
amb = sine(220, n/SR) * 0.3 + sine(330, n/SR) * 0.2 + sine(440, n/SR) * 0.15
lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.15*tt_arr)
amb = amb * lfo
amb = lowpass(amb, 1500)
amb = chorus(amb, 0.005, 0.5)
amb = delay_echo(amb, 0.3, 0.4, 0.4)
amb = bitcrush(amb, 12)
save_wav(f'{OUT_C}/12_ambient_loop.wav', normalize(amb[:n]))
print("C12 ambient loop done")

print("=== BANK C LOOPS COMPLETE ===\n")

# ============================================
# BANK D: WITCH HOUSE LOOPS (70bpm)
# ============================================
OUT_D = os.path.join(STAGING_BASE, 'D-WitchHouse')
BPM = 70
n = bar_samples(BPM, 2)

# Dark drum sounds
def dark_kick(dur=0.5):
    pe = np.exp(-np.linspace(0, 15, int(SR*dur)))
    k = np.sin(2*np.pi * np.cumsum(35 + 120*pe) / SR)
    k = k * env_perc(dur, 0.001, 0.2)
    return normalize(saturate(k, 3.0))

def dark_clap(dur=0.4):
    cl = np.zeros(int(SR*dur))
    for offset in [0, 0.01, 0.02]:
        o = int(offset*SR)
        nn = noise(0.03) * env_perc(0.03, 0.001, 3.0)
        nn = bandpass(nn, 800, 5000)
        end = min(o+len(nn), len(cl))
        cl[o:end] += nn[:end-o]
    cl += noise(dur) * env_perc(dur, 0.02, 0.5) * 0.4
    cl = lowpass(cl, 3000)
    return normalize(saturate(cl, 2.0))

def dark_hat(dur=0.2):
    h = sine(7500, dur) * sine(5300, dur) * env_perc(dur, 0.0005, 3.0)
    h += noise(dur) * env_perc(dur, 0.0005, 5.0) * 0.2
    h = highpass(h, 4000)
    return normalize(saturate(h, 2.0))

dk = dark_kick()
dc = dark_clap()
dh = dark_hat()

# Pad 5: Sub Bass Loop (slow, menacing, Cm)
bass_notes = [
    (0, NOTE['C2']*0.5, 3.0, 0.9, 'sine'),   # C1
    (4, NOTE['Eb2']*0.5, 2.0, 0.8, 'sine'),  # Eb1
    (6.5, NOTE['D2']*0.5, 1.5, 0.7, 'sine'), # D1
]
bass = make_bass_loop(BPM, 2, bass_notes)
bass = lowpass(bass, 200)
bass = saturate(bass, 2.5)
save_wav(f'{OUT_D}/05_sub_bass_loop.wav', normalize(bass[:n]))
print("D05 sub bass loop done")

# Pad 6: Dark Synth Riff Loop (minor, creepy)
riff_notes = [
    (0, NOTE['C3'], 1.0, 0.8),
    (1.5, NOTE['Eb3'], 0.5, 0.6),
    (2, NOTE['D3'], 1.5, 0.7),
    (4, NOTE['C3'], 0.75, 0.7),
    (5, NOTE['Bb2'], 1.5, 0.75),
    (7, NOTE['Ab2'], 0.75, 0.6),
]
riff = make_melodic_loop(BPM, 2, riff_notes, wave='square', filter_cutoff=1500, attack=0.05, release=0.2, detune=1.0)
riff = saturate(riff, 2.5)
riff = lowpass(riff, 2000)
save_wav(f'{OUT_D}/06_dark_riff_loop.wav', normalize(riff[:n]))
print("D06 dark riff loop done")

# Pad 7: Eerie Pad Loop (dissonant, shifting)
pad_chords = [
    (0, [NOTE['C3'], NOTE['Eb3'], NOTE['Gb3']], 4, 0.7),   # Cdim
    (4, [NOTE['Bb2'], NOTE['Db3'], NOTE['E3']], 4, 0.65),  # dark cluster
]
pad = make_pad_loop(BPM, 2, pad_chords, wave='saw', detune=1.5)
pad = lowpass(pad, 1000)
pad = delay_echo(pad, 0.4, 0.5, 0.5)
pad = saturate(pad, 2.0)
save_wav(f'{OUT_D}/07_eerie_pad_loop.wav', normalize(pad[:n]))
print("D07 eerie pad loop done")

# Pad 8: Dark Vocal/Drone Loop
tt_arr = np.arange(n) / SR
f0 = 120
src = saw(f0, n/SR) * 0.5 + square(f0, n/SR, 0.3) * 0.3
formant1 = bandpass(src[:n], 300, 500)
formant2 = bandpass(src[:n], 800, 1200) * 0.4
vox = formant1 + formant2
lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.2*tt_arr)
vox = vox * lfo
vox = saturate(vox, 2.0)
vox = delay_echo(vox, 0.3, 0.5, 0.5)
save_wav(f'{OUT_D}/08_dark_vocal_loop.wav', normalize(vox[:n]))
print("D08 dark vocal loop done")

# Pad 9: Heavy Drum Loop 1 (half-time, menacing)
kick_pat = [(0, 0.95), (3.5, 0.7), (4, 0.9), (7.5, 0.6)]
clap_pat = [(4, 0.8)]
hat_pat = [(i, 0.4) for i in range(8)]
drum1 = make_drum_loop(BPM, 2, kick_pat, clap_pat, hat_pat,
                        kick_sound=dk, snare_sound=dc, hat_sound=dh)
drum1 = saturate(drum1, 2.0)
drum1 = lowpass(drum1, 6000)
save_wav(f'{OUT_D}/09_drum_loop1.wav', normalize(drum1[:n]))
print("D09 drum loop 1 done")

# Pad 10: Drum Loop 2 (trap-influenced, sparse)
kick_pat2 = [(0, 0.95), (0.75, 0.5), (4, 0.9), (5, 0.6), (6.75, 0.5)]
clap_pat2 = [(2, 0.7), (6, 0.7)]
hat_pat2 = [(i*0.25, 0.3 if np.random.random()>0.3 else 0.0) for i in range(32)]
hat_pat2 = [(p, v) for p, v in hat_pat2 if v > 0]
drum2 = make_drum_loop(BPM, 2, kick_pat2, clap_pat2, hat_pat2,
                        kick_sound=dk, snare_sound=dc, hat_sound=dh)
drum2 = saturate(drum2, 1.8)
save_wav(f'{OUT_D}/10_drum_loop2.wav', normalize(drum2[:n]))
print("D10 drum loop 2 done")

# Pad 11: Dark Texture Loop (noise + rumble)
tex_dur = n / SR
pn = pink_noise(tex_dur)
pn = lowpass(pn, 600)
rumble = sine(30, tex_dur) * 0.4
tex = pn * 0.4 + rumble
tt_arr = np.arange(n)/SR
lfo = 0.4 + 0.6 * np.sin(2*np.pi*0.1*tt_arr)
tex = tex * lfo
tex = saturate(tex, 2.0)
save_wav(f'{OUT_D}/11_dark_texture_loop.wav', normalize(tex[:n]))
print("D11 dark texture loop done")

# Pad 12: Reverse/Ambient Drone Loop
tt_arr = np.arange(n)/SR
d1 = sine(55, n/SR)*0.4 + sine(55.3, n/SR)*0.3
d2 = sine(82.5, n/SR)*0.2
drone = d1 + d2
drone = drone * (0.5 + 0.5*np.sin(2*np.pi*0.08*tt_arr))
drone = lowpass(drone, 500)
drone = delay_echo(drone, 0.5, 0.5, 0.5)
save_wav(f'{OUT_D}/12_drone_loop.wav', normalize(drone[:n]))
print("D12 drone loop done")

print("=== BANK D LOOPS COMPLETE ===")
