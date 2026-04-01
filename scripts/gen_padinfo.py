#!/usr/bin/env python3
"""
Generate PAD_INFO.BIN for the SP-404SX SD card.
Sets per-pad metadata: loop mode, gate, volume, BPM, sample boundaries.

Based on the binary format reverse-engineered by @uttori/audio-padinfo.
Format: 120 pads x 32 bytes = 3,840 bytes, big-endian throughout.
"""
import struct, os, glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
SMPL_DIR = os.path.join(REPO_DIR, "sd-card-template", "ROLAND", "SP-404SX", "SMPL")

# Bank config: letter -> BPM
BANK_BPM = {
    'A': 120.0,  # user bank, default
    'B': 120.0,  # novelty FX
    'C': 88.0,   # lo-fi hip-hop
    'D': 70.0,   # witch house
    'E': 130.0,  # nu-rave
    'F': 120.0,  # electroclash
    'G': 110.0,  # funk & horns
    'H': 140.0,  # IDM
    'I': 105.0,  # ambient
    'J': 120.0,  # utility/FX
}

BANKS = 'ABCDEFGHIJ'


def encode_pad(sample_end=512, volume=127, lofi=False, loop=False, gate=True,
               reverse=False, channels=1, tempo_mode=0, bpm=120.0):
    """Encode a single 32-byte pad record (big-endian)."""
    sample_start = 512  # standard RIFF header offset
    if sample_end < sample_start:
        sample_end = sample_start
    return struct.pack('>IIII BBBBBBBB II',
        sample_start,           # originalSampleStart
        sample_end,             # originalSampleEnd
        sample_start,           # userSampleStart
        sample_end,             # userSampleEnd
        min(volume, 127),       # volume (0-127)
        1 if lofi else 0,       # lofi
        1 if loop else 0,       # loop
        1 if gate else 0,       # gate
        1 if reverse else 0,    # reverse
        1,                      # format: WAVE
        channels,               # 1=mono, 2=stereo
        tempo_mode,             # 0=Off, 1=Pattern, 2=User
        round(bpm * 10),        # originalTempo (BPM x 10)
        round(bpm * 10),        # userTempo (BPM x 10)
    )


def get_sample_path(bank, pad, smpl_dir):
    """Find the WAV file for a given bank/pad."""
    filename = f"{bank}{pad:07d}.WAV"
    path = os.path.join(smpl_dir, filename)
    if os.path.exists(path):
        return path
    return None


def generate_padinfo(smpl_dir=None):
    """Generate a complete PAD_INFO.BIN (3,840 bytes)."""
    if smpl_dir is None:
        smpl_dir = SMPL_DIR

    pad_records = []
    occupied = 0

    for bank_idx, bank in enumerate(BANKS):
        bpm = BANK_BPM.get(bank, 120.0)
        for pad_num in range(1, 13):
            wav_path = get_sample_path(bank, pad_num, smpl_dir)

            if wav_path:
                file_size = os.path.getsize(wav_path)
                is_loop = pad_num >= 5  # pads 5-12 are loops
                record = encode_pad(
                    sample_end=file_size,
                    volume=127,
                    loop=is_loop,
                    gate=not is_loop,  # gate for one-shots (pads 1-4)
                    channels=1,        # our pipeline outputs mono
                    tempo_mode=0,      # off (let user control)
                    bpm=bpm,
                )
                occupied += 1
            else:
                # Empty pad — default values
                record = encode_pad()

            pad_records.append(record)

    padinfo_bin = b''.join(pad_records)
    assert len(padinfo_bin) == 3840, f"Expected 3840 bytes, got {len(padinfo_bin)}"

    out_path = os.path.join(smpl_dir, "PAD_INFO.BIN")
    with open(out_path, 'wb') as f:
        f.write(padinfo_bin)

    print(f"Generated PAD_INFO.BIN ({len(padinfo_bin)} bytes, {occupied}/120 pads occupied)")
    print(f"  Written to: {out_path}")
    return out_path


if __name__ == '__main__':
    import sys
    smpl = sys.argv[1] if len(sys.argv) > 1 else None
    generate_padinfo(smpl)
