import os
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import ConfigError, build_subprocess_env, load_settings


class LoadSettingsTests(unittest.TestCase):
    def test_defaults_resolve_expected_paths(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings("/tmp/jambox-repo")

        self.assertEqual(settings["REPO_DIR"], "/tmp/jambox-repo")
        self.assertTrue(settings["SAMPLE_LIBRARY"].endswith("SP404-Sample-Library"))
        self.assertTrue(settings["SMPL_DIR"].endswith("sd-card-template/ROLAND/SP-404SX/SMPL"))
        self.assertFalse(settings["WEB_DEBUG"])

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


if __name__ == "__main__":
    unittest.main()
