#!/usr/bin/env python3
"""Check readiness gates before attempting pattern-model training."""

from __future__ import annotations

import argparse
import json
import os
import sys

import yaml


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SCRIPTS_DIR = os.path.join(REPO_DIR, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings


def _load_requirements(path):
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _check_path(repo_dir, entry):
    path = os.path.join(repo_dir, entry["path"])
    if entry["type"] == "dir":
        ok = os.path.isdir(path)
        file_count = len(os.listdir(path)) if ok else 0
        ok = ok and file_count >= entry.get("minimum_files", 0)
        return {"path": entry["path"], "ok": ok, "file_count": file_count}
    ok = os.path.isfile(path)
    return {"path": entry["path"], "ok": ok}


def main():
    parser = argparse.ArgumentParser(description="Check JamBox pattern-training readiness")
    parser.add_argument(
        "--requirements",
        default=os.path.join(REPO_DIR, "training", "pattern", "requirements.yaml"),
    )
    args = parser.parse_args()

    settings = load_settings(REPO_DIR)
    requirements = _load_requirements(args.requirements)
    checks = [_check_path(REPO_DIR, entry) for entry in requirements.get("required_paths", [])]
    checkpoint_dir = settings.get("MUSICVAE_CHECKPOINT_DIR", "")
    checkpoint_ok = bool(checkpoint_dir) and os.path.isdir(checkpoint_dir)
    report = {
        "checks": checks,
        "checkpoint_dir": checkpoint_dir,
        "checkpoint_ready": checkpoint_ok,
        "ready": checkpoint_ok and all(item["ok"] for item in checks),
    }
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
