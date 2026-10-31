"""What lands on a pad must match what its description asks for."""
import os
import struct
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
import fetch_samples
import gen_padinfo
import gen_patterns
from jambox_cache import score_cache_key
from scoring_engine import key_score
from tag_library import extract_key
from tag_vocab import canonical_key


class PadQueryTests(unittest.TestCase):
    def test_texture_words_are_not_rewritten_as_vibes(self):
        self.assertEqual(fetch_samples.parse_pad_query("BAS funk warm loop")["keywords"], {"funk", "warm"})
        self.assertEqual(fetch_samples.parse_pad_query("PAD dusty raw loop")["keywords"], {"dusty", "raw"})

    def test_aliases_still_apply_to_non_canonical_words(self):
        self.assertEqual(fetch_samples.parse_pad_query("SYN happy spooky loop")["keywords"], {"uplifting", "eerie"})

    def test_multiword_aliases_join_before_tokenizing(self):
        parsed = fetch_samples.parse_pad_query("BRK boom bap hip hop loop")
        self.assertEqual(parsed["keywords"], {"boom-bap", "hiphop"})

    def test_keys_in_descriptions_are_canonical(self):
        self.assertEqual(fetch_samples.parse_pad_query("BAS C#m loop")["key"], "Csm")
        self.assertEqual(fetch_samples.parse_pad_query("BAS Am loop")["key"], "Am")
        self.assertIsNone(fetch_samples.parse_pad_query("BAS bass loop")["key"])


class KeyTests(unittest.TestCase):
    def test_canonical_key(self):
        cases = {"A min": "Am", "c#m": "Csm", "Bbmaj": "Bb", "F#": "Fs", "Ebminor": "Ebm",
                 "Csm": "Csm", "XX": None, "": None, "bass": None}
        for raw, expected in cases.items():
            self.assertEqual(canonical_key(raw), expected, raw)

    def test_extract_key_keeps_minor(self):
        cases = {
            "Bass_Am_120.wav": "Am",
            "Synth - Cmin - 120.wav": "Cm",
            "Pad_C#m_90.wav": "Csm",
            "Drums_A_Kick_Ebmin_120.wav": "Ebm",
            "Lead_Bb_maj.wav": "Bb",
            "Vox_G.wav": "G",
            "kick_e_01.wav": None,
            "FM_Bass_120.wav": None,
            "Keys_AMin_90.wav": "Am",
            # Uppercase M is a word, not minor: ambient packs, FM synths, "CM".
            "musicradar-ambient_AM_GuitVerber120D-05.flac": None,
            "SYNTH-PWM-FM-Rich.flac": None,
            "Organic-Violin_CM 70 bpm 4.flac": None,
            "Bass Loop FM Mod C# 128bpm.flac": "Cs",
        }
        for name, expected in cases.items():
            self.assertEqual(extract_key(name), expected, name)

    def test_key_score_uses_canonical_spellings(self):
        self.assertEqual(key_score("Am", "A min"), 1.0)
        self.assertEqual(key_score("C#m", "Dbm"), 1.0)
        self.assertGreater(key_score("Am", "C"), 0)
        self.assertEqual(key_score("Am", "Fs"), 0)


class PadInfoTests(unittest.TestCase):
    def test_pad_mode_follows_playability(self):
        self.assertEqual(gen_padinfo.pad_mode("BRK big-beat stomp loop", 1), (True, False))
        self.assertEqual(gen_padinfo.pad_mode("KIK hard one-shot", 1), (False, True))
        self.assertEqual(gen_padinfo.pad_mode("SFX impact slam one-shot", 9), (False, False))
        self.assertEqual(gen_padinfo.pad_mode("RSR white-noise riser transition", 7), (False, False))
        self.assertEqual(gen_padinfo.pad_mode("KEY rhodes chromatic", 10), (False, True))
        self.assertEqual(gen_padinfo.pad_mode(None, 2), (False, True))
        self.assertEqual(gen_padinfo.pad_mode(None, 7), (True, False))

    def test_generated_records_use_the_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = os.path.join(tmp, "bank_config.yaml")
            with open(config, "w", encoding="utf-8") as fh:
                fh.write("bank_b:\n  bpm: 130\n  pads:\n    1: BRK fat stomp loop\n"
                         "bank_j:\n  pads:\n    5: VOX drop-callout one-shot\n")
            for name in ("B0000001.WAV", "J0000005.WAV"):
                with open(os.path.join(tmp, name), "wb") as fh:
                    fh.write(b"\x00" * 2048)

            with patch.object(gen_padinfo, "CONFIG_PATH", config):
                out = gen_padinfo.generate_padinfo(tmp)

            with open(out, "rb") as fh:
                data = fh.read()

        def flags(bank, pad):
            off = ((ord(bank) - ord("A")) * 12 + pad - 1) * 32
            rec = struct.unpack(">IIII BBBBBBBB II", data[off:off + 32])
            return rec[6], rec[7]  # loop, gate

        self.assertEqual(flags("B", 1), (1, 0))
        self.assertEqual(flags("J", 5), (0, 0))


class PatternRoleTests(unittest.TestCase):
    def test_roles_map_to_one_shot_drum_pads_only(self):
        pads = {1: "BRK break loop", 2: "KIK punch one-shot", 3: "CLP snap one-shot",
                4: "HAT tick one-shot", 5: "PRC conga loop"}
        self.assertEqual(gen_patterns.drum_roles(pads), {1: 2, 2: 3, 3: 4})

    def test_banks_without_kick_and_snare_get_no_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = os.path.join(tmp, "bank_config.yaml")
            with open(config, "w", encoding="utf-8") as fh:
                fh.write("bank_c:\n  pads:\n    1: KIK one-shot\n    2: SNR one-shot\n    3: HAT one-shot\n"
                         "bank_d:\n  pads:\n    1: BRK loop\n")
            ptn_dir = os.path.join(tmp, "PTN")
            os.makedirs(ptn_dir)
            stale_d = os.path.join(ptn_dir, gen_patterns.get_ptn_filename("d", 1))
            open(stale_d, "wb").close()

            with patch.object(gen_patterns, "CONFIG_PATH", config), patch("builtins.print"):
                gen_patterns.generate_patterns(ptn_dir)

            self.assertTrue(os.path.exists(os.path.join(ptn_dir, gen_patterns.get_ptn_filename("c", 1))))
            self.assertFalse(os.path.exists(stale_d))


class FetchPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.staging = os.path.join(self.tmp.name, "staging")
        self.smpl = os.path.join(self.tmp.name, "SMPL")
        os.makedirs(self.staging)
        os.makedirs(self.smpl)
        self.patches = [patch.object(fetch_samples, "STAGING", self.staging),
                        patch.object(fetch_samples, "SMPL_DIR", self.smpl)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _touch(self, folder, name, data=b"x"):
        with open(os.path.join(folder, name), "wb") as fh:
            fh.write(data)

    def test_publish_clears_unmatched_pads_in_scope_only(self):
        self._touch(self.smpl, "B0000001.WAV", b"old")
        self._touch(self.smpl, "B0000002.WAV", b"old")   # no match this run
        self._touch(self.smpl, "C0000001.WAV", b"other bank")
        self._touch(self.staging, "B0000001.WAV", b"new")

        self.assertEqual(fetch_samples.publish_staging(bank="b"), 1)

        self.assertEqual(sorted(os.listdir(self.smpl)), ["B0000001.WAV", "C0000001.WAV"])
        with open(os.path.join(self.smpl, "B0000001.WAV"), "rb") as fh:
            self.assertEqual(fh.read(), b"new")

    def test_clear_staging_with_pad_only_does_not_wipe_everything(self):
        self._touch(self.staging, "B0000003.WAV")
        self._touch(self.staging, "B0000004.WAV")
        fetch_samples.clear_staging_wavs(pad=3)
        self.assertEqual(os.listdir(self.staging), ["B0000004.WAV"])

    def test_fetch_pad_falls_back_when_conversion_fails(self):
        candidates = [{"path": "/lib/a.wav", "score": 9}, {"path": "/lib/b.wav", "score": 8}]
        converted = []

        def convert(src, *_args):
            converted.append(src)
            return src == "/lib/b.wav"

        with patch.object(fetch_samples, "search_local", return_value=("/lib/a.wav", 9, candidates)), \
             patch.object(fetch_samples, "convert_and_tag", side_effect=convert), \
             patch.object(fetch_samples, "_library_rel_path", return_value=None), \
             patch("builtins.print"):
            used = set()
            result = fetch_samples.fetch_pad("b", 1, "KIK one-shot", {}, {}, used)

        self.assertEqual(converted, ["/lib/a.wav", "/lib/b.wav"])
        self.assertEqual(result, os.path.join(self.staging, "B0000001.WAV"))
        self.assertEqual(used, {"/lib/b.wav"})


class CacheKeyTests(unittest.TestCase):
    def test_energy_is_part_of_the_score_cache_key(self):
        base = {"type_code": "KIK", "playability": None, "bpm": None, "key": None, "keywords": {"hard"}}
        high = score_cache_key({**base, "energy": "high"}, {}, score_version=1, tags_marker={})
        low = score_cache_key({**base, "energy": "low"}, {}, score_version=1, tags_marker={})
        self.assertNotEqual(high, low)


class FingerprintTests(unittest.TestCase):
    def test_near_identical_fingerprints_score_high_and_unrelated_low(self):
        rng = np.random.default_rng(7)
        a = rng.integers(0, 2**32, size=300, dtype=np.uint64).astype(np.uint32)
        noisy = a.copy()
        noisy[::10] ^= np.uint32(1 << 5)  # one flipped bit in every tenth frame
        unrelated = rng.integers(0, 2**32, size=300, dtype=np.uint64).astype(np.uint32)

        self.assertGreater(deduplicate_samples.fingerprint_similarity(a, noisy), 0.99)
        self.assertLess(deduplicate_samples.fingerprint_similarity(a, unrelated), 0.6)

    def test_similarity_parses_signed_fpcalc_strings(self):
        fp = {"kind": "fpcalc", "value": "-1,2,3,-4"}
        self.assertEqual(deduplicate_samples.similarity(fp, dict(fp)), 1.0)

    def test_missing_fpcalc_falls_back_to_python_fingerprint(self):
        with patch("deduplicate_samples.subprocess.run", side_effect=FileNotFoundError), \
             patch("deduplicate_samples.dedup_library.compute_fingerprint", return_value=np.array([0.5, 0.25])):
            fp = deduplicate_samples.compute_fingerprint("x.wav")
        self.assertEqual(fp, {"kind": "python", "value": [0.5, 0.25]})


if __name__ == "__main__":
    unittest.main()
