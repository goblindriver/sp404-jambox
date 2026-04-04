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
        chroma_mean = np.mean(chroma, axis=1)

        # Normalize
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

    result = {
        'duration': round(duration, 3),
        'bpm': detect_bpm(y, actual_sr),
        'key': detect_key(y, actual_sr),
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
        chroma = librosa.feature.chroma_cqt(y=y, sr=actual_sr)
        result['chroma'] = [round(float(c), 3) for c in np.mean(chroma, axis=1)]

    except Exception:
        # Partial features are fine — return what we have
        pass

    return result
