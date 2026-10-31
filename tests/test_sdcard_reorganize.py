"""SD-card reorganize: validate first, swap instead of delete, settings follow samples."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(REPO_ROOT, "scripts"), os.path.join(REPO_ROOT, "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api import sdcard as sdcard_api
from api.pipeline import pipeline_bp
from api.sdcard import sdcard_bp
from gen_padinfo import encode_pad


def _offset(bank, pad):
    return ((ord(bank) - ord("A")) * 12 + pad - 1) * 32


class ReorganizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.smpl = os.path.join(self.tmp.name, "card", "ROLAND", "SP-404SX", "SMPL")
        os.makedirs(self.smpl)
        # Distinct PAD_INFO records: each occupied pad gets its own BPM.
        records = bytearray(encode_pad() * 120)
        for (bank, pad), bpm in {("D", 1): 90.0, ("D", 2): 100.0, ("F", 3): 128.0}.items():
            off = _offset(bank, pad)
            records[off:off + 32] = encode_pad(sample_end=1000, loop=True, gate=False, bpm=bpm)
            self._write(f"{bank}{pad:07d}.WAV", f"{bank}{pad}".encode())
        with open(os.path.join(self.smpl, "PAD_INFO.BIN"), "wb") as fh:
            fh.write(records)

        app = Flask(__name__)
        app.config.update(SD_CARD=os.path.join(self.tmp.name, "card"), SD_SMPL_DIR=self.smpl,
                          REPO_DIR=self.tmp.name, GOLD_BANK_A_DIR=self.tmp.name)
        app.register_blueprint(sdcard_bp, url_prefix="/api")
        app.register_blueprint(pipeline_bp, url_prefix="/api")
        self.client = app.test_client()

    def _write(self, name, data):
        with open(os.path.join(self.smpl, name), "wb") as fh:
            fh.write(data)

    def _read(self, name):
        path = os.path.join(self.smpl, name)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as fh:
            return fh.read()

    def _record(self, bank, pad):
        with open(os.path.join(self.smpl, "PAD_INFO.BIN"), "rb") as fh:
            data = fh.read()
        return data[_offset(bank, pad):_offset(bank, pad) + 32]

    def _move(self, *moves):
        body = {"moves": [{"from": {"bank": a, "pad": b}, "to": {"bank": c, "pad": d}} for a, b, c, d in moves]}
        return self.client.post("/api/sdcard/reorganize", json=body)

    def test_moving_onto_an_occupied_pad_swaps_samples_and_settings(self):
        d1, f3 = self._record("D", 1), self._record("F", 3)

        response = self._move(("D", 1, "F", 3))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self._read("F0000003.WAV"), b"D1")
        self.assertEqual(self._read("D0000001.WAV"), b"F3")
        self.assertEqual(self._record("F", 3), d1)
        self.assertEqual(self._record("D", 1), f3)

    def test_explicit_swap_keeps_both_records(self):
        d1, d2 = self._record("D", 1), self._record("D", 2)

        response = self._move(("D", 1, "D", 2), ("D", 2, "D", 1))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual((self._read("D0000001.WAV"), self._read("D0000002.WAV")), (b"D2", b"D1"))
        self.assertEqual((self._record("D", 1), self._record("D", 2)), (d2, d1))

    def test_move_to_an_empty_pad_clears_the_vacated_record(self):
        d1 = self._record("D", 1)

        response = self._move(("D", 1, "E", 5))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._read("D0000001.WAV"))
        self.assertEqual(self._read("E0000005.WAV"), b"D1")
        self.assertEqual(self._record("E", 5), d1)
        self.assertEqual(self._record("D", 1), encode_pad())

    def test_invalid_moves_are_rejected_before_anything_changes(self):
        before = sorted(os.listdir(self.smpl))
        for moves in ([("../../x", 1, "D", 2)], [("D", 1, "K", 1)], [("D", 1, "D", 13)],
                      [("D", 1, "E", 1), ("D", 2, "E", 1)], [("G", 4, "D", 1)]):
            response = self._move(*moves)
            self.assertEqual(response.status_code, 400, moves)
            self.assertTrue(response.get_json()["errors"])
        self.assertEqual(sorted(os.listdir(self.smpl)), before)

    def test_failed_rename_rolls_back(self):
        real_rename = os.rename
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] == 3:
                raise OSError("card pulled")
            return real_rename(src, dst)

        with patch.object(sdcard_api.os, "rename", side_effect=flaky):
            response = self._move(("D", 1, "F", 3))

        self.assertEqual(response.status_code, 500)
        self.assertEqual((self._read("D0000001.WAV"), self._read("F0000003.WAV")), (b"D1", b"F3"))
        self.assertEqual(sorted(n for n in os.listdir(self.smpl) if n.endswith(".REORG_TMP")), [])

    def test_fetch_rejects_a_bad_bank(self):
        response = self.client.post("/api/pipeline/fetch", json={"bank": "../../etc"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
