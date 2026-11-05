import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import karaoke_card  # noqa: E402
from gen_padinfo import encode_pad  # noqa: E402
from wav_utils import build_sp404_wav  # noqa: E402


def _song(root, name, bpm, *, bv=False, mix=None):
    song_dir = os.path.join(root, name)
    os.makedirs(song_dir)
    for f in ["backing.flac"] + (["backing_bv.flac"] if bv else []):
        open(os.path.join(song_dir, f), "wb").close()
    artist, title = name.split(" - ")
    song = {"artist": artist, "title": title, "bpm": bpm, "key": "Am"}
    if mix:
        song["mix"] = mix
    with open(os.path.join(song_dir, "song.json"), "w", encoding="utf-8") as fh:
        json.dump(song, fh)
    return {"dir": name}


def _record(table, bank, pad):
    at = ("ABCDEFGHIJ".index(bank) * 12 + pad - 1) * 32
    start, end, _us, _ue, vol, lofi, loop, gate, rev, fmt, ch, tempo, otempo, utempo = struct.unpack(
        ">IIII BBBBBBBB II", table[at:at + 32])
    return {"end": end, "loop": loop, "gate": gate, "channels": ch, "tempo_mode": tempo, "bpm": otempo / 10}


class KaraokeCardTests(unittest.TestCase):
    def test_wav_layout_mono_and_stereo(self):
        for channels in (1, 2):
            wav = build_sp404_wav(b"\x01\x00" * 8, "C", 1, channels=channels)
            ch, rate, byte_rate, align = struct.unpack("<HIIH", wav[22:34])
            self.assertEqual((ch, rate, byte_rate, align), (channels, 44100, 44100 * 2 * channels, 2 * channels))
            self.assertEqual(wav[504:508], b"data")      # samples start at 512, as the 404 expects
            self.assertEqual(len(wav), 512 + 16)

    def test_bpm_folds_into_the_404_range(self):
        self.assertEqual(karaoke_card.pad_bpm(161.5), 161.5)
        self.assertEqual(karaoke_card.pad_bpm(230), 115.0)
        self.assertEqual(karaoke_card.pad_bpm(35), 70.0)
        self.assertEqual(karaoke_card.pad_bpm(None), 120.0)

    def test_sings_to_the_backing_vocal_mix_unless_dry(self):
        with tempfile.TemporaryDirectory() as root:
            _song(root, "A - One", 100, bv=True)
            _song(root, "B - Two", 100, bv=True, mix="dry")
            _song(root, "C - Three", 100)
            pick = {name: os.path.basename(karaoke_card.song_audio(os.path.join(root, name), song))
                    for (song_dir, song), name in zip(
                        karaoke_card.pick_songs(root, ["A - One", "B - Two", "C - Three"]),
                        ["A - One", "B - Two", "C - Three"])}
            self.assertEqual(pick, {"A - One": "backing_bv.flac", "B - Two": "backing.flac",
                                    "C - Three": "backing.flac"})

    def test_build_writes_song_pads_and_only_their_pad_info(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as smpl:
            index = [_song(root, "Le Tigre - Deceptacon", 161.5), _song(root, "P.O.S - Stuff", 230),
                     _song(root, "Ween - Push", 112)]
            with open(os.path.join(root, "_index.json"), "w", encoding="utf-8") as fh:
                json.dump({"songs": index}, fh)
            # An existing PAD_INFO: every pad a looped mono one at 128 bpm.
            with open(os.path.join(smpl, "PAD_INFO.BIN"), "wb") as fh:
                fh.write(b"".join(encode_pad(sample_end=9000, loop=True, gate=False, bpm=128) for _ in range(120)))
            seconds = {1: 2.0, 2: 1.0}
            convert = lambda src, ch: b"\x00\x00" * ch * int(44100 * seconds[ch])  # noqa: E731
            book = karaoke_card.build(root, "c", count=2, mono_check=True, smpl_dir=smpl,
                                      convert=convert, log=lambda *_: None)

            self.assertEqual(len(book), 3)
            self.assertIn("C1   Le Tigre - Deceptacon  [161.5 bpm", book[0])
            self.assertIn("stereo", book[0])
            self.assertIn("C3   Le Tigre - Deceptacon", book[2])   # the mono check repeats song 1
            self.assertIn("mono", book[2])
            with open(os.path.join(smpl, "PAD_INFO.BIN"), "rb") as fh:
                table = fh.read()
            self.assertEqual(len(table), 3840)
            first = _record(table, "C", 1)
            self.assertEqual((first["loop"], first["gate"], first["channels"], first["tempo_mode"], first["bpm"]),
                             (0, 0, 2, 0, 161.5))
            self.assertEqual(first["end"], os.path.getsize(os.path.join(smpl, "C0000001.WAV")))
            self.assertEqual(_record(table, "C", 2)["bpm"], 115.0)
            self.assertEqual(_record(table, "C", 3)["channels"], 1)
            untouched = _record(table, "C", 4)
            self.assertEqual((untouched["loop"], untouched["bpm"], untouched["end"]), (1, 128.0, 9000))
            self.assertEqual(_record(table, "B", 1)["bpm"], 128.0)
            self.assertFalse(os.path.exists(os.path.join(smpl, "C0000004.WAV")))

    def test_too_many_songs_for_a_bank_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            names = [_song(root, f"A - S{i}", 100)["dir"] for i in range(12)]
            with self.assertRaises(ValueError):
                karaoke_card.build(root, "C", names=names, mono_check=True, smpl_dir=root,
                                   convert=lambda src, ch: b"\x00\x00", log=lambda *_: None)


if __name__ == "__main__":
    unittest.main()
