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
        with redirect_stdout(io.StringIO()) as out:
            library_trim.run_execute(_args(**overrides))
        return out.getvalue()

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

    def _run_dedup(self, fingerprints, **overrides):
        """Run execute with the dedup pass on; fingerprints maps file name -> fingerprint (absent = unreadable)."""
        import deduplicate_samples

        def backend(kind):
            def fingerprint(path):
                fp = fingerprints.get(os.path.basename(path))
                return fp if fp and fp["kind"] == kind else None
            return fingerprint

        with patch.object(deduplicate_samples, "LIBRARY", self.lib), \
             patch("deduplicate_samples._fingerprint_with_fpcalc", side_effect=backend("fpcalc")), \
             patch("deduplicate_samples._fingerprint_with_python", side_effect=backend("python")), \
             patch("sys.stderr", io.StringIO()):
            return self._run(skip_dedup=False, skip_audio_quality=True, **overrides)

    def _add_copy(self, rel_path, row):
        with open(os.path.join(self.lib, rel_path), "wb") as fh:
            fh.write(b"RIFF")
        with open(os.path.join(self.lib, "Drums", "good.wav"), "wb") as fh:
            fh.write(b"RIFF" * 10)  # the bigger copy is kept
        upsert_tag_entries(self.tags, {rel_path: row})

    def _trash_manifest(self):
        run_id = os.listdir(os.path.join(self.lib, "_TRASH"))[0]
        with open(os.path.join(self.lib, "_TRASH", run_id, "manifest.jsonl"), encoding="utf-8") as fh:
            return run_id, {item["rel_path"]: item for item in map(json.loads, fh)}

    def _report(self):
        with open(os.path.join(self.tmp.name, "data", "audit_reports", "trim_report_latest.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_chromaprint_duplicate_is_trashed_and_restore_brings_it_back(self):
        copy_row = {"duration": 1, "type_code": "HAT"}
        self._add_copy("Drums/good_copy.wav", copy_row)
        same = {"kind": "fpcalc", "value": "1,2,3,4"}

        self._run_dedup({"good.wav": same, "good_copy.wav": dict(same),
                         "silent.wav": {"kind": "fpcalc", "value": "-1,-1,-1,-1"}}, apply=True)

        remaining = set(load_tag_db(self.tags))
        self.assertNotIn("Drums/good_copy.wav", remaining)
        self.assertTrue({"Drums/good.wav", "Drums/unreadable.wav", "Drums/silent.wav"} <= remaining)
        run_id, manifest = self._trash_manifest()
        self.assertEqual(manifest["Drums/good_copy.wav"]["reason"], "dedup")

        with redirect_stdout(io.StringIO()):
            self.assertEqual(library_trim.run_restore(argparse.Namespace(run_id=run_id)), 0)
        self.assertEqual(load_tag_db(self.tags)["Drums/good_copy.wav"], copy_row)
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Drums", "good_copy.wav")))

    def test_fallback_fingerprint_match_is_reported_and_never_trashed(self):
        self._add_copy("Drums/good_copy.wav", {"duration": 1, "type_code": "HAT"})
        same = {"kind": "python", "value": [1.0, 0.0, 1.0]}

        out = self._run_dedup({"good.wav": same, "good_copy.wav": dict(same),
                               "silent.wav": {"kind": "python", "value": [0.0, 1.0, 0.0]}}, apply=True)

        self.assertIn("Drums/good_copy.wav", load_tag_db(self.tags))
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Drums", "good_copy.wav")))
        _run_id, manifest = self._trash_manifest()  # the duration pass still trashed long.wav
        self.assertNotIn("dedup", {item["reason"] for item in manifest.values()})
        dedup = self._report()["passes"]["dedup"]
        self.assertEqual(dedup["trashed"], 0)
        self.assertEqual(dedup["review_only"], 1)
        self.assertEqual(dedup["possible_duplicates"], [{"keep": "Drums/good.wav", "duplicates": ["Drums/good_copy.wav"]}])
        self.assertIn("Possible duplicates (fallback fingerprint, not moved): 1 files in 1 groups", out)

    def test_dry_run_shows_chromaprint_cuts_and_fallback_review_apart(self):
        self._add_copy("Drums/good_copy.wav", {"duration": 1, "type_code": "HAT"})
        self._add_copy("Drums/silent_copy.wav", {"duration": 1, "type_code": "KIK"})
        chroma = {"kind": "fpcalc", "value": "1,2,3,4"}
        loose = {"kind": "python", "value": [0.0, 1.0, 0.0]}

        out = self._run_dedup({"good.wav": chroma, "good_copy.wav": dict(chroma),
                               "silent.wav": loose, "silent_copy.wav": dict(loose)})

        dedup_section = out.split("--- Pass 2")[1].split("--- Pass")[0]
        self.assertIn("Found 1 duplicate groups on chromaprint", dedup_section)
        self.assertIn("Would trash: 1 files", dedup_section)
        self.assertIn("Possible duplicates (fallback fingerprint, not moved): 1 files in 1 groups", dedup_section)
        self.assertIn("1 flagged for review only (not moved)", out)
        self.assertEqual(len(load_tag_db(self.tags)), len(self.rows) + 2)  # dry run: nothing moved

    def test_refuses_to_run_without_ffmpeg(self):
        with patch.object(library_trim, "resolve_command", return_value=None), \
             redirect_stdout(io.StringIO()), patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                library_trim.run_execute(_args(apply=True))
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(set(load_tag_db(self.tags)), set(self.rows))


if __name__ == "__main__":
    unittest.main()
