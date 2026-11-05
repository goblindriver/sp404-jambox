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

``--strips`` gives each song a row of 4 pads instead (3 songs per bank,
filling banks from ``--bank`` on), all cut on the song's beat grid
(``bpm`` and ``beat_offset_s`` in ``song.json``):

1. the full song (press to start, press to stop);
2. the last chorus to the end, with a bar's run-in: the way back in after a breakdown;
3. the original singer's hook (the first chorus, from ``guide.flac``, mono);
4. a 4-bar loop of the instrumental from the first chorus (loops until pressed).

Choruses come from ``song.json`` ``choruses``; without them the hook and loop
start a third of the way in and the last chorus two thirds.

    python scripts/karaoke_card.py --bank C --strips --count 6

Run it after ``gen_padinfo.py`` (which resets every pad to its bank's
defaults) and before ``deploy_sd.py``. It writes into the card template.
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

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
LOOP_BEATS = 16                   # 4 bars of 4/4
HOOK_BEATS = (4, 32)              # the hook pad is 1 to 8 bars
RUN_IN_BEATS = 4                  # the last-chorus pad starts a bar early
FADE_S = 0.003                    # de-click every cut edge
STRIP = (("song", 2, False), ("last chorus", 2, False), ("hook vocal", 1, False), ("loop", 2, True))


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


def write_pad(pcm, smpl_dir, bank, pad, channels):
    """Write ``{bank}000000{pad}.WAV`` from raw PCM; returns (path, size in bytes, seconds)."""
    path = os.path.join(smpl_dir, f"{bank}{pad:07d}.WAV")
    data = build_sp404_wav(pcm, bank, pad, channels=channels)
    _replace(path, data)
    return path, len(data), len(pcm) / (SR * 2 * channels)


def write_song_pad(src, smpl_dir, bank, pad, channels, convert=pcm_s16):
    """Convert ``src`` and write it to a pad; returns (path, size in bytes, seconds)."""
    return write_pad(convert(src, channels), smpl_dir, bank, pad, channels)


def snap(t, offset, beat, rounding=round):
    """``t`` moved onto the beat grid that starts at ``offset`` (never before 0)."""
    return max(0.0, offset + rounding((t - offset) / beat) * beat)


def strip_cuts(song, duration):
    """Start and end, in seconds, of the last-chorus, hook and loop pads."""
    beat = 60.0 / float(song.get("bpm") or 120.0)
    offset = float(song.get("beat_offset_s") or 0.0)
    choruses = []
    for a, b in sorted((float(a), float(b)) for a, b in (song.get("choruses") or []) if float(b) > float(a)):
        if choruses and a - choruses[-1][1] <= 2 * RUN_IN_BEATS * beat:   # pieces < 2 bars apart: one chorus
            choruses[-1] = (choruses[-1][0], max(choruses[-1][1], b))
        else:
            choruses.append((a, b))
    if choruses:
        hook_start = snap(choruses[0][0], offset, beat, math.floor)
        hook_end = snap(choruses[0][1], offset, beat, math.ceil)
        last_start = snap(choruses[-1][0], offset, beat, math.floor) - RUN_IN_BEATS * beat
    else:
        hook_start = snap(duration / 3, offset, beat, math.floor)
        hook_end = hook_start + LOOP_BEATS * beat
        last_start = snap(duration * 2 / 3, offset, beat, math.floor)
    lo, hi = HOOK_BEATS
    hook_end = min(max(hook_end, hook_start + lo * beat), hook_start + hi * beat)

    def clamp(a, b):
        a = min(max(a, 0.0), duration)
        return a, min(max(b, a), duration)

    return {"last chorus": clamp(last_start, duration), "hook vocal": clamp(hook_start, hook_end),
            "loop": clamp(hook_start, hook_start + LOOP_BEATS * beat)}


def cut(pcm, channels, start, end, fade_in=True, fade_out=True):
    """``pcm`` from ``start`` to ``end`` seconds, with a few ms of fade on the cut edges."""
    frames = np.frombuffer(pcm, dtype="<i2").reshape(-1, channels)
    seg = frames[int(round(start * SR)):int(round(end * SR))].astype(np.float32)
    n = min(int(FADE_S * SR), len(seg) // 2)
    if n:
        ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None]
        if fade_in:
            seg[:n] *= ramp
        if fade_out:
            seg[-n:] *= ramp[::-1]
    return np.round(seg).astype("<i2").tobytes()


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


def song_record(size, channels, bpm, loop=False):
    return encode_pad(sample_end=size, volume=127, loop=loop, gate=False, channels=channels,
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


def _clock(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def build_strips(root, bank, *, names=None, count=5, smpl_dir=None, convert=pcm_s16, log=print):
    """A row of 4 pads per song (see the module doc), 3 songs per bank from ``bank`` on.

    Returns the songbook lines.
    """
    bank = bank.upper()
    if bank not in BANKS:
        raise ValueError(f"bank must be one of {BANKS}")
    smpl_dir = smpl_dir or SETTINGS["SMPL_DIR"]
    os.makedirs(smpl_dir, exist_ok=True)
    songs = pick_songs(root, names, count)
    first = BANKS.index(bank)
    if first + (len(songs) + 2) // 3 > len(BANKS):
        raise ValueError(f"{len(songs)} songs need {(len(songs) + 2) // 3} banks from {bank}; only "
                         f"{len(BANKS) - first} left")
    records, book = {}, []
    for i, (song_dir, song) in enumerate(songs):
        b, base = BANKS[first + i // 3], (i % 3) * 4
        mix = song_audio(song_dir, song)
        full = convert(mix, 2)
        duration = len(full) / (SR * 4)
        cuts = strip_cuts(song, duration)
        dry = os.path.join(song_dir, "backing.flac")
        loop_src = convert(dry, 2) if dry != mix and os.path.isfile(dry) else full
        guide = os.path.join(song_dir, "guide.flac")
        hook_src = convert(guide, 1) if os.path.isfile(guide) else convert(mix, 1)
        audio = {"song": full,
                 "last chorus": cut(full, 2, *cuts["last chorus"], fade_out=False),
                 "hook vocal": cut(hook_src, 1, *cuts["hook vocal"]),
                 "loop": cut(loop_src, 2, *cuts["loop"])}
        name = f"{song.get('artist') or '?'} - {song.get('title') or '?'}"
        book.append(f"{b}{base + 1}-{base + 4}  {name}  [{pad_bpm(song.get('bpm'))} bpm, "
                    f"key {song.get('key') or '?'}]")
        for n, (label, ch, loop) in enumerate(STRIP, start=base + 1):
            _path, size, seconds = write_pad(audio[label], smpl_dir, b, n, ch)
            records[(b, n)] = song_record(size, ch, song.get("bpm"), loop=loop)
            start = cuts[label][0] if label in cuts else 0.0
            book.append(f"  {b}{n:<3} {label:<12} {_clock(seconds)}"
                        + (f"  from {_clock(start)}" if label != "song" else ""))
        for line in book[-5:]:
            log(line)
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
    ap.add_argument("--strips", action="store_true",
                    help="a row of 4 pads per song (song, last chorus, hook vocal, loop), 3 songs per bank")
    ap.add_argument("--smpl", default=None, help="SMPL folder to write (default: the card template)")
    args = ap.parse_args(argv)
    if args.strips:
        print(f"Song strips from bank {args.bank.upper()} on, from {args.root}:")
        book = build_strips(args.root, args.bank, names=args.songs, count=args.count, smpl_dir=args.smpl)
        print(f"{len(book) // 5} songs written, PAD_INFO patched. Next: deploy_sd.py "
              "(don't run gen_padinfo.py after this).")
        return 0
    print(f"Song pads for bank {args.bank.upper()} from {args.root}:")
    book = build(args.root, args.bank, names=args.songs, count=args.count, channels=1 if args.mono else 2,
                 mono_check=args.mono_check, smpl_dir=args.smpl)
    print(f"{len(book)} pads written, PAD_INFO patched. Next: deploy_sd.py (don't run gen_padinfo.py after this).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
