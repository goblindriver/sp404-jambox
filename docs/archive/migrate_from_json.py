#!/usr/bin/env python3
"""One-shot migration: _tags.json → data/jambox.db (normalized SQLite).

Safe to run while smart_retag is active — reads the JSON snapshot, does not
modify it. The retag process keeps writing to _tags.json; re-run this script
after retag completes to pick up the rest.

Usage:
    python scripts/migrate_from_json.py              # migrate
    python scripts/migrate_from_json.py --verify     # verify counts match
    python scripts/migrate_from_json.py --stats      # show DB coverage stats
"""

import argparse
import json
import os
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings_for_script
from db import JamboxDB

SETTINGS = load_settings_for_script(__file__)
TAGS_FILE = SETTINGS["TAGS_FILE"]


def load_json_tags():
    """Load _tags.json (the source of truth during migration)."""
    if not os.path.exists(TAGS_FILE):
        print("ERROR: %s not found" % TAGS_FILE)
        sys.exit(1)
    with open(TAGS_FILE, "r") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        print("ERROR: _tags.json is not a dict")
        sys.exit(1)
    return data


def migrate(db_path=None):
    """Run the migration."""
    tag_dict = load_json_tags()
    print("Source: %s (%d entries)" % (TAGS_FILE, len(tag_dict)))

    db = JamboxDB(db_path)
    existing = db.sample_count()
    if existing:
        print("Target DB already has %d samples — will merge/update" % existing)

    print("Importing...")
    t0 = time.time()
    count = db.import_from_tag_dict(tag_dict)
    elapsed = time.time() - t0

    print("\nMigration complete")
    print("  Imported: %d entries in %.1fs" % (count, elapsed))
    print("  DB: %s" % db.db_path)
    print("  DB size: %.1f KB" % (os.path.getsize(db.db_path) / 1024))

    # Coverage report
    coverage = db.tag_coverage()
    print("\nTag coverage:")
    print("  Total samples: %d" % coverage['total_samples'])
    for dim, cnt in sorted(coverage['dimensions'].items(),
                           key=lambda x: -x[1]):
        pct = cnt / max(coverage['total_samples'], 1) * 100
        print("  %-20s %5d (%5.1f%%)" % (dim, cnt, pct))

    db.close()


def verify(db_path=None):
    """Verify migration by comparing counts."""
    tag_dict = load_json_tags()
    db = JamboxDB(db_path)

    json_count = len(tag_dict)
    db_count = db.sample_count()

    print("JSON entries: %d" % json_count)
    print("DB samples:   %d" % db_count)

    if json_count == db_count:
        print("PASS — counts match")
    else:
        diff = json_count - db_count
        print("DIFF — %d entries %s in DB" % (
            abs(diff), "missing" if diff > 0 else "extra"))

    # Spot-check a few entries
    import random
    keys = list(tag_dict.keys())
    if keys:
        samples = random.sample(keys, min(5, len(keys)))
        print("\nSpot check:")
        for filepath in samples:
            json_entry = tag_dict[filepath]
            db_entry = db.get_sample(filepath)
            if db_entry is None:
                print("  MISSING: %s" % filepath)
                continue
            # Compare key fields
            checks = []
            for field in ('bpm', 'key', 'type_code'):
                jv = json_entry.get(field)
                dv = db_entry.get(field)
                match = str(jv) == str(dv) if jv is not None else dv is None
                checks.append("%s=%s" % (field, "ok" if match else
                              "MISMATCH(%s vs %s)" % (jv, dv)))
            print("  %s: %s" % (os.path.basename(filepath), ', '.join(checks)))

    db.close()


def stats(db_path=None):
    """Show DB coverage stats."""
    db = JamboxDB(db_path)
    coverage = db.tag_coverage()

    print("Jambox DB: %s" % db.db_path)
    print("DB size: %.1f KB" % (os.path.getsize(db.db_path) / 1024))
    print("\nTotal samples: %d" % coverage['total_samples'])
    print("\nDimension coverage:")
    for dim, cnt in sorted(coverage['dimensions'].items(),
                           key=lambda x: -x[1]):
        pct = cnt / max(coverage['total_samples'], 1) * 100
        bar = '#' * int(pct / 2)
        print("  %-20s %5d (%5.1f%%) %s" % (dim, cnt, pct, bar))

    # Top tags per dimension
    print("\nTop tags per dimension:")
    for dim in ('type_code', 'vibe', 'texture', 'genre', 'energy', 'playability'):
        counts = db.tag_counts(dim)
        if counts:
            top = counts[:5]
            vals = ', '.join("%s(%d)" % (v, c) for _, v, c in top)
            print("  %-12s: %s" % (dim, vals))

    db.close()


def main():
    parser = argparse.ArgumentParser(
        description='Migrate _tags.json to normalized SQLite (data/jambox.db)')
    parser.add_argument('--verify', action='store_true',
                        help='Verify migration counts match')
    parser.add_argument('--stats', action='store_true',
                        help='Show DB coverage statistics')
    parser.add_argument('--db', type=str, default=None,
                        help='Custom DB path (default: data/jambox.db)')
    args = parser.parse_args()

    if args.stats:
        stats(args.db)
    elif args.verify:
        verify(args.db)
    else:
        migrate(args.db)


if __name__ == '__main__':
    main()
