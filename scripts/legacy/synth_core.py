import numpy as np
import wave
import struct
import os

SR = 44100  # sample rate

def save_wav(filename, samples, sr=SR):
    """Save numpy array as 16-bit mono WAV"""
    samples = np.clip(samples, -1.0, 1.0)
    data = (samples * 32767).astype(np.int16)
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())

def t(dur):
    """Time array for given duration in seconds"""
    return np.linspace(0, dur, int(SR * dur), endpoint=False)

def sine(freq, dur, phase=0):
    return np.sin(2 * np.pi * freq * t(dur) + phase)

def saw(freq, dur):
    return 2.0 * (freq * t(dur) % 1.0) - 1.0

def square(freq, dur, pw=0.5):
    return np.where((freq * t(dur) % 1.0) < pw, 1.0, -1.0)

def noise(dur):
    return np.random.uniform(-1, 1, int(SR * dur))

def pink_noise(dur):
    """Approximate pink noise using filtered white noise"""
    n = int(SR * dur)
    white = np.random.randn(n)
    # Simple pinking filter
    b = np.zeros(n)
    b0 = b1 = b2 = b3 = b4 = b5 = b6 = 0
    for i in range(n):
        w = white[i]
        b0 = 0.99886 * b0 + w * 0.0555179
        b1 = 0.99332 * b1 + w * 0.0750759
        b2 = 0.96900 * b2 + w * 0.1538520
        b3 = 0.86650 * b3 + w * 0.3104856
        b4 = 0.55000 * b4 + w * 0.5329522
        b5 = -0.7616 * b5 - w * 0.0168980
        b[i] = b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362
        b6 = w * 0.115926
    return b / np.max(np.abs(b) + 1e-10)

def env_adsr(dur, a=0.01, d=0.1, s=0.7, r=0.1):
    """ADSR envelope"""
    n = int(SR * dur)
    na = max(int(SR * a), 1)
    nd = max(int(SR * d), 1)
    nr = max(int(SR * r), 1)
    ns = max(n - na - nd - nr, 0)
    
    attack = np.linspace(0, 1, na)
    decay = np.linspace(1, s, nd)
    sustain = np.full(ns, s)
    release = np.linspace(s, 0, nr)
    
    e = np.concatenate([attack, decay, sustain, release])
    if len(e) > n:
        e = e[:n]
    elif len(e) < n:
        e = np.pad(e, (0, n - len(e)))
    return e

def env_perc(dur, a=0.001, decay=0.3):
    """Percussive envelope (fast attack, exponential decay)"""
    n = int(SR * dur)
    na = max(int(SR * a), 1)
    nd = n - na
    attack = np.linspace(0, 1, na)
    dec = np.exp(-np.linspace(0, decay * 10, nd))
    return np.concatenate([attack, dec])[:n]

def env_linear(dur, start=1.0, end=0.0):
    return np.linspace(start, end, int(SR * dur))

def lowpass(sig, cutoff, sr=SR):
    """Simple one-pole lowpass"""
    rc = 1.0 / (2 * np.pi * cutoff)
    dt = 1.0 / sr
    alpha = dt / (rc + dt)
    out = np.zeros_like(sig)
    out[0] = alpha * sig[0]
    for i in range(1, len(sig)):
        out[i] = out[i-1] + alpha * (sig[i] - out[i-1])
    return out

def highpass(sig, cutoff, sr=SR):
    """Simple one-pole highpass"""
    rc = 1.0 / (2 * np.pi * cutoff)
    dt = 1.0 / sr
    alpha = rc / (rc + dt)
    out = np.zeros_like(sig)
    out[0] = sig[0]
    for i in range(1, len(sig)):
        out[i] = alpha * (out[i-1] + sig[i] - sig[i-1])
    return out

def bandpass(sig, low, high, sr=SR):
    return highpass(lowpass(sig, high, sr), low, sr)

def saturate(sig, drive=2.0):
    """Soft clipping saturation"""
    return np.tanh(sig * drive)

def bitcrush(sig, bits=8):
    """Reduce bit depth for lo-fi effect"""
    levels = 2 ** bits
    return np.round(sig * levels) / levels

def decimate(sig, factor=4):
    """Sample rate reduction"""
    out = np.copy(sig)
    for i in range(len(out)):
        if i % factor != 0:
            out[i] = out[i - (i % factor)]
    return out

def chorus(sig, depth=0.002, rate=1.5):
    """Simple chorus effect"""
    n = len(sig)
    tt = np.arange(n) / SR
    delay_samples = (depth * SR * (1 + np.sin(2 * np.pi * rate * tt))).astype(int)
    out = np.copy(sig)
    for i in range(n):
        idx = i - delay_samples[i]
        if 0 <= idx < n:
            out[i] = 0.7 * sig[i] + 0.3 * sig[idx]
    return out

def delay_echo(sig, delay_time=0.15, feedback=0.3, mix=0.3):
    """Simple delay/echo"""
    delay_samp = int(delay_time * SR)
    out = np.copy(sig)
    buf = np.zeros(len(sig) + delay_samp * 4)
    buf[:len(sig)] = sig
    for tap in range(1, 5):
        offset = delay_samp * tap
        gain = feedback ** tap
        if offset < len(buf):
            end = min(len(sig) + offset, len(buf))
            buf[offset:end] += sig[:end-offset] * gain
    out = (1 - mix) * sig + mix * buf[:len(sig)]
    return out / (np.max(np.abs(out)) + 1e-10)

def pitch_sweep(start_freq, end_freq, dur):
    """Generate a pitch sweep"""
    freqs = np.linspace(start_freq, end_freq, int(SR * dur))
    phase = np.cumsum(freqs / SR) * 2 * np.pi
    return np.sin(phase)

def fm_synth(carrier_freq, mod_freq, mod_index, dur):
    """FM synthesis"""
    tt = t(dur)
    mod = mod_index * np.sin(2 * np.pi * mod_freq * tt)
    return np.sin(2 * np.pi * carrier_freq * tt + mod)

def normalize(sig, level=0.95):
    mx = np.max(np.abs(sig))
    if mx > 0:
        return sig * (level / mx)
    return sig

def mix_signals(*signals_and_gains):
    """Mix multiple (signal, gain) tuples"""
    max_len = max(len(s) for s, g in signals_and_gains)
    out = np.zeros(max_len)
    for sig, gain in signals_and_gains:
        out[:len(sig)] += sig * gain
    return out

def resample_env(env_array, target_len):
    """Resample an envelope to a target length"""
    return np.interp(np.linspace(0, 1, target_len), np.linspace(0, 1, len(env_array)), env_array)

print("Synth core loaded OK")
