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

from api.pipeline import pipeline_bp
import fetch_samples


class PipelineApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

        repo_dir = os.path.join(self.tmpdir.name, "repo")
        sd_card = os.path.join(self.tmpdir.name, "sd-card")
        os.makedirs(repo_dir, exist_ok=True)
        os.makedirs(sd_card, exist_ok=True)

        self.app = Flask(__name__)
        self.app.config.update(
            REPO_DIR=repo_dir,
            SMPL_DIR=os.path.join(repo_dir, "sd-card-template", "ROLAND", "SP-404SX", "SMPL"),
            SD_CARD=sd_card,
            INGEST_LOG=os.path.join(self.tmpdir.name, "_ingest_log.json"),
            TOOL_PATH_PREFIX="",
        )
        self.app.register_blueprint(pipeline_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_build_padinfo_returns_failure_payload_on_nonzero_exit(self):
        failed = SimpleNamespace(returncode=1, stdout="partial output", stderr="padinfo failed")
        with patch("api.pipeline.subprocess.run", return_value=failed):
            response = self.client.post("/api/pipeline/padinfo")

        self.assertEqual(response.status_code, 500)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "padinfo failed")
        self.assertEqual(payload["output"], "partial output")

    def test_ingest_returns_summary_on_success(self):
        succeeded = SimpleNamespace(returncode=0, stdout="step 1\nImported 3 packs", stderr="")
        with patch("api.pipeline.subprocess.run", return_value=succeeded):
            response = self.client.post("/api/pipeline/ingest")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"], "Imported 3 packs")

    def test_deploy_checks_configured_mount_path(self):
        os.rmdir(self.app.config["SD_CARD"])
        response = self.client.post("/api/pipeline/deploy")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "SD card not mounted")

    def test_fetch_samples_clear_staging_removes_only_wavs(self):
        with tempfile.TemporaryDirectory() as staging_dir:
            wav_path = os.path.join(staging_dir, "A0000001.WAV")
            txt_path = os.path.join(staging_dir, "notes.txt")
            with open(wav_path, "w", encoding="utf-8") as handle:
                handle.write("wav")
            with open(txt_path, "w", encoding="utf-8") as handle:
                handle.write("keep")

            with patch.object(fetch_samples, "STAGING", staging_dir):
                fetch_samples.clear_staging_wavs()

            self.assertFalse(os.path.exists(wav_path))
            self.assertTrue(os.path.exists(txt_path))


if __name__ == "__main__":
    unittest.main()
