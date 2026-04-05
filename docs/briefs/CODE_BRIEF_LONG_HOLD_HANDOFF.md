# Code Brief: `_LONG-HOLD` Sample Holding Area (Handoff)

**Status:** Shipped in repo (April 2026 session)  
**Intent:** Isolate long, chop-first audio so it does not compete with pad-ready samples in fetch, daily bank, or RAG library hints. Tagging there is **opt-in / lower priority** than the main library.

---

## Problem

Full tracks and other long clips need editing before they behave well on SP-404 pads. They were still present in `_tags.json` like one-shots, so fetch scoring and daily curation could surface them. Bulk maintenance (tag scan, smart retag walks, stem split, etc.) also treated them like normal inventory.

---

## Design (What We Did)

### Holding folder

- **Directory name:** `_LONG-HOLD` (constant `LONG_HOLD_DIRNAME` in `scripts/jambox_config.py`).
- **Absolute path:** `LONG_HOLD_DIR` under `SP404_SAMPLE_LIBRARY` (same as `~/Music/SP404-Sample-Library/_LONG-HOLD` by default).
- **Layout:** Mirror prior relative paths, e.g. `Drums/Kicks/x.flac` → `_LONG-HOLD/Drums/Kicks/x.flac`.

### Config / helpers


| Item                                           | Location / notes                                                                                |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `LONG_HOLD_DIRNAME`, `is_long_hold_rel_path()` | `scripts/jambox_config.py`                                                                      |
| `LONG_HOLD_DIR`, `LONG_HOLD_MIN_SECONDS`       | Returned by `load_settings()`; seconds from env `SP404_LONG_HOLD_MIN_SECONDS` (default **120**) |


### Excluded from “active” workflows

- **Fetch / pad matching:** `scripts/fetch_samples.py` — skips any tag DB key where `is_long_hold_rel_path(rel_path)`.
- **Daily bank:** `scripts/daily_bank.py` — skips long-hold entries in recent and trending candidate loops.
- **Vibe RAG library hints:** `scripts/vibe_retrieval.py` — skips long-hold rows when aggregating type/genre/vibe counts.

### Skipped in bulk directory walks

These prune `_LONG-HOLD` from `os.walk` (or equivalent) so routine passes do not touch the hold bucket:

- `scripts/smart_retag.py` — also skips long-hold rows in **bulk** `--retry-llm-failures` and **re-vibe** tag-DB scans (explicit `--path` runs still target hold when needed).
- `scripts/tag_library.py`
- `scripts/dedup_library.py`, `scripts/library_health.py`, `scripts/convert_to_flac.py`, `scripts/stem_split.py`

### Move tool

- **Script:** `scripts/move_long_samples_to_hold.py`
- **Default:** dry-run (lists candidates).
- **Apply:** `--apply` moves files and updates the tag database keys (and `path` field on entries).
- **Duration:** Uses `_tags.json` / SQLite `duration` when present and positive; else ffprobe via `tag_library.get_duration`.

```bash
python3 scripts/move_long_samples_to_hold.py              # preview
python3 scripts/move_long_samples_to_hold.py --apply
python3 scripts/move_long_samples_to_hold.py --min-seconds 90 --apply
```

### Tests

- `tests/test_jambox_config.py` — `LONG_HOLD_DIR`, `LONG_HOLD_MIN_SECONDS` defaults, `is_long_hold_rel_path`.

### Deliberately unchanged

- **Web UI library browser** — `_LONG-HOLD` remains visible so users can browse/drag long material.
- **Ingest** — new downloads are not auto-routed into `_LONG-HOLD`; that remains a manual or scripted move after ingest.

---

## Follow-Ups (Optional)

1. `**tag_library.py --path` or `--include-long-hold`** — Today, full `tag_library.py` scans skip `_LONG-HOLD`, so **new** files dropped only into hold without a prior tag row may not get filename/path heuristics until a targeted feature exists. **Smart retag** on a path still works: `python scripts/smart_retag.py --path _LONG-HOLD/`.
2. **Ingest hook** — Optional env threshold to land files over N seconds directly under `_LONG-HOLD` (would need tag DB updates and UX agreement).
3. **Score cache** — Fetch uses `_score_cache.json`; tag DB / `_tags.json` mtime changes after moves should refresh cache keys; no separate version bump was added.
4. **Docs / CLAUDE.md** — Consider a one-line pointer in root project context (Chat-owned); not required for correctness.

---

## Handoff Checklist for the Next Agent

- Confirm `SP404_SAMPLE_LIBRARY` and `SP404_LONG_HOLD_MIN_SECONDS` if defaults are wrong for this machine.
- Run `move_long_samples_to_hold.py` without `--apply` first; review candidate list.
- After `--apply`, spot-check fetch / daily bank behavior if regressions are suspected.
- For LLM tags on hold only: `smart_retag.py --path _LONG-HOLD/` (not bulk `--all`).

---

## Key Files Touched

`scripts/jambox_config.py`, `fetch_samples.py`, `daily_bank.py`, `vibe_retrieval.py`, `smart_retag.py`, `tag_library.py`, `dedup_library.py`, `library_health.py`, `convert_to_flac.py`, `stem_split.py`, `move_long_samples_to_hold.py`, `tests/test_jambox_config.py`.