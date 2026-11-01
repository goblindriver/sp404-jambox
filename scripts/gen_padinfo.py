#!/usr/bin/env python3
"""
Generate PAD_INFO.BIN for the SP-404SX SD card.
Sets per-pad metadata: loop mode, gate, volume, BPM, sample boundaries.

Loop/gate come from each pad description's playability in bank_config.yaml
(loop/chop-ready pads loop, drum hits gate, transitions play through), not
from the pad number.

Based on the binary format reverse-engineered by @uttori/audio-padinfo.
Format: 120 pads x 32 bytes = 3,840 bytes, big-endian throughout.
"""
import os
import struct
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jambox_config import load_settings_for_script
from tag_vocab import pad_type_and_playability

SETTINGS = load_settings_for_script(__file__)
SMPL_DIR = SETTINGS["SMPL_DIR"]
CONFIG_PATH = SETTINGS["CONFIG_PATH"]

BANKS = 'ABCDEFGHIJ'
DRUM_HIT_TYPES = frozenset({"KIK", "SNR", "HAT", "PRC", "CLP", "CYM", "RIM"})


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


def pad_mode(description, pad_num):
    """(loop, gate) for a pad, from its description's playability.

    loop / chop-ready  -> loop
    chromatic          -> gate (note length follows the pad press)
    one-shot drum hit  -> gate
    other one-shots, transitions, layers -> play through (neither)
    no playability     -> legacy layout rule: pads 1-4 gate, 5-12 loop
    """
    type_code, playability = pad_type_and_playability(description)
    if playability in ("loop", "chop-ready"):
        return True, False
    if playability == "chromatic":
        return False, True
    if playability == "one-shot" and type_code in DRUM_HIT_TYPES:
        return False, True
    if playability in ("one-shot", "transition", "layer"):
        return False, False
    is_loop = pad_num >= 5
    return is_loop, not is_loop


def _load_banks():
    """{bank: (bpm, {pad_num: description})} from bank_config.yaml."""
    banks = {bank: (120.0, {}) for bank in BANKS}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except (FileNotFoundError, OSError, yaml.YAMLError):
        return banks

    if not isinstance(payload, dict):
        return banks

    for bank in BANKS:
        entry = payload.get(f"bank_{bank.lower()}")
        if not isinstance(entry, dict):
            continue
        bpm = 120.0
        try:
            if entry.get("bpm") is not None:
                bpm = float(entry["bpm"])
        except (TypeError, ValueError):
            pass
        pads = {}
        for num, desc in (entry.get("pads") or {}).items():
            try:
                pads[int(num)] = desc
            except (TypeError, ValueError):
                continue
        banks[bank] = (bpm, pads)
    return banks


def generate_padinfo(smpl_dir=None):
    """Generate a complete PAD_INFO.BIN (3,840 bytes)."""
    if smpl_dir is None:
        smpl_dir = SMPL_DIR
    os.makedirs(smpl_dir, exist_ok=True)

    pad_records = []
    occupied = 0
    banks = _load_banks()

    for bank in BANKS:
        bpm, descriptions = banks[bank]
        for pad_num in range(1, 13):
            wav_path = get_sample_path(bank, pad_num, smpl_dir)

            if wav_path:
                try:
                    file_size = os.path.getsize(wav_path)
                except OSError:
                    file_size = 0
                if file_size > 0:
                    loop, gate = pad_mode(descriptions.get(pad_num), pad_num)
                    record = encode_pad(
                        sample_end=file_size,
                        volume=127,
                        loop=loop,
                        gate=gate,
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
    smpl = sys.argv[1] if len(sys.argv) > 1 else None
    generate_padinfo(smpl)
