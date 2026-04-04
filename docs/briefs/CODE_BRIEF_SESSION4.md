# CODE BRIEF — Session 4
**Date:** 2026-04-04
**From:** Chat (Claude)
**To:** Code Agent
**Project:** Jambox (SP-404A Sample Production System)
**Urgency:** HIGH — ARCH-1 is on a ~15-day timer

---

## System State

- Smart retag is running: qwen3:32b, ~42s/file, ~30,718 files total, ~250 processed
- 38% error rate on processed files — needs investigation
- Retag is writing to `_tags.json` — this file will not scale and must be migrated before retag completes
- Plugin v0.1.1 revision doc exists from Session 3 (`PLUGIN_REVISION_v0.1.1.md`)
- Freesound API has been removed from project scope
- Sub pad is a hardware retrigger button, NOT a 13th sample slot (120 pads total, not 130)

---

## Task 1: ARCH-1 — SQLite Migration (CRITICAL)

### Problem
`_tags.json` is the current tag store. With 30K+ files being retagged, this becomes a single massive JSON blob that is:
- Slow to read/write at scale
- Race-condition prone if multiple processes touch it
- Not queryable (can't filter by tag, vibe, genre without loading everything into memory)
- Fragile — one corrupt write kills the whole file

### Requirements

**Schema Design:**
```sql
-- Core sample metadata
CREATE TABLE samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT UNIQUE NOT NULL,      -- relative to library root
    filename TEXT NOT NULL,
    format TEXT,                         -- wav, aiff, etc.
    sample_rate INTEGER,
    bit_depth INTEGER,
    duration_ms INTEGER,
    file_hash TEXT,                      -- for dedup (fpcalc or xxhash)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tags from smart retag (many-to-one with samples)
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    tag_key TEXT NOT NULL,               -- e.g. 'genre', 'vibe', 'instrument', 'energy'
    tag_value TEXT NOT NULL,             -- e.g. 'house', 'warm', 'synth_pad', 'high'
    confidence REAL,                     -- model confidence if available
    model_version TEXT,                  -- 'qwen3:32b' etc.
    tagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sample_id, tag_key, tag_value)
);

-- Preset/bank assignments
CREATE TABLE pad_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER NOT NULL REFERENCES samples(id),
    preset_name TEXT NOT NULL,           -- e.g. 'tiger-dust-block-party'
    bank TEXT NOT NULL,                  -- A-J
    pad INTEGER NOT NULL,               -- 1-12
    UNIQUE(preset_name, bank, pad)
);

-- Tag taxonomy reference
CREATE TABLE taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_key TEXT NOT NULL,
    tag_value TEXT NOT NULL,
    parent_value TEXT,                   -- for hierarchical tags
    description TEXT,
    UNIQUE(tag_key, tag_value)
);

-- Indexes
CREATE INDEX idx_tags_key_value ON tags(tag_key, tag_value);
CREATE INDEX idx_tags_sample ON tags(sample_id);
CREATE INDEX idx_samples_filepath ON samples(filepath);
CREATE INDEX idx_samples_hash ON samples(file_hash);

-- CLAP audio embeddings (per Cowork CLAP research — laion/larger_clap_music, 512-dim)
-- Separate table to avoid bloating tag queries
CREATE TABLE clap_embeddings (
    sample_id INTEGER PRIMARY KEY REFERENCES samples(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL,             -- 512 x float32 = 2KB per sample
    model_name TEXT DEFAULT 'laion/larger_clap_music',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Migration Strategy:**
1. Build the SQLite DB alongside `_tags.json` — do NOT delete the JSON yet
2. Write a migration script that reads existing `_tags.json` and populates the DB
3. Modify the retag pipeline to write to BOTH `_tags.json` and SQLite during transition
4. Once migration is verified and retag completes, flip reads to SQLite-only
5. Archive `_tags.json` as backup, stop writing to it

**Key Constraints:**
- Retag is actively running — migration must not interrupt or corrupt the run
- DB file location: `{repo_root}/data/jambox.db`
- Use Python `sqlite3` stdlib — no external ORM dependency
- Provide a `db.py` module with helper functions: `get_sample()`, `upsert_tags()`, `query_by_tag()`, `assign_pad()`, etc.
- All writes should use transactions
- Include a `migrate_from_json.py` one-shot script

**Deadline:** Must be functional before retag finishes (~15 days from now, early-to-mid April)

---

## Task 2: Error Rate Triage

### Problem
38% of the first 250 retagged files are erroring. That's ~95 failures. If this rate holds, we lose ~11,600 files.

### Action
1. Pull retag logs and categorize failures into buckets:
   - **Model output parse failure** — qwen3:32b returning malformed JSON, extra tokens, markdown fencing, etc.
   - **Model timeout / OOM** — M3 iMac has 24GB unified memory, qwen3:32b may be tight
   - **File read errors** — corrupt WAV, unreadable metadata, unsupported format
   - **Schema validation** — model returns valid JSON but wrong shape (missing keys, bad types)
   - **Other**
2. Report distribution across buckets
3. For the top failure bucket, implement a fix:
   - If parse failure: add output sanitization (strip markdown fences, extract JSON from mixed output, retry with stricter prompt)
   - If OOM: consider batch size reduction or model swap for large files
   - If schema validation: tighten the prompt with explicit JSON schema, add validation + retry loop
4. Re-run failed files after fix and report new error rate

### Deliverable
- Error rate report (bucket counts + example failures)
- Patch PR for the top failure mode
- Re-run script for failed files only

---

## Task 3: Plugin v0.1.1 Fixes

### Reference
See `PLUGIN_REVISION_v0.1.1.md` from Session 3.

### Critical Fixes
1. **Sub pad correction:** Sub pad is a hardware retrigger button on the SP-404A. It is NOT a 13th sample slot. Any code or documentation treating sub pad as a programmable pad must be corrected. Total pad count = 120 (banks A–J × 12 pads), not 130.

2. **Freesound removal:** All Freesound API references, imports, config, and sample-sourcing code paths must be removed. This includes:
   - Any API key config
   - Freesound search/download functions
   - References in documentation or help text
   - Any fallback logic that routes to Freesound

3. **Folder structure:** SP-404A uses the SP-404SX folder structure on SD card. Verify all file path logic matches this.

### Deliverable
- Clean PR with sub pad fix, Freesound removal, folder structure verification
- Updated tests if applicable

---

## Task 4: Downloads Watcher — Expand to Route Non-Audio Files

### What Exists Today
`ingest_downloads.py --watch` is built and checked off in TODO. It uses Python watchdog, has stable file detection, reads `_SOURCE.txt` files, auto-tags audio, writes to `_ingest_log.json`, and has a web UI toggle + activity feed. This handles **audio sample intake** well.

### The Gap
The watcher currently handles audio files (WAV, FLAC, etc.) but does NOT appear to route non-audio files. The multi-agent workflow produces:
- `CODE_BRIEF_*.md` → should route to `{repo}/docs/`
- `COWORK_BRIEF_*.md` → should route to `{repo}/docs/`
- `HANDOFF_*.md`, `*_SPEC.md` → should route to `{repo}/docs/`
- `*_Research.md` → should route to `{repo}/docs/` (Cowork research deliverables)
- `*.yaml` preset files → should route to `{repo}/presets/` or `{repo}/sets/`
- Transcripts → should route to `{repo}/docs/`

Right now Jason manually drags these between agents. That breaks the flow.

### Requested Enhancement
Add a document routing layer to the existing watcher:

| Pattern | Destination |
|---------|------------|
| `CODE_BRIEF_*`, `COWORK_BRIEF_*` | `{repo}/docs/` |
| `HANDOFF_*`, `*_SPEC.md`, `*_PLAN.md` | `{repo}/docs/` |
| `*_Research.md`, `*_Survey.md` | `{repo}/docs/` |
| `*.yaml` (with preset/set structure) | `{repo}/presets/` or `{repo}/sets/` (validate schema) |
| `CLAUDE.md` | `{repo}/` root |
| Audio files (existing) | Existing audio pipeline (no change) |
| Unknown | `_staging/_unsorted/` + log entry |

### Constraints
- Don't break existing audio intake — this is additive
- Log all routing decisions to `_ingest_log.json` (same log, new event types)
- Surface doc routing in the web UI activity feed if possible

### Deliverable
PR that adds document routing to the existing watcher. Should work with current `--watch` flag.

---

## Research Input: UTS (Unified Tag System) — From Cowork

Cowork delivered a research brief on the Unified Tag System (CVPR 2026). Key takeaways that affect Code's work:

1. **Caption quality is the #1 driver of tag quality** — if the 38% error rate is mostly parse/output issues, the fix is prompt engineering on qwen3:32b, not retry loops. Investigate with this lens.
2. **Scene/environment dimension** — UTS proves a "scene" tag (club, outdoor, lo-fi room, etc.) carries signal. The SQLite schema already supports this via the flexible key-value tag structure (`tag_key = 'scene'`), but the retag prompt and taxonomy should be aware of it.
3. **TF-IDF vocabulary emergence** — once SQLite is live and retag finishes, run a TF-IDF pass on all `sonic_description` values to surface tags the fixed schema misses. This becomes the v2 taxonomy.
4. **Free eval data** — the AudenAI/UTS dataset (MIT license, 400K clips) can serve as calibration. Run a sample through the Jambox tagger and compare outputs to UTS ground truth for baseline accuracy.
5. **Full research brief:** `docs/research/Unified_Tag_System_Research.md` (once watcher routes it, or manually place it)

---

## Environment Reminders
- **Hardware:** M3 iMac, 24GB unified memory
- **Repo:** `/Users/jasongronvold/Desktop/SP-404SX/sp404-jambox/`
- **Library:** `~/Music/SP404-Sample-Library/` (~30,718 files)
- **Active model:** qwen3:32b via Ollama (assumed local)
- **Retag is running** — do not restart, redeploy, or do anything that kills the process
- **Banks A–B** are internal memory on the SP-404A (survive SD card swaps)

---

## Task 5: Docs Reorganization

### Context
`docs/` is a flat directory with 62 files, 4 competing naming conventions, and no subdirectories. Chat has created `CONVENTIONS.md` (the naming/folder rules) and `docs_reorg.sh` (a dry-run-by-default migration script).

### Action
1. Review `CONVENTIONS.md` — it defines folder structure, naming rules, lifecycle, and watcher routing patterns
2. Run `docs_reorg.sh` in dry-run mode first: `bash docs/docs_reorg.sh`
3. Review output, then execute: `DRY_RUN=0 bash docs/docs_reorg.sh`
4. Fix any internal cross-references that break (grep for old filenames in scripts, CLAUDE.md, etc.)
5. Update `.gitignore` if needed
6. When implementing watcher expansion (Task 4), use the routing table from CONVENTIONS.md
7. Watcher should normalize incoming filenames to SCREAMING_SNAKE_CASE on ingest

### Deliverable
- Clean `docs/` folder matching the structure in CONVENTIONS.md
- PR with the reorg + any broken reference fixes

---

## Priority Order
1. **Error rate triage** — fast, unblocks confidence in the retag run
2. **Docs reorg** — fast, run the script, fix broken refs
3. **Watcher expansion** — add doc routing per CONVENTIONS.md routing table
4. **ARCH-1 SQLite migration** — critical path, ~15 day deadline
5. **Plugin v0.1.1** — important but not blocking anything active

---

*End of brief. Report back with error rate findings first, then docs reorg, then SQLite migration PR.*
