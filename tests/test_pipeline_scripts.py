import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fetch_samples
import ingest_downloads
import jambox_tuning


class FetchSamplesScriptTests(unittest.TestCase):
    def test_load_config_rejects_non_mapping_yaml(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = os.path.join(tempdir, "bank_config.yaml")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write("- just\n- a\n- list\n")

            with patch.object(fetch_samples, "CONFIG_PATH", config_path):
                with self.assertRaisesRegex(ValueError, "must contain a mapping"):
                    fetch_samples.load_config()

    def test_load_tag_db_returns_empty_dict_for_non_mapping_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tags_path = os.path.join(tempdir, "_tags.json")
            with open(tags_path, "w", encoding="utf-8") as handle:
                handle.write('["not", "a", "mapping"]')

            with patch.object(fetch_samples, "TAGS_FILE", tags_path):
                payload = fetch_samples.load_tag_db()

        self.assertEqual(payload, {})

    def test_parse_pad_query_handles_none(self):
        parsed = fetch_samples.parse_pad_query(None)

        self.assertEqual(parsed["type_code"], None)
        self.assertEqual(parsed["playability"], None)
        self.assertEqual(parsed["keywords"], set())

    def test_load_scoring_config_falls_back_on_invalid_weight(self):
        with tempfile.TemporaryDirectory() as tempdir:
            scoring_path = os.path.join(tempdir, "scoring.yaml")
            with open(scoring_path, "w", encoding="utf-8") as handle:
                handle.write("score_version: nope\nweights:\n  type_exact: loud\n")

            config = jambox_tuning.load_scoring_config(scoring_path)

        self.assertEqual(config["score_version"], 3)
        self.assertEqual(config["weights"]["type_exact"], 10)

    def test_score_from_tags_uses_configurable_weights(self):
        parsed = {
            "type_code": "KIK",
            "playability": "one-shot",
            "bpm": 120,
            "key": "Am",
            "keywords": {"dusty"},
        }
        entry = {
            "type_code": "KIK",
            "playability": "one-shot",
            "bpm": 120,
            "key": "Am",
            "vibe": ["dusty"],
            "texture": [],
            "genre": [],
            "tags": [],
            "path": "Hits/kick.wav",
            "duration": 1,
            "plex_moods": [],
            "plex_play_count": 0,
        }
        custom_weights = dict(fetch_samples.SCORING_WEIGHTS)
        custom_weights["type_exact"] = 99
        with patch.object(fetch_samples, "SCORING_WEIGHTS", custom_weights):
            score = fetch_samples.score_from_tags(entry, parsed, {"bpm": 120, "key": "Am"})

        self.assertGreaterEqual(score, 99)

    def test_rank_library_matches_reuses_score_cache_for_same_query(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tags_path = os.path.join(tempdir, "_tags.json")
            with open(tags_path, "w", encoding="utf-8") as handle:
                handle.write("{}")

            tag_db = {
                "Loops/a.wav": {"type_code": "BRK", "tags": ["dusty"], "vibe": ["dusty"], "genre": [], "texture": [], "duration": 2},
                "Loops/b.wav": {"type_code": "BRK", "tags": ["clean"], "vibe": ["clean"], "genre": [], "texture": [], "duration": 2},
            }
            score_mock = lambda entry, parsed, bank: 10 if "dusty" in entry.get("tags", []) else 1

            with patch.object(fetch_samples, "LIBRARY", tempdir), patch.object(fetch_samples, "TAGS_FILE", tags_path), patch("fetch_samples.score_from_tags", side_effect=score_mock) as score_spy:
                first = fetch_samples.rank_library_matches("BRK dusty loop", bank_config={"bpm": 120}, tag_db=tag_db)
                second = fetch_samples.rank_library_matches("BRK dusty loop", bank_config={"bpm": 120}, tag_db=tag_db)

        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertEqual(score_spy.call_count, 2)

    def test_choose_diverse_match_returns_top_result_in_deterministic_mode(self):
        matches = [
            {"path": "/tmp/a.wav", "score": 22},
            {"path": "/tmp/b.wav", "score": 20},
        ]
        picked = fetch_samples.choose_diverse_match(matches, deterministic=True)
        self.assertEqual(picked["path"], "/tmp/a.wav")

    def test_choose_diverse_match_applies_recent_use_penalty(self):
        matches = [
            {"path": "/tmp/recent.wav", "score": 30},
            {"path": "/tmp/older.wav", "score": 10},
        ]
        now = 1_700_000_000
        history = {"last_used": {"/tmp/recent.wav": now - 60}}

        with patch("fetch_samples.time.time", return_value=now), patch.object(fetch_samples, "FETCH_COOLDOWN_SECONDS", 3600), patch.object(fetch_samples, "_load_fetch_history", return_value=history), patch("fetch_samples.random.uniform", return_value=9.9):
            picked = fetch_samples.choose_diverse_match(matches, deterministic=False)

        self.assertEqual(picked["path"], "/tmp/older.wav")


class IngestDownloadsScriptTests(unittest.TestCase):
    def test_one_shot_ingest_returns_zero_when_downloads_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            downloads = os.path.join(tempdir, "missing-downloads")
            library = os.path.join(tempdir, "library")
            archive = os.path.join(tempdir, "archive")
            output = io.StringIO()

            with patch.object(ingest_downloads, "DOWNLOADS", downloads), patch.object(ingest_downloads, "LIBRARY", library), patch.object(ingest_downloads, "RAW_ARCHIVE", archive), redirect_stdout(output):
                result = ingest_downloads.one_shot_ingest()

        self.assertEqual(result, 0)
        self.assertIn("Downloads path not found", output.getvalue())

    def test_cleanup_downloads_returns_zero_when_downloads_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            downloads = os.path.join(tempdir, "missing-downloads")
            output = io.StringIO()

            with patch.object(ingest_downloads, "DOWNLOADS", downloads), redirect_stdout(output):
                freed, removed = ingest_downloads.cleanup_downloads()

        self.assertEqual((freed, removed), (0, 0))
        self.assertIn("Downloads path not found", output.getvalue())

    def test_extract_archive_returns_false_when_command_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            archive_path = os.path.join(tempdir, "pack.zip")
            with open(archive_path, "wb") as handle:
                handle.write(b"PK")

            with patch("ingest_downloads.subprocess.run", side_effect=FileNotFoundError):
                result = ingest_downloads.extract_archive(archive_path, os.path.join(tempdir, "out"))

        self.assertFalse(result)

    def test_start_watcher_returns_false_when_downloads_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            downloads = os.path.join(tempdir, "missing-downloads")
            output = io.StringIO()

            with patch.object(ingest_downloads, "DOWNLOADS", downloads), redirect_stdout(output):
                result = ingest_downloads.start_watcher()

        self.assertFalse(result)
        self.assertIn("downloads path not found", output.getvalue().lower())

    def test_disk_usage_report_handles_missing_downloads(self):
        with tempfile.TemporaryDirectory() as tempdir:
            downloads = os.path.join(tempdir, "missing-downloads")
            archive = os.path.join(tempdir, "archive")
            library = os.path.join(tempdir, "library")
            os.makedirs(archive, exist_ok=True)
            os.makedirs(library, exist_ok=True)

            with patch.object(ingest_downloads, "DOWNLOADS", downloads), patch.object(ingest_downloads, "RAW_ARCHIVE", archive), patch.object(ingest_downloads, "LIBRARY", library):
                report = ingest_downloads.disk_usage_report()

        self.assertEqual(report["downloads_size"], 0)
        self.assertEqual(report["cleanable_count"], 0)


if __name__ == "__main__":
    unittest.main()
