#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$REPO_DIR"

echo "=== SP-404 Jam Box Bootstrap ==="

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: Python interpreter not found: $PYTHON_BIN"
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install -r requirements.txt

echo
echo "Running setup validation..."
"$VENV_DIR/bin/python" "$SCRIPT_DIR/check_setup.py" || true

echo
echo "Bootstrap complete."
echo "Next steps:"
echo "  - Review any MISSING items above."
echo "  - Install system tools as needed, e.g. brew install ffmpeg unar chromaprint"
echo "  - Start the app with: $VENV_DIR/bin/python web/app.py"
