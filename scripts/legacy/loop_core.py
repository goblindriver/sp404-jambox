import os

# Loop generation utilities - extends synth_core
exec(open(os.path.join(os.path.dirname(__file__), 'synth_core.py')).read())

def bar_samples(bpm, bars=2, beats_per_bar=4):
    """Exact sample count for clean looping"""
    return int(SR * (60.0/bpm) * beats_per_bar * bars)

def beat_samples(bpm):
    """Samples per beat"""
    return int(SR * 60.0/bpm)

def sixteenth_samples(bpm):
    """Samples per 16th note"""
    return int(SR * 60.0/bpm / 4)

def make_drum_loop(bpm, bars, kick_pattern, snare_pattern, hat_pattern, 
                    perc_pattern=None, kick_sound=None, snare_sound=None, 
                    hat_sound=None, perc_sound=None, swing=0.0):
    """
    Build a drum loop from patterns.
    Patterns are lists of (beat_position, velocity) tuples.
    beat_position is in beats (0-indexed), velocity 0.0-1.0
    """
    n = bar_samples(bpm, bars)
    loop = np.zeros(n)
    bps = beat_samples(bpm)
    
    def place_hit(sig, beat_pos, vel=1.0):
        # Apply swing to offbeat 16ths
        pos_in_beat = beat_pos % 1
        if abs(pos_in_beat - 0.25) < 0.01 or abs(pos_in_beat - 0.75) < 0.01:
            beat_pos += swing * 0.25  # swing offset
        start = int(beat_pos * bps)
        if start < 0: start = 0
        if start >= n: return
        end = min(start + len(sig), n)
        loop[start:end] += sig[:end-start] * vel
    
    if kick_sound is not None:
        for pos, vel in kick_pattern:
            place_hit(kick_sound, pos, vel)
    if snare_sound is not None:
        for pos, vel in snare_pattern:
            place_hit(snare_sound, pos, vel)
    if hat_sound is not None:
        for pos, vel in hat_pattern:
            place_hit(hat_sound, pos, vel)
    if perc_sound is not None and perc_pattern is not None:
        for pos, vel in perc_pattern:
            place_hit(perc_sound, pos, vel)
    
    return loop

def make_bass_loop(bpm, bars, note_seq):
    """
    Build a bass loop from a note sequence.
    note_seq: list of (beat_pos, freq, duration_beats, velocity, waveform)
    waveform: 'sine', 'saw', 'square'
    """
    n = bar_samples(bpm, bars)
    loop = np.zeros(n)
    bps = beat_samples(bpm)
    
    for beat_pos, freq, dur_beats, vel, wave in note_seq:
        start = int(beat_pos * bps)
        dur_samp = int(dur_beats * bps)
        if start >= n: continue
        end = min(start + dur_samp, n)
        actual_dur = (end - start) / SR
        
        if wave == 'sine':
            note = sine(freq, actual_dur)
        elif wave == 'saw':
            note = saw(freq, actual_dur)
        elif wave == 'square':
            note = square(freq, actual_dur, 0.35)
        else:
            note = sine(freq, actual_dur)
        
        env = env_adsr(actual_dur, 0.005, 0.05, 0.7, 0.05)
        note = note[:len(env)] * env[:len(note)]
        note = lowpass(note, min(freq * 8, 4000))
        
        length = min(len(note), end - start)
        loop[start:start+length] += note[:length] * vel
    
    return loop

def make_melodic_loop(bpm, bars, note_seq, wave='saw', filter_cutoff=3000, 
                       attack=0.01, release=0.05, detune=0.0):
    """
    Build a melodic/synth loop.
    note_seq: list of (beat_pos, freq, duration_beats, velocity)
    """
    n = bar_samples(bpm, bars)
    loop = np.zeros(n)
    bps = beat_samples(bpm)
    
    for beat_pos, freq, dur_beats, vel in note_seq:
        start = int(beat_pos * bps)
        dur_samp = int(dur_beats * bps)
        if start >= n: continue
        end = min(start + dur_samp, n)
        actual_dur = (end - start) / SR
        
        if wave == 'saw':
            note = saw(freq, actual_dur)
            if detune > 0:
                note = (note + saw(freq + detune, actual_dur)) / 2
        elif wave == 'square':
            note = square(freq, actual_dur, 0.4)
        elif wave == 'sine':
            note = sine(freq, actual_dur)
        elif wave == 'fm':
            note = fm_synth(freq, freq*2, 3, actual_dur)
        else:
            note = saw(freq, actual_dur)
        
        env = env_adsr(actual_dur, attack, 0.05, 0.6, release)
        note = note[:len(env)] * env[:len(note)]
        note = lowpass(note, filter_cutoff)
        
        length = min(len(note), end - start)
        loop[start:start+length] += note[:length] * vel
    
    return loop

def make_pad_loop(bpm, bars, chord_seq, wave='saw', detune=0.5):
    """
    Build a pad/chord loop.
    chord_seq: list of (beat_pos, [freqs], duration_beats, velocity)
    """
    n = bar_samples(bpm, bars)
    loop = np.zeros(n)
    bps = beat_samples(bpm)
    
    for beat_pos, freqs, dur_beats, vel in chord_seq:
        start = int(beat_pos * bps)
        dur_samp = int(dur_beats * bps)
        if start >= n: continue
        end = min(start + dur_samp, n)
        actual_dur = (end - start) / SR
        
        chord = np.zeros(end - start)
        for freq in freqs:
            if wave == 'saw':
                p1 = saw(freq, actual_dur)
                p2 = saw(freq + detune, actual_dur)
                partial = (p1 + p2) / 2
            elif wave == 'sine':
                partial = sine(freq, actual_dur)
            else:
                partial = saw(freq, actual_dur)
            
            env = env_adsr(actual_dur, 0.15, 0.1, 0.7, 0.2)
            partial = partial[:len(env)] * env[:len(partial)]
            length = min(len(partial), end - start)
            chord[:length] += partial[:length] / len(freqs)
        
        chord = lowpass(chord, 2500)
        loop[start:end] += chord[:end-start] * vel
    
    return loop

# Musical note frequencies
NOTE = {
    'C1': 32.7, 'D1': 36.7, 'E1': 41.2, 'F1': 43.7, 'G1': 49.0, 'A1': 55.0, 'B1': 61.7,
    'C2': 65.4, 'D2': 73.4, 'Eb2': 77.8, 'E2': 82.4, 'F2': 87.3, 'G2': 98.0, 'Ab2': 103.8, 'A2': 110.0, 'Bb2': 116.5, 'B2': 123.5,
    'C3': 130.8, 'Db3': 138.6, 'D3': 146.8, 'Eb3': 155.6, 'E3': 164.8, 'F3': 174.6, 'Gb3': 185.0, 'G3': 196.0, 'Ab3': 207.7, 'A3': 220.0, 'Bb3': 233.1, 'B3': 246.9,
    'C4': 261.6, 'Db4': 277.2, 'D4': 293.7, 'Eb4': 311.1, 'E4': 329.6, 'F4': 349.2, 'Gb4': 370.0, 'G4': 392.0, 'Ab4': 415.3, 'A4': 440.0, 'Bb4': 466.2, 'B4': 493.9,
    'C5': 523.3, 'D5': 587.3, 'Eb5': 622.3, 'E5': 659.3, 'F5': 698.5, 'G5': 784.0, 'A5': 880.0,
}
