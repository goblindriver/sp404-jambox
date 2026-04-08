#!/usr/bin/env python3
"""Consolidated bulk type_code corrections for the sample library.

Replaces muscle_tags_round1 through round4 with a single rule-driven script.
Rules are ordered by specificity (most specific first). Each file matches
at most one rule (first match wins).

Usage:
    python scripts/muscle_tags.py                 # dry-run all rounds
    python scripts/muscle_tags.py --apply         # apply all rounds
    python scripts/muscle_tags.py --round 1       # dry-run round 1 only
    python scripts/muscle_tags.py --round 1 --apply
"""
import argparse
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from jambox_config import load_settings_for_script, load_tag_db, save_tag_db
from tag_hygiene import _expected_playability, _normalize_tags

SETTINGS = load_settings_for_script(__file__)
TAGS_FILE = SETTINGS["TAGS_FILE"]

# ── Vocal keyword detection ──
_VOCAL_KEYWORDS = {
    "vocal", "vocals", "lead vocal", "choir", "chant", "shout",
    "acapella", "vocoder", "vox", "break vocal", "sing a simple song",
}
_VOCAL_SHORT = {"vocal", "vox", "voice", "choir"}

_VOCAL_RE = re.compile(
    "|".join(re.escape(k) for k in sorted(_VOCAL_KEYWORDS, key=len, reverse=True)),
    re.IGNORECASE,
)
_VOCAL_SHORT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in _VOCAL_SHORT) + r")\b",
    re.IGNORECASE,
)
_DRUM_LOOP_RE = re.compile(r"drum loop|(?:\bbpm\b.*\bloop\b)", re.IGNORECASE)

# ── Instrument hint defaults per type code ──
_HINT_DEFAULTS = {
    "VOX": "vocals",
    "BAS": "bass",
    "CLP": "clap",
    "KIK": "kick",
    "SNR": "snare",
}

# ══════════════════════════════════════════════════════════════
# Rule definitions — ordered by specificity within each round
# ══════════════════════════════════════════════════════════════

def _rules():
    """Return all rules grouped by round number."""
    return {
        1: [
            {
                "id": "drum_loop_hh_prefix",
                "path_prefix": "Drums/Drum-Loops/",
                "basename_fn": lambda bn: bn.lower().startswith("hh_"),
                "tc_cond": lambda tc: tc != "BRK",
                "new_tc": "BRK",
            },
            {
                "id": "instrument_loop_hh_prefix",
                "path_prefix": "Loops/Instrument-Loops/",
                "basename_fn": lambda bn: bn.lower().startswith("hh_"),
                "tc_cond": lambda tc: tc != "BRK",
                "new_tc": "BRK",
            },
            {
                "id": "snares_folder_clap_filename",
                "path_prefix": "Drums/Snares-Claps/",
                "basename_fn": lambda bn: "clap" in bn.lower(),
                "tc_cond": lambda tc: tc != "CLP",
                "new_tc": "CLP",
            },
            {
                "id": "drum_loop_was_kik_or_snr",
                "path_prefix": "Drums/Drum-Loops/",
                "tc_cond": lambda tc: tc in ("KIK", "SNR"),
                "new_tc": "BRK",
            },
            {
                "id": "bass_folder_was_brk",
                "path_prefix": "Melodic/Bass/",
                "tc_cond": lambda tc: tc == "BRK",
                "new_tc": "BAS",
            },
            {
                "id": "vocals_chops_was_brk",
                "path_prefix": "Vocals/Chops/",
                "tc_cond": lambda tc: tc == "BRK",
                "new_tc": "VOX",
                "extra_genre": "hiphop",
            },
        ],
        2: [
            {
                "id": "drum_loop_vocal_content",
                "path_prefix": "Drums/Drum-Loops/",
                "basename_fn": lambda bn: bool(_VOCAL_RE.search(bn)),
                "tc_cond": lambda tc: tc == "BRK",
                "new_tc": "VOX",
                "extra_genre": "hiphop",
            },
            {
                "id": "hihat_pack_vocal",
                "path_prefix": "Drums/Hi-Hats/",
                "basename_fn": lambda bn: bool(_VOCAL_SHORT_RE.search(bn)),
                "tc_cond": lambda tc: tc == "HAT",
                "new_tc": "VOX",
                "extra_genre": "hiphop",
            },
            {
                "id": "drum_loop_wrong_drum_type",
                "path_prefix": "Drums/Drum-Loops/",
                "tc_cond": lambda tc: tc in ("CLP", "CYM", "DRM", "RIM"),
                "new_tc": "BRK",
            },
            {
                "id": "kicks_folder_was_brk",
                "path_prefix": "Drums/Kicks/",
                "tc_cond": lambda tc: tc == "BRK",
                "new_tc": "KIK",
            },
            {
                "id": "bass_folder_was_prc",
                "path_prefix": "Melodic/Bass/",
                "tc_cond": lambda tc: tc == "PRC",
                "new_tc": "BAS",
            },
            {
                "id": "snares_folder_was_brk",
                "path_prefix": "Drums/Snares-Claps/",
                "tc_cond": lambda tc: tc == "BRK",
                "new_tc": "SNR",
            },
            {
                "id": "vocals_chops_missing_type",
                "path_prefix": "Vocals/Chops/",
                "tc_cond": lambda tc: not tc or not tc.strip(),
                "new_tc": "VOX",
                "extra_genre": "hiphop",
            },
        ],
        3: [
            {
                "id": "snares_folder_drum_loop_to_brk",
                "path_prefix": "Drums/Snares-Claps/",
                "basename_fn": lambda bn: bool(_DRUM_LOOP_RE.search(bn)),
                "tc_cond": lambda tc: tc != "BRK",
                "new_tc": "BRK",
            },
        ],
        4: [
            {
                "id": "drum_loop_missing_type",
                "path_prefix": "Drums/Drum-Loops/",
                "tc_cond": lambda tc: not tc or not tc.strip(),
                "new_tc": "BRK",
                "set_source": "dug",
            },
        ],
    }


# ══════════════════════════════════════════════════════════════
# Rule application engine
# ══════════════════════════════════════════════════════════════

def _match_rule(rule, rel_path, basename, entry):
    """Check if a rule matches this file."""
    prefix = rule.get("path_prefix")
    if prefix and not rel_path.startswith(prefix):
        return False

    bn_fn = rule.get("basename_fn")
    if bn_fn and not bn_fn(basename):
        return False

    tc = (entry.get("type_code") or "").strip()
    tc_cond = rule.get("tc_cond")
    if tc_cond and not tc_cond(tc):
        return False

    return True


def _apply_rule(rule, rel_path, entry):
    """Apply a rule to an entry. Returns (patched_entry, change_description) or None."""
    new_tc = rule["new_tc"]
    old_tc = (entry.get("type_code") or "").strip()
    if old_tc == new_tc:
        return None  # No actual change needed

    patched = dict(entry)
    patched["type_code"] = new_tc

    # Playability from tag_hygiene
    cur_play = patched.get("playability", "")
    new_play = _expected_playability(new_tc, rel_path, cur_play)
    if new_play:
        patched["playability"] = new_play

    # Instrument hint defaults
    hint = _HINT_DEFAULTS.get(new_tc)
    if hint and not (patched.get("instrument_hint") or "").strip():
        patched["instrument_hint"] = hint

    # Extra genre
    extra_genre = rule.get("extra_genre")
    if extra_genre:
        genres = patched.get("genre", [])
        if not isinstance(genres, list):
            genres = []
        if extra_genre not in genres:
            genres = list(genres) + [extra_genre]
            patched["genre"] = genres

    # Source override
    set_source = rule.get("set_source")
    if set_source and not (patched.get("source") or "").strip():
        patched["source"] = set_source

    # Ensure tags list exists
    if not isinstance(patched.get("tags"), list):
        patched["tags"] = []

    # Normalize tags set
    _normalize_tags(patched)

    desc = f"{old_tc or '(empty)'} -> {new_tc}"
    return patched, desc


def apply_rules(tag_db, rounds=None, apply=False, verbose=True):
    """Run rules against the tag database.

    Args:
        tag_db: dict mapping rel_path -> entry
        rounds: list of round numbers to run, or None for all
        apply: if True, mutate tag_db in place
        verbose: print each change

    Returns: list of (rel_path, rule_id, change_description) for all matches
    """
    all_rules = _rules()
    if rounds:
        selected = []
        for r in sorted(rounds):
            selected.extend(all_rules.get(r, []))
    else:
        selected = []
        for r in sorted(all_rules):
            selected.extend(all_rules[r])

    changes = []
    seen = set()

    for rel_path, entry in sorted(tag_db.items()):
        if rel_path in seen:
            continue
        basename = os.path.basename(rel_path)

        for rule in selected:
            if _match_rule(rule, rel_path, basename, entry):
                result = _apply_rule(rule, rel_path, entry)
                if result:
                    patched, desc = result
                    changes.append((rel_path, rule["id"], desc))
                    if verbose:
                        print(f"  [{rule['id']}] {desc}: {rel_path}")
                    if apply:
                        tag_db[rel_path] = patched
                    seen.add(rel_path)
                break  # First match wins

    return changes


def main():
    parser = argparse.ArgumentParser(description="Bulk type_code corrections")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--round", type=int, action="append", dest="rounds",
                        help="Run specific round(s) only (1-4). Can repeat.")
    args = parser.parse_args()

    tag_db = load_tag_db(TAGS_FILE)
    if not tag_db:
        print("ERROR: No tag database found.")
        sys.exit(1)

    mode = "APPLYING" if args.apply else "DRY RUN"
    rounds_label = f"rounds {args.rounds}" if args.rounds else "all rounds"
    print(f"\n=== Muscle Tags ({mode}, {rounds_label}) ===")
    print(f"  Library: {len(tag_db)} files\n")

    changes = apply_rules(tag_db, rounds=args.rounds, apply=args.apply)

    print(f"\n  Total changes: {len(changes)}")
    if changes and not args.apply:
        print("  (dry run — use --apply to write)")

    if args.apply and changes:
        save_tag_db(TAGS_FILE, tag_db)
        print("  Saved to tag database.")


if __name__ == "__main__":
    main()
