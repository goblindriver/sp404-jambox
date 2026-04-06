#!/usr/bin/env python3
"""Low-rank audit for banks/presets with confidence metrics.

Outputs a machine-readable report for iterative curation:
  - top_score
  - top2_gap
  - type_match_ratio
  - conversion_success_rate
  - severity band (red/yellow/green)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, Iterable, List, Tuple

from jambox_config import load_settings_for_script, load_bank_config

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import fetch_samples
import preset_utils

SETTINGS = load_settings_for_script(__file__)
REPO_DIR = SETTINGS["REPO_DIR"]
DEFAULT_OUT = os.path.join(REPO_DIR, "data", "audit_reports", "low_rank_latest.json")
DEFAULT_MD_OUT = os.path.join(REPO_DIR, "data", "audit_reports", "low_rank_latest.md")
KNOWN_AUDIO_EXTS = {".wav", ".aif", ".aiff", ".mp3", ".flac"}


def _expected_type(description: str) -> str:
    parsed = fetch_samples.parse_pad_query(description or "")
    return (parsed.get("type_code") or "").upper()


def _is_candidate_viable(candidate: Dict) -> bool:
    path = candidate.get("path")
    if not path or not os.path.isfile(path):
        return False
    ext = os.path.splitext(path)[1].lower()
    if ext not in KNOWN_AUDIO_EXTS:
        return False
    duration = candidate.get("duration")
    if isinstance(duration, (int, float)) and duration <= 0:
        return False
    return True


def _is_mission_critical(description: str, bank_letter: str, pad_num: int) -> bool:
    text = (description or "").lower()
    if bank_letter.lower() == "j" and pad_num >= 10:
        return True
    # Keep strict gating for transition/utility behavior, not generic one-shots.
    markers = ("transition", "riser", "downlifter", "reverse", "stinger", "utility")
    return any(marker in text for marker in markers)


def _score_severity(
    top_score: float,
    top2_gap: float,
    type_match_ratio: float,
    conversion_success_rate: float,
    mission_critical: bool,
    top1_type_match: bool,
) -> str:
    # When the top candidate is the right type and viable, avoid over-penalizing
    # sparse libraries that naturally have low top-N type diversity.
    if top1_type_match and top_score >= 12 and conversion_success_rate >= 0.8:
        # For critical utility/transition pads, allow close ties when absolute score is strong.
        if mission_critical and top2_gap < 1.0 and top_score < 22:
            return "yellow"
        return "green" if top_score >= 18 else "yellow"

    if (
        top_score < 12
        or type_match_ratio < 0.34
        or conversion_success_rate < 0.40
        or (mission_critical and top2_gap < 1.0)
    ):
        return "red"
    if (
        top_score < 20
        or type_match_ratio < 0.67
        or conversion_success_rate < 0.70
        or (mission_critical and top2_gap < 2.0)
    ):
        return "yellow"
    return "green"


def _audit_pad(
    bank_letter: str,
    pad_num: int,
    description: str,
    bank_cfg: Dict,
    tag_db: Dict,
    top_n: int,
    min_score: int,
    deterministic: bool,
) -> Dict:
    expected_type = _expected_type(description)
    ranked = fetch_samples.rank_library_matches(
        description,
        bank_config=bank_cfg,
        tag_db=tag_db,
        limit=max(2, top_n),
        min_score=min_score,
    )
    top = ranked[:top_n]
    top_score = float(top[0]["score"]) if top else 0.0
    top2_score = float(top[1]["score"]) if len(top) > 1 else 0.0
    top2_gap = round(top_score - top2_score, 3) if len(top) > 1 else round(top_score, 3)

    if expected_type:
        type_matches = sum(1 for item in top if (item.get("type_code") or "").upper() == expected_type)
        type_match_ratio = type_matches / max(len(top), 1)
        top1_type_match = bool(top and (top[0].get("type_code") or "").upper() == expected_type)
    else:
        type_match_ratio = 1.0
        top1_type_match = True

    viable = sum(1 for item in top if _is_candidate_viable(item))
    conversion_success_rate = viable / max(len(top), 1) if top else 0.0

    mission_critical = _is_mission_critical(description, bank_letter, pad_num)
    severity = _score_severity(
        top_score=top_score,
        top2_gap=top2_gap,
        type_match_ratio=type_match_ratio,
        conversion_success_rate=conversion_success_rate,
        mission_critical=mission_critical,
        top1_type_match=top1_type_match,
    )

    selected = None
    if top:
        picked = fetch_samples.choose_diverse_match(top, deterministic=deterministic)
        selected = picked.get("rel_path") or picked.get("path")

    candidates = []
    for item in top:
        candidates.append(
            {
                "rel_path": item.get("rel_path"),
                "score": item.get("score"),
                "type_code": item.get("type_code"),
                "playability": item.get("playability"),
                "duration": item.get("duration"),
            }
        )

    return {
        "bank": bank_letter.lower(),
        "pad": int(pad_num),
        "description": description,
        "expected_type": expected_type or None,
        "selected_candidate": selected,
        "top_score": round(top_score, 3),
        "top2_gap": round(top2_gap, 3),
        "type_match_ratio": round(type_match_ratio, 3),
        "top1_type_match": top1_type_match,
        "conversion_success_rate": round(conversion_success_rate, 3),
        "mission_critical": mission_critical,
        "severity": severity,
        "candidate_count": len(top),
        "candidates": candidates,
    }


def _iter_bank_pad_specs(config: Dict, banks: Iterable[str]) -> Iterable[Tuple[str, int, str, Dict, str]]:
    for bank_letter in banks:
        bank_key = f"bank_{bank_letter.lower()}"
        bank = config.get(bank_key, {}) if isinstance(config, dict) else {}
        pads = bank.get("pads", {})
        bank_cfg = {"bpm": bank.get("bpm"), "key": bank.get("key")}
        preset_ref = bank.get("preset")
        for pad_key, desc in pads.items():
            try:
                pad_num = int(pad_key)
            except (TypeError, ValueError):
                continue
            if not isinstance(desc, str) or not desc.strip():
                continue
            yield bank_letter.lower(), pad_num, desc.strip(), bank_cfg, str(preset_ref or "")


def _iter_preset_pad_specs(preset_refs: Iterable[str]) -> Iterable[Tuple[str, int, str, Dict, str]]:
    for idx, ref in enumerate(preset_refs, start=1):
        preset = preset_utils.load_preset(ref, require_full_pads=True)
        if not preset:
            continue
        pads = preset.get("pads", {})
        bank_cfg = {"bpm": preset.get("bpm"), "key": preset.get("key")}
        pseudo_bank = f"p{idx}"
        for pad_num, desc in sorted(pads.items()):
            if not isinstance(desc, str) or not desc.strip():
                continue
            yield pseudo_bank, int(pad_num), desc.strip(), bank_cfg, ref


def _summarize(rows: List[Dict]) -> Dict:
    severity_counts = {"red": 0, "yellow": 0, "green": 0}
    for row in rows:
        severity = row.get("severity", "red")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    avg = lambda key: round(sum(float(r.get(key, 0.0)) for r in rows) / max(len(rows), 1), 3)
    return {
        "total_pads": len(rows),
        "severity_counts": severity_counts,
        "avg_top_score": avg("top_score"),
        "avg_top2_gap": avg("top2_gap"),
        "avg_type_match_ratio": avg("type_match_ratio"),
        "avg_conversion_success_rate": avg("conversion_success_rate"),
        "show_ready": severity_counts.get("red", 0) == 0,
    }


def _write_report(report: Dict, out_json: str, out_md: str) -> None:
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)

    rows = report.get("rows", [])
    summary = report.get("summary", {})
    with open(out_md, "w", encoding="utf-8") as handle:
        handle.write("# Low-rank audit report\n\n")
        handle.write(f"- generated_at: `{report.get('generated_at')}`\n")
        handle.write(f"- total_pads: `{summary.get('total_pads', 0)}`\n")
        handle.write(f"- red/yellow/green: `{summary.get('severity_counts', {})}`\n")
        handle.write(f"- show_ready: `{summary.get('show_ready', False)}`\n\n")
        handle.write("## Red pads\n\n")
        red_rows = [row for row in rows if row.get("severity") == "red"]
        if not red_rows:
            handle.write("- none\n")
        else:
            for row in red_rows:
                handle.write(
                    f"- `{row['bank'].upper()}{row['pad']:02d}` `{row['description']}` "
                    f"(score={row['top_score']}, gap={row['top2_gap']}, "
                    f"type_ratio={row['type_match_ratio']}, conv={row['conversion_success_rate']})\n"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit low-ranking bank/preset pads.")
    parser.add_argument("--bank", action="append", help="Bank letter(s) to audit (repeatable)")
    parser.add_argument("--preset-ref", action="append", help="Preset refs to audit directly (repeatable)")
    parser.add_argument("--top-n", type=int, default=5, help="Top N candidates per pad (default: 5)")
    parser.add_argument("--min-score", type=int, default=0, help="Minimum ranking score")
    parser.add_argument("--deterministic", action="store_true", help="Use deterministic selection for selected_candidate")
    parser.add_argument("--out", default=DEFAULT_OUT, help="JSON output path")
    parser.add_argument("--out-md", default=DEFAULT_MD_OUT, help="Markdown output path")
    args = parser.parse_args()

    config = load_bank_config(SETTINGS["CONFIG_PATH"], strict=True)
    tag_db = fetch_samples.load_tag_db()
    if not isinstance(tag_db, dict) or not tag_db:
        print("ERROR: no tag database loaded.")
        return 1

    rows: List[Dict] = []
    if args.preset_ref:
        specs = _iter_preset_pad_specs(args.preset_ref)
    else:
        banks = [b.lower() for b in (args.bank or list("bcdefghij")) if b and len(b) == 1]
        specs = _iter_bank_pad_specs(config, banks)

    for bank, pad_num, desc, bank_cfg, preset_ref in specs:
        row = _audit_pad(
            bank_letter=bank,
            pad_num=pad_num,
            description=desc,
            bank_cfg=bank_cfg,
            tag_db=tag_db,
            top_n=max(2, args.top_n),
            min_score=args.min_score,
            deterministic=args.deterministic,
        )
        row["preset_ref"] = preset_ref or None
        rows.append(row)

    rows.sort(key=lambda item: ("redyellowgreen".find(item["severity"][0]), item["top_score"]))
    summary = _summarize(rows)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo_dir": REPO_DIR,
        "settings": {
            "top_n": args.top_n,
            "min_score": args.min_score,
            "deterministic": bool(args.deterministic),
        },
        "summary": summary,
        "rows": rows,
    }
    _write_report(report, args.out, args.out_md)

    print(f"[AUDIT] wrote {len(rows)} pad rows")
    print(f"[AUDIT] summary: {summary}")
    print(f"[AUDIT] json: {args.out}")
    print(f"[AUDIT] md:   {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
