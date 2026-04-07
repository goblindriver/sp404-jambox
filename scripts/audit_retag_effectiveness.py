#!/usr/bin/env python3
"""Audit smart_retag vs the rest of the tag database.

Reports coverage, vocabulary violations, and cross-field mismatches.
Does not modify the database.

  .venv/bin/python scripts/audit_retag_effectiveness.py
  .venv/bin/python scripts/audit_retag_effectiveness.py --json data/audit_reports/retag_audit.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from jambox_config import is_excluded_rel_path, load_settings_for_script, load_tag_db
from tag_vocab import GENRES, TEXTURES, TYPE_CODES, VIBES

SETTINGS = load_settings_for_script(__file__)
TAGS_FILE = SETTINGS["TAGS_FILE"]
REPO_DIR = os.path.dirname(SCRIPT_DIR)

try:
    import tag_hygiene as th
except ImportError:
    th = None


def _norm_list(val: Any) -> List[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [val] if val.strip() else []
    if isinstance(val, list):
        return [str(x) for x in val if x]
    return []


def _invalid_vocab(items: List[str], allowed: Set[str]) -> List[str]:
    out = []
    for x in items:
        v = str(x).strip().lower()
        if v and v not in allowed:
            out.append(str(x))
    return out


# instrument_hint phrases that conflict with type_code (substring match, lower)
_TYPE_HINT_CONFLICTS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("KIK", ("snare", "clap", "hat", "cymbal", "vocal", "shaker", "percussion-only")),
    ("SNR", ("kick", "bass drum", "bd ", "clap", "hat", "vocal")),
    ("HAT", ("kick", "snare", "vocal", "bass")),
    ("CLP", ("kick", "snare", "hat", "vocal")),
    ("BAS", ("snare", "kick", "vocal", "hat")),
    ("VOX", ("kick", "snare", "808", "bass synth")),
)


def _hint_conflicts_type(type_code: str, hint: str) -> bool:
    if not type_code or not hint:
        return False
    tc = type_code.upper()
    h = hint.lower()
    for t, bad_subs in _TYPE_HINT_CONFLICTS:
        if tc != t:
            continue
        return any(s in h for s in bad_subs)
    return False


def audit(db: Dict[str, Dict]) -> Dict[str, Any]:
    rows = [(rel, e) for rel, e in db.items() if not is_excluded_rel_path(rel)]
    total = len(rows)
    by_source: Counter = Counter()
    smart_v1 = 0
    smart_v2 = 0
    other_source = 0
    no_source = 0

    # smart_retag_v1 completeness vs its own _entry_needs_smart_retag criteria
    v1_missing_sonic = 0
    v1_missing_qs = 0
    v1_missing_dims = 0  # no vibe AND no texture AND no genre
    v1_complete_dims = 0

    # dimensional coverage (whole library)
    has_vibe = has_texture = has_genre = has_energy = 0
    has_features = has_discogs = 0
    has_sonic = has_qs = 0

    invalid_vibe: Counter = Counter()
    invalid_texture: Counter = Counter()
    invalid_genre: Counter = Counter()
    hint_vs_type: List[str] = []

    # sonic_description keyword vs type_code (lightweight sanity)
    sonic_says_kick_type_not = 0
    sonic_says_snare_type_not = 0
    samples_sonic_mismatch: List[Dict[str, str]] = []

    kick_w = re.compile(r"\bkick\b|\b808\b|bass drum|bd\b", re.I)
    snare_w = re.compile(r"\bsnare\b|\brim\b|\brimshot\b", re.I)

    for rel, e in rows:
        src = (e.get("tag_source") or "").strip() or None
        if not src:
            no_source += 1
        else:
            by_source[src] += 1
            if src == "smart_retag_v1":
                smart_v1 += 1
            elif src == "smart_retag_v2_revibe":
                smart_v2 += 1
            else:
                other_source += 1

        if _norm_list(e.get("vibe")):
            has_vibe += 1
        if _norm_list(e.get("texture")):
            has_texture += 1
        if _norm_list(e.get("genre")):
            has_genre += 1
        if (e.get("energy") or "").strip():
            has_energy += 1
        if isinstance(e.get("features"), dict) and e["features"]:
            has_features += 1
        if e.get("discogs_styles") or e.get("parent_genre"):
            has_discogs += 1
        if (e.get("sonic_description") or "").strip():
            has_sonic += 1
        if e.get("quality_score") is not None:
            has_qs += 1

        for v in _invalid_vocab(_norm_list(e.get("vibe")), VIBES):
            invalid_vibe[v] += 1
        for v in _invalid_vocab(_norm_list(e.get("texture")), TEXTURES):
            invalid_texture[v] += 1
        for v in _invalid_vocab(_norm_list(e.get("genre")), GENRES):
            invalid_genre[v] += 1

        tc = (e.get("type_code") or "").upper()
        hint = (e.get("instrument_hint") or "").strip()
        if tc and hint and _hint_conflicts_type(tc, hint):
            hint_vs_type.append(rel)

        if src == "smart_retag_v1":
            if not (e.get("sonic_description") or "").strip():
                v1_missing_sonic += 1
            if e.get("quality_score") is None:
                v1_missing_qs += 1
            if not (_norm_list(e.get("vibe")) or _norm_list(e.get("texture")) or _norm_list(e.get("genre"))):
                v1_missing_dims += 1
            else:
                v1_complete_dims += 1

        sonic = (e.get("sonic_description") or "")
        if len(sonic) > 20 and tc:
            if kick_w.search(sonic) and tc not in ("KIK", "BRK", "DRM", "PRC", "SFX", "FX"):
                sonic_says_kick_type_not += 1
                if len(samples_sonic_mismatch) < 40:
                    samples_sonic_mismatch.append({"path": rel, "type": tc, "clip": sonic[:120]})
            if snare_w.search(sonic) and tc not in ("SNR", "BRK", "RIM", "CLP", "PRC", "SFX", "FX"):
                sonic_says_snare_type_not += 1

    # Rows never marked smart_retag: how many are dimensionally empty?
    no_src_void = no_src_no_vibe = no_src_no_genre = 0
    for rel, e in rows:
        if (e.get("tag_source") or "").strip():
            continue
        no_src_no_vibe += 0 if _norm_list(e.get("vibe")) else 1
        no_src_no_genre += 0 if _norm_list(e.get("genre")) else 1
        if not (
            _norm_list(e.get("vibe"))
            or _norm_list(e.get("texture"))
            or _norm_list(e.get("genre"))
        ):
            no_src_void += 1

    discogs_but_empty_genre_list = 0
    for _rel, e in rows:
        if _norm_list(e.get("genre")):
            continue
        if e.get("parent_genre") or e.get("discogs_styles"):
            discogs_but_empty_genre_list += 1

    hygiene_findings = 0
    hygiene_sample: List[Dict] = []
    if th is not None:
        try:
            findings = th._scan(db)
            hygiene_findings = len(findings)
            hygiene_sample = findings[:15]
        except Exception as exc:
            hygiene_sample = [{"error": str(exc)}]

    invalid_tc = sum(
        1
        for _rel, e in rows
        if (e.get("type_code") or "").upper() not in TYPE_CODES
        and (e.get("type_code") or "").strip()
    )

    return {
        "tags_file": TAGS_FILE,
        "total_entries": total,
        "tag_source": {
            "none": no_source,
            "smart_retag_v1": smart_v1,
            "smart_retag_v2_revibe": smart_v2,
            "other_labeled": other_source,
            "by_value": dict(by_source.most_common(20)),
        },
        "smart_retag_v1_row_health": {
            "count": smart_v1,
            "missing_sonic_description": v1_missing_sonic,
            "missing_quality_score": v1_missing_qs,
            "missing_all_vibe_texture_genre": v1_missing_dims,
            "has_any_dimension": v1_complete_dims,
            "note": "Current _merge_tags only adds sonic_description+quality from LLM; "
            "vibe/texture/genre expect CLAP/revibe/legacy — empty dims on v1 is normal.",
        },
        "library_dimensional_coverage": {
            "has_vibe": has_vibe,
            "has_texture": has_texture,
            "has_genre": has_genre,
            "has_energy": has_energy,
            "has_stored_features": has_features,
            "has_discogs_fields": has_discogs,
            "has_sonic_description": has_sonic,
            "has_quality_score": has_qs,
            "pct_vibe": round(100.0 * has_vibe / total, 2) if total else 0,
            "pct_genre": round(100.0 * has_genre / total, 2) if total else 0,
        },
        "vocabulary_violations": {
            "invalid_type_codes_non_empty": invalid_tc,
            "invalid_vibe_top": invalid_vibe.most_common(15),
            "invalid_texture_top": invalid_texture.most_common(15),
            "invalid_genre_top": invalid_genre.most_common(15),
        },
        "cross_field": {
            "instrument_hint_vs_type_code_rows": len(hint_vs_type),
            "sample_paths_hint_vs_type": hint_vs_type[:25],
            "sonic_mentions_kick_but_type_not_kick_like": sonic_says_kick_type_not,
            "sonic_mentions_snare_but_type_not_snare_like": sonic_says_snare_type_not,
            "sonic_mismatch_samples": samples_sonic_mismatch[:15],
        },
        "folder_hygiene_scan": {
            "findings_count": hygiene_findings,
            "sample_findings": hygiene_sample,
        },
        "non_smart_retag_rows": {
            "count": total - smart_v1 - smart_v2,
            "no_vibe_texture_genre_all_empty": no_src_void,
            "no_vibe_among_non_smart": no_src_no_vibe,
            "no_genre_list_among_non_smart": no_src_no_genre,
            "interpretation": "Fetch scoring uses vibe/genre/texture keywords; "
            "~half the library still has none of the three.",
        },
        "discogs_vs_genre_dimension": {
            "rows_with_discogs_metadata_but_empty_genre_list": discogs_but_empty_genre_list,
            "note": "parent_genre/discogs_styles are present from batch classify but "
            "may not populate the genre[] dimension used by keyword scoring.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit retag effectiveness and tag consistency")
    ap.add_argument("--json", default="", help="Write full report JSON to this path")
    args = ap.parse_args()

    db = load_tag_db(TAGS_FILE)
    if not db:
        print("No tag database at", TAGS_FILE)
        return 1

    report = audit(db)

    print("=== Retag & library tag audit ===")
    print(f"Database: {report['tags_file']}")
    print(f"Total entries: {report['total_entries']}")
    print()
    print("--- tag_source ---")
    ts = report["tag_source"]
    print(f"  (no tag_source): {ts['none']}")
    print(f"  smart_retag_v1:  {ts['smart_retag_v1']}")
    print(f"  smart_retag_v2_revibe: {ts['smart_retag_v2_revibe']}")
    print(f"  other labeled:   {ts['other_labeled']}")
    print("  top sources:", list(ts["by_value"].items())[:8])
    print()
    print("--- smart_retag_v1 row health ---")
    h = report["smart_retag_v1_row_health"]
    for k, v in h.items():
        if k != "note":
            print(f"  {k}: {v}")
    print(f"  NOTE: {h['note']}")
    print()
    print("--- library dimensional coverage ---")
    c = report["library_dimensional_coverage"]
    for k in ("has_vibe", "has_texture", "has_genre", "has_energy", "has_stored_features",
              "has_discogs_fields", "has_sonic_description", "has_quality_score"):
        print(f"  {k}: {c[k]}")
    print(f"  % with vibe: {c['pct_vibe']}%  |  % with genre: {c['pct_genre']}%")
    print()
    print("--- vocabulary violations (counts) ---")
    v = report["vocabulary_violations"]
    print(f"  non-empty type_code not in TYPE_CODES: {v['invalid_type_codes_non_empty']}")
    print("  invalid vibe (top):", v["invalid_vibe_top"][:8])
    print("  invalid texture (top):", v["invalid_texture_top"][:8])
    print("  invalid genre (top):", v["invalid_genre_top"][:8])
    print()
    print("--- cross-field ---")
    x = report["cross_field"]
    print(f"  instrument_hint vs type_code flagged: {x['instrument_hint_vs_type_code_rows']}")
    print(f"  sonic says kick-ish but type not KIK/BRK/...: {x['sonic_mentions_kick_but_type_not_kick_like']}")
    print(f"  sonic says snare-ish but type not SNR/...: {x['sonic_mentions_snare_but_type_not_snare_like']}")
    print()
    print("--- folder hygiene (type vs path) ---")
    fh = report["folder_hygiene_scan"]
    print(f"  findings: {fh['findings_count']}")
    print()
    print("--- rows without smart_retag ---")
    ns = report["non_smart_retag_rows"]
    print(f"  count: {ns['count']}")
    print(f"  all-empty vibe+texture+genre: {ns['no_vibe_texture_genre_all_empty']}")
    print(f"  interpretation: {ns['interpretation']}")
    print()
    print("--- discogs vs genre[] list ---")
    dg = report["discogs_vs_genre_dimension"]
    print(f"  discogs metadata but genre[] empty: {dg['rows_with_discogs_metadata_but_empty_genre_list']}")
    print(f"  {dg['note']}")

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nWrote {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
