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

import convert_to_flac


class StorageScriptsTests(unittest.TestCase):
    def test_load_tags_returns_empty_dict_for_invalid_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tags_path = os.path.join(tempdir, "_tags.json")
            with open(tags_path, "w", encoding="utf-8") as handle:
                handle.write("{not valid json")

            with patch.object(convert_to_flac, "TAGS_FILE", tags_path):
                tags = convert_to_flac.load_tags()

        self.assertEqual(tags, {})

    def test_batch_convert_keeps_wav_when_tag_save_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            wav_path = os.path.join(tempdir, "sample.wav")
            flac_path = os.path.join(tempdir, "sample.flac")
            tags_path = os.path.join(tempdir, "_tags.json")
            with open(wav_path, "wb") as handle:
                handle.write(b"wavdata")
            with open(tags_path, "w", encoding="utf-8") as handle:
                json.dump({"sample.wav": {"tags": ["dusty"]}}, handle)

            def fake_convert(_wav_path):
                with open(flac_path, "wb") as handle:
                    handle.write(b"flacdata")
                return flac_path

            with patch.object(convert_to_flac, "LIBRARY", tempdir), patch.object(convert_to_flac, "TAGS_FILE", tags_path), patch("convert_to_flac.find_wavs", return_value=[wav_path]), patch("convert_to_flac.convert_wav_to_flac", side_effect=fake_convert), patch("convert_to_flac.verify_flac", return_value=True), patch("convert_to_flac.save_tags", side_effect=OSError("disk full")):
                converted, skipped, failed, _bytes_saved = convert_to_flac.batch_convert()

            self.assertEqual((converted, skipped, failed), (0, 0, 1))
            self.assertTrue(os.path.exists(wav_path))
            self.assertFalse(os.path.exists(flac_path))


if __name__ == "__main__":
    unittest.main()
