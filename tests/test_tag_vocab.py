"""Canonical genre vocabulary and Discogs→fetch token bridging."""

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from discogs_fetch_bridge import discogs_keyword_tokens  # noqa: E402
from tag_vocab import GENRE_ALIASES, normalize_genre  # noqa: E402


class TestNormalizeGenre(unittest.TestCase):
    def test_subgenre_slugs(self):
        self.assertEqual(normalize_genre("Techno"), "techno")
        self.assertEqual(normalize_genre("trance"), "trance")
        self.assertEqual(normalize_genre("Dubstep"), "dubstep")
        self.assertEqual(normalize_genre("drum and bass"), "drum-and-bass")
        self.assertEqual(normalize_genre("dnb"), "drum-and-bass")
        self.assertEqual(normalize_genre("jungle"), "jungle")
        self.assertEqual(normalize_genre("breakbeat"), "breakbeat")
        self.assertEqual(normalize_genre("experimental"), "experimental")

    def test_aliases_resolve(self):
        self.assertEqual(GENRE_ALIASES.get("juke"), "footwork")
        self.assertEqual(normalize_genre("juke"), "footwork")


class TestDiscogsKeywordTokens(unittest.TestCase):
    def test_techno_style_tail_is_distinct(self):
        entry = {
            "parent_genre": "Unknown",
            "discogs_styles": [{"label": "Electronic---Techno", "probability": 0.5}],
        }
        toks = discogs_keyword_tokens(entry)
        self.assertIn("techno", toks)
        # Label also carries the parent segment, which normalizes to electronic.
        self.assertIn("electronic", toks)

    def test_drum_and_bass_phrase(self):
        entry = {
            "parent_genre": "Unknown",
            "discogs_styles": [{"label": "Electronic---Drum n Bass", "probability": 0.5}],
        }
        toks = discogs_keyword_tokens(entry)
        self.assertIn("drum-and-bass", toks)


if __name__ == "__main__":
    unittest.main()
