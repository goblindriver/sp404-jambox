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
from urllib import error, request

from jambox_config import build_subprocess_env, load_settings_for_script
import dedup_library


SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
DUPES_DIR = os.path.join(LIBRARY, "_DUPES")
REPORT_PATH = os.path.join(LIBRARY, "_dedupe_report.json")


def load_tag_db():
    try:
        with open(TAGS_FILE) as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


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


def similarity(a, b):
    if a["kind"] == "fpcalc" and b["kind"] == "fpcalc":
        return difflib.SequenceMatcher(a=a["value"], b=b["value"]).ratio()
    if a["kind"] == "python" and b["kind"] == "python":
        return float(dedup_library.cosine_similarity(a["value"], b["value"]))
    return 0.0


def _llm_tag_filename(rel_path):
    endpoint = SETTINGS.get("LLM_ENDPOINT", "").strip()
    if not endpoint:
        return []

    body = json.dumps({
        "model": SETTINGS.get("LLM_MODEL", "qwen3"),
        "messages": [
            {
                "role": "system",
                "content": "Suggest up to 5 lower-case descriptive sample tags as JSON: {\"tags\":[...]}",
            },
            {
                "role": "user",
                "content": json.dumps({"filename": rel_path, "directory": os.path.dirname(rel_path)}),
            },
        ],
        "temperature": 0.2,
    }).encode("utf-8")
    req = request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=SETTINGS.get("LLM_TIMEOUT", 30)) as response:
        payload = json.loads(response.read().decode("utf-8"))

    content = ""
    if payload.get("choices"):
        content = payload["choices"][0].get("message", {}).get("content", "")
    elif payload.get("message"):
        content = payload["message"].get("content", "")
    elif payload.get("response"):
        content = payload["response"]
    content = str(content).strip().removeprefix("```json").removesuffix("```").strip()
    parsed = json.loads(content or "{}")
    return [str(tag).lower() for tag in parsed.get("tags", []) if str(tag).strip()]


def find_duplicate_groups(db, threshold=0.93, limit=0, type_code=None):
    entries = list(db.items())
    if type_code:
        entries = [(path, entry) for path, entry in entries if entry.get("type_code") == type_code.upper()]
    if limit:
        entries = entries[:limit]

    fingerprints = {}
    for rel_path, _entry in entries:
        full_path = os.path.join(LIBRARY, rel_path)
        if not os.path.exists(full_path):
            continue
        fp = compute_fingerprint(full_path)
        if fp is not None:
            fingerprints[rel_path] = fp

    paths = list(fingerprints.keys())
    groups = []
    used = set()
    for idx, rel_path in enumerate(paths):
        if idx in used:
            continue
        group = [idx]
        for compare_idx in range(idx + 1, len(paths)):
            if compare_idx in used:
                continue
            sim = similarity(fingerprints[rel_path], fingerprints[paths[compare_idx]])
            if sim >= threshold:
                group.append(compare_idx)
                used.add(compare_idx)
        if len(group) > 1:
            used.add(idx)
            groups.append(group)

    reports = []
    for group in groups:
        members = []
        for item_idx in group:
            rel_path = paths[item_idx]
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


def apply_clean(report_groups):
    os.makedirs(DUPES_DIR, exist_ok=True)
    for group in report_groups:
        for rel_path in group["duplicates"]:
            src = os.path.join(LIBRARY, rel_path)
            if not os.path.exists(src):
                continue
            dst = os.path.join(DUPES_DIR, rel_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)


def build_report(args):
    db = load_tag_db()
    groups = find_duplicate_groups(db, threshold=args.threshold, limit=args.limit, type_code=args.type)
    unknown_tags = {}
    if args.llm_tag_unknown:
        for rel_path, entry in db.items():
            if entry.get("tags"):
                continue
            try:
                unknown_tags[rel_path] = _llm_tag_filename(rel_path)
            except (error.URLError, ValueError, json.JSONDecodeError):
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

    report = build_report(args)
    if args.clean:
        apply_clean(report["duplicate_groups"])

    if args.report_json or args.clean:
        with open(REPORT_PATH, "w") as handle:
            json.dump(report, handle, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
