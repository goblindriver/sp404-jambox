"""Features-only chroma/key refresh, and filename BPM/key taking precedence over librosa."""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import audio_analysis
import smart_retag
import tag_library
from jambox_config import load_tag_db, upsert_tag_entries


OLD_CHROMA = [0.5] * 12
NEW_CHROMA = [round(0.1 * i, 3) for i in range(12)]


class AudioAnalysisTests(unittest.TestCase):
    def test_this_environment_does_not_corrupt_named_arrays(self):
        self.assertTrue(audio_analysis.numpy_elision_safe())

    @unittest.skipUnless(audio_analysis.LIBROSA_AVAILABLE, "needs librosa")
    def test_key_from_chroma_reads_major_and_minor_profiles(self):
        major = np.array(audio_analysis._MAJOR_PROFILE)
        minor = np.array(audio_analysis._MINOR_PROFILE)
        self.assertEqual(audio_analysis.key_from_chroma(major), "C")
        self.assertEqual(audio_analysis.key_from_chroma(np.roll(minor, 9)), "Am")
        self.assertIsNone(audio_analysis.key_from_chroma(np.zeros(12)))

    @unittest.skipUnless(audio_analysis.LIBROSA_AVAILABLE, "needs librosa")
    def test_refresh_computes_chroma_and_key_exactly_as_extract_features(self):
        import soundfile

        sr = 22050
        t = np.arange(int(sr * 2.0)) / sr
        y = sum(np.sin(2 * np.pi * f * t) for f in (261.63, 329.63, 392.0)).astype(np.float32) / 3
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "chord.wav")
            soundfile.write(path, y, sr)

            features = audio_analysis.extract_features(path)
            chroma, key = audio_analysis.chroma_and_key(path)
            loaded, _sr = audio_analysis.librosa.load(path, sr=sr, mono=True)

        self.assertEqual(chroma, features["chroma"])
        self.assertEqual(key, features["key"])
        self.assertEqual(key, audio_analysis.detect_key(loaded, sr))


class ChromaRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = self.tmp.name
        self.tags = os.path.join(self.lib, "_tags.json")
        rows = {
            "Keys/librosa.wav": {"key": "C", "key_source": "librosa"},
            "Keys/filename Em.wav": {"key": "Em", "key_source": "filename"},
            "Keys/done.wav": {"key": "C", "key_source": "librosa", "chroma_refreshed": "2026-11-01"},
            "Keys/unchanged.wav": {"key": "Am", "key_source": "librosa", "chroma": NEW_CHROMA},
            "Keys/gone.wav": {"key": "C", "key_source": "librosa"},
        }
        for rel, row in rows.items():
            row["features"] = {"spectral_centroid": 900.0, "chroma": row.pop("chroma", OLD_CHROMA)}
            if rel != "Keys/gone.wav":
                os.makedirs(os.path.dirname(os.path.join(self.lib, rel)), exist_ok=True)
                open(os.path.join(self.lib, rel), "wb").close()
        upsert_tag_entries(self.tags, rows)
        self.analyzed = []

    def tearDown(self):
        self.tmp.cleanup()

    def _fresh(self, full_path):
        self.analyzed.append(os.path.basename(full_path))
        return NEW_CHROMA, "Am"

    def _refresh(self, apply):
        args = SimpleNamespace(apply=apply, workers=2, limit=None, type=None, quiet=True, force=False)
        with patch.object(smart_retag, "LIBRARY", self.lib), \
             patch.object(smart_retag, "TAGS_FILE", self.tags), \
             patch.object(smart_retag, "chroma_and_key", side_effect=self._fresh), \
             patch("builtins.print"):
            smart_retag.run_refresh_chroma(args)
        return load_tag_db(self.tags)

    def test_apply_rewrites_chroma_and_librosa_keys_only(self):
        db = self._refresh(apply=True)

        row = db["Keys/librosa.wav"]
        self.assertEqual((row["features"]["chroma"], row["key"], row["key_source"]), (NEW_CHROMA, "Am", "librosa"))
        self.assertEqual(row["features"]["spectral_centroid"], 900.0)
        self.assertTrue(row["chroma_refreshed"])
        row = db["Keys/filename Em.wav"]
        self.assertEqual((row["features"]["chroma"], row["key"], row["key_source"]), (NEW_CHROMA, "Em", "filename"))
        self.assertEqual(db["Keys/unchanged.wav"]["key"], "Am")
        self.assertTrue(db["Keys/unchanged.wav"]["chroma_refreshed"])
        self.assertEqual(db["Keys/done.wav"]["features"]["chroma"], OLD_CHROMA)
        self.assertEqual(sorted(self.analyzed), ["filename Em.wav", "librosa.wav", "unchanged.wav"])

    def test_a_second_apply_skips_refreshed_rows(self):
        self._refresh(apply=True)
        self.analyzed.clear()
        self._refresh(apply=True)
        self.assertEqual(self.analyzed, [])

    def test_dry_run_writes_nothing(self):
        before = load_tag_db(self.tags)
        self.assertEqual(self._refresh(apply=False), before)


class FilenamePrecedenceTests(unittest.TestCase):
    FEATURES = {"bpm": 70.0, "key": "C", "duration": 2.0, "chroma": NEW_CHROMA}

    def test_retag_keeps_bpm_and_key_read_from_the_filename(self):
        existing = {"bpm": 140, "bpm_source": "filename", "key": "Em", "key_source": "filename"}
        entry = smart_retag._merge_tags(existing, {}, self.FEATURES, "Loops/x 140BPM Em.wav")
        self.assertEqual((entry["bpm"], entry["bpm_source"]), (140, "filename"))
        self.assertEqual((entry["key"], entry["key_source"]), ("Em", "filename"))

    def test_retag_still_updates_librosa_estimates(self):
        existing = {"bpm": 120.0, "bpm_source": "librosa", "key": "G", "key_source": "librosa"}
        entry = smart_retag._merge_tags(existing, {}, self.FEATURES, "Loops/x.wav")
        self.assertEqual((entry["bpm"], entry["key"]), (70.0, "C"))

    def test_refresh_bpm_restores_filename_bpms_and_their_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            tags = os.path.join(tmp, "_tags.json")
            upsert_tag_entries(tags, {
                "Loops/beat 140BPM.wav": {"bpm": 70.0, "bpm_source": "librosa", "tags": ["70bpm", "BRK"]},
                "Loops/beat.wav": {"bpm": 120.0, "bpm_source": "librosa", "tags": ["120bpm"]},
                "Loops/kept 128 BPM.wav": {"bpm": 128, "bpm_source": "filename", "tags": ["128bpm"]},
            })
            with patch.object(tag_library, "TAGS_FILE", tags), patch("builtins.print"):
                tag_library.refresh_filename_bpms()
            db = load_tag_db(tags)

        row = db["Loops/beat 140BPM.wav"]
        self.assertEqual((row["bpm"], row["bpm_source"], row["tags"]), (140, "filename", ["140bpm", "BRK"]))
        self.assertEqual(db["Loops/beat.wav"]["bpm"], 120.0)
        self.assertEqual(db["Loops/kept 128 BPM.wav"]["bpm"], 128)

    def test_refresh_bpm_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tags = os.path.join(tmp, "_tags.json")
            upsert_tag_entries(tags, {"Loops/beat 140BPM.wav": {"bpm": 70.0, "bpm_source": "librosa"}})
            before = load_tag_db(tags)
            with patch.object(tag_library, "TAGS_FILE", tags), patch("builtins.print"):
                tag_library.refresh_filename_bpms(dry_run=True)
            self.assertEqual(load_tag_db(tags), before)


if __name__ == "__main__":
    unittest.main()
