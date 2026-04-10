#!/usr/bin/env python3
"""SP-404 Jambox — macOS menu bar launcher.

A lightweight status bar app for managing the Jambox server,
opening the web UI, and running quick pipeline actions.

Launch:  .venv/bin/python tools/jambox_menubar.py
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

import rumps

# ── Paths ──
REPO = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO / ".venv" / "bin" / "python"
WEB_APP = REPO / "web" / "app.py"
URL = "http://localhost:5404"
API = f"{URL}/api"

# ── Env for server subprocess ──
SERVER_ENV = {
    **os.environ,
    "SP404_LLM_ENDPOINT": os.environ.get(
        "SP404_LLM_ENDPOINT", "http://localhost:11434/v1/chat/completions"
    ),
    "SP404_LLM_MODEL": os.environ.get("SP404_LLM_MODEL", "qwen3.5:9b"),
    "SP404_LLM_TIMEOUT": os.environ.get("SP404_LLM_TIMEOUT", "90"),
}


def api_get(path):
    """Quick non-blocking GET to a Jambox API endpoint."""
    try:
        req = Request(f"{API}{path}", headers={"Accept": "application/json"})
        with urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def api_post(path, body=None):
    """Quick POST to a Jambox API endpoint."""
    try:
        data = json.dumps(body or {}).encode()
        req = Request(
            f"{API}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


class JamboxApp(rumps.App):
    def __init__(self):
        super().__init__(
            "SP-404",
            icon=None,
            title="\U0001f3db SP-404",  # 🏛 (closest to sampler in emoji)
            quit_button=None,
        )
        self.server_proc = None

        # ── Menu items ──
        self.open_ui = rumps.MenuItem("Open Web UI", callback=self.on_open_ui)
        self.status_item = rumps.MenuItem("Server: checking...")
        self.status_item.set_callback(None)
        self.toggle_server = rumps.MenuItem("Start Server", callback=self.on_toggle_server)
        self.library_item = rumps.MenuItem("Library: ...")
        self.library_item.set_callback(None)
        self.sd_item = rumps.MenuItem("SD Card: ...")
        self.sd_item.set_callback(None)

        # Quick actions
        self.fetch_all = rumps.MenuItem("Fetch All Banks", callback=self.on_fetch_all)
        self.ingest = rumps.MenuItem("Ingest Downloads", callback=self.on_ingest)
        self.deploy = rumps.MenuItem("Deploy to SD Card", callback=self.on_deploy)
        self.daily = rumps.MenuItem("Generate Daily Bank", callback=self.on_daily)

        self.menu = [
            self.open_ui,
            None,  # separator
            self.status_item,
            self.toggle_server,
            None,
            self.library_item,
            self.sd_item,
            None,
            self.fetch_all,
            self.ingest,
            self.deploy,
            self.daily,
            None,
            rumps.MenuItem("Quit Jambox", callback=self.on_quit),
        ]

        # Check if server is already running
        self._update_status()

    # ── Status polling ──
    @rumps.timer(8)
    def poll_status(self, _):
        threading.Thread(target=self._update_status, daemon=True).start()

    def _update_status(self):
        data = api_get("/pipeline/server/status")
        if data:
            self.title = "\U0001f7e2 SP-404"  # 🟢
            self.status_item.title = "Server: running"
            self.toggle_server.title = "Stop Server"

            # Library stats
            stats = api_get("/library/stats")
            if stats:
                total = stats.get("total_files", "?")
                self.library_item.title = f"Library: {total:,} samples" if isinstance(total, int) else f"Library: {total} samples"

            # SD card
            sd = api_get("/sdcard/status")
            if sd and sd.get("mounted"):
                free_mb = sd.get("free_space_mb", "?")
                self.sd_item.title = f"SD Card: mounted ({free_mb} MB free)"
            elif sd:
                self.sd_item.title = "SD Card: not mounted"
        else:
            self.title = "\u26aa SP-404"  # ⚪
            self.status_item.title = "Server: stopped"
            self.toggle_server.title = "Start Server"
            self.library_item.title = "Library: —"
            self.sd_item.title = "SD Card: —"

    # ── Actions ──
    def on_open_ui(self, _):
        webbrowser.open(URL)

    def on_toggle_server(self, _):
        if self.status_item.title == "Server: running":
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self):
        if self.server_proc and self.server_proc.poll() is None:
            return  # already running

        self.title = "\U0001f7e1 SP-404"  # 🟡 starting
        self.status_item.title = "Server: starting..."

        self.server_proc = subprocess.Popen(
            [str(VENV_PYTHON), str(WEB_APP)],
            cwd=str(REPO),
            env=SERVER_ENV,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait for it to come up
        threading.Thread(target=self._wait_for_server, daemon=True).start()

    def _wait_for_server(self):
        for _ in range(30):  # wait up to 15s
            time.sleep(0.5)
            if api_get("/pipeline/server/status"):
                self._update_status()
                rumps.notification(
                    "SP-404 Jambox",
                    "Server started",
                    f"Web UI at {URL}",
                    sound=False,
                )
                return
        self.status_item.title = "Server: failed to start"
        self.title = "\U0001f534 SP-404"  # 🔴

    def _stop_server(self):
        # Try graceful API shutdown first
        api_post("/pipeline/server/restart")
        time.sleep(0.5)

        # Kill our managed process if we have one
        if self.server_proc and self.server_proc.poll() is None:
            self.server_proc.terminate()
            try:
                self.server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_proc.kill()
            self.server_proc = None

        # Also kill any other process on port 5404
        try:
            result = subprocess.run(
                ["lsof", "-ti", ":5404"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                for pid in result.stdout.strip().split("\n"):
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except (ProcessLookupError, ValueError):
                        pass
        except Exception:
            pass

        self._update_status()

    def on_fetch_all(self, _):
        result = api_post("/pipeline/fetch")
        if result and result.get("job_id"):
            rumps.notification(
                "SP-404 Jambox", "Fetch started", f"Job: {result['job_id']}", sound=False
            )
        else:
            rumps.notification(
                "SP-404 Jambox", "Fetch failed", "Is the server running?", sound=False
            )

    def on_ingest(self, _):
        result = api_post("/pipeline/ingest")
        if result:
            rumps.notification(
                "SP-404 Jambox", "Ingest started", "Processing ~/Downloads", sound=False
            )
        else:
            rumps.notification(
                "SP-404 Jambox", "Ingest failed", "Is the server running?", sound=False
            )

    def on_deploy(self, _):
        result = api_post("/pipeline/deploy")
        if result and result.get("success"):
            rumps.notification(
                "SP-404 Jambox", "Deploy complete", "Card is ready", sound=False
            )
        else:
            rumps.notification(
                "SP-404 Jambox",
                "Deploy failed",
                "Check SD card and server status",
                sound=False,
            )

    def on_daily(self, _):
        result = api_post("/presets/daily")
        if result:
            name = result.get("name", "daily preset")
            rumps.notification(
                "SP-404 Jambox", "Daily bank generated", name, sound=False
            )
        else:
            rumps.notification(
                "SP-404 Jambox", "Daily bank failed", "Is the server running?", sound=False
            )

    def on_quit(self, _):
        if self.server_proc and self.server_proc.poll() is None:
            self.server_proc.terminate()
        rumps.quit_application()


if __name__ == "__main__":
    JamboxApp().run()
