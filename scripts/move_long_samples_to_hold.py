#!/usr/bin/env python3
"""Move long audio files into _LONG-HOLD/ (mirrored subpaths).

Long raw material is excluded from fetch scoring, daily bank, bulk tag_library,
and bulk smart_retag walks. Tag or smart_retag explicitly on that folder when
you are ready.

Usage:
    python scripts/move_long_samples_to_hold.py              # dry-run (default)
    python scripts/move_long_samples_to_hold.py --apply      # move files + update tag DB

Env:
    SP404_LONG_HOLD_MIN_SECONDS — threshold (default 120; also in jambox_config)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import (  # noqa: E402
    LONG_HOLD_DIRNAME,
    is_long_hold_rel_path,
    load_settings_for_script,
    load_tag_db,
    save_tag_db,
)
from tag_library import AUDIO_EXTS, get_duration  # noqa: E402

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]

SKIP_DIRS = {
    "_RAW-DOWNLOADS",
    "_GOLD",
    "_DUPES",
    "_QUARANTINE",
    "Stems",
    LONG_HOLD_DIRNAME,
}


def _duration_for_file(rel_path: str, full_path: str, db: dict) -> float:
    entry = db.get(rel_path) or {}
    raw = entry.get("duration")
    if raw is not None:
        try:
            d = float(raw)
            if d > 0:
                return d
        except (TypeError, ValueError):
            pass
    return float(get_duration(full_path) or 0.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Move long samples into _LONG-HOLD/")
    parser.add_argument(
        "--min-seconds",
        type=float,
        default=float(SETTINGS.get("LONG_HOLD_MIN_SECONDS", 120)),
        help="Move files at or above this duration (default: settings / SP404_LONG_HOLD_MIN_SECONDS)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move files and rewrite tag DB keys (default is dry-run)",
    )
    args = parser.parse_args()
    min_sec = args.min_seconds
    if min_sec <= 0:
        print("--min-seconds must be positive", file=sys.stderr)
        return 2

    db = load_tag_db(TAGS_FILE)
    planned = []

    for root, dirs, files in os.walk(LIBRARY):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in AUDIO_EXTS:
                continue
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, LIBRARY)
            if os.sep != "/":
                rel_path = rel_path.replace(os.sep, "/")
            if is_long_hold_rel_path(rel_path):
                continue
            dur = _duration_for_file(rel_path, full_path, db)
            if dur < min_sec:
                continue
            dest_rel = f"{LONG_HOLD_DIRNAME}/{rel_path}"
            planned.append((full_path, rel_path, dest_rel, dur))

    planned.sort(key=lambda x: -x[3])
    print(f"Library: {LIBRARY}")
    print(f"Threshold: >= {min_sec:.1f}s  |  candidates: {len(planned)}")
    for full_path, rel_path, dest_rel, dur in planned[:200]:
        print(f"  {dur:8.1f}s  {rel_path}  ->  {dest_rel}")
    if len(planned) > 200:
        print(f"  ... and {len(planned) - 200} more")

    if not args.apply:
        print("\nDry-run only. Pass --apply to move files and update the tag database.")
        return 0

    moved = 0
    skipped = 0
    for full_path, rel_path, dest_rel, dur in planned:
        dest_abs = os.path.join(LIBRARY, dest_rel)
        if os.path.exists(dest_abs):
            print(f"SKIP (exists): {dest_rel}")
            skipped += 1
            continue
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        try:
            shutil.move(full_path, dest_abs)
        except OSError as exc:
            print(f"ERROR move {rel_path}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        entry = db.pop(rel_path, None)
        if entry is not None:
            entry["path"] = dest_rel
            db[dest_rel] = entry
        else:
            db[dest_rel] = {"path": dest_rel, "duration": dur, "tag_source": "move_long_hold"}
        moved += 1

    save_tag_db(TAGS_FILE, db)
    print(f"\nDone. Moved: {moved}  Skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
