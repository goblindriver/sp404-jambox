#!/bin/bash
# Deploy logic lives in deploy_sd.py (works on macOS, Windows and Linux).
# This wrapper stays for muscle memory: bash scripts/copy_to_sd.sh [--prune]
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO_DIR/.venv/bin/python"
[ -x "$PY" ] || PY=python3
exec "$PY" "$REPO_DIR/scripts/deploy_sd.py" "$@"
