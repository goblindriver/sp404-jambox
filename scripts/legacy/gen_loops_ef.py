import os
exec(open(os.path.join(os.path.dirname(__file__), 'loop_core.py')).read())

# ============================================
# BANK E: NU-RAVE LOOPS (130bpm)
# ============================================
OUT_E = os.path.join(STAGING_BASE, 'E-NuRave')
BPM = 130
n = bar_samples(BPM, 2)

# Rave drum sounds
def rave_kick(dur=0.2):
    pe = np.exp(-np.linspace(0, 40, int(SR*dur)))
    k = np.sin(2*np.pi * np.cumsum(50 + 200*pe) / SR)
    return normalize(saturate(k * env_perc(dur, 0.0005, 0.6), 1.8))

def rave_snare(dur=0.15):
    b = sine(250, dur) * env_perc(dur, 0.001, 2.5)
    ns = bandpass(noise(dur) * env_perc(dur, 0.001, 2.0), 2000, 10000)
    return normalize(saturate(b*0.4 + ns*0.7, 1.5))

def rave_hat(dur=0.05):
    return normalize(highpass(noise(dur) * env_perc(dur, 0.0003, 6.0), 7000))

def rave_clap(dur=0.15):
    cl = np.zeros(int(SR*dur))
    for off in [0, 0.008, 0.015]:
        o = int(off*SR)
        nn = bandpass(noise(0.02) * env_perc(0.02, 0.0005, 4.0), 1000, 8000)
        end = min(o+len(nn), len(cl))
        cl[o:end] += nn[:end-o]
    return normalize(cl)

rk = rave_kick()
rs = rave_snare()
rh = rave_hat()
rc = rave_clap()

# Pad 5: Acid Bass Loop (303-style, C minor)
acid_notes = [
    (0, NOTE['C2'], 0.5, 0.9, 'saw'),
    (0.5, NOTE['C2'], 0.25, 0.6, 'saw'),
    (1, NOTE['Eb2'], 0.5, 0.85, 'saw'),
    (2, NOTE['G2'], 0.75, 0.8, 'saw'),
    (3, NOTE['F2'], 0.5, 0.75, 'saw'),
    (3.5, NOTE['Eb2'], 0.25, 0.6, 'saw'),
    (4, NOTE['C2'], 0.5, 0.9, 'saw'),
    (4.75, NOTE['C2'], 0.25, 0.5, 'saw'),
    (5, NOTE['Bb2']*0.5, 0.75, 0.8, 'saw'),
    (6, NOTE['Ab2']*0.5, 0.5, 0.7, 'saw'),
    (6.75, NOTE['G2']*0.5, 0.25, 0.6, 'saw'),
    (7, NOTE['Ab2']*0.5, 0.5, 0.7, 'saw'),
    (7.5, NOTE['Bb2']*0.5, 0.25, 0.65, 'saw'),
]
bass = make_bass_loop(BPM, 2, acid_notes)
# Acid filter sweep simulation
nn = len(bass)
filtered = np.zeros(nn)
prev = 0
for i in range(nn):
    # Pulsing filter tied to 16th notes
    beat_phase = (i / beat_samples(BPM)) % 1
    cutoff = 400 + 2500 * max(0, 1 - beat_phase*4)
    rc_val = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc_val + 1.0/SR)
    filtered[i] = prev + alpha * (bass[i] - prev)
    prev = filtered[i]
filtered = saturate(filtered, 3.0)
save_wav(f'{OUT_E}/05_acid_bass_loop.wav', normalize(filtered[:n]))
print("E05 acid bass loop done")

# Pad 6: Hoover Riff Loop (detuned saws, menacing)
hoover_notes = [
    (0, NOTE['C3'], 1.5, 0.8),
    (2, NOTE['Eb3'], 1.0, 0.75),
    (3, NOTE['C3'], 0.5, 0.6),
    (4, NOTE['G3'], 1.5, 0.85),
    (6, NOTE['F3'], 1.0, 0.7),
    (7, NOTE['Eb3'], 0.75, 0.65),
]
hoover = np.zeros(n)
bps = beat_samples(BPM)
for bp, freq, dur_b, vel in hoover_notes:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, n)
    actual_dur = (end-start)/SR
    # 5 detuned saws
    chunk = np.zeros(end-start)
    for dt in [-2, -1, 0, 1, 2]:
        chunk += saw(freq+dt, actual_dur)[:end-start]
    chunk /= 5
    chunk = lowpass(chunk, 3000)
    env_h = env_adsr(actual_dur, 0.03, 0.1, 0.7, 0.1)[:end-start]
    hoover[start:end] += chunk * env_h * vel
hoover = chorus(hoover, 0.004, 2.0)
hoover = saturate(hoover, 1.8)
save_wav(f'{OUT_E}/06_hoover_loop.wav', normalize(hoover[:n]))
print("E06 hoover loop done")

# Pad 7: Rave Stab Loop (chord stabs, rhythmic)
stab_hits = [
    (0, [NOTE['C4'], NOTE['E4'], NOTE['G4']], 0.25, 0.9),
    (0.5, [NOTE['C4'], NOTE['E4'], NOTE['G4']], 0.15, 0.5),
    (2, [NOTE['F4'], NOTE['A4'], NOTE['C5']], 0.25, 0.85),
    (3, [NOTE['G4'], NOTE['B4'], NOTE['D5']], 0.25, 0.8),
    (4, [NOTE['C4'], NOTE['E4'], NOTE['G4']], 0.25, 0.9),
    (4.5, [NOTE['C4'], NOTE['E4'], NOTE['G4']], 0.15, 0.5),
    (5.5, [NOTE['F4'], NOTE['A4'], NOTE['C5']], 0.25, 0.7),
    (6, [NOTE['G4'], NOTE['B4'], NOTE['D5']], 0.25, 0.85),
    (7, [NOTE['C4'], NOTE['E4'], NOTE['G4'], NOTE['C5']], 0.5, 0.9),
]
stab_loop = np.zeros(n)
for bp, freqs, dur_b, vel in stab_hits:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, n)
    actual_dur = (end-start)/SR
    chord = np.zeros(end-start)
    for f in freqs:
        chord += square(f, actual_dur, 0.4)[:end-start]
    chord /= len(freqs)
    chord = lowpass(chord, 6000)
    env_s = env_perc(actual_dur, 0.002, 1.5)[:end-start]
    stab_loop[start:end] += chord * env_s * vel
stab_loop = saturate(stab_loop, 1.5)
save_wav(f'{OUT_E}/07_stab_loop.wav', normalize(stab_loop[:n]))
print("E07 stab loop done")

# Pad 8: Supersaw Pad Loop (evolving, big chords)
pad_chords = [
    (0, [NOTE['C3'], NOTE['E3'], NOTE['G3'], NOTE['C4']], 4, 0.8),
    (4, [NOTE['F3'], NOTE['A3'], NOTE['C4'], NOTE['F4']], 4, 0.75),
]
pad = make_pad_loop(BPM, 2, pad_chords, wave='saw', detune=2.0)
pad = lowpass(pad, 3000)
pad = chorus(pad, 0.003, 1.0)
save_wav(f'{OUT_E}/08_supersaw_loop.wav', normalize(pad[:n]))
print("E08 supersaw pad loop done")

# Pad 9: Rave Drum Loop 1 (4-on-floor + offbeat hats)
kick_pat = [(i, 0.95) for i in range(8)]
snare_pat = [(2, 0.8), (6, 0.8)]
hat_pat = [(i+0.5, 0.55) for i in range(8)]
drum1 = make_drum_loop(BPM, 2, kick_pat, snare_pat, hat_pat,
                        kick_sound=rk, snare_sound=rs, hat_sound=rh)
save_wav(f'{OUT_E}/09_drum_loop1.wav', normalize(drum1[:n]))
print("E09 drum loop 1 done")

# Pad 10: Rave Drum Loop 2 (busier, breakbeat-influenced)
kick_pat2 = [(0, 0.95), (1.25, 0.6), (2.5, 0.7), (4, 0.95), (5, 0.6), (6.5, 0.7)]
clap_pat2 = [(2, 0.85), (6, 0.85), (7.5, 0.5)]
hat_pat2 = [(i*0.25, 0.45 if i%2==0 else 0.25) for i in range(32)]
drum2 = make_drum_loop(BPM, 2, kick_pat2, clap_pat2, hat_pat2,
                        kick_sound=rk, snare_sound=rc, hat_sound=rh)
drum2 = saturate(drum2, 1.3)
save_wav(f'{OUT_E}/10_drum_loop2.wav', normalize(drum2[:n]))
print("E10 drum loop 2 done")

# Pad 11: Arp Synth Loop (16th note arpeggiation)
step = sixteenth_samples(BPM)
arp_notes_seq = [NOTE['C4'], NOTE['E4'], NOTE['G4'], NOTE['C5'],
                 NOTE['G4'], NOTE['E4'], NOTE['C4'], NOTE['G3']]
arp = np.zeros(n)
for rep in range(n // (step * len(arp_notes_seq)) + 1):
    for i, note_f in enumerate(arp_notes_seq):
        idx = rep * len(arp_notes_seq) + i
        start = idx * step
        if start >= n: break
        note_dur = step * 0.7 / SR
        note_sig = square(note_f, note_dur, 0.3) * env_perc(note_dur, 0.002, 2.5)
        note_sig = lowpass(note_sig, 5000)
        end = min(start + len(note_sig), n)
        arp[start:end] += note_sig[:end-start] * 0.7
arp = saturate(arp, 1.3)
save_wav(f'{OUT_E}/11_arp_loop.wav', normalize(arp[:n]))
print("E11 arp loop done")

# Pad 12: Build/Siren FX Loop (tension builder)
tt_arr = np.arange(n)/SR
siren_f = 500 + 300 * np.sin(2*np.pi*3*tt_arr)
siren = np.sin(2*np.pi * np.cumsum(siren_f) / SR)
# Add noise riser
riser_ns = noise(n/SR) * np.linspace(0, 0.4, n)
riser_ns = highpass(riser_ns, 2000)
combo = siren*0.5 + riser_ns*0.5
combo = saturate(combo, 1.5)
save_wav(f'{OUT_E}/12_siren_loop.wav', normalize(combo[:n]))
print("E12 siren loop done")
print("=== BANK E LOOPS COMPLETE ===\n")

# ============================================
# BANK F: ELECTROCLASH LOOPS (120bpm)
# ============================================
OUT_F = os.path.join(STAGING_BASE, 'F-Electroclash')
BPM = 120
n = bar_samples(BPM, 2)

def ec_kick(dur=0.2):
    pe = np.exp(-np.linspace(0, 35, int(SR*dur)))
    k = np.sin(2*np.pi * np.cumsum(45 + 180*pe) / SR)
    return normalize(saturate(k * env_perc(dur, 0.0005, 0.5), 2.0))

def ec_clap(dur=0.15):
    cl = np.zeros(int(SR*dur))
    for off in [0, 0.005, 0.012]:
        o = int(off*SR)
        nn = bandpass(noise(0.02)*env_perc(0.02, 0.0005, 5.0), 1500, 9000)
        end = min(o+len(nn), len(cl))
        cl[o:end] += nn[:end-o]
    return normalize(saturate(cl, 1.8))

def ec_hat(dur=0.04):
    return normalize(highpass(noise(dur)*env_perc(dur, 0.0003, 6.0), 7000))

def ec_cowbell(dur=0.15):
    cb = (sine(540, dur)*0.6 + sine(800, dur)*0.4) * env_perc(dur, 0.001, 2.0)
    return normalize(saturate(cb, 1.5))

ek = ec_kick()
ecl = ec_clap()
eh = ec_hat()
ecb = ec_cowbell()
bps = beat_samples(BPM)

# Pad 5: Dirty Bass Loop (distorted square, repetitive)
bass_notes = [
    (0, NOTE['C2'], 0.5, 0.9, 'square'),
    (0.75, NOTE['C2'], 0.25, 0.5, 'square'),
    (1, NOTE['C2'], 0.5, 0.85, 'square'),
    (2, NOTE['Eb2'], 0.75, 0.8, 'square'),
    (3, NOTE['D2'], 0.5, 0.7, 'square'),
    (3.5, NOTE['C2'], 0.5, 0.75, 'square'),
    (4, NOTE['C2'], 0.5, 0.9, 'square'),
    (4.75, NOTE['C2'], 0.25, 0.5, 'square'),
    (5, NOTE['Eb2'], 0.5, 0.8, 'square'),
    (5.5, NOTE['F2'], 0.5, 0.75, 'square'),
    (6, NOTE['Eb2'], 1.0, 0.85, 'square'),
    (7, NOTE['D2'], 0.75, 0.7, 'square'),
]
bass = make_bass_loop(BPM, 2, bass_notes)
bass = saturate(bass, 4.0)
bass = lowpass(bass, 1200)
save_wav(f'{OUT_F}/05_dirty_bass_loop.wav', normalize(bass[:n]))
print("F05 dirty bass loop done")

# Pad 6: Analog Lead Loop (square wave, robotic melody)
lead_notes = [
    (0, NOTE['C4'], 0.5, 0.8),
    (0.75, NOTE['Eb4'], 0.25, 0.5),
    (1, NOTE['G4'], 0.75, 0.7),
    (2, NOTE['Eb4'], 0.5, 0.65),
    (3, NOTE['C4'], 0.5, 0.7),
    (3.5, NOTE['D4'], 0.5, 0.6),
    (4, NOTE['Eb4'], 0.75, 0.8),
    (5, NOTE['G4'], 0.5, 0.7),
    (5.5, NOTE['F4'], 0.5, 0.65),
    (6, NOTE['Eb4'], 1.0, 0.75),
    (7, NOTE['D4'], 0.5, 0.6),
    (7.5, NOTE['C4'], 0.5, 0.65),
]
lead = make_melodic_loop(BPM, 2, lead_notes, wave='square', filter_cutoff=2500, attack=0.01, release=0.05)
lead = saturate(lead, 2.0)
save_wav(f'{OUT_F}/06_analog_lead_loop.wav', normalize(lead[:n]))
print("F06 analog lead loop done")

# Pad 7: Robot Vocal Loop (ring mod, rhythmic)
robot = np.zeros(n)
syllables = [(0, 180, 0.3), (0.5, 200, 0.2), (1, 160, 0.3), (2, 220, 0.5),
             (3, 180, 0.3), (3.5, 200, 0.2), (4, 160, 0.4), (5, 240, 0.3),
             (5.5, 180, 0.2), (6, 200, 0.5), (7, 160, 0.3), (7.5, 220, 0.2)]
for bp, f0, dur_b in syllables:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, n)
    ad = (end-start)/SR
    src = saw(f0, ad)[:end-start]
    carrier = sine(300, ad)[:end-start]
    chunk = src * carrier
    chunk = bandpass(chunk, 200, 4000)
    chunk = chunk * env_perc(ad, 0.01, 1.5)[:end-start]
    robot[start:end] += chunk * 0.7
robot = saturate(robot, 2.0)
save_wav(f'{OUT_F}/07_robot_vocal_loop.wav', normalize(robot[:n]))
print("F07 robot vocal loop done")

# Pad 8: Synth Stab Loop (harsh, rhythmic)
stab_hits = [
    (0, [NOTE['C4'], NOTE['Eb4'], NOTE['G4']], 0.2, 0.9),
    (1, [NOTE['C4'], NOTE['Eb4'], NOTE['G4']], 0.15, 0.5),
    (2, [NOTE['Ab3'], NOTE['C4'], NOTE['Eb4']], 0.25, 0.8),
    (3.5, [NOTE['Bb3'], NOTE['D4'], NOTE['F4']], 0.2, 0.7),
    (4, [NOTE['C4'], NOTE['Eb4'], NOTE['G4']], 0.2, 0.9),
    (5, [NOTE['C4'], NOTE['Eb4'], NOTE['G4']], 0.15, 0.5),
    (6, [NOTE['Ab3'], NOTE['C4'], NOTE['Eb4']], 0.3, 0.85),
    (7, [NOTE['G3'], NOTE['B3'], NOTE['D4']], 0.5, 0.8),
]
stab = np.zeros(n)
for bp, freqs, dur_b, vel in stab_hits:
    start = int(bp * bps)
    dur_s = int(dur_b * bps)
    end = min(start+dur_s, n)
    ad = (end-start)/SR
    ch = sum(square(f, ad, 0.3)[:end-start] + saw(f, ad)[:end-start]*0.3 for f in freqs) / len(freqs)
    ch = lowpass(ch, 5000)
    ch = ch * env_perc(ad, 0.001, 1.5)[:end-start]
    stab[start:end] += ch * vel
stab = saturate(stab, 2.5)
save_wav(f'{OUT_F}/08_stab_loop.wav', normalize(stab[:n]))
print("F08 stab loop done")

# Pad 9: EC Drum Loop 1 (4-on-floor + clap + cowbell)
kick_pat = [(i, 0.95) for i in range(8)]
clap_pat = [(2, 0.8), (6, 0.8)]
hat_pat = [(i+0.5, 0.5) for i in range(8)]
cb_pat = [(1, 0.4), (3, 0.4), (5, 0.4), (7, 0.4)]
drum1 = make_drum_loop(BPM, 2, kick_pat, clap_pat, hat_pat, cb_pat,
                        kick_sound=ek, snare_sound=ecl, hat_sound=eh, perc_sound=ecb)
save_wav(f'{OUT_F}/09_drum_loop1.wav', normalize(drum1[:n]))
print("F09 drum loop 1 done")

# Pad 10: EC Drum Loop 2 (new wave influenced, sparser)
kick_pat2 = [(0, 0.9), (2, 0.7), (4, 0.9), (6.5, 0.7)]
clap_pat2 = [(2, 0.85), (6, 0.85)]
hat_pat2 = [(i*0.5, 0.4 if i%2==0 else 0.25) for i in range(16)]
drum2 = make_drum_loop(BPM, 2, kick_pat2, clap_pat2, hat_pat2,
                        kick_sound=ek, snare_sound=ecl, hat_sound=eh)
save_wav(f'{OUT_F}/10_drum_loop2.wav', normalize(drum2[:n]))
print("F10 drum loop 2 done")

# Pad 11: Filter Sweep Loop
tt_arr = np.arange(n)/SR
raw = noise(n/SR)*0.4 + saw(100, n/SR)*0.5
nn = len(raw)
sweep = np.zeros(nn)
prev = 0
for i in range(nn):
    p = (i/nn) % 1
    cutoff = 200 + 6000 * (0.5 + 0.5*np.sin(2*np.pi*p*2))
    rc_val = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc_val + 1.0/SR)
    sweep[i] = prev + alpha * (raw[i] - prev)
    prev = sweep[i]
save_wav(f'{OUT_F}/11_sweep_loop.wav', normalize(sweep[:n]))
print("F11 sweep loop done")

# Pad 12: Static/Noise Texture Loop
tex = noise(n/SR)
tex = bitcrush(tex, 4)
tex = decimate(tex, 6)
tt_arr = np.arange(n)/SR
gate = (np.sin(2*np.pi*2*tt_arr) > 0).astype(float)
tex = tex * gate * 0.5
tex = lowpass(tex, 6000)
save_wav(f'{OUT_F}/12_static_loop.wav', normalize(tex[:n], 0.6))
print("F12 static loop done")
print("=== BANK F LOOPS COMPLETE ===")
