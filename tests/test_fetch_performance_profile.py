"""Tests for card-session → performance profile aggregation (fetch scoring)."""
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fetch_samples as fs


class FetchPerformanceProfileTests(unittest.TestCase):
    def setUp(self):
        fs._PERFORMANCE_PROFILE = None

    def tearDown(self):
        fs._PERFORMANCE_PROFILE = None

    def test_parse_pattern_pad_key(self):
        self.assertEqual(fs._parse_pattern_pad_key("E2"), ("E", 2))
        self.assertEqual(fs._parse_pattern_pad_key("A10"), ("A", 10))
        self.assertEqual(fs._parse_pattern_pad_key(""), (None, None))
        self.assertEqual(fs._parse_pattern_pad_key("X1"), (None, None))

    def test_ingest_session_maps_identity_for_patterns_and_bpm(self):
        ident_e2 = "aa" * 32
        ident_b1 = "bb" * 32
        ident_a1 = "cc" * 32
        session = {
            "bed_context": {
                "files": [{"name": "A0000001.WAV", "identity": ident_a1}],
            },
            "toolkit": {
                "files": [{"pad": 1, "identity": ident_b1}],
                "adjustments": [],
            },
            "session_banks": {
                "adjustments": [
                    {"bank": "F", "pad": 6, "field": "bpm", "original": 120.0, "user": 90.0},
                ],
                "banks": {
                    "F": {
                        "pads": [
                            {
                                "pad": 6,
                                "on_card": True,
                                "identity": ident_e2,
                                "settings": {"bpm_adjusted": True},
                            },
                        ],
                    },
                },
                "pattern_usage": {
                    "most_used": [
                        {"pad": "F6", "hit_count": 10, "avg_velocity": 80.0},
                        {"pad": "B1", "hit_count": 3, "avg_velocity": 70.0},
                        {"pad": "A1", "hit_count": 5, "avg_velocity": 60.0},
                    ],
                },
            },
        }
        profile = {}
        fs._ingest_card_session(profile, session)

        self.assertIn(ident_e2, profile)
        self.assertEqual(profile[ident_e2]["pattern_hits"], 10)
        self.assertEqual(len(profile[ident_e2]["bpm_adjustments"]), 1)
        self.assertEqual(profile[ident_e2]["bpm_adjustments"][0]["user"], 90.0)

        self.assertIn(ident_b1, profile)
        self.assertEqual(profile[ident_b1]["pattern_hits"], 3)

        self.assertIn(ident_a1, profile)
        self.assertEqual(profile[ident_a1]["pattern_hits"], 5)

    def test_toolkit_bpm_adjustment_merges(self):
        ident = "dd" * 32
        session = {
            "bed_context": {"files": []},
            "toolkit": {
                "files": [{"pad": 2, "identity": ident}],
                "adjustments": [
                    {"bank": "B", "pad": 2, "field": "bpm", "original": 100.0, "user": 88.0},
                ],
            },
            "session_banks": {
                "adjustments": [],
                "banks": {},
                "pattern_usage": {"most_used": []},
            },
        }
        profile = {}
        fs._ingest_card_session(profile, session)
        self.assertEqual(len(profile[ident]["bpm_adjustments"]), 1)


if __name__ == "__main__":
    unittest.main()
