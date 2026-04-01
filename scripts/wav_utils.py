#!/usr/bin/env python3
"""
WAV utility functions for SP-404SX sample processing.
- RLND chunk injection (proprietary Roland header for pad metadata)
- Leading silence trimming
- SP-404 format conversion wrapper

Based on reverse engineering from @uttori/audio-wave and sp404loader.
"""
import struct, os, wave, subprocess, tempfile


# === RLND Chunk Injection ===
# The SP-404SX expects a proprietary "RLND" chunk in WAV files.
# Format: 466 bytes total (8-byte header + 458-byte payload)
# Device: "roifspsx" (8 chars), sample index at byte 20.

RLND_DEVICE = b'roifspsx'
RLND_PAYLOAD_SIZE = 458
RLND_UNKNOWN_BYTES = b'\x04\x00\x00\x00'

BANKS = 'ABCDEFGHIJ'


def make_rlnd_chunk(bank_letter, pad_number):
    """Create a 466-byte RLND chunk for the given bank/pad.

    Args:
        bank_letter: 'A' through 'J'
        pad_number: 1 through 12

    Returns:
        bytes: 466-byte RLND chunk ready to insert into a WAV file
    """
    bank_idx = BANKS.index(bank_letter.upper())
    sample_index = bank_idx * 12 + (pad_number - 1)

    payload = bytearray(RLND_PAYLOAD_SIZE)
    # Device string at offset 0 (relative to payload start)
    payload[0:8] = RLND_DEVICE
    # Unknown bytes at offset 8
    payload[8:12] = RLND_UNKNOWN_BYTES
    # Sample index at offset 12
    payload[12] = sample_index
    # Rest is zero-padded (already zeroed by bytearray)

    # Chunk header: "RLND" + UInt32LE size
    header = b'RLND' + struct.pack('<I', RLND_PAYLOAD_SIZE)
    return header + bytes(payload)


def inject_rlnd(wav_path, bank_letter, pad_number):
    """Inject an RLND chunk into an existing WAV file.

    Inserts the RLND chunk just before the 'data' chunk in the RIFF structure.
    Updates the RIFF file size accordingly.
    """
    with open(wav_path, 'rb') as f:
        data = bytearray(f.read())

    # Verify RIFF header
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise ValueError(f"Not a valid WAV file: {wav_path}")

    # Check if RLND chunk already exists
    if b'RLND' in data:
        return  # already has it

    rlnd = make_rlnd_chunk(bank_letter, pad_number)

    # Find the 'data' chunk and insert RLND before it
    pos = 12  # skip RIFF header (12 bytes)
    while pos < len(data) - 8:
        chunk_id = data[pos:pos+4]
        chunk_size = struct.unpack('<I', data[pos+4:pos+8])[0]
        if chunk_id == b'data':
            # Insert RLND chunk here
            data[pos:pos] = rlnd
            break
        pos += 8 + chunk_size
        # Word-align
        if chunk_size % 2:
            pos += 1

    # Update RIFF size (total file size - 8)
    struct.pack_into('<I', data, 4, len(data) - 8)

    with open(wav_path, 'wb') as f:
        f.write(data)


# === Leading Silence Trimming ===
# Adapted from sp404loader's approach using raw sample analysis.

def trim_leading_silence(wav_path, threshold_db=-50.0, chunk_ms=10):
    """Trim leading silence from a WAV file in-place.

    Args:
        wav_path: Path to WAV file
        threshold_db: dBFS threshold below which audio is considered silence
        chunk_ms: Chunk size in milliseconds for analysis

    Returns:
        float: Seconds of silence trimmed
    """
    with wave.open(wav_path, 'rb') as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        sw = w.getsampwidth()
        nframes = w.getnframes()
        raw = w.readframes(nframes)

    if sw != 2:  # only handle 16-bit
        return 0.0

    import numpy as np
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    if nch > 1:
        samples = samples[::nch]  # take first channel for analysis

    chunk_samples = int(sr * chunk_ms / 1000)
    if chunk_samples == 0:
        return 0.0

    # Convert threshold from dB to linear amplitude
    # dBFS: 0 dB = full scale (32767), threshold_db is negative
    ref = 32767.0
    threshold_linear = ref * (10 ** (threshold_db / 20))

    trim_frames = 0
    for start in range(0, len(samples) - chunk_samples, chunk_samples):
        chunk = samples[start:start + chunk_samples]
        peak = np.max(np.abs(chunk))
        if peak > threshold_linear:
            break
        trim_frames += chunk_samples

    if trim_frames == 0:
        return 0.0

    # Trim by re-reading and writing from the trim point
    trimmed_seconds = trim_frames / sr
    with wave.open(wav_path, 'rb') as w:
        params = w.getparams()
        w.setpos(trim_frames)
        remaining = w.readframes(nframes - trim_frames)

    with wave.open(wav_path, 'wb') as w:
        w.setparams(params._replace(nframes=nframes - trim_frames))
        w.writeframes(remaining)

    return trimmed_seconds


# === SP-404 Format Conversion ===

def convert_for_sp404(src, dst, trim_silence=True):
    """Convert any audio file to SP-404 compatible format and optionally trim silence.

    Output: 16-bit / 44.1kHz / Mono / PCM WAV

    Args:
        src: Source audio file path
        dst: Destination WAV path
        trim_silence: Whether to trim leading silence

    Returns:
        bool: True if conversion succeeded
    """
    result = subprocess.run([
        'ffmpeg', '-y', '-i', src,
        '-ar', '44100', '-ac', '1', '-sample_fmt', 's16', '-c:a', 'pcm_s16le',
        dst
    ], capture_output=True, timeout=30)

    if not os.path.exists(dst):
        return False

    if trim_silence:
        try:
            trimmed = trim_leading_silence(dst)
            if trimmed > 0:
                pass  # silence trimmed
        except Exception:
            pass  # non-fatal, keep the file as-is

    return True


def convert_and_tag(src, dst, bank_letter, pad_number, trim_silence=True):
    """Convert audio to SP-404 format, trim silence, and inject RLND chunk.

    This is the full pipeline for preparing a sample for the SP-404SX.
    """
    if not convert_for_sp404(src, dst, trim_silence=trim_silence):
        return False

    try:
        inject_rlnd(dst, bank_letter, pad_number)
    except Exception as e:
        print(f"  Warning: RLND injection failed for {dst}: {e}")
        # Non-fatal — file still works, just without pad metadata

    return True
