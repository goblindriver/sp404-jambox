#!/usr/bin/env python3
"""Offline evaluation for JamBox vibe parsing, draft generation, and ranking."""

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

import fetch_samples
import vibe_generate


def _load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _set_mode(mode):
    vibe_generate.SETTINGS["VIBE_PARSER_MODE"] = mode


def evaluate_parse(path):
    rows = _load_jsonl(path)
    summary = {"cases": len(rows), "type_code_hits": 0, "playability_hits": 0, "keyword_hits": 0}
    details = []
    for row in rows:
        result = vibe_generate.parse_vibe_prompt(row["prompt"], bpm=row.get("bpm"), key=row.get("key"))
        parsed = result["tags"]
        expected = row["expected"]
        if parsed.get("type_code") == expected.get("type_code"):
            summary["type_code_hits"] += 1
        if parsed.get("playability") == expected.get("playability"):
            summary["playability_hits"] += 1
        expected_keywords = set(expected.get("keywords", []))
        actual_keywords = set(parsed.get("keywords", []))
        keyword_hit = len(expected_keywords & actual_keywords)
        summary["keyword_hits"] += keyword_hit
        details.append({"id": row["id"], "parsed": parsed, "expected": expected, "keyword_hit_count": keyword_hit})
    summary["type_code_accuracy"] = round(summary["type_code_hits"] / summary["cases"], 3) if summary["cases"] else 0.0
    summary["playability_accuracy"] = round(summary["playability_hits"] / summary["cases"], 3) if summary["cases"] else 0.0
    return summary, details


def evaluate_draft(path):
    rows = _load_jsonl(path)
    summary = {"cases": len(rows), "pad_prefix_hits": 0, "contains_hits": 0, "pad_checks": 0, "contains_checks": 0}
    details = []
    for row in rows:
        result = vibe_generate.build_bank_from_vibe(row)
        preset = result["preset"]
        expected = row["expected"]
        for pad_num, prefix in expected.get("pads", {}).items():
            summary["pad_checks"] += 1
            actual = preset["pads"].get(int(pad_num), "")
            if actual.startswith(prefix):
                summary["pad_prefix_hits"] += 1
        full_text = " ".join(preset["pads"].values()).lower()
        for token in expected.get("contains", []):
            summary["contains_checks"] += 1
            if token.lower() in full_text:
                summary["contains_hits"] += 1
        details.append({"id": row["id"], "preset": preset, "expected": expected})
    summary["pad_prefix_accuracy"] = round(summary["pad_prefix_hits"] / summary["pad_checks"], 3) if summary["pad_checks"] else 0.0
    summary["contains_accuracy"] = round(summary["contains_hits"] / summary["contains_checks"], 3) if summary["contains_checks"] else 0.0
    return summary, details


def evaluate_ranking(path, fixture_path):
    rows = _load_jsonl(path)
    fixture = _load_json(fixture_path)
    summary = {"cases": len(rows), "top1_hits": 0}
    details = []
    for row in rows:
        parse_result = vibe_generate.parse_vibe_prompt(row["prompt"], bpm=row.get("bpm"), key=row.get("key"))
        query = vibe_generate._build_query(row, parse_result["tags"])
        # Force legacy path: fixture entries don't have CLAP embeddings
        matches = fetch_samples.rank_library_matches_legacy(
            query,
            bank_config={"bpm": row.get("bpm"), "key": row.get("key")},
            tag_db=fixture,
            limit=5,
            min_score=0,
        )
        top = matches[0]["rel_path"] if matches else None
        if top == row["expected_top"]:
            summary["top1_hits"] += 1
        details.append({"id": row["id"], "query": query, "top": top, "expected_top": row["expected_top"]})
    summary["top1_accuracy"] = round(summary["top1_hits"] / summary["cases"], 3) if summary["cases"] else 0.0
    return summary, details


def main():
    parser = argparse.ArgumentParser(description="Evaluate JamBox vibe parsing and draft quality")
    parser.add_argument("--mode", default="base", choices=["base", "rag", "fine_tuned"])
    parser.add_argument("--eval-dir", default=os.path.join(REPO_DIR, "data", "evals"))
    parser.add_argument("--write-report")
    args = parser.parse_args()

    _set_mode(args.mode)
    parse_summary, parse_details = evaluate_parse(os.path.join(args.eval_dir, "prompt_to_parse.jsonl"))
    draft_summary, draft_details = evaluate_draft(os.path.join(args.eval_dir, "prompt_to_draft.jsonl"))
    ranking_summary, ranking_details = evaluate_ranking(
        os.path.join(args.eval_dir, "prompt_to_ranking.jsonl"),
        os.path.join(args.eval_dir, "ranking_fixture.json"),
    )
    report = {
        "mode": args.mode,
        "parse": parse_summary,
        "draft": draft_summary,
        "ranking": ranking_summary,
        "details": {
            "parse": parse_details,
            "draft": draft_details,
            "ranking": ranking_details,
        },
    }

    if args.write_report:
        os.makedirs(os.path.dirname(args.write_report), exist_ok=True)
        with open(args.write_report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
