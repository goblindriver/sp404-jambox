#!/usr/bin/env python3
"""Audio analysis using librosa for BPM, key, and loudness detection.

Falls back gracefully when librosa is not installed — all functions
return None so callers can use filename-based extraction instead.

Usage:
    from audio_analysis import analyze_audio
    result = analyze_audio("/path/to/sample.wav")
    # {'bpm': 128.0, 'key': 'Am', 'loudness_db': -12.3, 'duration': 4.5}
"""

import os

try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

# Krumhansl-Schmuckler key profiles
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
_NOTE_NAMES = ['C', 'Cs', 'D', 'Ds', 'E', 'F', 'Fs', 'G', 'Gs', 'A', 'As', 'B']


def is_available():
    """Check if librosa is available for audio analysis."""
    return LIBROSA_AVAILABLE


def numpy_elision_safe(n=100_000):
    """False when numpy reuses a named array's buffer as if it were a temporary.

    numpy < 2.3 on Python 3.14+ does this for arrays over 256 KB: it corrupted
    every stored chroma vector and librosa key on the iMac from April to
    November 2026 without raising anything. Use a Python numpy supports.
    """
    if not LIBROSA_AVAILABLE:
        return True
    a = np.arange(n, dtype=np.uint32)
    b = a + np.uint32(1)
    _c = b + (b >> 1)
    return bool((b == a + 1).all())


def analyze_audio(filepath, sr=22050):
    """Analyze an audio file for BPM, key, loudness, and duration.

    Returns dict with keys: bpm, key, loudness_db, duration.
    All values may be None if analysis fails.
    """
    if not LIBROSA_AVAILABLE:
        return {'bpm': None, 'key': None, 'loudness_db': None, 'duration': None}

    if not os.path.exists(filepath):
        return {'bpm': None, 'key': None, 'loudness_db': None, 'duration': None}

    try:
        y, actual_sr = librosa.load(filepath, sr=sr, mono=True)
    except Exception:
        return {'bpm': None, 'key': None, 'loudness_db': None, 'duration': None}

    duration = len(y) / actual_sr

    return {
        'bpm': detect_bpm(y, actual_sr),
        'key': detect_key(y, actual_sr),
        'loudness_db': detect_loudness(y),
        'duration': round(duration, 3),
    }


def detect_bpm(y, sr):
    """Detect BPM using librosa's beat tracker.

    Returns float BPM or None.
    """
    if not LIBROSA_AVAILABLE or y is None:
        return None

    try:
        # Need at least ~1 second of audio for beat detection
        if len(y) / sr < 1.0:
            return None

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        # librosa >= 0.10 returns an array, older returns scalar
        if hasattr(tempo, '__len__'):
            tempo = float(tempo[0]) if len(tempo) > 0 else None
        else:
            tempo = float(tempo)

        if tempo and 40 <= tempo <= 250:
            return round(tempo, 1)
    except Exception:
        pass

    return None


def detect_beat_grid(y, sr):
    """Detect tempo and the time of the first beat.

    Karaoke sync needs both: MIDI clock runs at ``bpm`` and the Start message
    goes out at ``first_beat_s`` so the sampler's BPM-synced FX land on the
    song's grid. Returns ``{'bpm': float|None, 'first_beat_s': float|None,
    'beats': [float, ...]}``.
    """
    empty = {'bpm': None, 'first_beat_s': None, 'beats': []}
    if not LIBROSA_AVAILABLE or y is None or len(y) / sr < 1.0:
        return empty
    try:
        tempo, frames = librosa.beat.beat_track(y=y, sr=sr)
        if hasattr(tempo, '__len__'):
            tempo = float(tempo[0]) if len(tempo) > 0 else None
        else:
            tempo = float(tempo)
        beats = [round(float(t), 3) for t in librosa.frames_to_time(frames, sr=sr)]
        if not tempo or not (40 <= tempo <= 250):
            tempo = None
        return {
            'bpm': round(tempo, 1) if tempo else None,
            'first_beat_s': beats[0] if beats else None,
            'beats': beats,
        }
    except Exception:
        return empty


def detect_key(y, sr):
    """Detect musical key using chroma features and Krumhansl-Schmuckler algorithm.

    Returns key string like 'Am', 'C', 'Fs' or None.
    """
    if not LIBROSA_AVAILABLE or y is None:
        return None

    try:
        # Need at least 0.5 seconds
        if len(y) / sr < 0.5:
            return None

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        return key_from_chroma(np.mean(chroma, axis=1))
    except Exception:
        pass

    return None


def key_from_chroma(chroma_mean):
    """Krumhansl-Schmuckler key for a 12-bin mean chroma vector, or None."""
    try:
        chroma_mean = np.asarray(chroma_mean, dtype=float)
        norm = np.linalg.norm(chroma_mean)
        if norm < 1e-6:
            return None
        chroma_mean = chroma_mean / norm

        best_corr = -2.0
        best_key = None

        major = np.array(_MAJOR_PROFILE)
        minor = np.array(_MINOR_PROFILE)

        for shift in range(12):
            shifted = np.roll(chroma_mean, -shift)
            # Major correlation
            corr_maj = np.corrcoef(shifted, major)[0, 1]
            if corr_maj > best_corr:
                best_corr = corr_maj
                best_key = _NOTE_NAMES[shift]

            # Minor correlation
            corr_min = np.corrcoef(shifted, minor)[0, 1]
            if corr_min > best_corr:
                best_corr = corr_min
                best_key = _NOTE_NAMES[shift] + 'm'

        return best_key
    except Exception:
        pass

    return None


def detect_loudness(y):
    """Detect loudness as RMS in dB.

    Returns float dB value or None.
    """
    if not LIBROSA_AVAILABLE or y is None:
        return None

    try:
        rms = np.sqrt(np.mean(y ** 2))
        if rms > 0:
            db = 20 * np.log10(rms)
            return round(float(db), 1)
    except Exception:
        pass

    return None


def _mean_chroma(y, sr):
    """Mean chroma_cqt per pitch class (what both the key and the stored chroma use), or None."""
    try:
        return np.mean(librosa.feature.chroma_cqt(y=y, sr=sr), axis=1)
    except Exception:
        return None


def _key_for(chroma_mean, duration):
    """detect_key() from an already computed mean chroma (keys need 0.5 s of audio)."""
    if chroma_mean is None or duration < 0.5:
        return None
    return key_from_chroma(chroma_mean)


def _rounded_chroma(chroma_mean):
    return [round(float(c), 3) for c in chroma_mean]


def chroma_and_key(filepath, sr=22050):
    """(stored chroma vector, key) exactly as extract_features() computes them, or None.

    Lets a features-only refresh redo just the chroma-derived values.
    """
    if not LIBROSA_AVAILABLE or not os.path.exists(filepath):
        return None
    try:
        y, actual_sr = librosa.load(filepath, sr=sr, mono=True)
    except Exception:
        return None
    if len(y) == 0:
        return None
    chroma_mean = _mean_chroma(y, actual_sr)
    if chroma_mean is None:
        return None
    return _rounded_chroma(chroma_mean), _key_for(chroma_mean, len(y) / actual_sr)


def extract_features(filepath, sr=22050):
    """Extract full spectral features for smart retagging.

    Returns dict with all audio features needed by the LLM tagger,
    or None if analysis fails. Loads audio once and extracts everything.
    """
    if not LIBROSA_AVAILABLE:
        return None

    if not os.path.exists(filepath):
        return None

    try:
        y, actual_sr = librosa.load(filepath, sr=sr, mono=True)
    except Exception:
        return None

    if len(y) == 0:
        return None

    duration = len(y) / actual_sr
    chroma_mean = _mean_chroma(y, actual_sr)

    result = {
        'duration': round(duration, 3),
        'bpm': detect_bpm(y, actual_sr),
        'key': _key_for(chroma_mean, duration),
        'loudness_db': detect_loudness(y),
    }

    try:
        # Spectral centroid — bright vs dark
        centroid = librosa.feature.spectral_centroid(y=y, sr=actual_sr)
        result['spectral_centroid'] = round(float(np.mean(centroid)), 1)

        # Spectral rolloff — high-frequency content
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=actual_sr)
        result['spectral_rolloff'] = round(float(np.mean(rolloff)), 1)

        # Zero-crossing rate — noisy vs tonal
        zcr = librosa.feature.zero_crossing_rate(y)
        result['zero_crossing_rate'] = round(float(np.mean(zcr)), 4)

        # Onset strength — transient character
        onset_env = librosa.onset.onset_strength(y=y, sr=actual_sr)
        result['onset_strength'] = round(float(np.mean(onset_env)), 2)
        result['onset_count'] = int(len(librosa.onset.onset_detect(
            y=y, sr=actual_sr, onset_envelope=onset_env)))

        # RMS envelope — punch vs sustain
        rms = librosa.feature.rms(y=y)[0]
        result['rms_peak'] = round(float(np.max(rms)), 4) if len(rms) > 0 else 0.0
        result['rms_mean'] = round(float(np.mean(rms)), 4) if len(rms) > 0 else 0.0
        # Attack shape: ratio of peak position to duration
        if len(rms) > 1:
            peak_pos = int(np.argmax(rms))
            result['attack_position'] = round(peak_pos / len(rms), 2)
        else:
            result['attack_position'] = 0.0

        # MFCCs — timbral fingerprint (13 coefficients)
        mfcc = librosa.feature.mfcc(y=y, sr=actual_sr, n_mfcc=13)
        result['mfcc'] = [round(float(c), 2) for c in np.mean(mfcc, axis=1)]

        # Chroma — harmonic content (12 pitch classes)
        if chroma_mean is not None:
            result['chroma'] = _rounded_chroma(chroma_mean)

    except Exception:
        # Partial features are fine — return what we have
        pass

    return result
