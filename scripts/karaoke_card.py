#!/usr/bin/env python3
"""Put prepped karaoke songs on SP-404 pads, so the sampler holds the songs.

One song per pad, in the bank you name. Each song pad:

- plays once and starts/stops on a press (Loop off, Gate off: "trigger");
- carries the song's own BPM in PAD_INFO, so the 404's synced effects
  (delay, DJFX looper) follow the song. Tempo mode stays off: the 404 never
  speeds a song up to match a pattern;
- is untrimmed: lyrics and drop sheets count from the song's first sample;
- is stereo by default (the SP-404A plays 6 stereo voices; Owner's Manual p. 8).

It plays ``backing_bv.flac`` (instrumental with backing vocals) when the song
has one and its ``song.json`` doesn't say ``"mix": "dry"``, else ``backing.flac``.

    python scripts/karaoke_card.py --bank C                  # the first 5 songs in _index.json
    python scripts/karaoke_card.py --bank C --count 12
    python scripts/karaoke_card.py --bank C --songs "Le Tigre - Deceptacon" "P.O.S - Fuck Your Stuff"
    python scripts/karaoke_card.py --bank C --mono-check     # + song 1 again in mono on the next pad

Run it after ``gen_padinfo.py`` (which resets every pad to its bank's
defaults) and before ``deploy_sd.py``. It writes into the card template.
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings_for_script  # noqa: E402
from gen_padinfo import encode_pad  # noqa: E402
from wav_utils import BANKS, SR, build_sp404_wav  # noqa: E402

SETTINGS = load_settings_for_script(__file__)
PAD_INFO_SIZE = 3840
RECORD_SIZE = 32
MIN_BPM, MAX_BPM = 40.0, 200.0   # the SP-404A's sync range


def song_audio(song_dir, song):
    """The mix a singer hears: backing vocals kept when there is that mix, unless the song says dry."""
    bv = os.path.join(song_dir, "backing_bv.flac")
    if song.get("mix") != "dry" and os.path.isfile(bv):
        return bv
    return os.path.join(song_dir, "backing.flac")


def pad_bpm(bpm):
    """The song's BPM folded into the 404's 40-200 range (or 120 when unknown)."""
    if not bpm:
        return 120.0
    bpm = float(bpm)
    while bpm > MAX_BPM:
        bpm /= 2
    while bpm < MIN_BPM:
        bpm *= 2
    return round(bpm, 1)


def pcm_s16(src, channels, ffmpeg=None):
    """Raw 16-bit 44.1 kHz PCM (interleaved when stereo), straight from ffmpeg."""
    res = subprocess.run([ffmpeg or SETTINGS["FFMPEG_BIN"], "-v", "error", "-i", src, "-vn",
                          "-ar", str(SR), "-ac", str(channels), "-f", "s16le", "-acodec", "pcm_s16le", "-"],
                         capture_output=True, timeout=600)
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError(f"ffmpeg couldn't convert {src}: {res.stderr.decode('utf-8', 'replace')[-300:]}")
    return res.stdout


def _replace(path, data):
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def write_song_pad(src, smpl_dir, bank, pad, channels, convert=pcm_s16):
    """Write ``{bank}000000{pad}.WAV``; returns (path, size in bytes, seconds)."""
    pcm = convert(src, channels)
    path = os.path.join(smpl_dir, f"{bank}{pad:07d}.WAV")
    data = build_sp404_wav(pcm, bank, pad, channels=channels)
    _replace(path, data)
    return path, len(data), len(pcm) / (SR * 2 * channels)


def patch_padinfo(smpl_dir, records):
    """Swap the given ``{(bank, pad): 32-byte record}`` into PAD_INFO.BIN, keeping every other pad."""
    path = os.path.join(smpl_dir, "PAD_INFO.BIN")
    try:
        with open(path, "rb") as fh:
            table = bytearray(fh.read())
    except FileNotFoundError:
        table = bytearray()
    if len(table) != PAD_INFO_SIZE:
        table = bytearray(b"".join(encode_pad() for _ in range(120)))
    for (bank, pad), record in records.items():
        at = (BANKS.index(bank) * 12 + pad - 1) * RECORD_SIZE
        table[at:at + RECORD_SIZE] = record
    _replace(path, bytes(table))
    return path


def song_record(size, channels, bpm):
    return encode_pad(sample_end=size, volume=127, loop=False, gate=False, channels=channels,
                      tempo_mode=0, bpm=pad_bpm(bpm))


def pick_songs(root, names=None, count=5):
    """``[(song_dir, song)]``: the named song folders, or the first ``count`` in ``_index.json``."""
    if not names:
        with open(os.path.join(root, "_index.json"), encoding="utf-8") as fh:
            names = [s["dir"] for s in json.load(fh).get("songs", [])][:count]
    picked = []
    for name in names:
        song_dir = os.path.join(root, name)
        with open(os.path.join(song_dir, "song.json"), encoding="utf-8") as fh:
            picked.append((song_dir, json.load(fh)))
    return picked


def build(root, bank, *, names=None, count=5, channels=2, mono_check=False, smpl_dir=None,
          convert=pcm_s16, log=print):
    """Write the song pads and their PAD_INFO records; returns the songbook lines."""
    bank = bank.upper()
    if bank not in BANKS:
        raise ValueError(f"bank must be one of {BANKS}")
    smpl_dir = smpl_dir or SETTINGS["SMPL_DIR"]
    os.makedirs(smpl_dir, exist_ok=True)
    songs = pick_songs(root, names, count)
    plan = [(i + 1, song_dir, song, channels) for i, (song_dir, song) in enumerate(songs)]
    if mono_check and songs:
        plan.append((len(songs) + 1, songs[0][0], songs[0][1], 1))
    if len(plan) > 12:
        raise ValueError(f"{len(plan)} pads won't fit in one bank (12)")
    records, book = {}, []
    for pad, song_dir, song, ch in plan:
        src = song_audio(song_dir, song)
        _path, size, seconds = write_song_pad(src, smpl_dir, bank, pad, ch, convert=convert)
        records[(bank, pad)] = song_record(size, ch, song.get("bpm"))
        line = (f"{bank}{pad:<3} {song.get('artist') or '?'} - {song.get('title') or '?'}  "
                f"[{pad_bpm(song.get('bpm'))} bpm, key {song.get('key') or '?'}, "
                f"{int(seconds // 60)}:{int(seconds % 60):02d}, {'stereo' if ch == 2 else 'mono'}, "
                f"{os.path.basename(src)}]")
        book.append(line)
        log("  " + line)
    patch_padinfo(smpl_dir, records)
    return book


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=SETTINGS["KARAOKE_DIR"], help="prepped songs (with _index.json)")
    ap.add_argument("--bank", default="C")
    ap.add_argument("--songs", nargs="*", help="song folder names (default: the first --count in _index.json)")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--mono", action="store_true", help="write the songs in mono")
    ap.add_argument("--mono-check", action="store_true",
                    help="also put song 1 in mono on the next pad, to tell a stereo problem from any other")
    ap.add_argument("--smpl", default=None, help="SMPL folder to write (default: the card template)")
    args = ap.parse_args(argv)
    print(f"Song pads for bank {args.bank.upper()} from {args.root}:")
    book = build(args.root, args.bank, names=args.songs, count=args.count, channels=1 if args.mono else 2,
                 mono_check=args.mono_check, smpl_dir=args.smpl)
    print(f"{len(book)} pads written, PAD_INFO patched. Next: deploy_sd.py (don't run gen_padinfo.py after this).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
