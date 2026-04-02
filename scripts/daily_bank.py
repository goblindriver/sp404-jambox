#!/usr/bin/env python3
"""Generate a daily preset from recent library activity or trending tags."""

import json
import os
import random
from datetime import date

from jambox_config import load_settings_for_script
import preset_utils


SETTINGS = load_settings_for_script(__file__)
TODAY = date.today().isoformat()


def _load_tag_db():
    try:
        with open(SETTINGS["TAGS_FILE"]) as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _entry_query(entry):
    parts = []
    if entry.get("type_code"):
        parts.append(entry["type_code"])
    for group in ("genre", "vibe", "texture"):
        for value in entry.get(group, [])[:2]:
            if value not in parts:
                parts.append(value)
    if entry.get("playability"):
        parts.append(entry["playability"])
    return " ".join(parts[:5]).strip() or "SMP eclectic loop"


def _load_trending_terms():
    path = SETTINGS.get("TRENDING_FILE", "")
    if path and os.path.exists(path):
        with open(path) as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return [str(item).lower() for item in payload]
        if isinstance(payload, dict):
            terms = []
            for value in payload.values():
                if isinstance(value, list):
                    terms.extend(str(item).lower() for item in value)
            return terms
    return ["disco", "funk", "electronic", "ambient", "house", "neon"]


def _recent_candidates(db):
    candidates = []
    for rel_path, entry in db.items():
        full_path = os.path.join(SETTINGS["SAMPLE_LIBRARY"], rel_path)
        if not os.path.exists(full_path):
            continue
        try:
            mtime = os.path.getmtime(full_path)
        except OSError:
            continue
        candidates.append((mtime, rel_path, entry))
    candidates.sort(reverse=True)
    return candidates[:120]


def _trending_candidates(db, terms):
    candidates = []
    term_set = set(terms)
    for rel_path, entry in db.items():
        haystack = set(tag.lower() for tag in entry.get("tags", []))
        haystack.update(tag.lower() for tag in entry.get("genre", []))
        haystack.update(tag.lower() for tag in entry.get("vibe", []))
        matches = len(term_set & haystack)
        if matches:
            candidates.append((matches, rel_path, entry))
    candidates.sort(reverse=True)
    return candidates[:120]


def _weighted_pick(candidates, count):
    if not candidates:
        return []

    chosen = []
    pool = list(candidates)
    while pool and len(chosen) < count:
        weights = [max(1, item[0]) for item in pool]
        picked = random.choices(pool, weights=weights, k=1)[0]
        chosen.append(picked)
        pool.remove(picked)
    return chosen


def build_daily_preset(source=None, pad_count=12):
    source = (source or SETTINGS.get("DAILY_BANK_SOURCE", "recent")).lower()
    db = _load_tag_db()
    if not db:
        raise ValueError("Tag database is empty; run tag_library.py first")

    if source == "trending":
        candidates = _trending_candidates(db, _load_trending_terms())
        vibe = "Auto-curated from trending tag matches"
    else:
        candidates = _recent_candidates(db)
        vibe = "Auto-curated from recent library additions"

    picks = _weighted_pick(candidates, pad_count)
    if not picks:
        raise ValueError("Could not assemble a daily bank from the current library")

    pads = {}
    tags = set()
    bpm_values = []
    for index, (_weight, _rel_path, entry) in enumerate(picks, start=1):
        pads[index] = _entry_query(entry)
        tags.update(tag.lower() for tag in entry.get("genre", []))
        tags.update(tag.lower() for tag in entry.get("vibe", []))
        if entry.get("bpm"):
            bpm_values.append(int(entry["bpm"]))

    preset = {
        "name": f"Daily Bank {TODAY}",
        "slug": f"daily-{TODAY}",
        "author": "jambox",
        "bpm": round(sum(bpm_values) / len(bpm_values)) if bpm_values else 120,
        "key": None,
        "vibe": vibe,
        "notes": f"Generated on {TODAY} using source={source}.",
        "source": "daily-bank",
        "tags": sorted(tags)[:12],
        "pads": pads,
    }
    ref = preset_utils.save_preset(preset, category="auto")
    return {
        "ref": ref,
        "path": os.path.join(preset_utils.PRESETS_DIR, f"{ref}.yaml"),
        "preset": preset,
        "source": source,
    }


def main():
    result = build_daily_preset()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
