import os
exec(open(os.path.join(os.path.dirname(__file__), 'loop_core.py')).read())

# ============================================
# BANK I: AMBIENT/TEXTURAL LOOPS (free tempo, ~80bpm reference)
# ============================================
OUT_I = os.path.join(STAGING_BASE, 'I-AmbientTextural')
BPM = 80
n = bar_samples(BPM, 4)  # 4 bars for ambient (longer loops)
bps = beat_samples(BPM)

# Pad 5: Warm Evolving Pad Loop (Cmaj7, slow LFO)
tt_arr = np.arange(n)/SR
freqs = [NOTE['C3'], NOTE['E3'], NOTE['G3'], NOTE['B3']]
pad = np.zeros(n)
for f in freqs:
    p1 = saw(f, n/SR)[:n]
    p2 = saw(f+0.5, n/SR)[:n]
    pad += (p1 + p2) / (2 * len(freqs))
lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.07*tt_arr)
pad = pad * lfo
pad = lowpass(pad, 1500)
pad = chorus(pad, 0.005, 0.5)
# Smooth fade at edges for clean loop
fade_len = int(SR * 0.5)
pad[:fade_len] *= np.linspace(0, 1, fade_len)
pad[-fade_len:] *= np.linspace(1, 0, fade_len)
save_wav(f'{OUT_I}/05_warm_pad_loop.wav', normalize(pad[:n]))
print("I05 warm pad loop done")

# Pad 6: Deep Drone Loop (beating fundamentals)
d1 = sine(55, n/SR)[:n]*0.5 + sine(55.2, n/SR)[:n]*0.4
d2 = sine(82.5, n/SR)[:n]*0.3 + sine(110, n/SR)[:n]*0.2
drone = d1 + d2
drone = lowpass(drone, 800)
fade_len = int(SR * 0.3)
drone[:fade_len] *= np.linspace(0, 1, fade_len)
drone[-fade_len:] *= np.linspace(1, 0, fade_len)
save_wav(f'{OUT_I}/06_drone_loop.wav', normalize(drone[:n]))
print("I06 drone loop done")

# Pad 7: Rain/Field Recording Loop
rain = pink_noise(n/SR)[:n] * 0.4
# Droplets
drops = np.zeros(n)
for _ in range(100):
    pos = np.random.randint(0, n - int(SR*0.05))
    freq = np.random.uniform(2000, 6000)
    dd = np.random.uniform(0.01, 0.04)
    dn = int(SR*dd)
    drop = np.sin(2*np.pi*freq*np.arange(dn)/SR) * np.exp(-np.arange(dn)/(SR*0.01))
    end = min(pos+dn, n)
    drops[pos:end] += drop[:end-pos] * np.random.uniform(0.05, 0.15)
rain = bandpass(rain + drops, 200, 8000)
save_wav(f'{OUT_I}/07_rain_loop.wav', normalize(rain[:n]))
print("I07 rain loop done")

# Pad 8: Bell/Chime Sequence Loop (random gentle bells)
bells = np.zeros(n)
bell_times = sorted(np.random.uniform(0, n/SR - 0.5, 15))
bell_freqs = [NOTE['C5'], NOTE['E5'], NOTE['G5'], NOTE['A5'], NOTE['C5']*2, NOTE['E5']*0.5, NOTE['G4']]
for bt in bell_times:
    pos = int(bt * SR)
    freq = np.random.choice(bell_freqs)
    bd = 2.5
    bdn = min(int(SR*bd), n-pos)
    tt_b = np.arange(bdn)/SR
    mi = 8.0 * np.exp(-tt_b * 0.8)
    bell = np.sin(2*np.pi*freq*tt_b + mi * np.sin(2*np.pi*freq*3.5*tt_b))
    bell = bell * env_perc(bd, 0.002, 0.15)[:bdn]
    bells[pos:pos+bdn] += bell * np.random.uniform(0.3, 0.7)
bells = delay_echo(bells, 0.3, 0.4, 0.4)
save_wav(f'{OUT_I}/08_bells_loop.wav', normalize(bells[:n]))
print("I08 bells loop done")

# Pad 9: Atmosphere Loop (wind, slowly modulated)
wind = pink_noise(n/SR)[:n]
atmo = np.zeros(n)
prev = 0
tt_arr = np.arange(n)/SR
for i in range(n):
    cutoff = 300 + 1200 * (0.5 + 0.5*np.sin(2*np.pi*0.05*tt_arr[i]))
    rc_val = 1.0/(2*np.pi*cutoff)
    alpha = (1.0/SR)/(rc_val + 1.0/SR)
    atmo[i] = prev + alpha * (wind[i] - prev)
    prev = atmo[i]
save_wav(f'{OUT_I}/09_atmo_loop.wav', normalize(atmo[:n]))
print("I09 atmosphere loop done")

# Pad 10: Ambient Drum Loop (gentle, sparse, brushes-like)
# Use soft noise hits as "brushes"
brush_k = lowpass(sine(80, 0.3) * env_perc(0.3, 0.01, 0.5), 300)
brush_k = normalize(brush_k) 
brush_s = bandpass(noise(0.2) * env_perc(0.2, 0.005, 1.0), 1000, 5000)
brush_s = normalize(brush_s)
brush_h = bandpass(noise(0.08) * env_perc(0.08, 0.002, 3.0), 3000, 8000)
brush_h = normalize(brush_h)

# Very sparse, gentle pattern
kick_pat = [(0, 0.5), (4, 0.5), (8, 0.45), (12, 0.5)]
snare_pat = [(4, 0.35), (12, 0.35)]
hat_pat = [(i*2, 0.25) for i in range(8)]
drum1 = make_drum_loop(BPM, 4, kick_pat, snare_pat, hat_pat,
                        kick_sound=brush_k, snare_sound=brush_s, hat_sound=brush_h)
drum1 = lowpass(drum1, 5000)
drum1 = delay_echo(drum1, 0.25, 0.35, 0.4)
save_wav(f'{OUT_I}/10_ambient_drum_loop.wav', normalize(drum1[:n]))
print("I10 ambient drum loop done")

# Pad 11: Shimmer/Reverb Wash Loop
wash = np.zeros(n)
tt_arr = np.arange(n)/SR
# Periodic bright pings into reverb
for i in range(8):
    pos = int(i * n / 8)
    freq = np.random.choice([880, 1320, 1760, 2640])
    ping_n = int(SR * 0.02)
    ping = np.sin(2*np.pi*freq*np.arange(ping_n)/SR) * np.exp(-np.arange(ping_n)/(SR*0.01))
    if pos + ping_n < n:
        wash[pos:pos+ping_n] += ping * 0.5
    # Reverb tail
    for d in np.linspace(0.03, 1.5, 40):
        offset = pos + int(d * SR)
        if offset >= n: break
        decay = 0.9 ** (d * 8)
        freq_s = freq * (1 + d*0.08)
        ed = 0.02
        en = min(int(SR*ed), n-offset)
        echo = np.sin(2*np.pi*freq_s*np.arange(en)/SR) * np.exp(-np.arange(en)/(SR*0.015))
        wash[offset:offset+en] += echo * decay * 0.2
wash = lowpass(wash, 8000)
save_wav(f'{OUT_I}/11_shimmer_loop.wav', normalize(wash[:n]))
print("I11 shimmer loop done")

# Pad 12: Glass Pad Loop (bright, crystalline harmonics)
tt_arr = np.arange(n)/SR
glass = np.zeros(n)
for harm in [880, 1320, 1760, 2640, 3520]:
    glass += sine(harm, n/SR)[:n] * (880/harm)
lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.06*tt_arr)
glass = glass * lfo
glass = chorus(glass, 0.003, 0.7)
glass = lowpass(glass, 5000)
fade_len = int(SR * 0.5)
glass[:fade_len] *= np.linspace(0, 1, fade_len)
glass[-fade_len:] *= np.linspace(1, 0, fade_len)
save_wav(f'{OUT_I}/12_glass_pad_loop.wav', normalize(glass[:n]))
print("I12 glass pad loop done")
print("=== BANK I LOOPS COMPLETE ===\n")

# ============================================
# BANK J: UTILITY/FX LOOPS
# ============================================
OUT_J = os.path.join(STAGING_BASE, 'J-UtilityFX')
BPM = 120  # Reference tempo for utility loops
n = bar_samples(BPM, 2)
bps = beat_samples(BPM)

# Pad 5: Vinyl Crackle Loop (continuous, loopable)
tex_dur = n/SR
surface = pink_noise(tex_dur)[:n] * 0.07
surface = bandpass(surface, 300, 5000)
pops = np.zeros(n)
for _ in range(70):
    pos = np.random.randint(0, n-100)
    w = np.random.randint(3, 40)
    end = min(pos+w, n)
    pops[pos:end] = np.random.uniform(-0.25, 0.25)
pops = highpass(pops, 500)
vinyl = surface + pops * 0.35
vinyl = lowpass(vinyl, 8000)
vinyl += sine(60, tex_dur)[:n] * 0.015  # 60Hz hum
save_wav(f'{OUT_J}/05_vinyl_loop.wav', normalize(vinyl[:n], 0.5))
print("J05 vinyl loop done")

# Pad 6: Tape Hiss Loop (continuous)
hiss = bandpass(noise(n/SR)[:n], 2000, 12000) * 0.12
tt_arr = np.arange(n)/SR
mod = 1.0 + 0.03 * np.sin(2*np.pi*0.5*tt_arr)
hiss = hiss * mod
save_wav(f'{OUT_J}/06_tape_hiss_loop.wav', normalize(hiss[:n], 0.4))
print("J06 tape hiss loop done")

# Pad 7: Rhythmic Glitch Pattern Loop
step = sixteenth_samples(BPM)
glitch = np.zeros(n)
for i in range(0, n, step):
    end = min(i+step, n)
    length = end - i
    choice = np.random.randint(0, 5)
    if choice == 0:
        freq = np.random.uniform(200, 4000)
        glitch[i:end] = np.sin(2*np.pi*freq*np.arange(length)/SR) * 0.6
    elif choice == 1:
        glitch[i:end] = noise(length/SR)[:length] * 0.4
    elif choice == 2:
        pass  # silence
    elif choice == 3:
        freq = np.random.uniform(100, 2000)
        sig = np.sin(2*np.pi*freq*np.arange(length)/SR)
        glitch[i:end] = np.round(sig * 4) / 4 * 0.5
    elif choice == 4:
        f1 = np.random.uniform(300, 1500)
        f2 = np.random.uniform(500, 3000)
        glitch[i:end] = (np.sin(2*np.pi*f1*np.arange(length)/SR) *
                          np.sin(2*np.pi*f2*np.arange(length)/SR)) * 0.4
    window = np.hanning(length)
    glitch[i:end] *= window
save_wav(f'{OUT_J}/07_glitch_loop.wav', normalize(glitch[:n]))
print("J07 glitch loop done")

# Pad 8: Sub Pulse Loop (rhythmic sub bass pulses)
sub = np.zeros(n)
for b in range(8):
    pos = int(b * bps)
    pd = 0.4
    pn = min(int(SR*pd), n-pos)
    if pn <= 0: continue
    pe = np.exp(-np.arange(pn)/(SR*0.1))
    pulse = np.sin(2*np.pi*40*np.arange(pn)/SR) * pe
    sub[pos:pos+pn] += pulse * 0.8
sub = lowpass(sub, 150)
sub = saturate(sub, 1.5)
save_wav(f'{OUT_J}/08_sub_pulse_loop.wav', normalize(sub[:n]))
print("J08 sub pulse loop done")

# Pad 9: Riser Loop (builds every 2 bars then resets)
tt_arr = np.arange(n)/SR
total_dur = n/SR
riser = pitch_sweep(80, 4000, total_dur)[:n]
rns = noise(total_dur)[:n] * np.linspace(0, 0.5, n)
rns = highpass(rns, 1000)
riser_loop = riser * np.linspace(0.1, 0.9, n) * 0.5 + rns * 0.4
riser_loop = saturate(riser_loop, 1.5)
save_wav(f'{OUT_J}/09_riser_loop.wav', normalize(riser_loop[:n]))
print("J09 riser loop done")

# Pad 10: Transition Swoosh Loop (periodic swooshes)
swoosh = np.zeros(n)
for b in [0, 4]:
    pos = int(b * bps)
    sd = 1.5
    sn = min(int(SR*sd), n-pos)
    if sn <= 0: continue
    sw = noise(sd)[:sn]
    filt = np.zeros(sn)
    prev_s = 0
    for i in range(sn):
        p = i/sn
        cutoff = 200 + 8000 * np.sin(np.pi * p)
        rc_val = 1.0/(2*np.pi*cutoff)
        alpha = (1.0/SR)/(rc_val + 1.0/SR)
        filt[i] = prev_s + alpha * (sw[i] - prev_s)
        prev_s = filt[i]
    vol = np.sin(np.pi * np.linspace(0, 1, sn))
    swoosh[pos:pos+sn] += filt * vol * 0.7
save_wav(f'{OUT_J}/10_swoosh_loop.wav', normalize(swoosh[:n]))
print("J10 swoosh loop done")

# Pad 11: Click Track / Metronome Loop (handy for jamming)
click = np.zeros(n)
for b in range(8):
    pos = int(b * bps)
    freq = 1500 if b % 4 == 0 else 1000
    vol = 0.8 if b % 4 == 0 else 0.5
    cd = 0.02
    cn = min(int(SR*cd), n-pos)
    cl = np.sin(2*np.pi*freq*np.arange(cn)/SR) * env_perc(cd, 0.0001, 5.0)[:cn]
    click[pos:pos+cn] += cl * vol
save_wav(f'{OUT_J}/11_click_loop.wav', normalize(click[:n]))
print("J11 click loop done")

# Pad 12: Room Tone Loop (subtle ambience)
room = pink_noise(n/SR)[:n] * 0.08
room = lowpass(room, 2000)
room += sine(120, n/SR)[:n] * 0.015
room += sine(240, n/SR)[:n] * 0.008
save_wav(f'{OUT_J}/12_room_loop.wav', normalize(room[:n], 0.25))
print("J12 room loop done")
print("=== BANK J LOOPS COMPLETE ===")
