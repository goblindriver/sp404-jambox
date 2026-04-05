#!/usr/bin/env python3
"""Deep sample audit: one tagged file at a time, tags vs stored audio features.

Use this (or ask the coding agent to run it) when you care about *accuracy*, not
throughput. Compares smart_retag outputs to the same feature vector the LLM saw,
plus simple spectral heuristics from the smart_retag prompt.

Examples:
  .venv/bin/python scripts/audit_tag_vs_features.py
  .venv/bin/python scripts/audit_tag_vs_features.py --n 3 --seed 7
  .venv/bin/python scripts/audit_tag_vs_features.py --rel "Drums/Kicks/foo.flac"
"""

from __future__ import annotations

import argparse
import os
import random
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from jambox_config import load_settings_for_script, load_tag_db

SETTINGS = load_settings_for_script(__file__)
TAGS_FILE = SETTINGS["TAGS_FILE"]
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]


def _fmt_features(feat: dict) -> list[str]:
    if not feat:
        return ["  (no stored features — run smart_retag on this file first)"]
    order = [
        ("duration", "s", "%.3f"),
        ("spectral_centroid", "Hz", "%.0f"),
        ("spectral_rolloff", "Hz", "%.0f"),
        ("zero_crossing_rate", "", "%.4f"),
        ("onset_strength", "", "%.2f"),
        ("onset_count", "", "%d"),
        ("rms_peak", "", "%.4f"),
        ("rms_mean", "", "%.4f"),
        ("attack_position", "", "%.2f"),
    ]
    lines = []
    for key, unit, fmt in order:
        if key not in feat:
            continue
        val = feat[key]
        u = (" " + unit) if unit else ""
        lines.append("  %s: %s%s" % (key, fmt % val if isinstance(val, (int, float)) else val, u))
    if feat.get("mfcc"):
        lines.append("  mfcc (mean): %s" % feat["mfcc"][:6])
    if feat.get("chroma"):
        lines.append("  chroma (mean, 12): %s" % feat["chroma"])
    return lines


def _consistency_notes(type_code: str, feat: dict, rel: str, entry: dict) -> list[str]:
    """Heuristic flags — suggestions to listen, not ground truth."""
    notes = []
    tc = (type_code or "").upper()

    if entry.get("tag_source") == "smart_retag_v1":
        no_vibe = not entry.get("vibe")
        no_tex = not entry.get("texture")
        no_gen = not entry.get("genre")
        no_sonic = not (entry.get("sonic_description") or "").strip()
        no_q = entry.get("quality_score") is None
        if no_vibe and no_tex and no_gen and no_sonic:
            notes.append(
                "Row is smart_retag_v1 but vibe/texture/genre/sonic are empty — "
                "fetch keywords will be weak; likely LLM failure or validation stripped everything."
            )
        elif no_sonic and no_q:
            notes.append(
                "No sonic_description and no quality_score — incomplete retag output; "
                "spot-listen and consider re-run with a healthy LLM."
            )
    sc = feat.get("spectral_centroid")
    oc = feat.get("onset_count")
    dur = feat.get("duration")

    low = sc is not None and sc < 1800
    high = sc is not None and sc > 3800

    if tc == "KIK" and high:
        notes.append("KIK tagged but centroid is high (%.0f Hz) — listen: could be snare/hat/perc." % sc)
    if tc == "HAT" and sc is not None and sc < 3000:
        notes.append("HAT tagged but centroid is low (%.0f Hz) — listen: might not be bright hats." % sc)
    if tc == "BAS" and high:
        notes.append("BAS tagged but centroid is high — listen: might be mid melodic, not bass.")
    if tc == "BRK" and dur and dur > 2 and oc is not None and oc < 4:
        notes.append("BRK tagged but few onsets (n=%d) on %.1fs audio — listen: might be one-shot or pad." % (oc, dur))
    if tc == "PAD" and oc is not None and oc > 12:
        notes.append("PAD tagged but many onsets (%d) — listen: might be rhythmic loop." % oc)
    if tc in ("SNR", "CLP", "RIM") and low:
        notes.append("%s tagged but centroid is very low — listen: could be misclassified drum type." % tc)

    fn = os.path.basename(rel).lower()
    hint_map = [
        ("kick", "KIK"),
        ("kik", "KIK"),
        ("snare", "SNR"),
        ("snr", "SNR"),
        ("hat", "HAT"),
        ("clap", "CLP"),
        ("vox", "VOX"),
        ("vocal", "VOX"),
        ("bass", "BAS"),
        ("808", "BAS"),
    ]
    for needle, expect in hint_map:
        if needle in fn and tc and tc != expect:
            notes.append('Filename contains "%s" but type_code is %s — filename may mislead the LLM; trust ears.' % (needle, tc))
            break

    if not notes:
        notes.append("No heuristic red flags vs stored features (still listen once).")
    return notes


def _print_audit(rel: str, entry: dict, full_path: str) -> None:
    feat = entry.get("features") or {}
    tc = entry.get("type_code", "?")

    print("=" * 72)
    print("FILE")
    print("  rel:   %s" % rel)
    print("  path:  %s" % full_path)
    print("  exists:%s" % os.path.isfile(full_path))

    print("\nTAGS (what fetch / UI use)")
    print("  tag_source: %s" % entry.get("tag_source", "?"))
    print("  type_code:  %s" % tc)
    print("  playability:%s" % entry.get("playability", "—"))
    print("  energy:     %s" % entry.get("energy", "—"))
    print("  quality:    %s" % entry.get("quality_score", "—"))
    print("  vibe:       %s" % entry.get("vibe"))
    print("  texture:    %s" % entry.get("texture"))
    print("  genre:      %s" % entry.get("genre"))
    ih = entry.get("instrument_hint")
    if ih:
        print("  instrument: %s" % ih)
    desc = entry.get("sonic_description") or ""
    print("  sonic:      %s" % (desc[:500] + ("…" if len(desc) > 500 else "")))

    print("\nSTORED FEATURES (what smart_retag sent to the LLM)")
    for line in _fmt_features(feat):
        print(line)

    print("\nCONSISTENCY (heuristic — verify by listening)")
    for line in _consistency_notes(tc, feat, rel, entry):
        print("  • %s" % line)

    print("=" * 72)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit one tagged sample: tags vs stored features")
    parser.add_argument("--n", type=int, default=1, help="How many random samples")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    parser.add_argument("--rel", help="Audit this library-relative path only")
    parser.add_argument(
        "--source",
        default="smart_retag_v1",
        help="tag_source filter, or 'any'",
    )
    parser.add_argument(
        "--require-features",
        action="store_true",
        help="Only pick entries that already have a stored features dict",
    )
    args = parser.parse_args()

    db = load_tag_db(TAGS_FILE)
    if args.rel:
        e = db.get(args.rel)
        if not e:
            print("No tag entry for rel path: %s" % args.rel)
            return 1
        full = os.path.join(LIBRARY, args.rel)
        _print_audit(args.rel, e, full)
        return 0

    pool = []
    for rel, e in db.items():
        if args.source != "any" and e.get("tag_source") != args.source:
            continue
        if args.require_features and not e.get("features"):
            continue
        pool.append((rel, e))

    if not pool:
        print("No entries match filters (tags: %s)." % TAGS_FILE)
        return 1

    if args.seed is not None:
        random.seed(args.seed)
    k = min(args.n, len(pool))
    sample = random.sample(pool, k) if k < len(pool) else list(pool)

    print(
        "Tag DB: %s | pool=%d | showing %d sample(s)\n"
        % (TAGS_FILE, len(pool), len(sample))
    )
    for rel, e in sample:
        full = os.path.join(LIBRARY, rel) if not os.path.isabs(rel) else rel
        _print_audit(rel, e, full)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
