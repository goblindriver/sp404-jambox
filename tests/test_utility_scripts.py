import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def _load_module(module_name, relative_path):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(REPO_ROOT, relative_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


import dedup_library
import freesound_client
import library_health
import migrate_presets
from spedit404.binary import write_binary
from spedit404.note import Note
from spedit404.pattern import Pattern
import sync_bank_a

legacy_synth_core = _load_module("legacy_synth_core_test", "scripts/legacy/synth_core.py")


class UtilityScriptsTests(unittest.TestCase):
    def test_setup_oauth_rejects_missing_access_token(self):
        response = Mock(status_code=200)
        response.json.return_value = {}

        with patch.object(freesound_client, "_get_client_id", return_value="client"), patch.object(freesound_client, "_get_client_secret", return_value="secret"), patch("builtins.input", return_value="auth-code"), patch.object(freesound_client.webbrowser, "open"), patch.object(freesound_client, "_load_env", return_value={}), patch.object(freesound_client, "_save_env") as save_env, patch.object(freesound_client.requests, "post", return_value=response):
            ok = freesound_client.setup_oauth()

        self.assertFalse(ok)
        save_env.assert_not_called()

    def test_search_returns_empty_list_for_invalid_json(self):
        response = Mock(status_code=200)
        response.json.side_effect = ValueError("bad json")

        with patch.object(freesound_client, "_get_api_key", return_value="key"), patch.object(freesound_client.requests, "get", return_value=response):
            results = freesound_client.search("snare")

        self.assertEqual(results, [])

    def test_organize_library_import_has_no_side_effects(self):
        script_path = os.path.join(SCRIPTS_DIR, "organize_library.py")
        with tempfile.TemporaryDirectory() as tempdir:
            module_name = "organize_library_import_check"
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            module = importlib.util.module_from_spec(spec)

            with patch("glob.glob", return_value=[os.path.join(tempdir, "pack.zip")]), patch("shutil.copytree") as copytree, patch("builtins.print"):
                spec.loader.exec_module(module)

            copytree.assert_not_called()

    def test_dedup_library_load_tag_db_returns_empty_dict_for_non_mapping_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tags_path = os.path.join(tempdir, "_tags.json")
            with open(tags_path, "w", encoding="utf-8") as handle:
                json.dump(["not", "a", "mapping"], handle)

            with patch.object(dedup_library, "TAGS_FILE", tags_path):
                data = dedup_library.load_tag_db()

        self.assertEqual(data, {})

    def test_library_health_load_tag_db_returns_empty_dict_for_non_mapping_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tags_path = os.path.join(tempdir, "_tags.json")
            with open(tags_path, "w", encoding="utf-8") as handle:
                json.dump(["not", "a", "mapping"], handle)

            with patch.object(library_health, "TAGS_FILE", tags_path):
                data = library_health.load_tag_db()

        self.assertEqual(data, {})

    def test_sync_bank_a_get_bank_a_files_returns_empty_when_sd_listing_fails(self):
        with patch.object(sync_bank_a, "is_card_mounted", return_value=True), patch("sync_bank_a.os.listdir", side_effect=OSError("unreadable")):
            files = sync_bank_a.get_bank_a_files()

        self.assertEqual(files, [])

    def test_migrate_presets_skips_invalid_bank_config_entries(self):
        config = {"bank_b": "broken"}

        with patch.object(migrate_presets, "_load_config", return_value=config), patch.object(migrate_presets, "save_preset") as save_preset, patch.object(migrate_presets, "save_set") as save_set, patch.object(migrate_presets, "_save_config") as save_config, patch.object(sys, "argv", ["migrate_presets.py", "--dry-run"]):
            migrate_presets.main()

        save_preset.assert_not_called()
        save_set.assert_not_called()
        save_config.assert_not_called()

    def test_gen_novelty_import_has_no_side_effects(self):
        script_path = os.path.join(SCRIPTS_DIR, "gen_novelty.py")
        module_name = "gen_novelty_import_check"
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        module = importlib.util.module_from_spec(spec)

        with patch("os.makedirs") as makedirs, patch("builtins.print"):
            spec.loader.exec_module(module)

        makedirs.assert_not_called()

    def test_spedit404_write_binary_handles_sparse_note_gaps(self):
        pattern = Pattern(2)
        pattern.add_note(Note(pad=1, bank="c", start_tick=0, length=24, velocity=100))
        pattern.add_note(Note(pad=2, bank="c", start_tick=384, length=24, velocity=100))

        with tempfile.TemporaryDirectory() as tempdir:
            output_path = os.path.join(tempdir, "pattern.bin")
            write_binary(pattern, "c", 1, output_path)

            self.assertTrue(os.path.exists(output_path))
            self.assertGreater(os.path.getsize(output_path), 0)

    def test_legacy_env_perc_handles_tiny_duration(self):
        samples = legacy_synth_core.env_perc(0.0)
        self.assertEqual(len(samples), 0)


if __name__ == "__main__":
    unittest.main()
