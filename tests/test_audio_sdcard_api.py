import io
import os
import subprocess
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

from api.audio import audio_bp
from api.sdcard import sdcard_bp


class AudioSdcardApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

        repo_dir = os.path.join(self.tmpdir.name, "repo")
        sample_library = os.path.join(self.tmpdir.name, "library")
        sd_card = os.path.join(self.tmpdir.name, "sd-card")
        sd_smpl = os.path.join(sd_card, "ROLAND", "SP-404SX", "SMPL")
        gold_dir = os.path.join(sample_library, "_GOLD", "Bank-A")
        os.makedirs(repo_dir, exist_ok=True)
        os.makedirs(sample_library, exist_ok=True)
        os.makedirs(sd_smpl, exist_ok=True)
        os.makedirs(gold_dir, exist_ok=True)

        self.app = Flask(__name__)
        self.app.config.update(
            REPO_DIR=repo_dir,
            SAMPLE_LIBRARY=sample_library,
            FFMPEG_BIN="ffmpeg",
            SD_CARD=sd_card,
            SD_SMPL_DIR=sd_smpl,
            GOLD_BANK_A_DIR=gold_dir,
        )
        self.app.register_blueprint(audio_bp, url_prefix="/api")
        self.app.register_blueprint(sdcard_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_audio_assign_rejects_non_object_json_body(self):
        response = self.client.post("/api/audio/assign", json=["a", 1, "Loops/foo.wav"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Request body must be a JSON object")

    def test_audio_assign_rejects_invalid_pad(self):
        response = self.client.post("/api/audio/assign", json={"bank": "a", "pad": "thirteen", "library_path": "Loops/foo.wav"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "pad must be an integer")

    def test_convert_to_pad_reports_failure(self):
        with self.app.app_context():
            with patch("wav_utils.convert_and_tag", return_value=False):
                target, error = __import__("api.audio", fromlist=[""])._convert_to_pad("/tmp/source.wav", "a", 1)

        self.assertIsNone(target)
        self.assertIn("failed", error.lower())

    def test_audio_upload_rejects_missing_file(self):
        response = self.client.post(
            "/api/audio/upload",
            data={"bank": "a", "pad": "1", "file": (io.BytesIO(b"data"), "")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Missing file")

    def test_gold_sessions_ignores_non_directory_entries(self):
        gold_dir = self.app.config["GOLD_BANK_A_DIR"]
        with open(os.path.join(gold_dir, "session-note.txt"), "w", encoding="utf-8") as handle:
            handle.write("ignore")
        with open(os.path.join(gold_dir, "session-bad"), "w", encoding="utf-8") as handle:
            handle.write("not a directory")
        session_dir = os.path.join(gold_dir, "session-2026-04-02")
        os.makedirs(session_dir, exist_ok=True)
        with open(os.path.join(session_dir, "A0000001.WAV"), "wb") as handle:
            handle.write(b"wav")

        response = self.client.get("/api/gold/sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["sessions"], [{"name": "session-2026-04-02", "count": 1}])


if __name__ == "__main__":
    unittest.main()
