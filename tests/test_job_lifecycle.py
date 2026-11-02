"""Background jobs: start atomically, always finish, never block the UI forever."""
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from flask import Flask


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(REPO_ROOT, "scripts"), os.path.join(REPO_ROOT, "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api import pipeline as pipeline_api
from api import vibe as vibe_api
from api._helpers import JobTracker
from api.library import library_bp
from api.pipeline import pipeline_bp
from api.vibe import vibe_bp


class JobTrackerTests(unittest.TestCase):
    def test_start_exclusive_lets_only_one_concurrent_start_win(self):
        tracker = JobTracker()
        barrier = threading.Barrier(8)
        results = []

        def start():
            barrier.wait()
            results.append(tracker.start_exclusive(("running",), status="running"))

        threads = [threading.Thread(target=start) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sum(1 for r in results if r), 1)

    def test_unhandled_worker_error_finishes_the_job(self):
        tracker = JobTracker()
        job_id = tracker.start_exclusive(("running",), status="running")

        def boom():
            raise RuntimeError("worker crashed")

        tracker.start_thread(job_id, boom).join()

        job = tracker.get(job_id)
        self.assertEqual(job["status"], "error")
        self.assertEqual(job["error"], "worker crashed")
        self.assertTrue(job["finished_at"])
        self.assertIsNotNone(tracker.start_exclusive(("running",), status="running"))

    def test_terminal_status_stamps_finished_at(self):
        tracker = JobTracker()
        job_id = tracker.create(status="running")
        tracker.update(job_id, status="done")
        self.assertTrue(tracker.get(job_id)["finished_at"])


class ApiJobTests(unittest.TestCase):
    def setUp(self):
        pipeline_api._tracker.clear()
        vibe_api._vibe_tracker.clear()
        self.addCleanup(pipeline_api._tracker.clear)
        self.addCleanup(vibe_api._vibe_tracker.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        app = Flask(__name__)
        app.config.update(REPO_DIR=REPO_ROOT, TOOL_PATH_PREFIX="", LLM_TIMEOUT=30,
                          SAMPLE_LIBRARY=self.tmp.name, TAGS_FILE=os.path.join(self.tmp.name, "_tags.json"))
        for bp in (pipeline_bp, vibe_bp, library_bp):
            app.register_blueprint(bp, url_prefix="/api")
        self.client = app.test_client()

    def test_second_fetch_is_refused_while_one_runs(self):
        with pipeline_api._FETCH_LOCK:
            response = self.client.post("/api/pipeline/fetch", json={"bank": "b"})
            self.assertEqual(response.status_code, 409)
            with self.assertRaises(pipeline_api.FetchBusy):
                pipeline_api.execute_fetch_scope({}, bank="b")

    def test_a_fetch_without_ffmpeg_fails_before_clearing_the_bank(self):
        # Every conversion would fail, and publishing the empty staging area
        # used to clear the bank's WAVs from the card template.
        import fetch_samples

        with patch.object(fetch_samples, "resolve_command", return_value=None), \
             patch.object(fetch_samples, "clear_staging_wavs") as clear, \
             patch.object(fetch_samples, "publish_staging") as publish:
            with self.assertRaisesRegex(RuntimeError, "ffmpeg not found"):
                pipeline_api.execute_fetch_scope({"REPO_DIR": REPO_ROOT}, bank="b")
        clear.assert_not_called()
        publish.assert_not_called()

    def test_failed_vibe_startup_does_not_block_later_jobs(self):
        with patch.object(vibe_api, "_build_metadata_prompt", side_effect=RuntimeError("config unreadable")):
            response = self.client.post("/api/vibe/generate-fetch-bank", json={"bank": "c"})
        self.assertEqual(response.status_code, 500)

        with patch.object(vibe_api, "_run_populate_bank"):
            response = self.client.post("/api/vibe/populate-bank", json={"prompt": "dusty funk", "bank": "c"})
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_server_status_never_loads_the_discogs_model(self):
        with patch("discogs_engine._get_model", side_effect=AssertionError("model loaded in a request")):
            response = self.client.get("/api/pipeline/server/status")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_library_search_rejects_a_bad_limit(self):
        response = self.client.get("/api/library/search?q=kick&limit=lots")
        self.assertEqual(response.status_code, 400)


class SmartRetagCliTests(unittest.TestCase):
    def test_cli_accepts_the_flags_the_web_endpoint_passes(self):
        result = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "scripts", "smart_retag.py"), "--help"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--type", result.stdout)
        self.assertIn("--file", result.stdout)


if __name__ == "__main__":
    unittest.main()
