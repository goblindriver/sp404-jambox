"""The duration-bucketed dedup pass must find what the all-pairs comparison found."""
import itertools
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


THRESHOLD = 0.93


def _frames(rng, seconds):
    return rng.integers(0, 2**32, size=max(1, int(seconds * 8)), dtype=np.uint64).astype(np.uint32)


def _flip_bits(rng, frames, rate):
    """Flip about `rate` of the bits, as a lossy re-encode does."""
    bits = np.unpackbits(frames.view(np.uint8))
    bits[rng.random(bits.size) < rate] ^= 1
    return np.packbits(bits).view(np.uint32)


class SyntheticLibrary:
    """Chromaprint-like loops, Python-fingerprint one-shots, and planted copies of both."""

    def __init__(self, seed=11):
        rng = np.random.default_rng(seed)
        self.files = {}  # name -> (duration, fpcalc frames or None, python vector)
        for i in range(40):
            seconds = float(rng.uniform(3, 20))
            self.files["loop%02d.wav" % i] = (seconds, _frames(rng, seconds), rng.random(128) ** 3)
        for i in range(20):
            self.files["shot%02d.wav" % i] = (float(rng.uniform(0.2, 2.5)), None, rng.random(128) ** 3)

        def copy(source, name, seconds_delta=0.0, flip=0.0, shift=0, noise=0.0):
            seconds, frames, vector = self.files[source]
            if frames is not None:
                frames = np.concatenate([_frames(rng, shift / 8), frames])[:len(frames) + shift] if shift else frames
                frames = _flip_bits(rng, frames, flip) if flip else frames.copy()
            vector = vector + rng.normal(0, noise, vector.shape) * vector.mean() if noise else vector.copy()
            self.files[name] = (seconds + seconds_delta, frames, vector)

        copy("loop00.wav", "loop00_copy.wav")
        copy("loop01.wav", "loop01_perturbed.wav", seconds_delta=0.25, flip=0.03, shift=2)
        copy("loop02.wav", "loop02_reencode.wav", seconds_delta=-0.05, flip=0.01)
        copy("loop03.wav", "loop03_a.wav", flip=0.02)
        copy("loop03.wav", "loop03_b.wav", seconds_delta=0.4, flip=0.02, shift=1)
        copy("shot00.wav", "shot00_copy.wav", seconds_delta=0.01, noise=0.01)
        # A file fpcalc could not read, matched against a loop through its Python fingerprint.
        copy("loop04.wav", "loop04_python_only.wav", seconds_delta=0.1, noise=0.01)
        seconds, _frames_unused, vector = self.files["loop04_python_only.wav"]
        self.files["loop04_python_only.wav"] = (seconds, None, vector)

    def db(self):
        return {name: {"duration": seconds, "tags": []} for name, (seconds, _f, _v) in self.files.items()}

    def fpcalc(self, path):
        frames = self.files[os.path.basename(path)][1]
        if frames is None:
            return None
        return {"kind": "fpcalc", "value": ",".join(map(str, frames.tolist())), "duration": 0.0}

    def python(self, path):
        return {"kind": "python", "value": self.files[os.path.basename(path)][2].tolist()}

    def brute_force_groups(self, names=None):
        """The old all-pairs comparison: no duration gating at all."""
        names = sorted(names or self.files)
        fps = {name: self.fpcalc(name) or self.python(name) for name in names}
        adjacency = {name: set() for name in names}
        for a, b in itertools.combinations(names, 2):
            score = deduplicate_samples.similarity(fps[a], fps[b])
            if score is None:
                score = deduplicate_samples.similarity(self.python(a), self.python(b))
            if score >= THRESHOLD:
                adjacency[a].add(b)
                adjacency[b].add(a)
        groups, seen = set(), set()
        for name in names:
            if name in seen or not adjacency[name]:
                continue
            group, stack = set(), [name]
            while stack:
                current = stack.pop()
                if current not in group:
                    group.add(current)
                    stack.extend(adjacency[current] - group)
            seen |= group
            groups.add(frozenset(group))
        return groups


class BucketedDedupTests(unittest.TestCase):
    def setUp(self):
        self.lib = SyntheticLibrary()
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(deduplicate_samples, "LIBRARY", self.tmp.name),
            patch("deduplicate_samples._fingerprint_with_fpcalc", side_effect=self.lib.fpcalc),
            patch("deduplicate_samples._fingerprint_with_python", side_effect=self.lib.python),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _write(self, names):
        for name in names:
            with open(os.path.join(self.tmp.name, name), "wb") as handle:
                handle.write(b"data")

    def _groups(self, db, **kwargs):
        reports = deduplicate_samples.find_duplicate_groups(db, threshold=THRESHOLD, **kwargs)
        return {frozenset([r["keep"], *r["duplicates"]]) for r in reports}

    def test_finds_the_same_groups_as_brute_force(self):
        self._write(self.lib.files)
        expected = self.lib.brute_force_groups()

        self.assertEqual(self._groups(self.lib.db()), expected)
        self.assertEqual(len(expected), 6)
        self.assertIn(frozenset({"loop03.wav", "loop03_a.wav", "loop03_b.wav"}), expected)
        self.assertIn(frozenset({"loop04.wav", "loop04_python_only.wav"}), expected)

    def test_a_perturbed_copy_is_still_caught(self):
        original, perturbed = self.lib.fpcalc("loop01.wav"), self.lib.fpcalc("loop01_perturbed.wav")
        self.assertLess(deduplicate_samples.similarity(original, perturbed), 0.99)  # really perturbed
        self._write(self.lib.files)

        self.assertIn(frozenset({"loop01.wav", "loop01_perturbed.wav"}), self._groups(self.lib.db()))

    def test_files_of_very_different_length_are_not_compared(self):
        # A one-bar chop of a loop: brute force calls it a duplicate (the
        # overlap is identical), but it is a different sample on the pad.
        seconds, frames, vector = self.lib.files["loop05.wav"]
        self.lib.files["loop05_chop.wav"] = (seconds / 4, frames[:len(frames) // 4].copy(), vector * 0.5)
        names = ["loop05.wav", "loop05_chop.wav", "loop06.wav"]
        self._write(names)
        db = {name: row for name, row in self.lib.db().items() if name in names}

        self.assertEqual(self.lib.brute_force_groups(names), {frozenset({"loop05.wav", "loop05_chop.wav"})})
        self.assertEqual(self._groups(db), set())

    def test_unreadable_files_are_skipped_not_grouped(self):
        names = ["loop00.wav", "loop00_copy.wav", "broken_a.wav", "broken_b.wav"]
        self._write(names)
        db = {name: {"duration": 8.0, "tags": []} for name in names}
        db["loop00.wav"]["duration"] = db["loop00_copy.wav"]["duration"] = self.lib.files["loop00.wav"][0]
        self.lib.files["broken_a.wav"] = self.lib.files["broken_b.wav"] = (8.0, None, None)
        stats = {}

        with patch("deduplicate_samples._fingerprint_with_python",
                   side_effect=lambda path: None if "broken" in path else self.lib.python(path)):
            groups = self._groups(db, stats=stats)

        self.assertEqual(groups, {frozenset({"loop00.wav", "loop00_copy.wav"})})
        self.assertEqual(stats["unreadable"], 2)

    def test_second_run_reuses_the_fingerprint_cache(self):
        self._write(self.lib.files)
        first = self._groups(self.lib.db())
        calls = deduplicate_samples._fingerprint_with_fpcalc.call_count

        self.assertEqual(self._groups(self.lib.db()), first)
        fpcalc_files = sum(1 for _s, frames, _v in self.lib.files.values() if frames is not None)
        # Only the files fpcalc cannot read are retried; the fpcalc results come from the cache.
        self.assertEqual(deduplicate_samples._fingerprint_with_fpcalc.call_count - calls,
                         len(self.lib.files) - fpcalc_files)


class DurationWindowTests(unittest.TestCase):
    def test_every_comparable_pair_is_scored_and_no_other(self):
        rng = np.random.default_rng(5)
        durations = np.concatenate([
            rng.uniform(0.05, 30, 300),
            np.full(40, 8.0),  # a dense cluster of same-length loops
            rng.uniform(1.9, 2.1, 40),
            np.zeros(15),  # unknown duration: compared only with each other
        ])
        rng.shuffle(durations)
        scored = []

        def everything_matches(rows, cols):
            scored.append(len(rows) * len(cols))
            return np.ones((len(rows), len(cols)))

        with patch.object(deduplicate_samples, "_BLOCK_ELEMENTS", 500):  # force many small blocks
            pairs = deduplicate_samples._matching_pairs(durations, everything_matches, lambda items: 1, 0.5)

        expected = set()
        for i, j in itertools.combinations(range(len(durations)), 2):
            a, b = durations[i], durations[j]
            if (a == 0 and b == 0) or (a > 0 and b > 0 and abs(a - b) <= max(0.5, 0.1 * max(a, b))):
                expected.add((i, j))
        self.assertEqual({tuple(sorted(p)) for p in pairs}, expected)
        self.assertEqual(len(pairs), len(expected))  # each pair once
        self.assertGreater(len(scored), 10)
        self.assertLess(sum(scored), len(durations) ** 2 / 4)  # nowhere near all pairs

    def test_vectorized_scores_match_fingerprint_similarity_exactly(self):
        rng = np.random.default_rng(9)
        arrays = [_frames(rng, rng.uniform(0, 8)) for _ in range(30)]
        arrays += [_flip_bits(rng, arr, 0.02) for arr in arrays[:10]]
        arrays.append(np.zeros(0, dtype=np.uint32))
        score_block, _cost = deduplicate_samples._chromaprint_scorer(arrays)
        everything = np.arange(len(arrays))

        scores = score_block(everything, everything)

        for i, j in itertools.product(range(len(arrays)), repeat=2):
            self.assertEqual(scores[i, j], deduplicate_samples.fingerprint_similarity(arrays[i], arrays[j]))


if __name__ == "__main__":
    unittest.main()
