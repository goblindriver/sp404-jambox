#!/usr/bin/env python3
"""Detect and optionally move duplicate samples using fpcalc or Python fallback.

Usage:
    python scripts/deduplicate_samples.py --report-json
    python scripts/deduplicate_samples.py --dedupe --clean
"""

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

from jambox_cache import file_marker, get_cached_fingerprint, load_fingerprint_cache, put_cached_fingerprint, save_fingerprint_cache
from jambox_config import build_subprocess_env, load_settings_for_script
from llm_client import LLMError, call_llm_chat
import dedup_library


SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
DUPES_DIR = os.path.join(LIBRARY, "_DUPES")
REPORT_PATH = os.path.join(LIBRARY, "_dedupe_report.json")


def load_tag_db():
    from jambox_config import load_tag_db as _load
    return _load(TAGS_FILE)


def _fingerprint_with_fpcalc(filepath):
    tool = SETTINGS.get("FINGERPRINT_TOOL", "fpcalc")
    if not tool:
        return None

    result = subprocess.run(
        [tool, "-raw", filepath],
        capture_output=True,
        text=True,
        timeout=20,
        env=build_subprocess_env(SETTINGS),
    )
    if result.returncode != 0:
        return None

    fingerprint = ""
    duration = 0.0
    for line in result.stdout.splitlines():
        if line.startswith("FINGERPRINT="):
            fingerprint = line.split("=", 1)[1].strip()
        elif line.startswith("DURATION="):
            try:
                duration = float(line.split("=", 1)[1].strip())
            except ValueError:
                duration = 0.0
    if not fingerprint:
        return None
    return {"kind": "fpcalc", "value": fingerprint, "duration": duration}


def _fingerprint_with_python(filepath):
    vector = dedup_library.compute_fingerprint(filepath)
    if vector is None:
        return None
    return {"kind": "python", "value": vector}


def compute_fingerprint(filepath):
    return _fingerprint_with_fpcalc(filepath) or _fingerprint_with_python(filepath)


def _cached_fingerprint(rel_path, cache_entries, python_fingerprints):
    full_path = os.path.join(LIBRARY, rel_path)
    marker = file_marker(full_path)
    if not marker:
        return None

    cached = get_cached_fingerprint(cache_entries, rel_path, marker, "fpcalc")
    if cached is not None:
        return cached

    fingerprint = _fingerprint_with_fpcalc(full_path)
    if fingerprint is not None:
        put_cached_fingerprint(cache_entries, rel_path, marker, "fpcalc", fingerprint)
        return fingerprint

    cached_python = get_cached_fingerprint(cache_entries, rel_path, marker, "python")
    if cached_python is not None:
        python_fingerprints[rel_path] = cached_python
        return cached_python

    fingerprint = _fingerprint_with_python(full_path)
    if fingerprint is not None:
        put_cached_fingerprint(cache_entries, rel_path, marker, "python", fingerprint)
        python_fingerprints[rel_path] = fingerprint
    return fingerprint


def similarity(a, b):
    if a["kind"] == "fpcalc" and b["kind"] == "fpcalc":
        return difflib.SequenceMatcher(a=a["value"], b=b["value"]).ratio()
    if a["kind"] == "python" and b["kind"] == "python":
        return float(dedup_library.cosine_similarity(a["value"], b["value"]))
    return None


def _ensure_python_fingerprint(rel_path, fingerprints, python_fingerprints, cache_entries):
    if rel_path in python_fingerprints:
        return python_fingerprints[rel_path]

    fingerprint = fingerprints[rel_path]
    if fingerprint["kind"] == "python":
        python_fingerprints[rel_path] = fingerprint
        return fingerprint

    full_path = os.path.join(LIBRARY, rel_path)
    marker = file_marker(full_path)
    python_fp = get_cached_fingerprint(cache_entries, rel_path, marker, "python") if marker else None
    if python_fp is None:
        python_fp = _fingerprint_with_python(full_path)
        if python_fp is not None and marker:
            put_cached_fingerprint(cache_entries, rel_path, marker, "python", python_fp)
    if python_fp is not None:
        python_fingerprints[rel_path] = python_fp
    return python_fp


def _pair_similarity(rel_path, compare_path, fingerprints, python_fingerprints, cache_entries):
    primary_score = similarity(fingerprints[rel_path], fingerprints[compare_path])
    if primary_score is not None:
        return primary_score

    rel_python = _ensure_python_fingerprint(rel_path, fingerprints, python_fingerprints, cache_entries)
    compare_python = _ensure_python_fingerprint(compare_path, fingerprints, python_fingerprints, cache_entries)
    if rel_python is None or compare_python is None:
        return 0.0
    return similarity(rel_python, compare_python) or 0.0


def _llm_tag_filename(rel_path):
    endpoint = SETTINGS.get("LLM_ENDPOINT", "").strip()
    if not endpoint:
        return []

    try:
        parsed = call_llm_chat(
            endpoint,
            SETTINGS.get("LLM_MODEL", "qwen3.5:9b"),
            [
                {
                    "role": "system",
                    "content": 'Suggest up to 5 lower-case descriptive sample tags as JSON: {"tags":[...]}',
                },
                {
                    "role": "user",
                    "content": json.dumps({"filename": rel_path, "directory": os.path.dirname(rel_path)}),
                },
            ],
            timeout=SETTINGS.get("LLM_TIMEOUT", 30),
            temperature=0.2,
            json_mode=True,
            max_tokens=SETTINGS.get("DEDUP_TAG_MAX_TOKENS", 200),
        )
    except LLMError:
        return []

    if not isinstance(parsed, dict):
        return []
    return [str(tag).lower() for tag in parsed.get("tags", []) if str(tag).strip()]


def find_duplicate_groups(db, threshold=0.93, limit=0, type_code=None):
    entries = list(db.items())
    if type_code:
        entries = [(path, entry) for path, entry in entries if entry.get("type_code") == type_code.upper()]
    if limit:
        entries = entries[:limit]

    fingerprints = {}
    cache_entries = load_fingerprint_cache(LIBRARY)
    for rel_path, _entry in entries:
        full_path = os.path.join(LIBRARY, rel_path)
        if not os.path.exists(full_path):
            continue
        fp = _cached_fingerprint(rel_path, cache_entries, {})
        if fp is not None:
            fingerprints[rel_path] = fp

    paths = list(fingerprints.keys())
    python_fingerprints = {}
    adjacency = {rel_path: set() for rel_path in paths}
    for idx, rel_path in enumerate(paths):
        for compare_idx in range(idx + 1, len(paths)):
            compare_path = paths[compare_idx]
            sim = _pair_similarity(rel_path, compare_path, fingerprints, python_fingerprints, cache_entries)
            if sim >= threshold:
                adjacency[rel_path].add(compare_path)
                adjacency[compare_path].add(rel_path)
    save_fingerprint_cache(LIBRARY, cache_entries)

    groups = []
    visited = set()
    for rel_path in paths:
        if rel_path in visited or not adjacency[rel_path]:
            continue
        stack = [rel_path]
        group = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            group.append(current)
            stack.extend(sorted(adjacency[current] - visited, reverse=True))
        if len(group) > 1:
            groups.append(group)

    reports = []
    for group in groups:
        members = []
        for rel_path in group:
            full_path = os.path.join(LIBRARY, rel_path)
            entry = db.get(rel_path, {})
            members.append({
                "path": rel_path,
                "size": os.path.getsize(full_path) if os.path.exists(full_path) else 0,
                "tag_count": len(entry.get("tags", [])),
                "type_code": entry.get("type_code"),
            })
        members.sort(key=lambda item: (item["tag_count"], item["size"]), reverse=True)
        reports.append({
            "keep": members[0]["path"],
            "duplicates": [item["path"] for item in members[1:]],
            "members": members,
        })
    return reports


def apply_clean(report_groups, db):
    from jambox_config import save_tag_db
    os.makedirs(DUPES_DIR, exist_ok=True)
    updated_db = dict(db)
    for group in report_groups:
        for rel_path in group["duplicates"]:
            src = os.path.join(LIBRARY, rel_path)
            if not os.path.exists(src):
                updated_db.pop(rel_path, None)
                continue
            dst = os.path.join(DUPES_DIR, rel_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.move(src, dst)
            except OSError as e:
                print(f"  WARNING: could not move {rel_path}: {e}")
                continue
            updated_db.pop(rel_path, None)

    save_tag_db(TAGS_FILE, updated_db)
    return updated_db


def build_report(args, db=None):
    db = load_tag_db() if db is None else db
    groups = find_duplicate_groups(db, threshold=args.threshold, limit=args.limit, type_code=args.type)
    unknown_tags = {}
    if args.llm_tag_unknown:
        for rel_path, entry in db.items():
            if entry.get("tags"):
                continue
            try:
                unknown_tags[rel_path] = _llm_tag_filename(rel_path)
            except (TypeError, ValueError):
                unknown_tags[rel_path] = []

    report = {
        "created_at": datetime.now().isoformat(),
        "library": LIBRARY,
        "threshold": args.threshold,
        "duplicate_groups": groups,
        "duplicates_found": sum(len(group["duplicates"]) for group in groups),
        "llm_tag_suggestions": unknown_tags,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Detect duplicate samples with fpcalc or Python fallback")
    parser.add_argument("--threshold", type=float, default=0.93)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--type")
    parser.add_argument("--clean", action="store_true", help="Move duplicates into _DUPES")
    parser.add_argument("--report-json", action="store_true", help="Write a JSON report to the library root")
    parser.add_argument("--llm-tag-unknown", action="store_true", help="Ask the local LLM for tags on untagged files")
    args = parser.parse_args()

    db = load_tag_db()
    report = build_report(args, db=db)
    if args.clean:
        db = apply_clean(report["duplicate_groups"], db)

    if args.report_json or args.clean:
        with open(REPORT_PATH, "w") as handle:
            json.dump(report, handle, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
