#!/usr/bin/env python3
"""Optional multi-pass backfill: map Discogs classifier fields into ``genre[]``.

Pass 1 (``--pass parent``): append tokens from ``parent_genre`` only.
Pass 2 (``--pass styles``): append sub-style tokens from ``discogs_styles`` (deduped).

Fetch scoring already reads Discogs via ``discogs_fetch_bridge``; this script
only helps UIs, tag filters, and keyword_dimension matches on ``genre``.

Examples:
  python scripts/sync_discogs_genre.py --pass parent --dry-run --limit 500
  python scripts/sync_discogs_genre.py --pass parent --apply --offset 500 --limit 500
  python scripts/sync_discogs_genre.py --pass styles --apply --limit 2000
"""

from __future__ import annotations

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from discogs_fetch_bridge import discogs_style_tokens, parent_genre_tokens
from jambox_config import load_settings_for_script, load_tag_db, upsert_tag_entries


def _merge_genres(entry: dict, extra: set[str]) -> tuple[list[str], int]:
    """Return (new_genre_list, number of tokens appended)."""
    raw = entry.get("genre") or []
    out = [str(g) for g in raw if isinstance(g, str) and g.strip()]
    seen = {g.lower() for g in out}
    added = 0
    for t in sorted(extra):
        if t not in seen:
            out.append(t)
            seen.add(t)
            added += 1
    return out, added


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill genre[] from Discogs metadata")
    parser.add_argument("--pass", dest="pass_mode", choices=("parent", "styles"), required=True)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N paths (sorted) for chunked runs")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N paths after offset (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Print summary only (default if no --apply)")
    args = parser.parse_args()
    dry = not args.apply

    settings = load_settings_for_script(__file__)
    tags_file = settings["TAGS_FILE"]
    db = load_tag_db(tags_file)
    if not db:
        print("No tag database at", tags_file)
        return 1

    pending: dict[str, dict] = {}
    examined = changed = tokens_added = 0
    paths = sorted(db.keys())
    if args.offset:
        paths = paths[args.offset :]
    if args.limit:
        paths = paths[: args.limit]

    for rel_path in paths:
        entry = db.get(rel_path)
        examined += 1
        if not isinstance(entry, dict):
            continue
        if args.pass_mode == "parent":
            extra = parent_genre_tokens(entry)
        else:
            extra = discogs_style_tokens(entry, style_prob_floor=0.12, max_rows=3)
        if not extra:
            continue
        new_genres, nadd = _merge_genres(entry, extra)
        if nadd == 0:
            continue
        changed += 1
        tokens_added += nadd
        ne = dict(entry)
        ne["genre"] = new_genres
        pending[rel_path] = ne
        if dry and changed <= 12:
            print(f"  {rel_path}: +{nadd} -> {new_genres[-nadd:]}")

    print(
        f"pass={args.pass_mode} examined={examined} rows_to_update={changed} "
        f"tokens_appended={tokens_added} dry_run={dry}"
    )

    if dry or not pending:
        return 0

    upsert_tag_entries(tags_file, pending)
    print(f"Wrote {len(pending)} rows via upsert_tag_entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
