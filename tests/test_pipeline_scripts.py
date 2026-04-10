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
from ingest import _state as ingest_state
import jambox_config
import low_rank_audit
import tag_hygiene
import tag_vocab


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
                handle.write("score_version: nope\nweights:\n  keyword_dimension: loud\n")

            config = jambox_config.load_scoring_config(scoring_path)

        self.assertEqual(config["score_version"], jambox_config.DEFAULT_SCORING["score_version"])
        self.assertEqual(config["weights"]["keyword_dimension"], 3)

    def test_score_from_tags_returns_positive_for_good_match(self):
        """A perfect match across all dimensions should score well."""
        parsed = {
            "type_code": "KIK",
            "playability": "one-shot",
            "bpm": 120,
            "key": "Am",
            "keywords": {"dusty"},
            "energy": None,
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
        score = fetch_samples.score_from_tags(entry, parsed, {"bpm": 120, "key": "Am"})
        # Unified engine normalizes then scales to ~0-30 range
        self.assertGreater(score, 10)

    def test_score_from_tags_penalizes_type_mismatch(self):
        """Wrong type code should score much lower than a match."""
        parsed = {
            "type_code": "KIK",
            "playability": "one-shot",
            "bpm": 120,
            "key": None,
            "keywords": set(),
            "energy": None,
        }
        good = {
            "type_code": "KIK", "playability": "one-shot", "bpm": 120,
            "vibe": [], "texture": [], "genre": [], "tags": [],
            "path": "kick.wav", "duration": 1,
        }
        bad = {
            "type_code": "PAD", "playability": "loop", "bpm": 80,
            "vibe": [], "texture": [], "genre": [], "tags": [],
            "path": "pad.wav", "duration": 30,
        }
        good_score = fetch_samples.score_from_tags(good, parsed, {"bpm": 120})
        bad_score = fetch_samples.score_from_tags(bad, parsed, {"bpm": 120})
        self.assertGreater(good_score, bad_score)

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

            with patch.object(fetch_samples, "LIBRARY", tempdir), \
                 patch.object(fetch_samples, "TAGS_FILE", tags_path), \
                 patch("fetch_samples._clap_available", return_value=False), \
                 patch("fetch_samples.score_from_tags", side_effect=score_mock) as score_spy:
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


class LowRankAuditTests(unittest.TestCase):
    def test_score_severity_red_yellow_green(self):
        self.assertEqual(
            low_rank_audit._score_severity(10, 0.5, 0.3, 0.3, mission_critical=True, top1_type_match=False),
            "red",
        )
        self.assertEqual(
            low_rank_audit._score_severity(18, 1.5, 0.6, 0.6, mission_critical=True, top1_type_match=False),
            "yellow",
        )
        self.assertEqual(
            low_rank_audit._score_severity(25, 3.0, 1.0, 1.0, mission_critical=False, top1_type_match=True),
            "green",
        )

    def test_audit_pad_includes_confidence_fields(self):
        fake_ranked = [
            {
                "path": __file__,
                "rel_path": "x.wav",
                "score": 24,
                "type_code": "BRK",
                "playability": "loop",
                "duration": 2.0,
            },
            {
                "path": __file__,
                "rel_path": "y.wav",
                "score": 20,
                "type_code": "BRK",
                "playability": "loop",
                "duration": 1.5,
            },
        ]
        with patch("low_rank_audit.fetch_samples.rank_library_matches", return_value=fake_ranked), patch("low_rank_audit.fetch_samples.choose_diverse_match", return_value=fake_ranked[0]):
            row = low_rank_audit._audit_pad(
                bank_letter="b",
                pad_num=5,
                description="BRK dusty loop",
                bank_cfg={"bpm": 120, "key": "Am"},
                tag_db={},
                top_n=2,
                min_score=0,
                deterministic=True,
            )
        self.assertIn("top_score", row)
        self.assertIn("top2_gap", row)
        self.assertIn("type_match_ratio", row)
        self.assertIn("conversion_success_rate", row)
        self.assertIn(row["severity"], {"red", "yellow", "green"})


class TagHygieneTests(unittest.TestCase):
    def test_scan_finds_folder_type_mismatch(self):
        db = {
            "Melodic/Bass/foo.flac": {"type_code": "BRK", "playability": "loop", "tags": ["brk", "loop"]}
        }
        findings = tag_hygiene._scan(db)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["expected_type"], "BAS")

    def test_apply_rewrites_type_and_tags(self):
        db = {
            "Melodic/Bass/foo.flac": {"type_code": "BRK", "playability": "loop", "tags": ["brk", "loop"]}
        }
        findings = [{"path": "Melodic/Bass/foo.flac", "expected_type": "BAS", "actual_type": "BRK", "reason": "melodic_bass_folder", "current_playability": "loop"}]
        updated, changed = tag_hygiene._apply(db, findings)
        self.assertEqual(changed, 1)
        self.assertEqual(updated["Melodic/Bass/foo.flac"]["type_code"], "BAS")
        self.assertIn("bas", updated["Melodic/Bass/foo.flac"]["tags"])


class TagVocabExpansionTests(unittest.TestCase):
    def test_new_genre_aliases_normalize(self):
        self.assertEqual(tag_vocab.normalize_genre("riddim"), "dancehall")
        self.assertEqual(tag_vocab.normalize_genre("baile funk"), "baile-funk")
        self.assertEqual(tag_vocab.normalize_genre("industrial techno"), "industrial-techno")

    def test_new_texture_aliases_normalize(self):
        self.assertEqual(tag_vocab.normalize_texture("metallic-hit"), "crispy")
        self.assertEqual(tag_vocab.normalize_texture("ringy"), "glassy")


class IngestDownloadsScriptTests(unittest.TestCase):
    def test_one_shot_ingest_returns_zero_when_downloads_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            downloads = os.path.join(tempdir, "missing-downloads")
            library = os.path.join(tempdir, "library")
            archive = os.path.join(tempdir, "archive")
            output = io.StringIO()

            with patch.object(ingest_state, "DOWNLOADS", downloads), patch.object(ingest_state, "LIBRARY", library), patch.object(ingest_state, "RAW_ARCHIVE", archive), redirect_stdout(output):
                result = ingest_downloads.one_shot_ingest()

        self.assertEqual(result, 0)
        self.assertIn("Downloads path not found", output.getvalue())

    def test_cleanup_downloads_returns_zero_when_downloads_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            downloads = os.path.join(tempdir, "missing-downloads")
            output = io.StringIO()

            with patch.object(ingest_state, "DOWNLOADS", downloads), redirect_stdout(output):
                freed, removed = ingest_downloads.cleanup_downloads()

        self.assertEqual((freed, removed), (0, 0))
        self.assertIn("Downloads path not found", output.getvalue())

    def test_extract_archive_returns_false_when_command_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            archive_path = os.path.join(tempdir, "pack.zip")
            with open(archive_path, "wb") as handle:
                handle.write(b"PK")

            with patch("ingest.archive.subprocess.run", side_effect=FileNotFoundError):
                result = ingest_downloads.extract_archive(archive_path, os.path.join(tempdir, "out"))

        self.assertFalse(result)

    def test_start_watcher_returns_false_when_downloads_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            downloads = os.path.join(tempdir, "missing-downloads")
            output = io.StringIO()

            with patch.object(ingest_state, "DOWNLOADS", downloads), redirect_stdout(output):
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

            with patch.object(ingest_state, "DOWNLOADS", downloads), patch.object(ingest_state, "RAW_ARCHIVE", archive), patch.object(ingest_state, "LIBRARY", library):
                report = ingest_downloads.disk_usage_report()

        self.assertEqual(report["downloads_size"], 0)
        self.assertEqual(report["cleanable_count"], 0)


if __name__ == "__main__":
    unittest.main()
