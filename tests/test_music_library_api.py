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

import api.music as music_api
import api.library as library_api
from api.music import music_bp
from api.library import library_bp


class MusicLibraryApiTests(unittest.TestCase):
    def setUp(self):
        music_api._split_tracker.clear()
        library_api._retag_tracker.clear()
        self.addCleanup(music_api._split_tracker.clear)
        self.addCleanup(library_api._retag_tracker.clear)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

        sample_library = os.path.join(self.tmpdir.name, "library")
        downloads = os.path.join(self.tmpdir.name, "downloads")
        os.makedirs(sample_library, exist_ok=True)
        os.makedirs(downloads, exist_ok=True)

        self.app = Flask(__name__)
        self.app.config.update(
            REPO_DIR=REPO_ROOT,
            MUSIC_INDEX_FILE=os.path.join(self.tmpdir.name, "music-index.json"),
            STEMS_DIR=os.path.join(self.tmpdir.name, "stems"),
            SAMPLE_LIBRARY=sample_library,
            TAGS_FILE=os.path.join(sample_library, "_tags.json"),
            DOWNLOADS_PATH=downloads,
        )
        self.app.register_blueprint(music_bp, url_prefix="/api")
        self.app.register_blueprint(library_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_split_route_rejects_non_object_json_body(self):
        response = self.client.post("/api/music/split", json=["123"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Request body must be a JSON object")

    def test_split_route_rejects_non_integer_track_id(self):
        response = self.client.post("/api/music/split", json={"track_id": "abc"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "track_id must be an integer")

    def test_split_route_rejects_second_request_while_first_is_starting(self):
        track_path = os.path.join(self.tmpdir.name, "track.wav")
        with open(track_path, "wb") as handle:
            handle.write(b"data")

        fake_plex = SimpleNamespace(
            track=lambda track_id: {
                "id": track_id,
                "artist": "Test Artist",
                "title": "Test Track",
                "file_path": track_path,
            }
        )

        class FakeThread:
            daemon = False

            def __init__(self, target=None, args=None, kwargs=None):
                self.target = target
                self.args = args
                self.kwargs = kwargs or {}

            def start(self):
                return None

        with patch("api.music._get_plex", return_value=fake_plex), patch("api.music.threading.Thread", side_effect=FakeThread):
            first = self.client.post("/api/music/split", json={"track_id": 123})
            second = self.client.post("/api/music/split", json={"track_id": 123})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.get_json()["error"], "Already splitting")

    def test_library_by_tag_rejects_invalid_limit(self):
        with open(self.app.config["TAGS_FILE"], "w", encoding="utf-8") as handle:
            json.dump({"Loops/foo.wav": {"tags": ["dusty"]}}, handle)

        response = self.client.get("/api/library/by-tag?tag=dusty&limit=abc")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "limit must be an integer")

    def test_library_stats_handles_missing_downloads_path(self):
        os.rmdir(self.app.config["DOWNLOADS_PATH"])

        response = self.client.get("/api/library/stats")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pending_packs"], 0)

    def test_library_tags_returns_dimension_counts(self):
        with open(self.app.config["TAGS_FILE"], "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "Loops/foo.wav": {
                        "tags": ["dusty", "funk"],
                        "type_code": "BRK",
                        "vibe": ["warm"],
                        "genre": ["funk"],
                        "texture": ["lo-fi"],
                        "source": "dug",
                        "energy": "mid",
                        "playability": "loop",
                        "bpm": 120,
                    }
                },
                handle,
            )

        response = self.client.get("/api/library/tags")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["type_codes"]["BRK"], 1)
        self.assertEqual(payload["vibes"]["warm"], 1)

    def test_library_smart_retag_status_returns_not_found(self):
        response = self.client.get("/api/library/smart-retag/missing")

        self.assertEqual(response.status_code, 404)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "Job not found")

    def test_library_smart_retag_starts_background_job(self):
        started = {}

        class FakeThread:
            daemon = False

            def __init__(self, target=None, args=None):
                started["target"] = target
                started["args"] = args

            def start(self):
                started["started"] = True

        with patch("api.library.threading.Thread", side_effect=FakeThread):
            response = self.client.post("/api/library/smart-retag", json={"limit": 5, "dry_run": True})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("job_id", payload)
        self.assertTrue(started["started"])


if __name__ == "__main__":
    unittest.main()
