#!/bin/bash
cd "$(dirname "$0")/.."
if [ -n "${SP404_TOOL_PATH_PREFIX:-}" ]; then
  export PATH="${SP404_TOOL_PATH_PREFIX}:$PATH"
fi
exec python3 web/app.py
