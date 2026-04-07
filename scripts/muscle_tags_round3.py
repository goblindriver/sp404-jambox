#!/usr/bin/env python3
"""Round 3: full drum breaks filed under Snares-Claps (Cymatics-style packs).

Run:  .venv/bin/python scripts/muscle_tags_round3.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from jambox_config import load_settings_for_script, load_tag_db, save_tag_db
from tag_hygiene import _expected_playability, _normalize_tags

SETTINGS = load_settings_for_script(__file__)
TAGS_FILE = SETTINGS["TAGS_FILE"]


def _bn(rel: str) -> str:
    return os.path.basename(rel).lower()


def _patch(entry: Dict, rel_path: str, new_type: str) -> Dict:
    cur_play = str(entry.get("playability") or "")
    play = _expected_playability(new_type, rel_path, cur_play)
    e = dict(entry)
    e["type_code"] = new_type
    e["playability"] = play
    e["tags"] = _normalize_tags(e, new_type, play)
    return e


def _is_misfiled_snare_folder_loop(rel: str) -> bool:
    if not rel.startswith("Drums/Snares-Claps/"):
        return False
    b = _bn(rel)
    if "drum loop" in b:
        return True
    return " bpm " in b and "loop" in b


def _collect(db: Dict) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for rel, entry in db.items():
        if not _is_misfiled_snare_folder_loop(rel):
            continue
        tc = (entry.get("type_code") or "").upper()
        if tc != "BRK":
            out.append((rel, "snares_folder_drum_loop_to_brk"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Round 3: snare-folder drum loops -> BRK")
    ap.add_argument("--apply", action="store_true", help="Write changes")
    args = ap.parse_args()

    db = load_tag_db(TAGS_FILE)
    if not isinstance(db, dict) or not db:
        print("ERROR: empty tag database")
        return 1

    plan = _collect(db)
    print(f"Planned patches: {len(plan)}")
    if not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
        return 0

    updated = dict(db)
    n = 0
    for rel, _note in plan:
        entry = updated.get(rel)
        if not isinstance(entry, dict):
            continue
        updated[rel] = _patch(entry, rel, "BRK")
        n += 1

    save_tag_db(TAGS_FILE, updated)
    print(f"\nWrote {n} rows as BRK / loop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
