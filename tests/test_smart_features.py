import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
WEB_DIR = os.path.join(REPO_ROOT, "web")

for path in (SCRIPTS_DIR, WEB_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.vibe import vibe_bp
from api.pattern import pattern_bp
from api.presets import presets_bp
import deduplicate_samples
import daily_bank
import vibe_generate


class SmartFeatureApiTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            REPO_DIR=REPO_ROOT,
            TOOL_PATH_PREFIX="",
            LLM_TIMEOUT=30,
        )
        self.app.register_blueprint(vibe_bp, url_prefix="/api")
        self.app.register_blueprint(pattern_bp, url_prefix="/api")
        self.app.register_blueprint(presets_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_vibe_route_returns_script_payload(self):
        script_output = {
            "prompt": "dusty funk drums",
            "query": "BRK dusty funk loop",
            "parsed": {"keywords": ["dusty", "funk"]},
            "bank_suggestions": [],
            "sample_suggestions": [],
        }
        with patch("api.vibe.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(script_output), stderr="")):
            response = self.client.post("/api/vibe/generate", json={"prompt": "dusty funk drums"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["query"], "BRK dusty funk loop")

    def test_pattern_route_surfaces_generator_error(self):
        failed = SimpleNamespace(returncode=1, stdout="", stderr="checkpoint missing")
        with patch("api.pattern.subprocess.run", return_value=failed):
            response = self.client.post("/api/pattern/generate", json={"variant": "drum"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "checkpoint missing")

    def test_daily_preset_route_loads_into_bank(self):
        with patch("api.presets.db.build_daily_preset", return_value={"ref": "auto/daily-2026-04-02", "path": "/tmp/daily.yaml", "preset": {}}), patch("api.presets.pu.load_preset_to_bank") as load_mock:
            response = self.client.post("/api/presets/daily", json={"bank": "b"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["loaded_bank"], "b")
        load_mock.assert_called_once_with("auto/daily-2026-04-02", "b")


class DailyBankTests(unittest.TestCase):
    def test_build_daily_preset_uses_existing_preset_schema(self):
        fake_db = {
            "Loops/foo.wav": {
                "type_code": "BRK",
                "genre": ["funk"],
                "vibe": ["dusty"],
                "texture": ["warm"],
                "playability": "loop",
                "bpm": 118,
            }
        }
        with patch("daily_bank._load_tag_db", return_value=fake_db), patch("daily_bank._recent_candidates", return_value=[(10, "Loops/foo.wav", fake_db["Loops/foo.wav"])]), patch("daily_bank._weighted_pick", return_value=[(10, "Loops/foo.wav", fake_db["Loops/foo.wav"])] * 12), patch("daily_bank.preset_utils.save_preset", return_value="auto/daily-test") as save_mock:
            result = daily_bank.build_daily_preset(source="recent")

        preset_arg = save_mock.call_args[0][0]
        self.assertEqual(result["ref"], "auto/daily-test")
        self.assertEqual(len(preset_arg["pads"]), 12)
        self.assertTrue(all(isinstance(value, str) for value in preset_arg["pads"].values()))

    def test_build_daily_preset_skips_invalid_bpm_values(self):
        fake_db = {
            "Loops/foo.wav": {
                "type_code": "BRK",
                "genre": ["funk"],
                "vibe": ["dusty"],
                "texture": ["warm"],
                "playability": "loop",
                "bpm": "fast",
            }
        }
        picks = [(10, "Loops/foo.wav", fake_db["Loops/foo.wav"])] * 12
        with patch("daily_bank._load_tag_db", return_value=fake_db), patch("daily_bank._recent_candidates", return_value=picks), patch("daily_bank._weighted_pick", return_value=picks), patch("daily_bank.preset_utils.save_preset", return_value="auto/daily-test") as save_mock:
            result = daily_bank.build_daily_preset(source="recent")

        preset_arg = save_mock.call_args[0][0]
        self.assertEqual(result["ref"], "auto/daily-test")
        self.assertEqual(preset_arg["bpm"], 120)

    def test_load_trending_terms_falls_back_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            trending_path = os.path.join(tempdir, "trending.json")
            with open(trending_path, "w", encoding="utf-8") as handle:
                handle.write("{not valid json")

            with patch.dict(daily_bank.SETTINGS, {"TRENDING_FILE": trending_path}, clear=False):
                terms = daily_bank._load_trending_terms()

        self.assertEqual(terms, daily_bank.DEFAULT_TRENDING_TERMS)


class VibeGenerateTests(unittest.TestCase):
    def test_generate_vibe_suggestions_uses_defaults_for_bad_numeric_inputs(self):
        llm_tags = {
            "keywords": ["dusty"],
            "type_code": "BRK",
            "playability": "loop",
            "vibe": ["warm"],
            "genre": ["funk"],
            "texture": [],
            "energy": [],
            "rationale": "test",
        }
        with patch("vibe_generate._call_llm", return_value=llm_tags), patch("vibe_generate.fetch_samples.rank_library_matches", return_value=[] ) as match_mock, patch("vibe_generate._load_bank_config", return_value={}):
            result = vibe_generate.generate_vibe_suggestions(
                {"prompt": "dusty funk", "limit": "abc", "min_score": "-2"}
            )

        self.assertEqual(result["query"], "BRK dusty warm funk loop")
        self.assertEqual(match_mock.call_args.kwargs["limit"], 12)
        self.assertEqual(match_mock.call_args.kwargs["min_score"], 4)

    def test_generate_vibe_suggestions_handles_missing_bank_config(self):
        llm_tags = {
            "keywords": ["dusty"],
            "type_code": "BRK",
            "playability": "loop",
            "vibe": [],
            "genre": [],
            "texture": [],
            "energy": [],
            "rationale": "test",
        }
        with patch("vibe_generate._call_llm", return_value=llm_tags), patch("vibe_generate.fetch_samples.rank_library_matches", return_value=[{"path": "Loops/foo.wav"}]), patch("vibe_generate._load_bank_config", return_value={}):
            result = vibe_generate.generate_vibe_suggestions({"prompt": "dusty break"})

        self.assertEqual(result["sample_suggestions"], [{"path": "Loops/foo.wav"}])
        self.assertEqual(result["bank_suggestions"], [])


class DedupeTests(unittest.TestCase):
    def test_find_duplicate_groups_with_mocked_fingerprints(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db = {
                "a.wav": {"tags": ["one"]},
                "b.wav": {"tags": []},
                "c.wav": {"tags": ["other"]},
            }
            for name in db:
                with open(os.path.join(tempdir, name), "wb") as handle:
                    handle.write(b"data")

            with patch.object(deduplicate_samples, "LIBRARY", tempdir), patch("deduplicate_samples.compute_fingerprint", side_effect=[
                {"kind": "fpcalc", "value": "1,2,3"},
                {"kind": "fpcalc", "value": "1,2,3"},
                {"kind": "fpcalc", "value": "9,9,9"},
            ]):
                groups = deduplicate_samples.find_duplicate_groups(db, threshold=0.99)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["keep"], "a.wav")
        self.assertEqual(groups[0]["duplicates"], ["b.wav"])

    def test_find_duplicate_groups_merges_transitive_matches(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db = {
                "a.wav": {"tags": ["one"]},
                "b.wav": {"tags": []},
                "c.wav": {"tags": ["other"]},
            }
            for name in db:
                with open(os.path.join(tempdir, name), "wb") as handle:
                    handle.write(b"data")

            scores = {
                ("a.wav", "b.wav"): 0.99,
                ("a.wav", "c.wav"): 0.10,
                ("b.wav", "c.wav"): 0.99,
            }

            def fake_pair_similarity(rel_path, compare_path, fingerprints, python_fingerprints):
                return scores[(rel_path, compare_path)]

            with patch.object(deduplicate_samples, "LIBRARY", tempdir), patch("deduplicate_samples.compute_fingerprint", return_value={"kind": "fpcalc", "value": "stub"}), patch("deduplicate_samples._pair_similarity", side_effect=fake_pair_similarity):
                groups = deduplicate_samples.find_duplicate_groups(db, threshold=0.95)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["keep"], "a.wav")
        self.assertEqual(groups[0]["duplicates"], ["c.wav", "b.wav"])

    def test_find_duplicate_groups_uses_python_fallback_for_mixed_kinds(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db = {
                "a.wav": {"tags": ["one"]},
                "b.wav": {"tags": []},
            }
            for name in db:
                with open(os.path.join(tempdir, name), "wb") as handle:
                    handle.write(b"data")

            with patch.object(deduplicate_samples, "LIBRARY", tempdir), patch("deduplicate_samples.compute_fingerprint", side_effect=[
                {"kind": "fpcalc", "value": "1,2,3"},
                {"kind": "python", "value": [1.0, 2.0, 3.0]},
            ]), patch("deduplicate_samples._fingerprint_with_python", return_value={"kind": "python", "value": [1.0, 2.0, 3.0]}), patch("deduplicate_samples.dedup_library.cosine_similarity", return_value=0.999):
                groups = deduplicate_samples.find_duplicate_groups(db, threshold=0.95)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["keep"], "a.wav")
        self.assertEqual(groups[0]["duplicates"], ["b.wav"])

    def test_apply_clean_moves_files_and_updates_tag_db(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tags_path = os.path.join(tempdir, "_tags.json")
            db = {
                "keep.wav": {"tags": ["keep"]},
                "dupe.wav": {"tags": ["dupe"]},
            }
            for name in db:
                with open(os.path.join(tempdir, name), "wb") as handle:
                    handle.write(b"data")

            with patch.object(deduplicate_samples, "LIBRARY", tempdir), patch.object(deduplicate_samples, "TAGS_FILE", tags_path), patch.object(deduplicate_samples, "DUPES_DIR", os.path.join(tempdir, "_DUPES")):
                updated = deduplicate_samples.apply_clean(
                    [{"keep": "keep.wav", "duplicates": ["dupe.wav"], "members": []}],
                    db,
                )

            self.assertIn("keep.wav", updated)
            self.assertNotIn("dupe.wav", updated)
            self.assertFalse(os.path.exists(os.path.join(tempdir, "dupe.wav")))
            self.assertTrue(os.path.exists(os.path.join(tempdir, "_DUPES", "dupe.wav")))
            with open(tags_path, encoding="utf-8") as handle:
                persisted = json.load(handle)
            self.assertNotIn("dupe.wav", persisted)


if __name__ == "__main__":
    unittest.main()
