#!/bin/bash
# Double-click this file to launch Jambox in the macOS menu bar.
# The menu bar icon manages the server, opens the web UI, and runs pipeline actions.
cd "$(dirname "$0")/.."
exec .venv/bin/python tools/jambox_menubar.py
