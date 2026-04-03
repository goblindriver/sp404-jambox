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
