#!/usr/bin/env python3
"""
Ingest sample packs from ~/Downloads into the SP-404 sample library.

CLI entry point. All logic lives in scripts/ingest/.

Modes:
    python scripts/ingest_downloads.py              # one-shot: process everything now
    python scripts/ingest_downloads.py --dry-run     # show what would happen
    python scripts/ingest_downloads.py --watch       # background watcher daemon
"""
import os
import sys
import time
import argparse

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from ingest import (
    _state, set_downloads_path,
    one_shot_ingest, start_watcher, stop_watcher,
    cleanup_downloads, purge_raw_archive, disk_usage_report,
)


def main():
    parser = argparse.ArgumentParser(description='Ingest sample packs from Downloads')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen')
    parser.add_argument('--watch', action='store_true', help='Run as background watcher daemon')
    parser.add_argument('--cleanup', action='store_true', help='Remove already-ingested items from Downloads')
    parser.add_argument('--purge-archive', action='store_true', help='Delete _RAW-DOWNLOADS to free space')
    parser.add_argument('--disk-report', action='store_true', help='Show disk usage report')
    parser.add_argument('--downloads-path', type=str, help='Override downloads folder path')
    parser.add_argument('--dedupe', action='store_true', help='Run duplicate analysis after tagging')
    args = parser.parse_args()

    if args.downloads_path:
        set_downloads_path(args.downloads_path)

    os.makedirs(_state.LIBRARY, exist_ok=True)
    os.makedirs(_state.RAW_ARCHIVE, exist_ok=True)

    if args.disk_report:
        report = disk_usage_report()
        print(f"Disk free:      {report['disk_free_str']}")
        print(f"Downloads:      {report['downloads_str']}")
        print(f"  Cleanable:    {report['cleanable_str']} ({report['cleanable_count']} items)")
        print(f"Archive:        {report['archive_str']}")
        print(f"Library:        {report['library_str']}")
        print(f"Downloads path: {report['downloads_path']}")
        return

    if args.cleanup:
        cleanup_downloads(dry_run=args.dry_run)
        return

    if args.purge_archive:
        purge_raw_archive(dry_run=args.dry_run)
        return

    if args.watch:
        print("Running initial ingest pass...")
        one_shot_ingest(dry_run=args.dry_run, dedupe=args.dedupe)

        if args.dry_run:
            print("\nDry run \u2014 not starting watcher")
            return

        if not start_watcher(dedupe=args.dedupe):
            sys.exit(1)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping watcher...")
            stop_watcher()
    else:
        one_shot_ingest(dry_run=args.dry_run, dedupe=args.dedupe)


if __name__ == '__main__':
    main()
