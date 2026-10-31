"""Cross-platform plumbing: config defaults, SD card, deploy, process control."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(REPO_ROOT, "scripts"), os.path.join(REPO_ROOT, "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

import deploy_sd
import jambox_config
from api._helpers import kill_process_tree, new_process_group_kwargs, pid_alive
from api.pipeline import restart_helper_argv


def _touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class ConfigTests(unittest.TestCase):
    def test_subprocess_path_uses_the_os_separator(self):
        env = jambox_config.build_subprocess_env({"TOOL_PATH_PREFIX": "toolbin"}, {"PATH": "a"})
        self.assertEqual(env["PATH"], "toolbin" + os.pathsep + "a")

    def test_tool_default_prefers_an_existing_prefixed_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(jambox_config._tool_default("ffmpeg", tmp), "ffmpeg")
            _touch(os.path.join(tmp, "ffmpeg"))
            self.assertEqual(jambox_config._tool_default("ffmpeg", tmp), os.path.join(tmp, "ffmpeg"))
        self.assertEqual(jambox_config._tool_default("ffmpeg", ""), "ffmpeg")

    def test_tool_prefix_override_reaches_tool_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "fpcalc"))
            with patch.dict(os.environ, {"SP404_TOOL_PATH_PREFIX": tmp}, clear=True):
                settings = jambox_config.load_settings(REPO_ROOT)
        self.assertEqual(settings["FINGERPRINT_TOOL"], os.path.join(os.path.abspath(tmp), "fpcalc"))

    def test_plex_data_dir_override(self):
        with patch.dict(os.environ, {"SP404_PLEX_DATA_DIR": "plexdata"}):
            self.assertEqual(jambox_config.plex_data_dir(), os.path.abspath("plexdata"))


class SdCardTests(unittest.TestCase):
    def test_explicit_setting_wins(self):
        self.assertEqual(jambox_config.find_sd_card({"SD_CARD": "/cards/x"}), "/cards/x")

    def test_detects_a_mounted_card_by_its_roland_folder(self):
        with tempfile.TemporaryDirectory() as card, tempfile.TemporaryDirectory() as other:
            os.makedirs(os.path.join(card, "ROLAND", "SP-404SX"))
            parts = [SimpleNamespace(mountpoint=other), SimpleNamespace(mountpoint=card)]
            with patch("psutil.disk_partitions", return_value=parts):
                self.assertEqual(jambox_config.find_sd_card({"SD_CARD": ""}), card)
            with patch("psutil.disk_partitions", return_value=parts[:1]):
                self.assertIsNone(jambox_config.find_sd_card({}))


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.template = os.path.join(self.tmp.name, "template")
        self.card = os.path.join(self.tmp.name, "card")
        smpl = os.path.join(self.template, "ROLAND", "SP-404SX", "SMPL")
        _touch(os.path.join(smpl, "B0000001.WAV"), b"new")
        _touch(os.path.join(smpl, "PAD_INFO.BIN"), b"\0" * 3840)
        _touch(os.path.join(smpl, ".DS_Store"))
        self.pad_map = os.path.join(self.tmp.name, "PAD_MAP.txt")
        _touch(self.pad_map, b"map")
        self.card_smpl = os.path.join(self.card, "ROLAND", "SP-404SX", "SMPL")
        _touch(os.path.join(self.card_smpl, "E0000005.WAV"), b"resample")  # recorded on the device

    def _deploy(self, **kw):
        return deploy_sd.deploy(self.card, template_dir=self.template, pad_map=self.pad_map, **kw)

    def test_copies_template_and_keeps_card_only_pads(self):
        report = self._deploy()

        self.assertEqual(sorted(os.listdir(self.card_smpl)), ["B0000001.WAV", "E0000005.WAV", "PAD_INFO.BIN"])
        self.assertEqual(report["orphans"], ["E0000005.WAV"])
        self.assertTrue(os.path.exists(os.path.join(self.card, "PAD_MAP.txt")))
        self.assertEqual(self._deploy()["copied"], 0)  # second run: nothing changed

    def test_prune_deletes_card_only_pads(self):
        report = self._deploy(prune=True)
        self.assertEqual(report["pruned"], 1)
        self.assertNotIn("E0000005.WAV", os.listdir(self.card_smpl))

    def test_refuses_a_missing_card(self):
        with self.assertRaises(ValueError):
            deploy_sd.deploy(os.path.join(self.tmp.name, "nope"), template_dir=self.template)


class ProcessControlTests(unittest.TestCase):
    def test_kill_process_tree_stops_a_running_child(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                **new_process_group_kwargs())
        try:
            self.assertTrue(pid_alive(proc.pid))
            self.assertTrue(kill_process_tree(proc.pid, timeout=5))
            proc.wait(timeout=10)
            self.assertFalse(pid_alive(proc.pid))
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_restart_helper_waits_for_the_old_pid_then_launches_app(self):
        argv = restart_helper_argv("python", 1234, "app.py", "web")
        self.assertEqual(argv[0], "python")
        self.assertEqual(argv[3:], ["1234", "app.py", "web"])
        compile(argv[2], "<restart-helper>", "exec")

    def test_restart_helper_runs_to_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = os.path.join(tmp, "started")
            app = os.path.join(tmp, "app.py")
            with open(app, "w", encoding="utf-8") as fh:
                fh.write(f"open({marker!r}, 'w').close()\n")
            sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
            subprocess.run(restart_helper_argv(sys.executable, sleeper.pid, app, tmp), timeout=30, check=True)
            for _ in range(100):
                if os.path.exists(marker):
                    break
                time.sleep(0.1)
            self.assertTrue(os.path.exists(marker))
            sleeper.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
