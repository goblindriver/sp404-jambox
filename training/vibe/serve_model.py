#!/usr/bin/env python3
"""Serve a local GGUF vibe model through llama.cpp's OpenAI-compatible server."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Serve a fine-tuned JamBox vibe model locally")
    parser.add_argument("--model", required=True, help="Path to GGUF model file")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ctx-size", type=int, default=4096)
    args = parser.parse_args()

    if not os.path.exists(args.model):
        raise SystemExit(f"Model not found: {args.model}")

    command = [
        sys.executable,
        "-m",
        "llama_cpp.server",
        "--model",
        args.model,
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--n_ctx",
        str(args.ctx_size),
    ]
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
