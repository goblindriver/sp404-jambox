#!/usr/bin/env python3
"""
Generate PAD_INFO.BIN for the SP-404SX SD card.
Sets per-pad metadata: loop mode, gate, volume, BPM, sample boundaries.

Based on the binary format reverse-engineered by @uttori/audio-padinfo.
Format: 120 pads x 32 bytes = 3,840 bytes, big-endian throughout.
"""
import os
import struct

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
SMPL_DIR = os.path.join(REPO_DIR, "sd-card-template", "ROLAND", "SP-404SX", "SMPL")
CONFIG_PATH = os.path.join(REPO_DIR, "bank_config.yaml")

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


def _load_bank_bpms():
    bpms = {bank: 120.0 for bank in BANKS}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except (FileNotFoundError, OSError, yaml.YAMLError):
        return bpms

    if not isinstance(payload, dict):
        return bpms

    for bank in BANKS:
        entry = payload.get(f"bank_{bank.lower()}")
        if not isinstance(entry, dict):
            continue
        bpm = entry.get("bpm")
        try:
            if bpm is not None:
                bpms[bank] = float(bpm)
        except (TypeError, ValueError):
            continue
    return bpms


def generate_padinfo(smpl_dir=None):
    """Generate a complete PAD_INFO.BIN (3,840 bytes)."""
    if smpl_dir is None:
        smpl_dir = SMPL_DIR
    os.makedirs(smpl_dir, exist_ok=True)

    pad_records = []
    occupied = 0
    bank_bpms = _load_bank_bpms()

    for bank_idx, bank in enumerate(BANKS):
        bpm = bank_bpms.get(bank, 120.0)
        for pad_num in range(1, 13):
            wav_path = get_sample_path(bank, pad_num, smpl_dir)

            if wav_path:
                try:
                    file_size = os.path.getsize(wav_path)
                except OSError:
                    file_size = 0
                if file_size > 0:
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
                    record = encode_pad()
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
