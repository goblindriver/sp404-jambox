"""Row-level tag store: writers only touch the rows they name."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import jambox_config
from jambox_config import (
    delete_tag_paths,
    diff_tag_db,
    export_tags_json,
    library_rel_path,
    load_tag_db,
    merge_tag_fields,
    tags_version,
    upsert_tag_entries,
    write_tag_changes,
)
import tag_library


class TagStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tags = os.path.join(self.tmp.name, "_tags.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_never_delete_rows_they_do_not_name(self):
        upsert_tag_entries(self.tags, {"a.wav": {"type_code": "KIK"}, "b.wav": {"type_code": "SNR"}})
        upsert_tag_entries(self.tags, {"c.wav": {"type_code": "HAT"}})
        merge_tag_fields(self.tags, {"a.wav": {"vibe": ["dark"]}})

        self.assertEqual(set(load_tag_db(self.tags)), {"a.wav", "b.wav", "c.wav"})

    def test_merge_keeps_other_fields_and_skips_missing_rows(self):
        upsert_tag_entries(self.tags, {"a.wav": {"type_code": "KIK", "sonic_description": "thud"}})

        stats = merge_tag_fields(self.tags, {"a.wav": {"discogs_styles": ["Funk"]}, "gone.wav": {"x": 1}})

        row = load_tag_db(self.tags)["a.wav"]
        self.assertEqual(row["sonic_description"], "thud")
        self.assertEqual(row["discogs_styles"], ["Funk"])
        self.assertEqual(stats["merged"], 1)
        self.assertEqual(stats["missing"], 1)
        self.assertNotIn("gone.wav", load_tag_db(self.tags))

    def test_rekey_is_one_transaction_and_deletes_are_explicit(self):
        upsert_tag_entries(self.tags, {"x.wav": {"type_code": "BRK"}, "keep.wav": {}})

        write_tag_changes(self.tags, deletes=["x.wav"], upserts={"x.flac": {"type_code": "BRK"}})
        delete_tag_paths(self.tags, ["keep.wav", ""])

        self.assertEqual(set(load_tag_db(self.tags)), {"x.flac"})

    def test_version_bumps_on_every_write(self):
        self.assertEqual(tags_version(self.tags), 0)
        upsert_tag_entries(self.tags, {"a.wav": {}})
        merge_tag_fields(self.tags, {"a.wav": {"k": 1}})
        delete_tag_paths(self.tags, ["a.wav"])
        self.assertEqual(tags_version(self.tags), 3)

    def test_export_matches_sqlite(self):
        upsert_tag_entries(self.tags, {"a.wav": {"type_code": "KIK"}, "b.wav": {"type_code": "SNR"}})
        self.assertTrue(export_tags_json(self.tags))
        with open(self.tags, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), load_tag_db(self.tags))

    def test_legacy_json_is_migrated_before_the_first_write(self):
        with open(self.tags, "w", encoding="utf-8") as fh:
            json.dump({"old.wav": {"type_code": "PAD"}}, fh)

        upsert_tag_entries(self.tags, {"new.wav": {"type_code": "KIK"}})

        self.assertEqual(set(load_tag_db(self.tags)), {"old.wav", "new.wav"})

    def test_concurrent_writers_lose_nothing(self):
        upsert_tag_entries(self.tags, {"shared.wav": {"type_code": "BRK"}})

        def thread_writer(prefix):
            for i in range(25):
                upsert_tag_entries(self.tags, {f"{prefix}{i}.wav": {"n": i}})
                merge_tag_fields(self.tags, {"shared.wav": {f"{prefix}_field": i}})

        script = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "from jambox_config import upsert_tag_entries, merge_tag_fields\n"
            "for i in range(25):\n"
            "    upsert_tag_entries(sys.argv[2], {'proc%d.wav' % i: {'n': i}})\n"
            "    merge_tag_fields(sys.argv[2], {'shared.wav': {'proc_field': i}})\n"
        )
        proc = subprocess.Popen([sys.executable, "-c", script, SCRIPTS_DIR, self.tags])
        threads = [threading.Thread(target=thread_writer, args=(p,)) for p in ("t1_", "t2_")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(proc.wait(timeout=60), 0)

        db = load_tag_db(self.tags)
        self.assertEqual(len(db), 1 + 25 * 3)
        self.assertEqual(
            {k: db["shared.wav"][k] for k in ("t1__field", "t2__field", "proc_field")},
            {"t1__field": 24, "t2__field": 24, "proc_field": 24},
        )

    def test_diff_tag_db_reports_new_rows_and_changed_fields_only(self):
        before = {"a": {"x": 1, "y": [1]}, "b": {"x": 1}, "gone": {"x": 1}}
        after = {"a": {"x": 1, "y": [1, 2]}, "b": {"x": 1}, "new": {"x": 3}}

        upserts, merges = diff_tag_db(before, after)

        self.assertEqual(upserts, {"new": {"x": 3}})
        self.assertEqual(merges, {"a": {"y": [1, 2]}})

    def test_library_rel_path_uses_forward_slashes(self):
        root = os.path.join(self.tmp.name, "lib")
        full = os.path.join(root, "Drums", "Kicks", "k.wav")
        self.assertEqual(library_rel_path(full, root), "Drums/Kicks/k.wav")
        self.assertIsNone(library_rel_path(os.path.join(self.tmp.name, "elsewhere.wav"), root))


class TagLibraryScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = self.tmp.name
        self.tags = os.path.join(self.lib, "_tags.json")
        os.makedirs(os.path.join(self.lib, "Drums", "Kicks"))
        self.kick = os.path.join(self.lib, "Drums", "Kicks", "kick_120.wav")
        self.new = os.path.join(self.lib, "Drums", "Kicks", "new_kick.wav")
        for path in (self.kick, self.new):
            with open(path, "wb") as fh:
                fh.write(b"RIFF")

    def tearDown(self):
        self.tmp.cleanup()

    def _scan(self, *argv):
        with patch.object(tag_library, "LIBRARY", self.lib), \
             patch.object(tag_library, "TAGS_FILE", self.tags), \
             patch.object(sys, "argv", ["tag_library.py", "--no-duration", *argv]), \
             patch("tag_library.print_summary"):
            tag_library.main()
        return load_tag_db(self.tags)

    def test_full_scan_merges_into_rows_and_keeps_skip_dir_rows(self):
        upsert_tag_entries(self.tags, {
            "Drums/Kicks/kick_120.wav": {
                "type_code": "SNR", "sonic_description": "deep thud", "discogs_styles": ["Funk"],
                "mtime": 1.0,
            },
            "Stems/song/drums.wav": {"type_code": "BRK"},
            "_QUARANTINE/Drums/bad.wav": {"type_code": "KIK"},
            "Drums/Kicks/gone.wav": {"type_code": "KIK"},
        })

        db = self._scan()

        kick = db["Drums/Kicks/kick_120.wav"]
        self.assertEqual(kick["sonic_description"], "deep thud")
        self.assertEqual(kick["discogs_styles"], ["Funk"])
        self.assertEqual(kick["type_code"], "KIK")
        self.assertTrue(kick["smart_retag_pending"])
        self.assertIn("Drums/Kicks/new_kick.wav", db)
        self.assertIn("Stems/song/drums.wav", db)
        self.assertIn("_QUARANTINE/Drums/bad.wav", db)
        self.assertNotIn("Drums/Kicks/gone.wav", db)

    def test_unchanged_files_are_skipped(self):
        upsert_tag_entries(self.tags, {
            "Drums/Kicks/kick_120.wav": {"type_code": "SNR", "mtime": time.time() + 3600},
        })

        db = self._scan()

        self.assertEqual(db["Drums/Kicks/kick_120.wav"]["type_code"], "SNR")

    def test_rebuild_keeps_smart_retag_classification(self):
        upsert_tag_entries(self.tags, {
            "Drums/Kicks/kick_120.wav": {
                "type_code": "BRK", "vibe": ["dark"], "tag_source": "smart_retag_v1",
                "bpm": 118.0, "bpm_source": "librosa", "mtime": time.time() + 3600,
            },
        })

        db = self._scan("--rebuild")

        kick = db["Drums/Kicks/kick_120.wav"]
        self.assertEqual(kick["type_code"], "BRK")
        self.assertEqual(kick["vibe"], ["dark"])
        self.assertEqual(kick["bpm"], 118.0)
        self.assertNotIn("smart_retag_pending", kick)


if __name__ == "__main__":
    unittest.main()
