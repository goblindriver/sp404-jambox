#!/usr/bin/env python3
"""Check banks against the "song-follower" pad layout.

Song-follower splits a bank's 12 pads by whether they care about the song's
key and tempo, so a bank can ride on top of any song (karaoke) and muscle
memory carries across banks:

  pads 1-4   drum hits             gate            keyless, any tempo
  pads 5-8   hype and transitions  play-through    keyless, any tempo
  pads 9-12  the bank's identity   loop            needs the tempo and a matching key

Only row 3 has to match the song: that's the part the MIDI clock keeps in time.
Bank A on karaoke night is the all-one-shot drop bank (utility/karaoke-drops),
so this is the rule for genre banks.

    python scripts/pad_layout.py                       # every genre preset
    python scripts/pad_layout.py genre/funk-muscle-follower bank_config.yaml
"""
import argparse
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from tag_vocab import pad_type_and_playability  # noqa: E402

DRUM_HITS = {"KIK", "SNR", "CLP", "HAT", "CYM", "RIM", "PRC", "DRM"}
# Unpitched (or pitch-irrelevant) one-shots that land over any key.
KEYLESS_HITS = {"VOX", "FX", "SFX", "RSR", "CYM", "AMB", "FLY", "TPE"}
SUSTAINED = {"loop", "chop-ready", "chromatic", "layer"}

ROWS = (
    ("drum hit", range(1, 5), DRUM_HITS, {"one-shot", None}),
    ("keyless hype/transition", range(5, 9), KEYLESS_HITS, {"one-shot", "transition", None}),
    ("in-key loop", range(9, 13), None, SUSTAINED),
)


def check(pads):
    """Song-follower issues for a {pad: description} bank, as [(pad, message)]."""
    issues = []
    for row_name, numbers, types, playabilities in ROWS:
        for num in numbers:
            desc = pads.get(num, pads.get(str(num)))
            if not desc:
                issues.append((num, "empty (%s)" % row_name))
                continue
            type_code, playability = pad_type_and_playability(desc)
            if types is not None and type_code not in types:
                issues.append((num, "%s is not a %s" % (type_code or "untyped", row_name)))
            elif playability not in playabilities:
                issues.append((num, "%s %s: wants %s" % (
                    type_code or "untyped", playability or "no playability", row_name)))
    return issues


def _load_banks(ref):
    """[(label, pads)] for a preset ref or a bank_config.yaml path."""
    import yaml
    if ref.endswith((".yaml", ".yml")) and os.path.isfile(ref) and "presets" not in ref.replace("\\", "/"):
        with open(ref, encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
        return [("%s %s" % (os.path.basename(ref), key), bank.get("pads") or {})
                for key, bank in sorted(config.items())
                if key.startswith("bank_") and isinstance(bank, dict)]
    from preset_utils import load_preset
    preset = load_preset(ref, require_full_pads=False)
    return [(ref, preset.get("pads") or {})]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("refs", nargs="*", help="preset refs (genre/funk-muscle) or bank_config.yaml")
    ap.add_argument("--quiet", "-q", action="store_true", help="one line per bank")
    args = ap.parse_args(argv)

    refs = args.refs
    if not refs:
        from preset_utils import list_presets
        refs = [p["ref"] for p in list_presets(category="genre")]

    conforming = 0
    for ref in refs:
        for label, pads in _load_banks(ref):
            issues = check(pads)
            conforming += not issues
            print("%-44s %s" % (label, "song-follower" if not issues else "%d pads off" % len(issues)))
            if not args.quiet:
                for num, message in issues:
                    print("    pad %-2d %s" % (num, message))
    print("\n%d conforming" % conforming)
    return 0


if __name__ == "__main__":
    sys.exit(main())
