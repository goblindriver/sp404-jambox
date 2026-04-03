import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
WEB_DIR = os.path.join(REPO_ROOT, "web")

for path in (SCRIPTS_DIR, WEB_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.banks import banks_bp
import preset_utils


class BanksApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

        repo_dir = os.path.join(self.tmpdir.name, "repo")
        smpl_dir = os.path.join(repo_dir, "sd-card-template", "ROLAND", "SP-404SX", "SMPL")
        os.makedirs(smpl_dir, exist_ok=True)
        with open(os.path.join(repo_dir, "bank_config.yaml"), "w", encoding="utf-8") as handle:
            handle.write(
                "bank_a:\n"
                "  name: Alpha\n"
                "  pads:\n"
                "    1: KIK dusty one-shot\n"
            )

        self.app = Flask(__name__)
        self.app.config.update(REPO_DIR=repo_dir)
        self.app.register_blueprint(banks_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_update_bank_rejects_non_object_json_body(self):
        response = self.client.put("/api/banks/a", json=["Alpha"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Request body must be a JSON object")

    def test_update_bank_rejects_invalid_bpm(self):
        response = self.client.put("/api/banks/a", json={"bpm": "fast"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "bpm must be an integer")

    def test_update_pad_rejects_non_string_description(self):
        response = self.client.put("/api/banks/a/pads/1", json={"description": 123})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "description must be a string")

    def test_get_bank_rejects_invalid_letter(self):
        response = self.client.get("/api/banks/xyz")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "Bank not found")


class PresetUtilsTests(unittest.TestCase):
    def test_load_preset_returns_none_for_invalid_yaml(self):
        with tempfile.TemporaryDirectory() as tempdir:
            cat_dir = os.path.join(tempdir, "community")
            os.makedirs(cat_dir, exist_ok=True)
            preset_path = os.path.join(cat_dir, "broken.yaml")
            with open(preset_path, "w", encoding="utf-8") as handle:
                handle.write(": not yaml")

            with patch.object(preset_utils, "PRESETS_DIR", tempdir):
                self.assertIsNone(preset_utils.load_preset("community/broken"))

    def test_list_presets_handles_scalar_tags(self):
        with tempfile.TemporaryDirectory() as tempdir:
            cat_dir = os.path.join(tempdir, "community")
            os.makedirs(cat_dir, exist_ok=True)
            preset_path = os.path.join(cat_dir, "odd.yaml")
            with open(preset_path, "w", encoding="utf-8") as handle:
                handle.write("name: Odd Preset\ntags: dusty\npads:\n  1: BRK dusty loop\n")

            with patch.object(preset_utils, "PRESETS_DIR", tempdir):
                results = preset_utils.list_presets(tag="dusty")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Odd Preset")

    def test_load_config_returns_empty_dict_for_invalid_yaml(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = os.path.join(tempdir, "bank_config.yaml")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write(": not yaml")

            with patch.object(preset_utils, "CONFIG_PATH", config_path):
                self.assertEqual(preset_utils._load_config(), {})


if __name__ == "__main__":
    unittest.main()
