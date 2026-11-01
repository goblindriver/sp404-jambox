"""library_trim must never destroy data: dry run by default, trash instead of delete."""
import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import numpy as np


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import library_trim
from jambox_config import load_tag_db, upsert_tag_entries


def _args(**overrides):
    values = dict(min_duration=30, dedup_threshold=0.93, min_quality=3, skip_dedup=True,
                  skip_audio_quality=False, apply=False, dry_run=False)
    values.update(overrides)
    return argparse.Namespace(**values)


class LibraryTrimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = os.path.join(self.tmp.name, "lib")
        self.tags = os.path.join(self.lib, "_tags.json")
        os.makedirs(os.path.join(self.lib, "Drums"))
        self.rows = {
            "Drums/long.wav": {"duration": 90, "type_code": "BRK"},
            "Drums/silent.wav": {"duration": 1, "type_code": "KIK"},
            "Drums/unreadable.wav": {"duration": 1, "type_code": "SNR"},
            "Drums/good.wav": {"duration": 1, "type_code": "HAT", "quality_score": 4},
        }
        for rel in self.rows:
            with open(os.path.join(self.lib, rel), "wb") as fh:
                fh.write(b"RIFF")
        upsert_tag_entries(self.tags, self.rows)

        def fake_pcm(path):
            name = os.path.basename(path)
            if name == "unreadable.wav":
                return None
            if name == "silent.wav":
                return np.zeros(1000, dtype=np.float32)
            return np.linspace(-0.5, 0.5, 1000, dtype=np.float32)

        self.patches = [
            patch.object(library_trim, "LIBRARY", self.lib),
            patch.object(library_trim, "TAGS_FILE", self.tags),
            patch.object(library_trim, "REPO_DIR", self.tmp.name),
            patch.object(library_trim, "resolve_command", return_value="ffmpeg"),
            patch.object(library_trim, "_read_pcm_short", side_effect=fake_pcm),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _run(self, **overrides):
        with redirect_stdout(io.StringIO()):
            library_trim.run_execute(_args(**overrides))

    def test_execute_is_a_dry_run_by_default(self):
        self._run()
        self.assertEqual(set(load_tag_db(self.tags)), set(self.rows))
        for rel in self.rows:
            self.assertTrue(os.path.exists(os.path.join(self.lib, rel)))

    def test_apply_moves_to_trash_and_skips_unreadable_files(self):
        self._run(apply=True)

        remaining = set(load_tag_db(self.tags))
        self.assertEqual(remaining, {"Drums/unreadable.wav", "Drums/good.wav"})
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Drums", "unreadable.wav")))
        runs = os.listdir(os.path.join(self.lib, "_TRASH"))
        self.assertEqual(len(runs), 1)
        run_dir = os.path.join(self.lib, "_TRASH", runs[0])
        self.assertTrue(os.path.exists(os.path.join(run_dir, "Drums", "long.wav")))
        self.assertTrue(os.path.exists(os.path.join(run_dir, "Drums", "silent.wav")))
        with open(os.path.join(run_dir, "manifest.jsonl"), encoding="utf-8") as fh:
            manifest = {item["rel_path"]: item for item in map(json.loads, fh)}
        self.assertEqual(manifest["Drums/long.wav"]["reason"], "duration")
        self.assertEqual(manifest["Drums/silent.wav"]["tag_row"], self.rows["Drums/silent.wav"])

    def test_restore_puts_files_and_tag_rows_back(self):
        self._run(apply=True)
        run_id = os.listdir(os.path.join(self.lib, "_TRASH"))[0]

        with redirect_stdout(io.StringIO()):
            self.assertEqual(library_trim.run_restore(argparse.Namespace(run_id=run_id)), 0)

        self.assertEqual(load_tag_db(self.tags), self.rows)
        for rel in self.rows:
            self.assertTrue(os.path.exists(os.path.join(self.lib, rel)))

    def test_refuses_to_run_without_ffmpeg(self):
        with patch.object(library_trim, "resolve_command", return_value=None), \
             redirect_stdout(io.StringIO()), patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                library_trim.run_execute(_args(apply=True))
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(set(load_tag_db(self.tags)), set(self.rows))


if __name__ == "__main__":
    unittest.main()
