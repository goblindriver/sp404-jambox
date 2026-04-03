import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import stem_split
import tag_library
import wav_utils


class TaggingAudioHelpersTests(unittest.TestCase):
    def test_convert_and_tag_returns_false_on_ffmpeg_timeout(self):
        with tempfile.TemporaryDirectory() as tempdir:
            dst = os.path.join(tempdir, "out.WAV")
            with patch("wav_utils.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)):
                result = wav_utils.convert_and_tag("/tmp/input.wav", dst, "a", 1)

        self.assertFalse(result)

    def test_load_existing_tags_returns_empty_dict_for_non_mapping_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tags_path = os.path.join(tempdir, "_tags.json")
            with open(tags_path, "w", encoding="utf-8") as handle:
                handle.write('["bad"]')

            with patch.object(tag_library, "TAGS_FILE", tags_path):
                payload = tag_library.load_existing_tags()

        self.assertEqual(payload, {})

    def test_tag_file_uses_zero_mtime_when_file_missing(self):
        with patch("tag_library.get_duration", return_value=0.0), patch("tag_library.os.path.getmtime", side_effect=OSError):
            entry = tag_library.tag_file("Drums/Kicks/test.wav", "/missing/test.wav", get_dur=False)

        self.assertEqual(entry["mtime"], 0.0)

    def test_stem_split_load_tag_db_returns_empty_dict_for_non_mapping_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tags_path = os.path.join(tempdir, "_tags.json")
            with open(tags_path, "w", encoding="utf-8") as handle:
                handle.write('["bad"]')

            with patch.object(stem_split, "TAGS_FILE", tags_path):
                payload = stem_split.load_tag_db()

        self.assertEqual(payload, {})

    def test_run_demucs_returns_empty_list_when_preconvert_fails(self):
        failed = subprocess.CompletedProcess(args=["ffmpeg"], returncode=1, stdout="", stderr="ffmpeg failed")
        with tempfile.TemporaryDirectory() as tempdir:
            with patch("stem_split.subprocess.run", return_value=failed):
                stems = stem_split.run_demucs("/tmp/input.wav", tempdir)

        self.assertEqual(stems, [])


if __name__ == "__main__":
    unittest.main()
