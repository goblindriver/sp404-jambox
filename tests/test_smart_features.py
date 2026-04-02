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


if __name__ == "__main__":
    unittest.main()
