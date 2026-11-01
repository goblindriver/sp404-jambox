#!/usr/bin/env python3
"""Deploy the sd-card-template to the SP-404 SD card (macOS, Windows, Linux).

Copies ROLAND/ (plus BKUP/ and FCTRY/ when present) and PAD_MAP.txt onto the
card, skipping files that are already identical (same size and mtime), and
never deletes anything on the card unless --prune is passed: pad WAVs on the
card that the template doesn't have may be resamples recorded on the device.

Usage:
    python scripts/deploy_sd.py                 # card from SP404_SD_CARD or auto-detect
    python scripts/deploy_sd.py --card E:\\
    python scripts/deploy_sd.py --prune         # also delete card pads missing from the template
"""
import argparse
import os
import re
import shutil
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import find_sd_card, load_settings_for_script

REPO_DIR = os.path.dirname(SCRIPTS_DIR)
TEMPLATE_DIR = os.path.join(REPO_DIR, "sd-card-template")
PAD_MAP = os.path.join(REPO_DIR, "PAD_MAP.txt")
TREES = ("ROLAND", "BKUP", "FCTRY")
JUNK_NAMES = (".DS_Store", ".gitkeep")
PAD_WAV_RE = re.compile(r"[A-J]\d{7}\.WAV", re.IGNORECASE)
SMPL_PARTS = ("ROLAND", "SP-404SX", "SMPL")


def _is_junk(name):
    return name.startswith("._") or name in JUNK_NAMES


def _same_file(src, dest):
    try:
        a, b = os.stat(src), os.stat(dest)
    except OSError:
        return False
    # FAT32 stores mtimes with 2-second resolution.
    return a.st_size == b.st_size and abs(a.st_mtime - b.st_mtime) < 2.1


def _copy_tree(src_root, dest_root, report):
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if not _is_junk(d)]
        rel = os.path.relpath(dirpath, src_root)
        dest_dir = os.path.normpath(os.path.join(dest_root, rel))
        os.makedirs(dest_dir, exist_ok=True)
        for name in filenames:
            if _is_junk(name):
                continue
            src, dest = os.path.join(dirpath, name), os.path.join(dest_dir, name)
            if _same_file(src, dest):
                report["unchanged"] += 1
                continue
            shutil.copy2(src, dest)
            report["copied"] += 1


def _remove_junk(root):
    removed = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if _is_junk(name):
                try:
                    os.remove(os.path.join(dirpath, name))
                    removed += 1
                except OSError:
                    pass
    return removed


def _pad_wavs(smpl_dir):
    if not os.path.isdir(smpl_dir):
        return set()
    return {n.upper() for n in os.listdir(smpl_dir) if PAD_WAV_RE.fullmatch(n)}


def deploy(card_root, template_dir=TEMPLATE_DIR, pad_map=PAD_MAP, prune=False):
    """Copy the template onto the card. Returns a report dict; raises ValueError on bad input."""
    if not card_root or not os.path.isdir(card_root):
        raise ValueError(f"SD card not found at {card_root or '(not detected)'}")
    card_root = os.path.abspath(card_root)
    if os.path.abspath(template_dir).startswith(card_root + os.sep) or card_root == os.path.abspath(os.sep):
        raise ValueError(f"Refusing to deploy to {card_root}")
    if not os.path.isdir(os.path.join(template_dir, "ROLAND")):
        raise ValueError(f"Template has no ROLAND folder: {template_dir}")

    report = {"card": card_root, "copied": 0, "unchanged": 0, "orphans": [], "pruned": 0}
    for tree in TREES:
        src = os.path.join(template_dir, tree)
        if os.path.isdir(src):
            _copy_tree(src, os.path.join(card_root, tree), report)
    if os.path.isfile(pad_map):
        shutil.copy2(pad_map, os.path.join(card_root, "PAD_MAP.txt"))
    report["junk_removed"] = _remove_junk(os.path.join(card_root, "ROLAND"))

    card_smpl = os.path.join(card_root, *SMPL_PARTS)
    orphans = sorted(_pad_wavs(card_smpl) - _pad_wavs(os.path.join(template_dir, *SMPL_PARTS)))
    report["orphans"] = orphans
    if prune:
        for name in orphans:
            os.remove(os.path.join(card_smpl, name))
        report["pruned"] = len(orphans)
    report["card_wavs"] = len(_pad_wavs(card_smpl))
    return report


def format_report(report):
    lines = [
        f"Deployed to {report['card']}",
        f"  Copied {report['copied']} files ({report['unchanged']} already up to date)",
        f"  Pad WAVs on card: {report['card_wavs']}",
    ]
    if report["orphans"]:
        verb = "Deleted" if report["pruned"] else "Kept"
        lines.append(f"  {verb} {len(report['orphans'])} card pads not in the template "
                     f"(possibly on-device resamples): {', '.join(report['orphans'][:12])}"
                     + (" ..." if len(report["orphans"]) > 12 else ""))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Copy sd-card-template onto the SP-404 SD card")
    parser.add_argument("--card", help="Card root (default: SP404_SD_CARD or auto-detect)")
    parser.add_argument("--prune", action="store_true",
                        help="Delete pad WAVs on the card that the template doesn't have")
    args = parser.parse_args()

    card = args.card or find_sd_card(load_settings_for_script(__file__))
    try:
        report = deploy(card, prune=args.prune)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(format_report(report))
    print("Safely eject the card before removing it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
