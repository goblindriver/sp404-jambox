#!/usr/bin/env python3
"""Pull random or stratified samples from _tags.json / tags DB for human quality review.

Run occasionally while smart retag (or other pipelines) are advancing — sanity-check
sonic_description, type_code, vibes, and quality_score before trusting fetch scoring.

Examples:
  .venv/bin/python scripts/review_tag_outputs.py --limit 12
  .venv/bin/python scripts/review_tag_outputs.py --mode lowest-quality --limit 20
  .venv/bin/python scripts/review_tag_outputs.py --source any --type-code KIK --limit 8
  .venv/bin/python scripts/review_tag_outputs.py --markdown ~/Desktop/tag_review_notes.md

Deep single-file audit (tags vs stored features + heuristics): scripts/audit_tag_vs_features.py
"""

from __future__ import annotations

import argparse
import os
import random
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from jambox_config import load_settings_for_script, load_tag_db

SETTINGS = load_settings_for_script(__file__)
TAGS_FILE = SETTINGS["TAGS_FILE"]
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]


def _fmt_list(val, max_items=6):
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, tuple)):
        return ", ".join(str(x) for x in val[:max_items])
    return str(val)


def _print_entry(i, n, rel, entry, full_path: str):
    tc = entry.get("type_code", "?")
    q = entry.get("quality_score", "?")
    src = entry.get("tag_source", "?")
    print("--- %d / %d ---" % (i, n))
    print("rel:  %s" % rel)
    print("file: %s" % full_path)
    print("type: %s  quality: %s  source: %s" % (tc, q, src))
    print("vibe:   %s" % _fmt_list(entry.get("vibe")))
    print("genre:  %s" % _fmt_list(entry.get("genre")))
    print("texture:%s" % _fmt_list(entry.get("texture")))
    ih = entry.get("instrument_hint")
    if ih:
        print("instr:  %s" % ih)
    desc = entry.get("sonic_description") or ""
    print("sonic:  %s" % (desc[:400] + ("…" if len(desc) > 400 else "")))
    print()


def _md_block(rel, entry, full_path: str) -> str:
    lines = [
        "### `%s`" % rel.replace("`", "'"),
        "- **File:** `%s`" % full_path.replace("`", "'"),
        "- **type / quality / source:** %s / %s / %s"
        % (entry.get("type_code", "?"), entry.get("quality_score", "?"), entry.get("tag_source", "?")),
        "- **sonic:** %s" % (entry.get("sonic_description") or "—"),
        "",
        "**Verdict:** OK / fix / quarantine — notes:",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample tag DB rows for manual quality review")
    parser.add_argument("--limit", type=int, default=15, help="Max rows to show")
    parser.add_argument(
        "--source",
        default="smart_retag_v1",
        help="tag_source filter, or 'any' for all entries",
    )
    parser.add_argument(
        "--type-code",
        dest="type_code",
        help="Only entries with this type_code (e.g. KIK)",
    )
    parser.add_argument(
        "--mode",
        choices=("random", "lowest-quality", "highest-quality"),
        default="random",
        help="Sampling strategy",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for random mode")
    parser.add_argument(
        "--markdown",
        metavar="PATH",
        help="Append a markdown section for note-taking",
    )
    args = parser.parse_args()

    db = load_tag_db(TAGS_FILE)
    items = []
    for rel, e in db.items():
        if args.source != "any" and e.get("tag_source") != args.source:
            continue
        if args.type_code and (e.get("type_code") or "").upper() != args.type_code.upper():
            continue
        items.append((rel, e))

    if not items:
        print("No entries match filters (tags file: %s)." % TAGS_FILE)
        return 1

    if args.mode == "random":
        if args.seed is not None:
            random.seed(args.seed)
        k = min(args.limit, len(items))
        sample = random.sample(items, k)
    elif args.mode == "lowest-quality":
        items.sort(key=lambda x: (x[1].get("quality_score") is None, x[1].get("quality_score") or 99, x[0]))
        sample = items[: args.limit]
    else:
        items.sort(
            key=lambda x: (
                x[1].get("quality_score") is None,
                -(x[1].get("quality_score") or 0),
                x[0],
            )
        )
        sample = items[: args.limit]

    print("Tag DB: %s (%d entries total, %d after filter, showing %d)\n" % (
        TAGS_FILE, len(db), len(items), len(sample)))

    md_chunks = []
    if args.markdown:
        md_chunks.append("\n## Tag review %s — %s — n=%d\n" % (
            args.mode, args.source, len(sample)))

    for i, (rel, e) in enumerate(sample, start=1):
        full = os.path.join(LIBRARY, rel) if not os.path.isabs(rel) else rel
        _print_entry(i, len(sample), rel, e, full)
        if args.markdown:
            md_chunks.append(_md_block(rel, e, full))

    if args.markdown and md_chunks:
        path = os.path.expanduser(args.markdown)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(md_chunks))
        print("Appended markdown to %s" % path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
