#!/usr/bin/env python3
"""Round 2 bulk tag fixes: vocal drum loops, mis-typed loops, kicks/bass/hat edge cases.

Run:  .venv/bin/python scripts/muscle_tags_round2.py --apply
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

# Drum loops with clear vocal content (basename, lowercased substrings).
_VOCAL_LOOP_KEYS = (
    "vocal",
    "vocals",
    "lead vocal",
    "choir",
    "chant",
    "shout",
    "acapella",
    "vocoder",
    "vox",
    "break vocal",
    "sing a simple song",  # classic break with vox
)


def _bn(rel: str) -> str:
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
    elif new_type == "SNR":
        e["instrument_hint"] = e.get("instrument_hint") or "snare"
    elif new_type == "KIK":
        e["instrument_hint"] = e.get("instrument_hint") or "kick"
    return e


def _collect(db: Dict) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []

    for rel, entry in db.items():
        tc = (entry.get("type_code") or "").upper()
        b = _bn(rel)

        # Full drum loops mis-tagged as one-shots / hats / cymbals.
        if rel.startswith("Drums/Drum-Loops/") and tc in {"CLP", "CYM", "DRM", "RIM"}:
            out.append((rel, "BRK", "drum_loop_wrong_drum_type"))

        # Vocal musical content in drum loop pack -> VOX (keep loop playability).
        if rel.startswith("Drums/Drum-Loops/") and tc == "BRK":
            if any(k in b for k in _VOCAL_LOOP_KEYS):
                out.append((rel, "VOX", "drum_loop_vocal_content"))

        # Kick one-shot filed as break.
        if rel.startswith("Drums/Kicks/") and tc == "BRK":
            out.append((rel, "KIK", "kicks_folder_was_brk"))

        # Bass folder percussion hit -> bass.
        if rel.startswith("Melodic/Bass/") and tc == "PRC":
            out.append((rel, "BAS", "bass_folder_was_prc"))

        # Obvious vocal in hat pack.
        if rel.startswith("Drums/Hi-Hats/") and tc == "HAT":
            if "vocal" in b or "vox" in b or "voice" in b or "choir" in b:
                out.append((rel, "VOX", "hihat_pack_vocal"))

        # Snare one-shot tagged as break.
        if rel.startswith("Drums/Snares-Claps/") and tc == "BRK":
            out.append((rel, "SNR", "snares_folder_was_brk"))

        # Chops with no type_code yet.
        if rel.startswith("Vocals/Chops/") and not tc:
            out.append((rel, "VOX", "vocals_chops_missing_type"))

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Round 2 muscular tag DB corrections")
    ap.add_argument("--apply", action="store_true", help="Write changes")
    args = ap.parse_args()

    db = load_tag_db(TAGS_FILE)
    if not isinstance(db, dict) or not db:
        print("ERROR: empty tag database")
        return 1

    plan = _collect(db)
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
    type_changes = 0
    for rel, new_type, _note in unique:
        entry = updated.get(rel)
        if not isinstance(entry, dict):
            continue
        patched = _patch(entry, rel, new_type)
        if patched.get("type_code") != entry.get("type_code"):
            type_changes += 1
        updated[rel] = patched

    save_tag_db(TAGS_FILE, updated)
    print(f"\nWrote {len(unique)} rows ({type_changes} type_code changes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
