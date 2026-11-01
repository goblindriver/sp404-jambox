"""Song-follower layout checker."""
import os
import sys
import unittest

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import gen_padinfo  # noqa: E402
import gen_patterns  # noqa: E402
import pad_layout  # noqa: E402


def _pads(name):
    with open(os.path.join(REPO_ROOT, "presets", "genre", name + ".yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)["pads"]


class SongFollowerTests(unittest.TestCase):
    def test_the_follower_preset_conforms_and_gets_the_right_pad_modes(self):
        pads = _pads("funk-muscle-follower")
        self.assertEqual(pad_layout.check(pads), [])
        modes = [gen_padinfo.pad_mode(pads[n], n) for n in range(1, 13)]
        self.assertEqual(modes, [(False, True)] * 4 + [(False, False)] * 4 + [(True, False)] * 4)
        self.assertEqual(gen_patterns.drum_roles(pads), {1: 1, 2: 2, 3: 3, 4: 4})

    def test_loops_in_row_two_and_pitched_hits_in_row_three_are_flagged(self):
        issues = dict(pad_layout.check(_pads("funk-muscle")))
        self.assertEqual(sorted(issues), [5, 6, 7, 8, 10])
        self.assertIn("BRK", issues[5])
        self.assertIn("in-key loop", issues[10])

    def test_rows_take_legacy_codes_string_keys_and_chromatic_keys(self):
        pads = {"1": "KIK hard one-shot", "2": "SNR crack one-shot", "3": "HHT open one-shot",
                "4": "TOM floor one-shot", "5": "VOX shout one-shot", "6": "RSR riser transition",
                "7": "FX impact one-shot", "8": "CYM crash one-shot", "9": "BRK break loop",
                "10": "BAS warm loop", "11": "KEY rhodes chromatic", "12": "PAD lush layer"}
        self.assertEqual(pad_layout.check(pads), [])
        del pads["12"]
        self.assertEqual(pad_layout.check(pads), [(12, "empty (in-key loop)")])


if __name__ == "__main__":
    unittest.main()
