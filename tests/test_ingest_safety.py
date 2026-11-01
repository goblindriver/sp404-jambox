"""Ingest must never lose or half-write data: extraction, cleanup, copies, watcher."""
import io
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import ingest
from ingest import _state as ingest_state
from ingest import archive as ingest_archive
from ingest import enrichment as ingest_enrichment
from ingest import orchestration as ingest_orchestration
from ingest import watcher as ingest_watcher
import jambox_config


def _make_zip(path, names):
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, b"RIFF....WAVE")


class IngestSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.downloads = os.path.join(root, "Downloads")
        self.library = os.path.join(root, "Library")
        self.raw = os.path.join(self.library, "_RAW-DOWNLOADS")
        self.tags = os.path.join(self.library, "_tags.json")
        for d in (self.downloads, self.raw):
            os.makedirs(d)
        self.patches = [
            patch.object(ingest_state, "DOWNLOADS", self.downloads),
            patch.object(ingest_state, "LIBRARY", self.library),
            patch.object(ingest_state, "RAW_ARCHIVE", self.raw),
            patch.object(ingest_state, "TAGS_FILE", self.tags),
            patch.object(ingest_state, "INGEST_LOG", os.path.join(self.library, "_ingest_log.json")),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_failed_extraction_leaves_no_folder(self):
        archive = os.path.join(self.downloads, "pack.rar")
        open(archive, "wb").close()
        dest = os.path.join(self.raw, "pack")

        def half_then_fail(_src, partial):
            open(os.path.join(partial, "half.wav"), "wb").close()
            return False

        with patch.object(ingest_archive, "_run_extractor", side_effect=half_then_fail):
            self.assertFalse(ingest.extract_archive(archive, dest))

        self.assertEqual(os.listdir(self.raw), [])

    def test_zip_extracts_atomically_with_python(self):
        archive = os.path.join(self.downloads, "pack.zip")
        _make_zip(archive, ["Kicks/kick.wav"])
        dest = os.path.join(self.raw, "pack")

        with redirect_stdout(io.StringIO()):
            self.assertTrue(ingest.extract_archive(archive, dest))

        self.assertTrue(os.path.isfile(os.path.join(dest, "Kicks", "kick.wav")))
        self.assertEqual(os.listdir(self.raw), ["pack"])

    def test_cleanup_deletes_archives_only_after_ingest_finished(self):
        for name in ("done.zip", "failed.zip"):
            _make_zip(os.path.join(self.downloads, name), ["a.wav"])
        os.makedirs(os.path.join(self.raw, "done"))
        os.makedirs(os.path.join(self.raw, "failed"))  # extraction folder, no marker
        ingest_archive.mark_ingested(os.path.join(self.raw, "done"), 1)

        with redirect_stdout(io.StringIO()):
            freed, removed = ingest.cleanup_downloads()

        self.assertEqual(removed, 1)
        self.assertEqual(sorted(os.listdir(self.downloads)), ["failed.zip"])

    def test_archive_without_marker_is_reextracted_and_then_marked(self):
        archive = os.path.join(self.library, "pack.zip")  # outside Downloads: not moved away
        _make_zip(archive, ["kick.wav"])
        os.makedirs(os.path.join(self.raw, "pack"))  # leftover from an interrupted run

        def fake_copy(_src, dest_path):
            open(dest_path, "wb").close()
            return dest_path

        with patch.object(ingest_orchestration, "_copy_as_flac", side_effect=fake_copy), \
             patch.object(ingest_orchestration, "_route_and_process", return_value="keep") as route, \
             redirect_stdout(io.StringIO()):
            count = ingest.ingest_archive_file(archive)

        self.assertEqual(count, 1)
        route.assert_called_once()
        self.assertTrue(ingest_archive.is_ingested(os.path.join(self.raw, "pack")))

        with redirect_stdout(io.StringIO()):
            self.assertEqual(ingest.ingest_archive_file(archive), 0)

    def test_copy_as_flac_never_leaves_a_partial_output(self):
        src = os.path.join(self.downloads, "kick.wav")
        with open(src, "wb") as fh:
            fh.write(b"RIFF")
        dest = os.path.join(self.library, "kick.wav")

        def failing_ffmpeg(cmd, **_kwargs):
            with open(cmd[-1], "wb") as fh:  # ffmpeg wrote some bytes, then died
                fh.write(b"fLaC")
            raise ingest_archive.subprocess.TimeoutExpired(cmd, 60)

        with patch("jambox_config.subprocess.run", side_effect=failing_ffmpeg):
            actual = ingest_archive._copy_as_flac(src, dest)

        self.assertEqual(actual, dest)
        self.assertEqual(sorted(os.listdir(self.library)), ["_RAW-DOWNLOADS", "kick.wav"])

    def test_watcher_survives_a_file_that_raises(self):
        bad = os.path.join(self.downloads, "bad.wav")
        with patch.object(ingest_watcher, "ingest_single_file", side_effect=RuntimeError("disk full")), \
             redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ingest_watcher.ingest_ready_file(bad), 0)
        self.assertIn("disk full", out.getvalue())

    def test_duplicate_gets_no_tag_row_and_a_unique_dupes_name(self):
        os.makedirs(os.path.join(self.library, "_DUPES"))
        open(os.path.join(self.library, "_DUPES", "kick.flac"), "wb").close()
        path = os.path.join(self.library, "kick.flac")
        open(path, "wb").close()

        with patch.object(ingest_enrichment, "_is_recent_duplicate", return_value=True):
            result = ingest_enrichment._route_and_process(path, "kick.flac")

        self.assertEqual(result, "duplicate")
        self.assertEqual(sorted(os.listdir(os.path.join(self.library, "_DUPES"))), ["kick-2.flac", "kick.flac"])
        self.assertEqual(jambox_config.load_tag_db(self.tags), {})

    def test_ingest_writes_one_row_with_source_context(self):
        path = os.path.join(self.library, "Drums", "kick.flac")
        os.makedirs(os.path.dirname(path))
        open(path, "wb").close()

        with patch.object(ingest_enrichment, "_is_recent_duplicate", return_value=False), \
             patch("tag_library.tag_file", return_value={"type_code": "KIK", "duration": 1}), \
             patch("smart_retag.retag_single", return_value=None), \
             patch.dict(sys.modules, {"clap_engine": None, "discogs_engine": None}):
            result = ingest_enrichment._route_and_process(path, "Drums/kick.flac", "from cowork")

        self.assertEqual(result, "keep")
        self.assertEqual(
            jambox_config.load_tag_db(self.tags),
            {"Drums/kick.flac": {"type_code": "KIK", "duration": 1, "cowork_source": "from cowork"}},
        )


if __name__ == "__main__":
    unittest.main()
