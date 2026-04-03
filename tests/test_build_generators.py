import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import gen_padinfo
import gen_patterns
from spedit404.binary import get_sorted_notes


class BuildGeneratorTests(unittest.TestCase):
    def test_generate_padinfo_creates_output_directory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            smpl_dir = os.path.join(tempdir, "missing", "SMPL")

            out_path = gen_padinfo.generate_padinfo(smpl_dir)

        self.assertTrue(out_path.endswith("PAD_INFO.BIN"))

    def test_generate_padinfo_ignores_unstatable_sample(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sample_path = os.path.join(tempdir, "A0000001.WAV")
            with open(sample_path, "wb") as handle:
                handle.write(b"wav")

            with patch("gen_padinfo.get_sample_path", return_value=sample_path), patch("gen_padinfo.os.path.getsize", side_effect=OSError):
                out_path = gen_padinfo.generate_padinfo(tempdir)

            self.assertTrue(os.path.exists(out_path))
            self.assertEqual(os.path.getsize(out_path), 3840)

    def test_generate_padinfo_uses_bank_config_bpm(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = os.path.join(tempdir, "bank_config.yaml")
            sample_path = os.path.join(tempdir, "A0000001.WAV")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write("bank_a:\n  bpm: 98\n")
            with open(sample_path, "wb") as handle:
                handle.write(b"\x00" * 1024)

            with patch.object(gen_padinfo, "CONFIG_PATH", config_path):
                out_path = gen_padinfo.generate_padinfo(tempdir)

            with open(out_path, "rb") as handle:
                first_record = handle.read(32)
            unpacked = struct.unpack(">IIII BBBBBBBB II", first_record)

            self.assertEqual(unpacked[-2], 980)
            self.assertEqual(unpacked[-1], 980)

    def test_gen_nu_rave_uses_snare_on_pad_two_and_hat_on_pad_three(self):
        pattern = gen_patterns.gen_nu_rave()
        notes = get_sorted_notes(pattern)
        by_tick = {}
        for note in notes:
            by_tick.setdefault(note.start_tick, set()).add(note.pad)

        self.assertIn(2, by_tick[gen_patterns.Q])
        self.assertIn(2, by_tick[gen_patterns.Q * 3])
        self.assertIn(3, by_tick[0])
        self.assertIn(3, by_tick[gen_patterns.S])


if __name__ == "__main__":
    unittest.main()
