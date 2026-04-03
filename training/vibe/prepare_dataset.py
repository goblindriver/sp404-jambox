#!/usr/bin/env python3
"""Prepare supervised training data from reviewed vibe sessions."""

from __future__ import annotations

import argparse
import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SCRIPTS_DIR = os.path.join(REPO_DIR, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import vibe_training_store as vts


def _load_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _jsonl_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def build_examples(rows):
    parse_rows = []
    draft_rows = []
    for row in rows:
        reviewed_parsed = _load_json(row.get("reviewed_parsed_json")) or _load_json(row.get("parsed_json"))
        reviewed_preset = (
            _load_json(row.get("applied_preset_json"))
            or _load_json(row.get("reviewed_preset_json"))
            or _load_json(row.get("draft_preset_json"))
        )
        if reviewed_parsed:
            parse_rows.append(
                {
                    "id": row["id"],
                    "task": "prompt_to_parse",
                    "input": {
                        "prompt": row["prompt"],
                        "bpm": row.get("bpm"),
                        "key": row.get("musical_key"),
                    },
                    "output": reviewed_parsed,
                }
            )
        if reviewed_preset:
            draft_rows.append(
                {
                    "id": row["id"],
                    "task": "prompt_to_draft",
                    "input": {
                        "prompt": row["prompt"],
                        "bpm": row.get("bpm"),
                        "key": row.get("musical_key"),
                        "parsed": reviewed_parsed or {},
                    },
                    "output": reviewed_preset,
                }
            )
    return parse_rows, draft_rows


def main():
    parser = argparse.ArgumentParser(description="Prepare vibe training data from reviewed sessions")
    parser.add_argument("--dataset-status", default="reviewed")
    parser.add_argument("--output-dir", default=os.path.join(REPO_DIR, "data", "training", "vibe"))
    args = parser.parse_args()

    rows = vts.list_sessions(limit=5000, dataset_status=args.dataset_status)
    parse_rows, draft_rows = build_examples(rows)
    _jsonl_write(os.path.join(args.output_dir, "parse_train.jsonl"), parse_rows)
    _jsonl_write(os.path.join(args.output_dir, "draft_train.jsonl"), draft_rows)

    summary = {
        "dataset_status": args.dataset_status,
        "session_count": len(rows),
        "parse_examples": len(parse_rows),
        "draft_examples": len(draft_rows),
    }
    with open(os.path.join(args.output_dir, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
