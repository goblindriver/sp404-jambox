#!/bin/bash
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:$PATH"
exec python3 web/app.py
