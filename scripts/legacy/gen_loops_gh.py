exec(open('/sessions/happy-intelligent-edison/loop_core.py').read())

# ============================================
# BANK G: FUNK & HORNS LOOPS (105bpm)
# ============================================
OUT_G = '/sessions/happy-intelligent-edison/SP-404A-Samples/_BANK-STAGING/G-FunkHorns'
BPM = 105
n = bar_samples(BPM, 2)
bps = beat_samples(BPM)

# Funk drum sounds
def funk_kick(dur=0.15):
    pe = np.exp(-np.linspace(0, 50, int(SR*dur)))
    k = np.sin(2*np.pi * np.cumsum(60 + 150*pe) / SR)
    click = noise(0.003) * env_perc(0.003, 0.0001, 10.0) * 0.5
    k = k * env_perc(dur, 0.0005, 1.0)
    kk = np.zeros(int(SR*dur))
    kk[:len(k)] = k; kk[:len(click)] += click
    return normalize(kk)

def funk_snare(dur=0.2):
    b = sine(220, dur) * env_perc(dur, 0.001, 2.0) * 0.5
    snap = bandpass(noise(dur)*env_perc(dur, 0.001, 2.5), 2000, 12000) * 0.6
    wire = bandpass(noise(dur)*env_perc(dur, 0.01, 0.8), 3000, 7000) * 0.3
    return normalize(b + snap + wire)

def funk_hat(dur=0.06):
    return normalize(highpass(lowpass(noise(dur)*env_perc(dur, 0.0003, 4.0), 14000), 7000))

def funk_conga(dur=0.3):
    tt = np.arange(int(SR*dur))/SR
    pe = np.exp(-tt*20)*200 + 300
    c = np.sin(2*np.pi * np.cumsum(pe)/SR) * env_perc(dur, 0.001, 1.0)
    return normalize(saturate(c, 1.3))

fk = funk_kick()
fs = funk_snare()
fh = funk_hat()
fc = funk_conga()

# Pad 5: Funk Bass Loop (slap-style, E minor pentatonic)
bass_notes = [
    (0, NOTE['E2'], 0.25, 0.9, 'saw'),
    (0.5, NOTE['E2'], 0.15, 0.5, 'saw'),
    (0.75, NOTE['G2'], 0.25, 0.7, 'saw'),
    (1, NOTE['A2'], 0.5, 0.85, 'saw'),
    (2, NOTE['E2'], 0.25, 0.9, 'saw'),
    (2.5, NOTE['D2'], 0.25, 0.7, 'saw'),
    (3, NOTE['E2'], 0.75, 0.8, 'saw'),
    (4, NOTE['E2'], 0.25, 0.9, 'saw'),
    (4.5, NOTE['G2'], 0.25, 0.7, 'saw'),
    (5, NOTE['A2'], 0.5, 0.85, 'saw'),
    (5.75, NOTE['B2'], 0.25, 0.6, 'saw'),
    (6, NOTE['A2'], 0.5, 0.8, 'saw'),
    (6.75, NOTE['G2'], 0.25, 0.7, 'saw'),
    (7, NOTE['E2'], 0.5, 0.85, 'saw'),
    (7.5, NOTE['D2'], 0.25, 0.6, 'saw'),
]
bass = make_bass_loop(BPM, 2, bass_notes)
# Bright filter for slap character
nn_b = len(bass)
filt_bass = np.zeros(nn_b)
fenv = np.zeros(nn_b)
for bp, freq, dur_b, vel, _ in bass_notes:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, nn_b)
    pe = env_perc(dur_b*60/BPM, 0.001, 0.4)
    for i in range(end-start):
        if i < len(pe): fenv[start+i] = max(fenv[start+i], pe[i])
prev = 0
for i in range(nn_b):
    cutoff = 300 + 3000 * fenv[i]
    rc_val = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc_val + 1.0/SR)
    filt_bass[i] = prev + alpha * (bass[i] - prev)
    prev = filt_bass[i]
filt_bass = saturate(filt_bass, 2.0)
save_wav(f'{OUT_G}/05_funk_bass_loop.wav', normalize(filt_bass[:n]))
print("G05 funk bass loop done")

# Pad 6: Horn Stab Loop (brass FM hits, rhythmic)
horn_hits = [
    (0, NOTE['E4'], 0.3, 0.9),
    (0.75, NOTE['G4'], 0.15, 0.5),
    (2, NOTE['A4'], 0.5, 0.85),
    (3, NOTE['G4'], 0.3, 0.7),
    (3.5, NOTE['E4'], 0.25, 0.6),
    (4, NOTE['E4'], 0.3, 0.9),
    (5, NOTE['B4'], 0.3, 0.8),
    (5.5, NOTE['A4'], 0.25, 0.65),
    (6, NOTE['G4'], 0.5, 0.85),
    (7, NOTE['A4'], 0.3, 0.7),
    (7.5, NOTE['B4'], 0.25, 0.6),
]
horn_loop = np.zeros(n)
for bp, freq, dur_b, vel in horn_hits:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, n)
    ad = (end-start)/SR
    tt_h = np.arange(end-start)/SR
    mi = env_perc(ad, 0.005, 0.8)[:end-start] * 6
    mod = mi * np.sin(2*np.pi*freq*tt_h)
    h = np.sin(2*np.pi*freq*tt_h + mod)
    h += np.sin(2*np.pi*freq*2*tt_h + mod*0.5) * 0.3
    h += np.sin(2*np.pi*freq*3*tt_h + mod*0.3) * 0.15
    h = h * env_perc(ad, 0.008, 1.2)[:end-start]
    h = lowpass(h, 6000)
    horn_loop[start:end] += h * vel
horn_loop = saturate(horn_loop, 1.5)
save_wav(f'{OUT_G}/06_horn_stab_loop.wav', normalize(horn_loop[:n]))
print("G06 horn stab loop done")

# Pad 7: Horn Phrase Loop (longer brass runs, call-response)
phrase_notes = [
    (0, NOTE['E4'], 0.5, 0.8),
    (0.5, NOTE['G4'], 0.3, 0.7),
    (1, NOTE['A4'], 0.7, 0.85),
    # response
    (2, NOTE['B4'], 0.3, 0.75),
    (2.5, NOTE['A4'], 0.3, 0.7),
    (3, NOTE['G4'], 0.5, 0.8),
    (3.5, NOTE['E4'], 0.5, 0.7),
    # second call
    (4, NOTE['A4'], 0.5, 0.8),
    (4.5, NOTE['B4'], 0.3, 0.7),
    (5, NOTE['C5'], 0.7, 0.9),
    # response
    (6, NOTE['B4'], 0.3, 0.7),
    (6.5, NOTE['A4'], 0.3, 0.65),
    (7, NOTE['G4'], 0.75, 0.8),
]
phrase = np.zeros(n)
for bp, freq, dur_b, vel in phrase_notes:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, n)
    ad = (end-start)/SR
    tt_h = np.arange(end-start)/SR
    mi = env_perc(ad, 0.008, 0.6)[:end-start] * 5
    mod = mi * np.sin(2*np.pi*freq*tt_h)
    h = np.sin(2*np.pi*freq*tt_h + mod)
    h += np.sin(2*np.pi*freq*2*tt_h + mod*0.5) * 0.25
    h = h * env_adsr(ad, 0.008, 0.05, 0.6, 0.05)[:end-start]
    h = lowpass(h, 5000)
    phrase[start:end] += h * vel
phrase = saturate(phrase, 1.5)
save_wav(f'{OUT_G}/07_horn_phrase_loop.wav', normalize(phrase[:n]))
print("G07 horn phrase loop done")

# Pad 8: Clavinet/Keys Loop (rhythmic, funky)
clav_notes = [
    (0, NOTE['E4'], 0.25, 0.8),
    (0.5, NOTE['G4'], 0.15, 0.5),
    (0.75, NOTE['A4'], 0.25, 0.6),
    (1, NOTE['B4'], 0.5, 0.75),
    (2, NOTE['E4'], 0.25, 0.8),
    (2.5, NOTE['E4'], 0.15, 0.4),
    (3, NOTE['D4'], 0.5, 0.7),
    (3.5, NOTE['E4'], 0.25, 0.65),
    (4, NOTE['E4'], 0.25, 0.8),
    (4.5, NOTE['G4'], 0.15, 0.5),
    (5, NOTE['A4'], 0.5, 0.75),
    (5.75, NOTE['B4'], 0.25, 0.6),
    (6, NOTE['A4'], 0.5, 0.7),
    (6.75, NOTE['G4'], 0.25, 0.55),
    (7, NOTE['E4'], 0.5, 0.75),
]
clav = np.zeros(n)
for bp, freq, dur_b, vel in clav_notes:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, n)
    ad = (end-start)/SR
    ch = square(freq, ad, 0.2)[:end-start]
    ch += square(freq*2, ad, 0.15)[:end-start] * 0.3
    fe = env_perc(ad, 0.001, 0.5)[:end-start]
    # Filter per note
    fc_arr = np.zeros(end-start)
    prev_f = 0
    for i in range(end-start):
        cutoff = 500 + 5000 * fe[i]
        rc_val = 1.0/(2*np.pi*cutoff)
        alpha_f = (1.0/SR)/(rc_val + 1.0/SR)
        fc_arr[i] = prev_f + alpha_f * (ch[i] - prev_f)
        prev_f = fc_arr[i]
    fc_arr = fc_arr * env_adsr(ad, 0.002, 0.05, 0.3, 0.02)[:end-start]
    clav[start:end] += fc_arr * vel
save_wav(f'{OUT_G}/08_clavinet_loop.wav', normalize(clav[:n]))
print("G08 clavinet loop done")

# Pad 9: Funk Drum Loop 1 (classic funk, 16th hats, syncopated kick)
kick_pat = [(0, 0.9), (0.75, 0.5), (2, 0.7), (3.5, 0.6), (4, 0.9), (4.75, 0.5), (6, 0.7), (7.5, 0.55)]
snare_pat = [(2, 0.85), (6, 0.85)]
hat_pat = [(i*0.25, 0.5 if i%4==0 else 0.3 if i%2==0 else 0.2) for i in range(32)]
conga_pat = [(1, 0.4), (3, 0.35), (5, 0.4), (7, 0.35)]
drum1 = make_drum_loop(BPM, 2, kick_pat, snare_pat, hat_pat, conga_pat,
                        kick_sound=fk, snare_sound=fs, hat_sound=fh, perc_sound=fc, swing=0.1)
save_wav(f'{OUT_G}/09_funk_loop1.wav', normalize(drum1[:n]))
print("G09 funk drum loop 1 done")

# Pad 10: Funk Drum Loop 2 (breakbeat variation, busier)
kick_pat2 = [(0, 0.9), (1.25, 0.5), (2.5, 0.6), (3.75, 0.5), (4, 0.9), (5.5, 0.6), (7, 0.5)]
snare_pat2 = [(2, 0.85), (4.75, 0.4), (6, 0.85), (7.5, 0.45)]
hat_pat2 = [(i*0.25, 0.45 if i%4==0 else 0.2) for i in range(32)]
conga_pat2 = [(0.5, 0.35), (1.5, 0.3), (3, 0.4), (5, 0.35), (6.5, 0.3)]
drum2 = make_drum_loop(BPM, 2, kick_pat2, snare_pat2, hat_pat2, conga_pat2,
                        kick_sound=fk, snare_sound=fs, hat_sound=fh, perc_sound=fc, swing=0.1)
save_wav(f'{OUT_G}/10_funk_loop2.wav', normalize(drum2[:n]))
print("G10 funk drum loop 2 done")

# Pad 11: Wah Guitar Loop (filtered saw, rhythmic wah)
wah = np.zeros(n)
gtr_notes = [
    (0, NOTE['E3'], 0.5, 0.8), (0.75, NOTE['G3'], 0.25, 0.5),
    (1, NOTE['A3'], 0.5, 0.7), (2, NOTE['E3'], 0.5, 0.8),
    (2.75, NOTE['D3'], 0.25, 0.5), (3, NOTE['E3'], 0.75, 0.75),
    (4, NOTE['E3'], 0.5, 0.8), (4.75, NOTE['G3'], 0.25, 0.5),
    (5, NOTE['A3'], 0.75, 0.7), (6, NOTE['B3'], 0.5, 0.75),
    (6.75, NOTE['A3'], 0.25, 0.5), (7, NOTE['G3'], 0.75, 0.7),
]
for bp, freq, dur_b, vel in gtr_notes:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, n)
    ad = (end-start)/SR
    g = (saw(freq, ad)*0.6 + square(freq, ad, 0.4)*0.3)[:end-start]
    # Wah sweep per note
    wah_env = np.sin(np.pi * np.linspace(0, 1, end-start))
    filt_g = np.zeros(end-start)
    prev_w = 0
    for i in range(end-start):
        cutoff = 400 + 3000 * wah_env[i]
        rc_val = 1.0/(2*np.pi*cutoff)
        alpha_w = (1.0/SR)/(rc_val + 1.0/SR)
        filt_g[i] = prev_w + alpha_w * (g[i] - prev_w)
        prev_w = filt_g[i]
    filt_g = filt_g * env_adsr(ad, 0.003, 0.05, 0.5, 0.03)[:end-start]
    wah[start:end] += filt_g * vel
wah = saturate(wah, 2.0)
save_wav(f'{OUT_G}/11_wah_guitar_loop.wav', normalize(wah[:n]))
print("G11 wah guitar loop done")

# Pad 12: Scratch/Vinyl FX Loop
tt_arr = np.arange(n)/SR
scratch = np.zeros(n)
# Rhythmic scratch hits
for bp in [0, 0.5, 2, 2.75, 4, 4.5, 6, 6.75, 7.5]:
    start = int(bp * bps)
    sdur = int(0.15 * SR)
    end = min(start+sdur, n)
    ad = (end-start)/SR
    tt_s = np.arange(end-start)/SR
    sf = 200 + 1500 * np.abs(np.sin(2*np.pi*12*tt_s))
    phase = np.cumsum(sf/SR) * 2 * np.pi
    sc = np.sin(phase) * noise(ad)[:end-start]
    sc = bandpass(sc, 300, 6000)
    sc = sc * env_perc(ad, 0.005, 2.0)[:end-start]
    scratch[start:end] += sc * 0.7
scratch = saturate(scratch, 2.0)
save_wav(f'{OUT_G}/12_scratch_loop.wav', normalize(scratch[:n]))
print("G12 scratch loop done")
print("=== BANK G LOOPS COMPLETE ===\n")

# ============================================
# BANK H: IDM LOOPS (140bpm)
# ============================================
OUT_H = '/sessions/happy-intelligent-edison/SP-404A-Samples/_BANK-STAGING/H-IDM'
BPM = 140
n = bar_samples(BPM, 2)
bps = beat_samples(BPM)

# IDM drum sounds
def idm_kick(dur=0.25):
    pe = np.exp(-np.linspace(0, 25, int(SR*dur)))
    tt = np.arange(int(SR*dur))/SR
    flutter = 30 * np.sin(2*np.pi*45*tt) * np.exp(-tt*10)
    k = np.sin(2*np.pi * np.cumsum(50 + 180*pe + flutter[:len(pe)]) / SR)
    k = k * env_perc(dur, 0.0005, 0.4)
    return normalize(saturate(k, 2.5))

def idm_snare(dur=0.2):
    b = sine(180, dur) * env_perc(dur, 0.001, 2.0) * 0.4
    ns = bandpass(noise(dur)*env_perc(dur, 0.001, 1.5), 1500, 10000) * 0.6
    ring = sine(1200, dur)*sine(780, dur)*env_perc(dur, 0.002, 3.0) * 0.3
    return normalize(saturate(b + ns + ring, 2.0))

def idm_hat(dur=0.1):
    h = sine(6731, dur)*sine(4523, dur)*env_perc(dur, 0.0005, 3.0)
    h += noise(dur)*env_perc(dur, 0.0005, 5.0)*0.2
    return normalize(highpass(saturate(h, 1.5), 3000))

def idm_glitch(dur=0.1):
    g = fm_synth(400, 730, 5, dur) * env_perc(dur, 0.001, 3.0)
    return normalize(saturate(g, 2.0))

ik = idm_kick()
isn = idm_snare()
ih = idm_hat()
ig = idm_glitch()

# Pad 5: Morphing Bass Loop (FM modulation evolves over time)
bass_notes = [
    (0, NOTE['C2'], 0.75, 0.9, 'sine'),
    (1, NOTE['Eb2'], 0.5, 0.7, 'sine'),
    (1.75, NOTE['C2'], 0.25, 0.5, 'sine'),
    (2, NOTE['F2'], 0.75, 0.85, 'sine'),
    (3, NOTE['Eb2'], 0.5, 0.7, 'sine'),
    (3.75, NOTE['D2'], 0.25, 0.6, 'sine'),
    (4, NOTE['C2'], 0.5, 0.9, 'sine'),
    (4.75, NOTE['C2'], 0.25, 0.4, 'sine'),
    (5, NOTE['G2']*0.5, 0.75, 0.8, 'sine'),
    (6, NOTE['Ab2']*0.5, 0.5, 0.7, 'sine'),
    (7, NOTE['Bb2']*0.5, 0.75, 0.75, 'sine'),
]
bass_raw = make_bass_loop(BPM, 2, bass_notes)
# Add FM modulation that evolves
tt_arr = np.arange(n)/SR
mod_env = 2.0 + 3.0 * np.sin(2*np.pi*0.25*tt_arr)
mod_sig = mod_env * np.sin(2*np.pi*55*tt_arr)
bass_fm = np.sin(np.cumsum(bass_raw*2*np.pi/SR*10) + mod_sig*0.3)
bass_mix = bass_raw*0.6 + bass_fm*0.3
bass_mix = lowpass(bass_mix, 1500)
bass_mix = saturate(bass_mix, 2.5)
save_wav(f'{OUT_H}/05_morph_bass_loop.wav', normalize(bass_mix[:n]))
print("H05 morph bass loop done")

# Pad 6: Complex FM Synth Loop (bell-like, evolving)
fm_notes = [
    (0, NOTE['C4'], 0.5, 0.8),
    (0.75, NOTE['Eb4'], 0.25, 0.5),
    (1.5, NOTE['G4'], 0.75, 0.7),
    (2.5, NOTE['F4'], 0.5, 0.6),
    (3.5, NOTE['Eb4'], 0.5, 0.65),
    (4, NOTE['C4'], 0.75, 0.8),
    (5, NOTE['Ab3'], 0.5, 0.7),
    (5.75, NOTE['Bb3'], 0.25, 0.5),
    (6, NOTE['C4'], 1.0, 0.75),
    (7, NOTE['G3'], 0.75, 0.6),
]
fm_loop = np.zeros(n)
for bp, freq, dur_b, vel in fm_notes:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, n)
    ad = (end-start)/SR
    tt_n = np.arange(end-start)/SR
    mi = 7.0 * np.exp(-tt_n*1.5)
    m1 = mi * np.sin(2*np.pi*freq*1.41*tt_n)
    m2 = 3.0 * np.sin(2*np.pi*freq*2.76*tt_n + m1)
    note = np.sin(2*np.pi*freq*tt_n + m2)
    note = note * env_adsr(ad, 0.005, 0.2, 0.3, 0.1)[:end-start]
    fm_loop[start:end] += note * vel
fm_loop = delay_echo(fm_loop, 0.17, 0.3, 0.3)
save_wav(f'{OUT_H}/06_fm_synth_loop.wav', normalize(fm_loop[:n]))
print("H06 FM synth loop done")

# Pad 7: Digital Texture Loop (ring-mod noise, rhythmic)
tex = np.zeros(n)
step = sixteenth_samples(BPM)
for i in range(0, n, step):
    end = min(i+step, n)
    length = end - i
    if np.random.random() > 0.3:
        freq = np.random.uniform(800, 5000)
        band = noise(length/SR)[:length]
        band = bandpass(band, freq-200, freq+200)
        mod = sine(freq*0.13, length/SR)[:length]
        chunk = band * mod * 0.5
        window = np.hanning(length)
        tex[i:end] += chunk * window
tex = saturate(tex, 1.5)
save_wav(f'{OUT_H}/07_texture_loop.wav', normalize(tex[:n]))
print("H07 texture loop done")

# Pad 8: Granular Pad Loop (evolving, atmospheric)
tt_arr = np.arange(n)/SR
base = sine(220, n/SR) + sine(330, n/SR)*0.5 + sine(440, n/SR)*0.3
grain_size = int(SR * 0.04)
window = np.hanning(grain_size)
pad = np.zeros(n)
for i in range(0, n - grain_size, int(grain_size * 0.3)):
    src_pos = int(i + np.random.uniform(-SR*0.1, SR*0.1))
    src_pos = max(0, min(src_pos, n - grain_size))
    grain = base[src_pos:src_pos+grain_size] * window
    end = min(i + grain_size, n)
    pad[i:end] += grain[:end-i]
pad = lowpass(pad, 3000)
pad = delay_echo(pad, 0.2, 0.35, 0.35)
save_wav(f'{OUT_H}/08_granular_loop.wav', normalize(pad[:n]))
print("H08 granular pad loop done")

# Pad 9: IDM Drum Loop 1 (complex, irregular)
kick_pat = [(0, 0.9), (1.25, 0.6), (2.5, 0.7), (3, 0.5), (4.5, 0.85), (5.75, 0.6), (7, 0.7)]
snare_pat = [(1.75, 0.7), (3.5, 0.6), (5.25, 0.75), (7.5, 0.5)]
hat_pat = [(0, 0.45), (0.5, 0.3), (1, 0.4), (1.5, 0.25), (2.25, 0.4), (3.25, 0.35),
           (3.75, 0.3), (4, 0.45), (4.75, 0.3), (5.5, 0.4), (6, 0.35), (6.5, 0.3), (7, 0.4), (7.25, 0.25)]
glitch_pat = [(0.25, 0.35), (2.75, 0.4), (4.25, 0.35), (6.75, 0.4)]
drum1 = make_drum_loop(BPM, 2, kick_pat, snare_pat, hat_pat, glitch_pat,
                        kick_sound=ik, snare_sound=isn, hat_sound=ih, perc_sound=ig)
drum1 = saturate(drum1, 1.3)
save_wav(f'{OUT_H}/09_idm_loop1.wav', normalize(drum1[:n]))
print("H09 IDM drum loop 1 done")

# Pad 10: IDM Drum Loop 2 (different pattern, more glitchy)
kick_pat2 = [(0, 0.9), (0.5, 0.4), (2, 0.7), (3.75, 0.8), (4, 0.9), (6, 0.6), (6.75, 0.5)]
snare_pat2 = [(1, 0.6), (3, 0.7), (5, 0.65), (7, 0.7)]
hat_pat2 = [(i*0.25, np.random.uniform(0.2, 0.5) if np.random.random() > 0.25 else 0) for i in range(32)]
hat_pat2 = [(p, v) for p, v in hat_pat2 if v > 0]
glitch_pat2 = [(0.75, 0.4), (1.5, 0.35), (3.25, 0.4), (5.5, 0.35), (7.25, 0.45)]
drum2 = make_drum_loop(BPM, 2, kick_pat2, snare_pat2, hat_pat2, glitch_pat2,
                        kick_sound=ik, snare_sound=isn, hat_sound=ih, perc_sound=ig)
drum2 = saturate(drum2, 1.5)
save_wav(f'{OUT_H}/10_idm_loop2.wav', normalize(drum2[:n]))
print("H10 IDM drum loop 2 done")

# Pad 11: Stutter/Buffer FX Loop (rhythmic digital artifacts)
src = fm_synth(300, 500, 4, n/SR)[:n]
buf_size = int(SR * 0.06)
stutter = np.zeros(n)
pos = 0
while pos < n:
    chunk_end = min(pos + buf_size, n)
    chunk = src[pos:chunk_end]
    repeats = np.random.choice([1, 2, 3, 4])
    for r in range(repeats):
        start = pos + r * len(chunk)
        end = min(start + len(chunk), n)
        if start < n:
            stutter[start:end] = chunk[:end-start]
    pos += len(chunk) * repeats
    buf_size = int(SR * np.random.choice([0.03, 0.05, 0.08, 0.12]))
stutter = saturate(stutter, 1.5)
save_wav(f'{OUT_H}/11_stutter_loop.wav', normalize(stutter[:n]))
print("H11 stutter loop done")

# Pad 12: Ambient Drone Loop
tt_arr = np.arange(n)/SR
d1 = sine(110, n/SR)*0.4 + sine(110.3, n/SR)*0.3
d3 = sine(165, n/SR)*0.2
lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.15*tt_arr)
drone = (d1 + d3) * lfo
drone = lowpass(drone, 2000)
drone = delay_echo(drone, 0.3, 0.4, 0.4)
save_wav(f'{OUT_H}/12_drone_loop.wav', normalize(drone[:n]))
print("H12 drone loop done")
print("=== BANK H LOOPS COMPLETE ===")
