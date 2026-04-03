import os
import sys
import unittest
from io import StringIO
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import check_setup
from jambox_config import ConfigError, build_subprocess_env, load_settings, resolve_command


class LoadSettingsTests(unittest.TestCase):
    def test_defaults_resolve_expected_paths(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings("/tmp/jambox-repo")

        self.assertEqual(settings["REPO_DIR"], "/tmp/jambox-repo")
        self.assertTrue(settings["SAMPLE_LIBRARY"].endswith("SP404-Sample-Library"))
        self.assertTrue(settings["SMPL_DIR"].endswith("sd-card-template/ROLAND/SP-404SX/SMPL"))
        self.assertFalse(settings["WEB_DEBUG"])
        self.assertEqual(settings["DAILY_BANK_SOURCE"], "recent")
        self.assertEqual(settings["LLM_TIMEOUT"], 30)

    def test_invalid_boolean_raises_clear_error(self):
        with patch.dict(os.environ, {"SP404_WEB_DEBUG": "maybe"}, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                load_settings("/tmp/jambox-repo")

        self.assertIn("SP404_WEB_DEBUG", str(ctx.exception))

    def test_empty_required_path_raises_clear_error(self):
        with patch.dict(os.environ, {"SP404_SAMPLE_LIBRARY": "   "}, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                load_settings("/tmp/jambox-repo")

        self.assertIn("SP404_SAMPLE_LIBRARY", str(ctx.exception))

    def test_empty_tool_path_prefix_disables_path_injection(self):
        with patch.dict(os.environ, {"SP404_TOOL_PATH_PREFIX": ""}, clear=True):
            settings = load_settings("/tmp/jambox-repo")

        env = build_subprocess_env(settings, {"PATH": "/usr/bin"})
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_invalid_daily_bank_source_raises_clear_error(self):
        with patch.dict(os.environ, {"SP404_DAILY_BANK_SOURCE": "weekly"}, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                load_settings("/tmp/jambox-repo")

        self.assertIn("SP404_DAILY_BANK_SOURCE", str(ctx.exception))

    def test_invalid_llm_timeout_raises_clear_error(self):
        with patch.dict(os.environ, {"SP404_LLM_TIMEOUT": "0"}, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                load_settings("/tmp/jambox-repo")

        self.assertIn("SP404_LLM_TIMEOUT", str(ctx.exception))

    def test_resolve_command_accepts_executable_absolute_path(self):
        with patch("jambox_config.os.path.isfile", return_value=True), patch("jambox_config.os.access", return_value=True):
            resolved = resolve_command("/tmp/tool")

        self.assertEqual(resolved, "/tmp/tool")

    def test_resolve_command_uses_path_lookup_for_relative_command(self):
        with patch("jambox_config.shutil.which", return_value="/usr/bin/ffmpeg") as which:
            resolved = resolve_command("ffmpeg")

        self.assertEqual(resolved, "/usr/bin/ffmpeg")
        which.assert_called_once()


class CheckSetupTests(unittest.TestCase):
    def test_run_checks_returns_failure_for_missing_required_prereqs(self):
        settings = {
            "REPO_DIR": "/repo",
            "CONFIG_PATH": "/repo/bank_config.yaml",
            "SAMPLE_LIBRARY": "/library",
            "DOWNLOADS_PATH": "/downloads",
            "SD_CARD": "/sdcard",
            "SMPL_DIR": "/repo/sd-card-template/ROLAND/SP-404SX/SMPL",
            "FFMPEG_BIN": "ffmpeg",
            "FFPROBE_BIN": "ffprobe",
            "UNAR_BIN": "unar",
            "FINGERPRINT_TOOL": "fpcalc",
            "MAGENTA_COMMAND": "music_vae_generate",
            "MUSICVAE_CHECKPOINT_DIR": "/repo/models/musicvae",
            "LLM_ENDPOINT": "",
            "TOOL_PATH_PREFIX": "",
        }
        stdout = StringIO()
        with patch.object(check_setup, "load_settings_for_script", return_value=settings), patch.object(check_setup, "_module_installed", return_value=True), patch.object(check_setup, "resolve_command", side_effect=["/usr/bin/ffmpeg", "/usr/bin/ffprobe", None, None, None]), patch.object(check_setup, "build_subprocess_env", return_value={}), patch("check_setup.os.path.exists", return_value=True), patch("sys.stdout", stdout):
            exit_code = check_setup.run_checks()

        self.assertEqual(exit_code, 1)
        self.assertIn("unar", stdout.getvalue())

    def test_run_checks_allows_optional_integrations_to_be_missing(self):
        settings = {
            "REPO_DIR": "/repo",
            "CONFIG_PATH": "/repo/bank_config.yaml",
            "SAMPLE_LIBRARY": "/library",
            "DOWNLOADS_PATH": "/downloads",
            "SD_CARD": "/sdcard",
            "SMPL_DIR": "/repo/sd-card-template/ROLAND/SP-404SX/SMPL",
            "FFMPEG_BIN": "ffmpeg",
            "FFPROBE_BIN": "ffprobe",
            "UNAR_BIN": "unar",
            "FINGERPRINT_TOOL": "fpcalc",
            "MAGENTA_COMMAND": "music_vae_generate",
            "MUSICVAE_CHECKPOINT_DIR": "",
            "LLM_ENDPOINT": "",
            "TOOL_PATH_PREFIX": "",
        }
        stdout = StringIO()
        with patch.object(check_setup, "load_settings_for_script", return_value=settings), patch.object(check_setup, "_module_installed", return_value=True), patch.object(check_setup, "resolve_command", side_effect=["/usr/bin/ffmpeg", "/usr/bin/ffprobe", "/usr/bin/unar", None, None]), patch.object(check_setup, "build_subprocess_env", return_value={}), patch("check_setup.os.path.exists", return_value=True), patch("sys.stdout", stdout):
            exit_code = check_setup.run_checks()

        self.assertEqual(exit_code, 0)
        self.assertIn("OPTIONAL", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
