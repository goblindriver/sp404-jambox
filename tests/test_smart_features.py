import json
import os
import subprocess
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

from api.vibe import vibe_bp
from api.pattern import pattern_bp
from api.presets import presets_bp
import deduplicate_samples
import daily_bank
import generate_patterns
from integration_runtime import IntegrationFailure
import jambox_tuning
import vibe_generate


class SmartFeatureApiTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            REPO_DIR=REPO_ROOT,
            TOOL_PATH_PREFIX="",
            LLM_TIMEOUT=30,
        )
        self.app.register_blueprint(vibe_bp, url_prefix="/api")
        self.app.register_blueprint(pattern_bp, url_prefix="/api")
        self.app.register_blueprint(presets_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_vibe_route_returns_script_payload(self):
        script_output = {
            "prompt": "dusty funk drums",
            "query": "BRK dusty funk loop",
            "parsed": {"keywords": ["dusty", "funk"]},
            "bank_suggestions": [],
            "sample_suggestions": [],
            "fallback_used": False,
        }
        with patch("api.vibe.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(script_output), stderr="")):
            response = self.client.post("/api/vibe/generate", json={"prompt": "dusty funk drums"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["query"], "BRK dusty funk loop")

    def test_vibe_route_surfaces_structured_script_error(self):
        failed = SimpleNamespace(
            returncode=1,
            stdout=json.dumps({"ok": False, "error": "LLM unavailable", "error_code": "connection_error"}),
            stderr="",
        )
        with patch("api.vibe.subprocess.run", return_value=failed):
            response = self.client.post("/api/vibe/generate", json={"prompt": "dusty funk drums"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "LLM unavailable")
        self.assertEqual(response.get_json()["error_code"], "connection_error")

    def test_pattern_route_surfaces_generator_error(self):
        failed = SimpleNamespace(
            returncode=1,
            stdout=json.dumps({"ok": False, "error": "checkpoint missing", "error_code": "invalid_input"}),
            stderr="",
        )
        with patch("api.pattern.subprocess.run", return_value=failed):
            response = self.client.post("/api/pattern/generate", json={"variant": "drum"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "checkpoint missing")
        self.assertEqual(response.get_json()["error_code"], "invalid_input")

    def test_pattern_route_rejects_non_object_json_body(self):
        response = self.client.post("/api/pattern/generate", json=["drum"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Request body must be a JSON object")

    def test_pattern_route_rejects_non_object_script_output(self):
        with patch("api.pattern.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout='["not","an","object"]', stderr="")):
            response = self.client.post("/api/pattern/generate", json={"variant": "drum"})

        self.assertEqual(response.status_code, 500)
        self.assertIn("Script output must be a JSON object", response.get_json()["error"])

    def test_daily_preset_route_loads_into_bank(self):
        with patch("api.presets.db.build_daily_preset", return_value={"ref": "auto/daily-2026-04-02", "path": "/tmp/daily.yaml", "preset": {}}), patch("api.presets.pu.load_preset_to_bank") as load_mock:
            response = self.client.post("/api/presets/daily", json={"bank": "b"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["loaded_bank"], "b")
        load_mock.assert_called_once_with("auto/daily-2026-04-02", "b")

    def test_save_bank_as_preset_rejects_invalid_tags_payload(self):
        with patch("api.presets.pu.bank_to_preset", return_value={"name": "Test", "slug": "test", "pads": {1: "BRK dusty loop"}}):
            response = self.client.post("/api/presets/from-bank/b", json={"tags": 123})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "tags must be a comma-separated string or list of strings")

    def test_load_preset_rejects_non_object_json_body(self):
        response = self.client.post("/api/presets/load", json=["community/test", "b"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Request body must be a JSON object")

    def test_create_set_rejects_invalid_banks_payload(self):
        response = self.client.post("/api/sets", json={"name": "Weekend", "banks": []})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "banks must be an object")

    def test_vibe_route_rejects_non_object_json_body(self):
        response = self.client.post("/api/vibe/generate", json=["dusty funk drums"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Request body must be a JSON object")

    def test_vibe_route_rejects_non_string_prompt(self):
        response = self.client.post("/api/vibe/generate", json={"prompt": 123})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "prompt is required")

    def test_vibe_route_rejects_non_object_script_output(self):
        with patch("api.vibe.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout='["not","an","object"]', stderr="")):
            response = self.client.post("/api/vibe/generate", json={"prompt": "dusty funk drums"})

        self.assertEqual(response.status_code, 500)
        self.assertIn("Script output must be a JSON object", response.get_json()["error"])

    def test_vibe_apply_bank_rejects_invalid_preset_payload(self):
        response = self.client.post("/api/vibe/apply-bank", json={"bank": "b", "preset": {"pads": []}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "preset.pads must be an object")

    def test_vibe_apply_bank_starts_background_job(self):
        thread_calls = {}

        class FakeThread:
            daemon = False

            def __init__(self, target=None, args=None):
                thread_calls["target"] = target
                thread_calls["args"] = args

            def start(self):
                thread_calls["started"] = True

        preset = {
            "name": "Draft",
            "pads": {1: "KIK dusty one-shot", 2: "SNR dusty one-shot"},
            "bpm": 120,
            "key": "Am",
            "vibe": "dusty funk",
        }
        with patch("api.vibe.threading.Thread", FakeThread):
            response = self.client.post("/api/vibe/apply-bank", json={"bank": "b", "preset": preset, "fetch": False})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertTrue(thread_calls["started"])


class DailyBankTests(unittest.TestCase):
    def test_build_daily_preset_uses_existing_preset_schema(self):
        fake_db = {
            "Loops/foo.wav": {
                "type_code": "BRK",
                "genre": ["funk"],
                "vibe": ["dusty"],
                "texture": ["warm"],
                "playability": "loop",
                "bpm": 118,
            }
        }
        with patch("daily_bank._load_tag_db", return_value=fake_db), patch("daily_bank._recent_candidates", return_value=[(10, "Loops/foo.wav", fake_db["Loops/foo.wav"])]), patch("daily_bank._weighted_pick", return_value=[(10, "Loops/foo.wav", fake_db["Loops/foo.wav"])] * 12), patch("daily_bank.preset_utils.save_preset", return_value="auto/daily-test") as save_mock:
            result = daily_bank.build_daily_preset(source="recent")

        preset_arg = save_mock.call_args[0][0]
        self.assertEqual(result["ref"], "auto/daily-test")
        self.assertEqual(len(preset_arg["pads"]), 12)
        self.assertTrue(all(isinstance(value, str) for value in preset_arg["pads"].values()))

    def test_build_daily_preset_skips_invalid_bpm_values(self):
        fake_db = {
            "Loops/foo.wav": {
                "type_code": "BRK",
                "genre": ["funk"],
                "vibe": ["dusty"],
                "texture": ["warm"],
                "playability": "loop",
                "bpm": "fast",
            }
        }
        picks = [(10, "Loops/foo.wav", fake_db["Loops/foo.wav"])] * 12
        with patch("daily_bank._load_tag_db", return_value=fake_db), patch("daily_bank._recent_candidates", return_value=picks), patch("daily_bank._weighted_pick", return_value=picks), patch("daily_bank.preset_utils.save_preset", return_value="auto/daily-test") as save_mock:
            result = daily_bank.build_daily_preset(source="recent")

        preset_arg = save_mock.call_args[0][0]
        self.assertEqual(result["ref"], "auto/daily-test")
        self.assertEqual(preset_arg["bpm"], 120)

    def test_load_trending_terms_falls_back_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            trending_path = os.path.join(tempdir, "trending.json")
            with open(trending_path, "w", encoding="utf-8") as handle:
                handle.write("{not valid json")

            with patch.dict(daily_bank.SETTINGS, {"TRENDING_FILE": trending_path}, clear=False):
                terms = daily_bank._load_trending_terms()

        self.assertEqual(terms, daily_bank.DEFAULT_TRENDING_TERMS)


class VibeGenerateTests(unittest.TestCase):
    def test_load_vibe_mappings_falls_back_on_invalid_yaml(self):
        with tempfile.TemporaryDirectory() as tempdir:
            mappings_path = os.path.join(tempdir, "vibe_mappings.yaml")
            with open(mappings_path, "w", encoding="utf-8") as handle:
                handle.write("genre_instruments:\n  funk: nope\n")

            mappings = jambox_tuning.load_vibe_mappings(mappings_path)

        self.assertEqual(mappings["genre_instruments"]["funk"][0][0], "GTR")

    def test_generate_vibe_suggestions_uses_defaults_for_bad_numeric_inputs(self):
        llm_tags = {
            "keywords": ["dusty"],
            "type_code": "BRK",
            "playability": "loop",
            "vibe": ["warm"],
            "genre": ["funk"],
            "texture": [],
            "energy": [],
            "rationale": "test",
        }
        with patch("vibe_generate._call_llm", return_value=llm_tags), patch("vibe_generate.fetch_samples.rank_library_matches", return_value=[] ) as match_mock, patch("vibe_generate._load_bank_config", return_value={}):
            result = vibe_generate.generate_vibe_suggestions(
                {"prompt": "dusty funk", "limit": "abc", "min_score": "-2"}
            )

        self.assertEqual(result["query"], "BRK dusty warm funk loop")
        self.assertEqual(match_mock.call_args.kwargs["limit"], 12)
        self.assertEqual(match_mock.call_args.kwargs["min_score"], 4)

    def test_generate_vibe_suggestions_handles_missing_bank_config(self):
        llm_tags = {
            "keywords": ["dusty"],
            "type_code": "BRK",
            "playability": "loop",
            "vibe": [],
            "genre": [],
            "texture": [],
            "energy": [],
            "rationale": "test",
        }
        with patch("vibe_generate._call_llm", return_value=llm_tags), patch("vibe_generate.fetch_samples.rank_library_matches", return_value=[{"path": "Loops/foo.wav"}]), patch("vibe_generate._load_bank_config", return_value={}):
            result = vibe_generate.generate_vibe_suggestions({"prompt": "dusty break"})

        self.assertEqual(result["sample_suggestions"], [{"path": "Loops/foo.wav"}])
        self.assertEqual(result["bank_suggestions"], [])

    def test_generate_vibe_suggestions_falls_back_when_llm_unavailable(self):
        with patch("vibe_generate._call_llm", side_effect=IntegrationFailure("connection_error", "LLM unavailable")), patch("vibe_generate.fetch_samples.rank_library_matches", return_value=[]), patch("vibe_generate._load_bank_config", return_value={}):
            result = vibe_generate.generate_vibe_suggestions({"prompt": "dusty funk loop"})

        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["fallback_code"], "connection_error")
        self.assertIn("dusty", result["parsed"]["keywords"])

    def test_generate_vibe_suggestions_uses_type_alias_in_keyword_fallback(self):
        with patch("vibe_generate._call_llm", side_effect=IntegrationFailure("connection_error", "LLM unavailable")), patch("vibe_generate.fetch_samples.rank_library_matches", return_value=[]), patch("vibe_generate._load_bank_config", return_value={}), patch.object(vibe_generate, "_TYPE_KEYWORD_ALIASES", {"kick": "KIK"}):
            result = vibe_generate.generate_vibe_suggestions({"prompt": "dusty kick loop"})

        self.assertEqual(result["parsed"]["type_code"], "KIK")

    def test_build_bank_from_vibe_preserves_fallback_metadata(self):
        fallback_result = {
            "tags": {
                "keywords": ["dusty"],
                "type_code": "BRK",
                "playability": "loop",
                "vibe": [],
                "genre": ["funk"],
                "texture": [],
                "energy": [],
                "rationale": "Fallback",
            },
            "fallback_used": True,
            "fallback_reason": "LLM unavailable",
            "fallback_code": "connection_error",
        }
        with patch("vibe_generate.parse_vibe_prompt", return_value=fallback_result):
            result = vibe_generate.build_bank_from_vibe({"prompt": "dusty funk", "bpm": 95, "key": "Am"})

        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["fallback_code"], "connection_error")
        self.assertEqual(result["preset"]["bpm"], 95)

    def test_generate_vibe_suggestions_includes_draft_preset(self):
        llm_result = {
            "tags": {
                "keywords": ["dusty"],
                "type_code": "BRK",
                "playability": "loop",
                "vibe": ["warm"],
                "genre": ["funk"],
                "texture": [],
                "energy": [],
                "rationale": "test",
            },
            "fallback_used": False,
            "fallback_reason": "",
            "fallback_code": "",
        }
        with patch("vibe_generate.parse_vibe_prompt", return_value=llm_result), patch("vibe_generate.fetch_samples.rank_library_matches", return_value=[]), patch("vibe_generate._load_bank_config", return_value={}):
            result = vibe_generate.generate_vibe_suggestions({"prompt": "dusty funk", "bpm": 110, "key": "Am"})

        self.assertIn("draft_preset", result)
        self.assertEqual(result["draft_preset"]["bpm"], 110)
        self.assertIn(1, result["draft_preset"]["pads"])


class PatternGeneratorTests(unittest.TestCase):
    def test_parse_midi_file_rejects_truncated_header(self):
        with tempfile.TemporaryDirectory() as tempdir:
            midi_path = os.path.join(tempdir, "bad.mid")
            with open(midi_path, "wb") as handle:
                handle.write(b"MThd\x00\x00\x00\x06\x00\x01")

            with self.assertRaisesRegex(ValueError, "Truncated MIDI header"):
                generate_patterns._parse_midi_file(midi_path)

    def test_parse_midi_file_rejects_smpte_division(self):
        midi_bytes = (
            b"MThd"
            + b"\x00\x00\x00\x06"
            + b"\x00\x00"
            + b"\x00\x01"
            + b"\xE7\x28"
            + b"MTrk"
            + b"\x00\x00\x00\x00"
        )
        with tempfile.TemporaryDirectory() as tempdir:
            midi_path = os.path.join(tempdir, "smpte.mid")
            with open(midi_path, "wb") as handle:
                handle.write(midi_bytes)

            with self.assertRaisesRegex(ValueError, "SMPTE MIDI time division is not supported"):
                generate_patterns._parse_midi_file(midi_path)

    def test_build_magenta_command_rejects_short_trio_run(self):
        with patch.dict(generate_patterns.SETTINGS, {"MAGENTA_COMMAND": "music_vae_generate"}, clear=False):
            with self.assertRaisesRegex(ValueError, "trio variant requires 16 bars"):
                generate_patterns._build_magenta_command(
                    {"variant": "trio", "bars": 2, "bpm": 120},
                    "/tmp/trio.mag",
                    "/tmp",
                )

    def test_generate_pattern_times_out_magenta_command(self):
        with patch("generate_patterns._resolve_checkpoint", return_value=("drum", "/tmp/drum.mag")), patch("generate_patterns._build_magenta_command", return_value=(["magenta"], "/tmp/generated.mid")), patch("generate_patterns.run_command", side_effect=IntegrationFailure("timeout", "Integration timed out")), patch("generate_patterns._write_starter_fallback", return_value="/tmp/fallback.PTN"):
            result = generate_patterns.generate_pattern({"variant": "drum"})

        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["fallback_code"], "magenta_timeout")
        self.assertEqual(result["path"], "/tmp/fallback.PTN")


class DedupeTests(unittest.TestCase):
    def test_find_duplicate_groups_with_mocked_fingerprints(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db = {
                "a.wav": {"tags": ["one"]},
                "b.wav": {"tags": []},
                "c.wav": {"tags": ["other"]},
            }
            for name in db:
                with open(os.path.join(tempdir, name), "wb") as handle:
                    handle.write(b"data")

            with patch.object(deduplicate_samples, "LIBRARY", tempdir), patch("deduplicate_samples._fingerprint_with_fpcalc", side_effect=[
                {"kind": "fpcalc", "value": "1,2,3"},
                {"kind": "fpcalc", "value": "1,2,3"},
                {"kind": "fpcalc", "value": "9,9,9"},
            ]):
                groups = deduplicate_samples.find_duplicate_groups(db, threshold=0.99)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["keep"], "a.wav")
        self.assertEqual(groups[0]["duplicates"], ["b.wav"])

    def test_find_duplicate_groups_merges_transitive_matches(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db = {
                "a.wav": {"tags": ["one"]},
                "b.wav": {"tags": []},
                "c.wav": {"tags": ["other"]},
            }
            for name in db:
                with open(os.path.join(tempdir, name), "wb") as handle:
                    handle.write(b"data")

            scores = {
                ("a.wav", "b.wav"): 0.99,
                ("a.wav", "c.wav"): 0.10,
                ("b.wav", "c.wav"): 0.99,
            }

            def fake_pair_similarity(rel_path, compare_path, fingerprints, python_fingerprints, cache_entries):
                return scores[(rel_path, compare_path)]

            with patch.object(deduplicate_samples, "LIBRARY", tempdir), patch("deduplicate_samples._fingerprint_with_fpcalc", return_value={"kind": "fpcalc", "value": "stub"}), patch("deduplicate_samples._pair_similarity", side_effect=fake_pair_similarity):
                groups = deduplicate_samples.find_duplicate_groups(db, threshold=0.95)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["keep"], "a.wav")
        self.assertEqual(groups[0]["duplicates"], ["c.wav", "b.wav"])

    def test_find_duplicate_groups_reuses_fingerprint_cache(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db = {
                "a.wav": {"tags": ["one"]},
                "b.wav": {"tags": []},
            }
            for name in db:
                with open(os.path.join(tempdir, name), "wb") as handle:
                    handle.write(b"data")

            with patch.object(deduplicate_samples, "LIBRARY", tempdir), patch("deduplicate_samples._fingerprint_with_fpcalc", side_effect=[
                {"kind": "fpcalc", "value": "1,2,3"},
                {"kind": "fpcalc", "value": "1,2,3"},
            ]) as fpcalc_mock:
                deduplicate_samples.find_duplicate_groups(db, threshold=0.99)
                deduplicate_samples.find_duplicate_groups(db, threshold=0.99)

        self.assertEqual(fpcalc_mock.call_count, 2)

    def test_find_duplicate_groups_uses_python_fallback_for_mixed_kinds(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db = {
                "a.wav": {"tags": ["one"]},
                "b.wav": {"tags": []},
            }
            for name in db:
                with open(os.path.join(tempdir, name), "wb") as handle:
                    handle.write(b"data")

            with patch.object(deduplicate_samples, "LIBRARY", tempdir), patch("deduplicate_samples._fingerprint_with_fpcalc", side_effect=[
                {"kind": "fpcalc", "value": "1,2,3"},
                {"kind": "python", "value": [1.0, 2.0, 3.0]},
            ]), patch("deduplicate_samples._fingerprint_with_python", return_value={"kind": "python", "value": [1.0, 2.0, 3.0]}), patch("deduplicate_samples.dedup_library.cosine_similarity", return_value=0.999):
                groups = deduplicate_samples.find_duplicate_groups(db, threshold=0.95)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["keep"], "a.wav")
        self.assertEqual(groups[0]["duplicates"], ["b.wav"])

    def test_apply_clean_moves_files_and_updates_tag_db(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tags_path = os.path.join(tempdir, "_tags.json")
            db = {
                "keep.wav": {"tags": ["keep"]},
                "dupe.wav": {"tags": ["dupe"]},
            }
            for name in db:
                with open(os.path.join(tempdir, name), "wb") as handle:
                    handle.write(b"data")

            with patch.object(deduplicate_samples, "LIBRARY", tempdir), patch.object(deduplicate_samples, "TAGS_FILE", tags_path), patch.object(deduplicate_samples, "DUPES_DIR", os.path.join(tempdir, "_DUPES")):
                updated = deduplicate_samples.apply_clean(
                    [{"keep": "keep.wav", "duplicates": ["dupe.wav"], "members": []}],
                    db,
                )

            self.assertIn("keep.wav", updated)
            self.assertNotIn("dupe.wav", updated)
            self.assertFalse(os.path.exists(os.path.join(tempdir, "dupe.wav")))
            self.assertTrue(os.path.exists(os.path.join(tempdir, "_DUPES", "dupe.wav")))
            with open(tags_path, encoding="utf-8") as handle:
                persisted = json.load(handle)
            self.assertNotIn("dupe.wav", persisted)


if __name__ == "__main__":
    unittest.main()
