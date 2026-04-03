# Code Brief: Doc Deliverable Ingest

**Priority:** Medium (establishes the default multi-agent doc delivery workflow)
**Scope:** Extend `scripts/ingest_downloads.py` to handle markdown and text deliverables from Chat and Cowork agents. This becomes the standard path for all deliverables into the repo — not a convenience feature but the default workflow.

---

## Problem

Chat and Cowork produce `.md` and `.txt` deliverables (handoffs, briefs, source catalogs, bug reports, research docs) that currently sit in `~/Downloads` until manually moved into the repo. The audio ingest pipeline already watches Downloads — extend it to handle docs too.

## Design

### Routing Rules

Files are matched by naming convention and routed to the correct destination:

| Pattern | Destination | Example |
|---------|-------------|---------|
| `CLAUDE.md` | Repo root (`./CLAUDE.md`) | Always overwrites, backup old as `CLAUDE.md.bak` |
| `HANDOFF_*.md` | `docs/` | `HANDOFF_SESSION3.md` |
| `BUG_HUNT_*.md` | `docs/` | `BUG_HUNT_SESSION3.md` |
| `CODE_BRIEF_*.md` | `docs/briefs/` | `CODE_BRIEF_bug_fixes.md` |
| `COWORK_BRIEF_*.md` | `docs/briefs/` | `COWORK_BRIEF_riot_mode_downloads.md` |
| `*_SOURCES.txt` | `docs/sources/` | `RIOT_MODE_SOURCES.txt` |
| `SP404_*.md` | `docs/` | `SP404_ECOSYSTEM_RESEARCH.md` |
| `*_Research.md` | `docs/research/` | `Jambox_LLM_Post_Training_Research.md` |
| `_DELIVERY.yaml` | (already handled by audio ingest) | Skip |
| Other `.md` / `.txt` | **Skip + log warning** | Unknown naming convention |

### After Routing

1. Copy the file to its destination
2. Move the original to `~/Downloads/_PROCESSED/` (create if needed)
3. Log the action to `_ingest_log.json` with timestamp, source path, destination path

### CLAUDE.md Special Case

```
if filename == "CLAUDE.md":
    backup existing ./CLAUDE.md to ./CLAUDE.md.bak
    copy new CLAUDE.md to repo root
    log: "CLAUDE.md updated (backup at CLAUDE.md.bak)"
```

### Integration Points

- Hook into the existing `ingest_downloads.py` file processing loop
- Run doc routing **before** audio processing (docs are fast, don't block audio ingest)
- The `--watch` mode should pick up docs the same way it picks up audio files
- Add a `--docs-only` flag for dry-run testing: `python scripts/ingest_downloads.py --docs-only`

### Skip Logic

- Ignore files already present at destination with identical content (md5 check)
- Ignore anything in `_PROCESSED/` or `_RAW-DOWNLOADS/` subdirectories
- Ignore hidden files (`.DS_Store`, etc.)
- Log but skip any `.md` / `.txt` that doesn't match a known pattern — don't silently drop it

## Implementation Notes

- Keep the routing table as a list of `(regex, destination)` tuples near the top of the file so it's easy to extend when new naming conventions appear
- Use `shutil.copy2` to preserve timestamps
- Create destination subdirectories (`docs/briefs/`, `docs/sources/`, `docs/research/`) if they don't exist
- The `_PROCESSED/` folder mirrors `_RAW-DOWNLOADS/` in spirit — receipts for what came in and where it went

## Verification

After implementing, test with:
```bash
# Simulate a doc drop
cp /path/to/HANDOFF_SESSION3.md ~/Downloads/
python scripts/ingest_downloads.py --docs-only

# Verify
ls docs/HANDOFF_SESSION3.md          # should exist
ls ~/Downloads/_PROCESSED/            # should contain original
cat _ingest_log.json | tail -1        # should show the routing
```

## Files to Modify

- `scripts/ingest_downloads.py` — add doc routing logic
- Create dirs if needed: `docs/briefs/`, `docs/sources/`, `docs/research/`
- `.gitignore` — add `CLAUDE.md.bak` if not already ignored
