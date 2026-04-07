#!/usr/bin/env python3
"""Round 4: drum-loop rows missing type_code (minimal / partial ingest rows).

Run:  .venv/bin/python scripts/muscle_tags_round4.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from jambox_config import load_settings_for_script, load_tag_db, save_tag_db
from tag_hygiene import _expected_playability, _normalize_tags

SETTINGS = load_settings_for_script(__file__)
TAGS_FILE = SETTINGS["TAGS_FILE"]


def _patch(entry: Dict, rel_path: str, new_type: str) -> Dict:
    cur_play = str(entry.get("playability") or "")
    play = _expected_playability(new_type, rel_path, cur_play) or "loop"
    e = dict(entry)
    e["type_code"] = new_type
    e["playability"] = play
    if "tags" not in e or not isinstance(e.get("tags"), list):
        e["tags"] = []
    e["tags"] = _normalize_tags(e, new_type, play)
    if not e.get("source"):
        e["source"] = "dug"
    return e


def main() -> int:
    ap = argparse.ArgumentParser(description="Round 4: bare drum-loop tag rows")
    ap.add_argument("--apply", action="store_true", help="Write changes")
    args = ap.parse_args()

    db = load_tag_db(TAGS_FILE)
    if not isinstance(db, dict) or not db:
        print("ERROR: empty tag database")
        return 1

    targets: List[str] = [
        rel
        for rel, entry in db.items()
        if rel.startswith("Drums/Drum-Loops/")
        and not str(entry.get("type_code") or "").strip()
    ]
    print(f"Planned patches: {len(targets)}")
    for rel in targets:
        print(f"  {rel}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
        return 0

    updated = dict(db)
    for rel in targets:
        entry = updated.get(rel)
        if not isinstance(entry, dict):
            continue
        updated[rel] = _patch(entry, rel, "BRK")

    save_tag_db(TAGS_FILE, updated)
    print(f"\nWrote {len(targets)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
