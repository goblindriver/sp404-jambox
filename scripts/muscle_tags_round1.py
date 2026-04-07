#!/usr/bin/env python3
"""One-shot bulk type_code / playability fixes (Round 1).

Run from repo:  .venv/bin/python scripts/muscle_tags_round1.py --apply

Rules (high confidence only):
  - Drums/Drum-Loops + basename starting with HH_  -> BRK / loop
  - Loops/Instrument-Loops + basename starting HH_ -> BRK / loop
  - Drums/Snares-Claps + "clap" in basename       -> CLP / one-shot
  - Drums/Drum-Loops + was KIK or SNR             -> BRK / loop (full loops, not one-shots)
  - Melodic/Bass + was BRK                        -> BAS / loop
  - Vocals/Chops + was BRK                        -> VOX / chop-ready
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


def _basename_lower(rel: str) -> str:
    return os.path.basename(rel).lower()


def _patch(
    entry: Dict,
    rel_path: str,
    new_type: str,
    playability_override: str | None = None,
) -> Dict:
    cur_play = str(entry.get("playability") or "")
    play = playability_override or _expected_playability(new_type, rel_path, cur_play)
    e = dict(entry)
    e["type_code"] = new_type
    e["playability"] = play
    e["tags"] = _normalize_tags(e, new_type, play)
    if new_type == "VOX":
        e["instrument_hint"] = e.get("instrument_hint") or "vocals"
        e["genre"] = sorted(set(e.get("genre") or []) | {"hiphop"})
    elif new_type == "BAS":
        e["instrument_hint"] = e.get("instrument_hint") or "bass"
    elif new_type == "CLP":
        e["instrument_hint"] = e.get("instrument_hint") or "clap"
    return e


def _collect_round1(db: Dict) -> List[Tuple[str, str, str]]:
    """Return list of (rel_path, new_type_code, note)."""
    out: List[Tuple[str, str, str]] = []

    for rel, entry in db.items():
        tc = (entry.get("type_code") or "").upper()

        if rel.startswith("Drums/Drum-Loops/") and _basename_lower(rel).startswith("hh_"):
            if tc != "BRK":
                out.append((rel, "BRK", "drum_loop_hh_prefix"))

        if rel.startswith("Loops/Instrument-Loops/") and _basename_lower(rel).startswith("hh_"):
            if tc != "BRK":
                out.append((rel, "BRK", "instrument_loop_hh_prefix"))

        if rel.startswith("Drums/Snares-Claps/") and "clap" in _basename_lower(rel):
            if tc != "CLP":
                out.append((rel, "CLP", "snares_folder_clap_filename"))

        if rel.startswith("Drums/Drum-Loops/") and tc in {"KIK", "SNR"}:
            out.append((rel, "BRK", "drum_loop_was_kik_or_snr"))

        if rel.startswith("Melodic/Bass/") and tc == "BRK":
            out.append((rel, "BAS", "bass_folder_was_brk"))

        if rel.startswith("Vocals/Chops/") and tc == "BRK":
            out.append((rel, "VOX", "vocals_chops_was_brk"))

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Round 1 muscular tag DB corrections")
    ap.add_argument("--apply", action="store_true", help="Write changes via save_tag_db")
    args = ap.parse_args()

    db = load_tag_db(TAGS_FILE)
    if not isinstance(db, dict) or not db:
        print("ERROR: empty tag database")
        return 1

    plan = _collect_round1(db)
    by_rule: Dict[str, int] = {}
    for _, _, note in plan:
        by_rule[note] = by_rule.get(note, 0) + 1

    print(f"Planned patches: {len(plan)}")
    for note, n in sorted(by_rule.items(), key=lambda x: -x[1]):
        print(f"  {n:4}  {note}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
        return 0

    seen: set[str] = set()
    unique: List[Tuple[str, str, str]] = []
    for row in plan:
        if row[0] in seen:
            continue
        seen.add(row[0])
        unique.append(row)

    updated = dict(db)
    changed = 0
    for rel, new_type, _note in unique:
        entry = updated.get(rel)
        if not isinstance(entry, dict):
            continue
        patched = _patch(entry, rel, new_type)
        if patched.get("type_code") != entry.get("type_code") or patched.get("playability") != entry.get("playability"):
            changed += 1
        updated[rel] = patched

    save_tag_db(TAGS_FILE, updated)
    print(f"\nWrote {len(unique)} rows touched ({changed} with type/playability change) to tag database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
