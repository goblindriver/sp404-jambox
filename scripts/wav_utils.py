#!/usr/bin/env python3
"""
WAV utility functions for SP-404 sample processing.
Builds WAVs with the exact structure the SP-404 expects:
  RIFF header (12) + fmt chunk (24) + RLND chunk (468) + data chunk header (8) = 512
  Sample data begins at offset 512.

Based on reverse engineering from @uttori/audio-wave, super-pads, and sp404loader.
"""
import struct, os, wave, subprocess

SR = 44100
BANKS = 'ABCDEFGHIJ'
RLND_DEVICE = b'roifspsx'

# RLND payload is 460 bytes (not the standard 458) so that:
# 12 (RIFF) + 24 (fmt) + 468 (RLND chunk) + 8 (data header) = 512
RLND_PAYLOAD_SIZE = 460


def _make_rlnd_chunk(bank_letter, pad_number):
    """Create RLND chunk (468 bytes: 8 header + 460 payload).
    Sized so data payload lands at offset 512 in the final WAV.
    """
    bank_idx = BANKS.index(bank_letter.upper())
    sample_index = bank_idx * 12 + (pad_number - 1)

    payload = bytearray(RLND_PAYLOAD_SIZE)
    payload[0:8] = RLND_DEVICE
    payload[8:12] = b'\x04\x00\x00\x00'
    payload[12] = sample_index

    return b'RLND' + struct.pack('<I', RLND_PAYLOAD_SIZE) + bytes(payload)


def _read_raw_pcm(wav_path):
    """Read raw PCM samples from a WAV file."""
    with wave.open(wav_path, 'rb') as w:
        nframes = w.getnframes()
        return w.readframes(nframes), nframes


def _trim_silence(pcm_data, threshold_db=-50.0, chunk_ms=10):
    """Trim leading silence from raw 16-bit mono PCM data.
    Returns trimmed PCM bytes.
    """
    import numpy as np
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float64)
    chunk_samples = int(SR * chunk_ms / 1000)
    if chunk_samples == 0:
        return pcm_data

    threshold_linear = 32767.0 * (10 ** (threshold_db / 20))

    trim_frames = 0
    for start in range(0, len(samples) - chunk_samples, chunk_samples):
        chunk = samples[start:start + chunk_samples]
        if np.max(np.abs(chunk)) > threshold_linear:
            break
        trim_frames += chunk_samples

    if trim_frames == 0:
        return pcm_data

    return pcm_data[trim_frames * 2:]  # 2 bytes per 16-bit sample


def build_sp404_wav(pcm_data, bank_letter, pad_number):
    """Build a complete SP-404 compatible WAV from raw 16-bit mono PCM.

    Structure: RIFF(12) + fmt(24) + RLND(468) + data(8+N) = 512 + N
    Sample data begins at exactly offset 512.
    """
    # fmt chunk: 24 bytes (8 header + 16 payload)
    fmt_chunk = b'fmt ' + struct.pack('<I', 16)
    fmt_chunk += struct.pack('<HHIIHH', 1, 1, SR, SR * 2, 2, 16)

    # RLND chunk: 468 bytes
    rlnd_chunk = _make_rlnd_chunk(bank_letter, pad_number)

    # data chunk
    data_chunk = b'data' + struct.pack('<I', len(pcm_data)) + pcm_data

    # RIFF header
    body = fmt_chunk + rlnd_chunk + data_chunk
    riff = b'RIFF' + struct.pack('<I', 4 + len(body)) + b'WAVE'

    return riff + body


def convert_and_tag(src, dst, bank_letter, pad_number, trim_silence=True):
    """Full pipeline: convert any audio to SP-404 format.

    1. ffmpeg converts to 16-bit/44.1kHz/mono PCM WAV (temp file)
    2. Read raw PCM data
    3. Optionally trim leading silence
    4. Rebuild as clean WAV with RLND chunk, data at offset 512
    """
    # Step 1: ffmpeg to temp WAV
    tmp = dst + '.tmp.wav'
    try:
        subprocess.run([
            '/opt/homebrew/bin/ffmpeg', '-y', '-i', src,
            '-ar', '44100', '-ac', '1', '-sample_fmt', 's16', '-c:a', 'pcm_s16le',
            tmp
        ], capture_output=True, timeout=30)

        if not os.path.exists(tmp):
            return False

        # Step 2: Read raw PCM
        pcm_data, _ = _read_raw_pcm(tmp)

        # Step 3: Trim silence
        if trim_silence:
            try:
                pcm_data = _trim_silence(pcm_data)
            except Exception:
                pass

        # Step 4: Build clean SP-404 WAV
        wav_data = build_sp404_wav(pcm_data, bank_letter, pad_number)

        with open(dst, 'wb') as f:
            f.write(wav_data)

        return True
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def build_sp404_wav_from_samples(samples_int16, bank_letter, pad_number):
    """Build SP-404 WAV from a numpy int16 array (for synthesized sounds)."""
    pcm_data = samples_int16.tobytes()
    return build_sp404_wav(pcm_data, bank_letter, pad_number)
