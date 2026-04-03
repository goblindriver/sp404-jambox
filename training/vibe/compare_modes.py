#!/usr/bin/env python3
"""Compare base, RAG, and fine-tuned parser modes on the eval suite."""

from __future__ import annotations

import argparse
import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import eval_model


def run_mode(mode, eval_dir):
    eval_model._set_mode(mode)
    parse_summary, _ = eval_model.evaluate_parse(os.path.join(eval_dir, "prompt_to_parse.jsonl"))
    draft_summary, _ = eval_model.evaluate_draft(os.path.join(eval_dir, "prompt_to_draft.jsonl"))
    ranking_summary, _ = eval_model.evaluate_ranking(
        os.path.join(eval_dir, "prompt_to_ranking.jsonl"),
        os.path.join(eval_dir, "ranking_fixture.json"),
    )
    return {
        "parse": parse_summary,
        "draft": draft_summary,
        "ranking": ranking_summary,
    }


def main():
    parser = argparse.ArgumentParser(description="Compare JamBox parser modes")
    parser.add_argument("--eval-dir", default=os.path.join(REPO_DIR, "data", "evals"))
    parser.add_argument("--modes", nargs="+", default=["base", "rag", "fine_tuned"])
    parser.add_argument("--write-report")
    args = parser.parse_args()

    report = {mode: run_mode(mode, args.eval_dir) for mode in args.modes}
    if args.write_report:
        os.makedirs(os.path.dirname(args.write_report), exist_ok=True)
        with open(args.write_report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
