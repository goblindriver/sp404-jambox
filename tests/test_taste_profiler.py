"""taste_profiler reads the QNAP media folders through the jambox settings."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import jambox_config
import taste_profiler


class MediaRootTests(unittest.TestCase):
    def test_defaults_follow_the_media_production_layout(self):
        root = os.path.abspath("/qnap")  # settings paths are absolute (drive-qualified on Windows)
        with patch.dict(os.environ, {"SP404_QNAP_ROOT": root}):
            settings = jambox_config.load_settings(REPO_ROOT)
        self.assertEqual(settings["MULTITRACK_SESSIONS_ROOT"], os.path.join(
            root, "Media Production", "Multitrack Practice Stems", "FUN SESSIONS"))
        self.assertEqual(settings["MULTITRACK_H4N_ROOT"], os.path.join(root, "Media Production", "Zoom H4N Recordings"))
        self.assertEqual(settings["MULTITRACK_FILM_ROOT"], os.path.join(root, "Jason Finished Work"))

    def test_own_films_match_titles_however_they_are_spelled(self):
        with tempfile.TemporaryDirectory() as films:
            for name in ("Norwest Passages†.mp4", "Urban Exploration†.mov", "Garden State†.mov"):
                open(os.path.join(films, name), "wb").close()
            with patch.dict(taste_profiler.SETTINGS, {"MULTITRACK_FILM_ROOT": films}):
                profile = taste_profiler.profile_own_films()

        self.assertEqual(len(profile["inventory"]), 3)
        self.assertEqual(profile["vibes"], {"nostalgic": 2, "dreamy": 1, "eerie": 2, "gritty": 2})

    def test_multitrack_sessions_read_the_configured_root(self):
        with tempfile.TemporaryDirectory() as sessions:
            os.makedirs(os.path.join(sessions, "Stevie Wonder - Superstition"))
            os.makedirs(os.path.join(sessions, "MIXDOWNS"))
            with patch.dict(taste_profiler.SETTINGS, {"MULTITRACK_SESSIONS_ROOT": sessions}):
                profile = taste_profiler.profile_multitrack_sessions()

        self.assertEqual(list(profile["inventory"]), ["Stevie Wonder - Superstition"])
        self.assertEqual(profile["vibes"]["soulful"], 5)


if __name__ == "__main__":
    unittest.main()
