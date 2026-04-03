#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
if [ -n "${SP404_TOOL_PATH_PREFIX:-}" ]; then
  export PATH="${SP404_TOOL_PATH_PREFIX}:$PATH"
fi
exec python3 web/app.py
