"""Exact-audio dedup: identical decoded samples are a copy, whatever the fingerprints say."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import deduplicate_samples

soundfile = None
try:
    import soundfile
except ImportError:
    pass


def _tone(step, seconds=0.5):
    # int16 samples: every container then stores the same integers (float input is
    # rounded differently by libsndfile's WAV and FLAC writers).
    return (9000 * np.sin(np.arange(int(44100 * seconds)) * step)).astype(np.int16)


@unittest.skipUnless(soundfile, "needs soundfile")
class PcmHashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, samples, subtype="PCM_16"):
        path = os.path.join(self.tmp.name, name)
        soundfile.write(path, samples, 44100, subtype=subtype)
        return path

    def test_the_same_samples_hash_alike_in_any_lossless_container(self):
        tone = _tone(0.05)
        self.assertEqual(deduplicate_samples.pcm_hash(self._write("a.wav", tone)),
                         deduplicate_samples.pcm_hash(self._write("a.flac", tone)))
        self.assertNotEqual(deduplicate_samples.pcm_hash(self._write("a.wav", tone)),
                            deduplicate_samples.pcm_hash(self._write("b.wav", _tone(0.07))))

    def test_silence_and_unreadable_files_get_no_hash(self):
        self.assertIsNone(deduplicate_samples.pcm_hash(self._write("silent.wav", np.zeros(22050, np.int16))))
        path = os.path.join(self.tmp.name, "broken.wav")
        with open(path, "wb") as fh:
            fh.write(b"RIFF")
        self.assertIsNone(deduplicate_samples.pcm_hash(path))

    def test_exact_copies_are_grouped_before_fingerprinting_and_flac_is_kept(self):
        tone = _tone(0.05)
        self._write("hit.wav", tone)
        self._write("hit.flac", tone)
        self._write("other.wav", _tone(0.07))
        db = {name: {"duration": 0.5, "tags": []} for name in ("hit.wav", "hit.flac", "other.wav")}
        fingerprinted = []

        def fallback(path):  # no chromaprint, and fallback vectors that never match
            fingerprinted.append(os.path.basename(path))
            return {"kind": "python", "value": [1.0 if i == len(fingerprinted) else 0.0 for i in range(4)]}

        with patch.object(deduplicate_samples, "LIBRARY", self.tmp.name), \
             patch("deduplicate_samples._fingerprint_with_fpcalc", return_value=None), \
             patch("deduplicate_samples._fingerprint_with_python", side_effect=fallback):
            stats = {}
            groups = deduplicate_samples.find_duplicate_groups(db, stats=stats)

        self.assertEqual([(g["keep"], g["duplicates"], g["match"]) for g in groups],
                         [("hit.flac", ["hit.wav"], "exact")])
        self.assertNotIn("hit.wav", fingerprinted)  # settled by the hash, never fingerprinted
        self.assertEqual(stats["exact_copies"], 1)

    def test_the_hash_is_cached_per_file(self):
        self._write("hit.wav", _tone(0.05))
        cache = {}
        with patch.object(deduplicate_samples, "LIBRARY", self.tmp.name), \
             patch.object(deduplicate_samples, "save_fingerprint_cache"):
            first = deduplicate_samples._pcm_hashes(["hit.wav"], cache, 1)
            with patch.object(deduplicate_samples, "pcm_hash", side_effect=AssertionError("re-read")):
                self.assertEqual(deduplicate_samples._pcm_hashes(["hit.wav"], cache, 1), first)


if __name__ == "__main__":
    unittest.main()
