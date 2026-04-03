import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import index_music
import plex_client


class MusicIndexerTests(unittest.TestCase):
    def test_build_browse_index_ignores_non_mapping_entries(self):
        browse = index_music.build_browse_index({
            "good.flac": {"artist": "Artist", "album": "Album", "genre": "Jazz", "year": 2001},
            "bad.flac": ["not", "a", "dict"],
        })

        self.assertEqual(browse["total_tracks"], 2)
        self.assertEqual(browse["total_artists"], 1)
        self.assertEqual(browse["genres"]["Jazz"], 1)

    def test_scan_library_tolerates_non_mapping_existing_index(self):
        with tempfile.TemporaryDirectory() as tempdir:
            result = index_music.scan_library(tempdir, existing_index=["bad"], update_only=True)

        self.assertEqual(result, {})

    def test_read_tags_handles_non_numeric_duration(self):
        fake_audio = type("Audio", (), {"info": type("Info", (), {"length": "oops"})(), "get": lambda self, key: None})()
        with patch("mutagen.File", return_value=fake_audio):
            tags = index_music.read_tags("/tmp/test.mp3")

        self.assertIsNotNone(tags)
        self.assertEqual(tags["duration"], 0)


class PlexClientHelperTests(unittest.TestCase):
    def test_moods_to_vibes_ignores_non_strings(self):
        db = object.__new__(plex_client.PlexMusicDB)

        vibes = db._moods_to_vibes(["Aggressive", None, 123, "Dreamy"])

        self.assertEqual(vibes, ["aggressive", "dreamy"])

    def test_format_duration_handles_invalid_values(self):
        self.assertEqual(plex_client._format_duration("oops"), "")
        self.assertEqual(plex_client._format_duration(65000), "1:05")

    def test_parse_loudness_ignores_non_string_input(self):
        out = {}

        plex_client._parse_loudness(None, out)

        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
