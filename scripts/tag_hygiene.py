#!/usr/bin/env python3
"""Folder-aware tag hygiene scan and safe fixer.

Workflow:
  1) scan: detect high-confidence folder/type mismatches
  2) apply: rewrite only safe fixes (explicit rule-based mappings)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from jambox_config import load_settings_for_script, load_tag_db, save_tag_db

SETTINGS = load_settings_for_script(__file__)
TAGS_FILE = SETTINGS["TAGS_FILE"]
REPO_DIR = SETTINGS["REPO_DIR"]
DEFAULT_OUT = os.path.join(REPO_DIR, "data", "audit_reports", "tag_hygiene_latest.json")


def _safe_split_tokens(rel_path: str) -> set:
    return set(re.findall(r"[a-z0-9]+", rel_path.lower()))


def _expect_type(rel_path: str) -> Tuple[Optional[str], str]:
    """Return expected type_code and confidence reason for folder layout."""
    if rel_path.startswith("Vocals/"):
        return "VOX", "vocals_folder"
    if rel_path.startswith("Drums/Kicks/"):
        return "KIK", "drums_kicks_folder"
    if rel_path.startswith("Drums/Snares-Claps/"):
        # Basename substring checks: tokenization misses Clap01, Snr02, etc.
        base = os.path.basename(rel_path)
        bl = base.lower()
        # Full breaks sometimes land in Snares-Claps by pack layout.
        if "drum loop" in bl or (" bpm " in bl and "loop" in bl):
            return "BRK", "drums_snares_misfiled_loop"
        if "clap" in bl:
            return "CLP", "drums_snares_clap_filename"
        if "snare" in bl or "snr" in bl or "rimshot" in bl:
            return "SNR", "drums_snares_snare_filename"
        return "SNR", "drums_snares_default"
    if rel_path.startswith("Drums/Hi-Hats/"):
        tokens = _safe_split_tokens(rel_path)
        # Do not force hi-hat class for clearly vocal one-shots.
        if "vocal" in tokens or "vocals" in tokens or "vox" in tokens:
            return "VOX", "drums_hihats_vocal_exception"
        return "HAT", "drums_hihats_folder"
    if rel_path.startswith("Drums/Drum-Loops/"):
        tokens = _safe_split_tokens(rel_path)
        bl = os.path.basename(rel_path).lower()
        if "vocal" in tokens or "vocals" in tokens or "vox" in tokens:
            return "VOX", "drums_loops_vocal_exception"
        if any(
            x in bl
            for x in ("vocal", "vocals", "vox", "choir", "chant", "acapella", "vocoder")
        ):
            return "VOX", "drums_loops_vocal_filename"
        # Word "sing", not substring inside "rising", "processing", etc.
        if re.search(r"(?<![a-z])sing(ing)?(?![a-z])", bl):
            return "VOX", "drums_loops_vocal_filename"
        return "BRK", "drums_drumloops_folder"
    if rel_path.startswith("Melodic/Bass/"):
        return "BAS", "melodic_bass_folder"
    return None, ""


def _expected_playability(expected_type: str, rel_path: str, current: str) -> str:
    if expected_type in {"KIK", "SNR", "CLP", "HAT", "SFX", "FX"}:
        return "one-shot"
    if expected_type in {"BAS", "BRK", "SYN", "KEY", "PAD", "HRN", "WND", "GTR", "STR"}:
        return "loop"
    if expected_type == "VOX":
        if rel_path.startswith("Vocals/Chops/"):
            return "chop-ready"
        return current or "one-shot"
    return current or "one-shot"


def _normalize_tags(entry: Dict, expected_type: str, playability: str) -> List[str]:
    tags = set(str(tag).lower() for tag in entry.get("tags", []) if isinstance(tag, str))
    for stale in ("kik", "snr", "clp", "hat", "brk", "bas", "vox", "one-shot", "loop", "chop-ready"):
        tags.discard(stale)
    tags.add(expected_type.lower())
    tags.add(playability.lower())
    return sorted(tags)


def _scan(db: Dict) -> List[Dict]:
    findings: List[Dict] = []
    for rel_path, entry in db.items():
        expected_type, reason = _expect_type(rel_path)
        if not expected_type:
            continue
        actual_type = (entry.get("type_code") or "").upper()
        if actual_type == expected_type:
            continue
        findings.append(
            {
                "path": rel_path,
                "expected_type": expected_type,
                "actual_type": actual_type or None,
                "reason": reason,
                "current_playability": entry.get("playability"),
            }
        )
    return findings


def _apply(db: Dict, findings: List[Dict], limit: int = 0) -> Tuple[Dict, int]:
    updated = dict(db)
    changed = 0
    for finding in findings:
        if limit and changed >= limit:
            break
        rel_path = finding["path"]
        entry = dict(updated.get(rel_path, {}))
        expected_type = finding["expected_type"]
        playability = _expected_playability(expected_type, rel_path, str(entry.get("playability") or ""))

        entry["type_code"] = expected_type
        entry["playability"] = playability
        entry["tags"] = _normalize_tags(entry, expected_type, playability)

        if expected_type == "VOX":
            entry["instrument_hint"] = entry.get("instrument_hint") or "vocals"
            entry["genre"] = sorted(set(entry.get("genre") or []) | {"hiphop"})
        elif expected_type == "BAS":
            entry["instrument_hint"] = entry.get("instrument_hint") or "bass"
        elif expected_type in {"KIK", "SNR", "CLP", "HAT"}:
            entry["instrument_hint"] = entry.get("instrument_hint") or expected_type.lower()

        updated[rel_path] = entry
        changed += 1
    return updated, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Folder-aware tag hygiene detector/fixer")
    parser.add_argument("--apply", action="store_true", help="Apply safe fixes")
    parser.add_argument("--limit", type=int, default=0, help="Max number of fixes to apply (0 = all)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Scan/fix report output path")
    args = parser.parse_args()

    db = load_tag_db(TAGS_FILE)
    if not isinstance(db, dict) or not db:
        print("ERROR: no tag database loaded.")
        return 1

    findings = _scan(db)
    changed = 0
    if args.apply and findings:
        db, changed = _apply(db, findings, limit=max(0, args.limit))
        if changed:
            save_tag_db(TAGS_FILE, db)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "apply_mode": bool(args.apply),
        "findings_count": len(findings),
        "changed_count": changed,
        "findings": findings,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)

    print(f"[HYGIENE] findings={len(findings)} changed={changed}")
    print(f"[HYGIENE] report={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
