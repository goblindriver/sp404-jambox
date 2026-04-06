# Enrichment Process Inspection

This document implements the enrichment process observability plan: process map, health scorecard, artifact semantics, runbook, validation gaps, and a baseline inspection snapshot.

## 1) Process Map (Enrichment Flows)

### `scripts/ingest_downloads.py`

- Trigger: CLI one-shot (`python scripts/ingest_downloads.py`) or watcher (`--watch`), plus `POST /api/pipeline/ingest`.
- Inputs: `~/Downloads`, archives/audio/docs, optional `_SOURCE.txt` and `_DELIVERY.yaml`.
- Writes: library audio files, `~/Music/SP404-Sample-Library/_ingest_log.json`, `_RAW-DOWNLOADS` archive, tag DB updates via `tag_library` + optional `smart_retag`.
- Telemetry: console lines (`[ROUTE]`), ingest log entries (timestamp/source/samples/categories), watcher state in-memory.
- Failure modes: archive extraction issues, ffmpeg/demucs/tool path failures, duplicate move errors, noisy/failed inline smart-retag calls.

### `scripts/tag_library.py`

- Trigger: direct CLI (`--update` incremental/full), called from ingest route.
- Inputs: sample library files + filename/path heuristics + optional librosa analysis.
- Writes: canonical tag DB via `jambox_config.save_tag_db()` (SQLite primary, JSON compatibility).
- Telemetry: console progress + aggregate counts.
- Failure modes: heuristic misclassification, missing ffprobe/librosa degradation, stale rows if run against partial library snapshots.

### `scripts/smart_retag.py`

- Trigger: direct CLI (`--all`, `--resume`, `--path`, validation modes), optional per-file inline call from ingest.
- Inputs: tag DB row + audio features + LLM endpoint/model config.
- Writes: enriched tag fields, `data/retag_checkpoint.json`, optional `_QUARANTINE` routing logic.
- Telemetry: checkpoint counters (`processed/tagged/errors`), `llm_stats` (`success/parse_fail/empty/...`), console warnings.
- Failure modes: LLM latency/parse failures, duplicate concurrent runs, checkpoint drift vs real DB state.

### `scripts/stem_split.py`

- Trigger: direct CLI or queued by ingest for long files.
- Inputs: full tracks, demucs model, parent tag metadata.
- Writes: `Stems/<source>/`, inherited stem tag rows (type/playability/source linkage).
- Telemetry: demucs output + split marker behavior.
- Failure modes: demucs missing/timeouts, pre-convert failures, incorrect stem path classification.

### `scripts/ingest_multitracks.py`

- Trigger: CLI scan/ingest (`--scan`, `--artist`, `--all`).
- Inputs: multitrack session roots (`QNAP/H4N/Film`), WAV stem names.
- Writes: converted FLAC stems in library categories + tag DB rows with provenance.
- Telemetry: scan counts, ingest counts, console summary.
- Failure modes: weak filename stem inference, category drift, source roots unavailable.

### `scripts/fetch_samples.py`

- Trigger: CLI fetch, `pipeline.execute_fetch_scope()`, vibe populate/generate-fetch-bank endpoints.
- Inputs: `bank_config.yaml`/preset pad text + tag DB + scoring config + diversity history.
- Writes: `_CARD_STAGING`, `sd-card-template/.../SMPL`, `data/fetch_history.json`, score cache in library root.
- Telemetry: fetch success/fail counts, candidate scoring behavior, diversity cooldown effects.
- Failure modes: stale or malformed tag DB, conversion failures, cache write instability, low-confidence pad candidates.

### `web/api/library.py`

- Trigger: UI/API (`/api/library/tags`, `/by-tag`, `/browse`, `/search`).
- Inputs: in-memory cached DB loaded from SQLite/JSON freshness marker.
- Writes: none (read-only API), cache memory in process.
- Telemetry: API responses reflect current dimensional distributions.
- Failure modes: stale cache if mtime logic misses edge cases, DB loader fallback masking SQLite read errors.

### `web/api/pipeline.py`

- Trigger: API control plane (`/pipeline/fetch`, `/ingest`, `/patterns`, `/padinfo`, `/deploy`).
- Inputs: request payload + app config + script subprocesses.
- Writes: job status in memory + delegated script outputs.
- Telemetry: job state (`starting/running/done/error`, progress strings), response payloads.
- Failure modes: 409 contention while fetch running, script timeout/failure propagation, subprocess env path issues.

### `web/api/vibe.py`

- Trigger: `/vibe/generate`, `/vibe/populate-bank`, `/vibe/generate-fetch-bank`, `/vibe/apply-bank`.
- Inputs: prompt or metadata-built prompt + parser mode + preset payload review.
- Writes: vibe session DB, preset save/load, fetch via pipeline execute scope.
- Telemetry: vibe job state/progress, fallback flags, fetched ratio, persisted session data.
- Failure modes: LLM timeout/fallback frequency, invalid reviewed payloads, background job contention.

### `scripts/jambox_config.py` (shared control plane)

- Trigger: imported by scripts/APIs.
- Inputs: `.env`, defaults, path settings.
- Writes: tag DB persistence (`_tags.sqlite` + optional `_tags.json`), atomic JSON/YAML writes.
- Telemetry: migration warning prints and stale-delete guard warnings.
- Failure modes: partial save attempts, config variable invalidity, filesystem edge cases on atomic writes.

## 2) Health Scorecard (Pass/Fail Thresholds)

Use this scorecard for go/no-go decisions before major fetch/reseed work.


| Dimension          | Metric                                                          | Pass                      | Warn                        | Fail                      |
| ------------------ | --------------------------------------------------------------- | ------------------------- | --------------------------- | ------------------------- |
| Process alive      | expected process present + recent output                        | alive + <15m stale output | alive + 15-60m stale output | missing/crashed process   |
| Progress moving    | artifact timestamp freshness                                    | <30m old when run active  | 30-120m                     | >120m with active process |
| Enrichment quality | dimensional coverage (`vibe/texture/genre/energy`)              | >=95% rows populated      | 80-95%                      | <80%                      |
| Enrichment quality | high-value smart fields (`quality_score` + `sonic_description`) | >=25% rows populated      | 5-25%                       | <5%                       |
| DB integrity       | row parity (loader vs sqlite vs json)                           | exact match               | <=1% mismatch               | >1% mismatch              |
| DB integrity       | missing file paths in DB                                        | <0.5%                     | 0.5-2%                      | >2%                       |
| DB integrity       | forbidden legacy types (`SMP`)                                  | 0 rows                    | n/a                         | >0 rows                   |
| Fetch fitness      | low-rank audit red pad ratio                                    | 0%                        | <=3%                        | >3%                       |
| Fetch fitness      | low-rank audit avg conversion success                           | >=0.95                    | 0.85-0.95                   | <0.85                     |


## 3) Artifact Semantics and Caveats

### `data/retag_checkpoint.json`

- Meaning: runtime heartbeat for smart-retag batches (`processed/tagged/errors/llm_stats` + processed file sample).
- Caveat: reflects one run/batch, not guaranteed full-library coverage; can look "healthy" while smart fields are sparse.

### `~/Music/SP404-Sample-Library/_ingest_log.json`

- Meaning: append-style ingest events (`timestamp`, `source`, `samples`, category distribution).
- Caveat: activity signal only; does not guarantee downstream tag quality or fetch fitness.

### `data/audit_reports/low_rank_*.json`

- Meaning: per-pad confidence (`top_score`, `top2_gap`, `type_match_ratio`, `conversion_success_rate`, severity).
- Caveat: deterministic mode removes diversity variance; non-deterministic runtime can still pick lower-ranked viable candidates.

### `data/fetch_history.json`

- Meaning: last-used timestamps used to apply diversity cooldown penalties.
- Caveat: can contain stale/non-library paths; influences selection even when ranking is unchanged.

### Tag DB stores (`_tags.sqlite` + `_tags.json`)

- Meaning: canonical DB is SQLite; JSON is compatibility copy when size/IO allows.
- Caveat: always validate SQLite parity and row counts; JSON may lag if write skipped.

## 4) Operator Runbook (Inspect First)

1. Confirm process liveness and resource posture.
  - `ps -axo pid,pcpu,pmem,etime,command | rg "smart_retag.py|ingest_downloads.py --watch|web/app.py"`
2. Check artifact freshness/counters.
  - `data/retag_checkpoint.json` (`last_updated`, `processed/tagged/errors`, `llm_stats`)
  - `_ingest_log.json` last event timestamp/source.
3. Sample live quality/noise signals.
  - Parse-fail/empty rates from checkpoint `llm_stats`.
  - Unexpected warning bursts in active terminal output.
4. Validate DB integrity.
  - loader/sqlite/json row parity, missing path scan, excluded-path contamination, forbidden type codes.
5. Validate enrichment quality.
  - dimensional coverage (`vibe/texture/genre/energy`) and high-value smart field coverage (`quality_score`, `sonic_description`).
6. Run fetch fitness checkpoint only after substantial DB edits.
  - `.venv/bin/python3 scripts/low_rank_audit.py --deterministic --out ... --out-md ...`
7. Classify blockers into:
  - config/infra
  - parsing quality
  - taxonomy drift
  - file-layout anomalies

## 5) Validation Coverage and Gaps

Current tested coverage:

- `tests/test_pipeline_scripts.py`
  - fetch scoring/cache behavior basics
  - low-rank severity logic and confidence fields
  - tag hygiene scan/apply logic
  - ingest download edge cases (missing dirs, command failures)
- `tests/test_smart_features.py`
  - vibe/pattern/preset API contract and error-path behavior
  - job lifecycle and payload validation for smart endpoints
- Scripted audit tools:
  - `scripts/library_health.py` (audio health and BPM gap checks)
  - `scripts/low_rank_audit.py` (fetch fitness confidence report)
  - `scripts/tag_hygiene.py` (folder/type drift detection and safe rewrites)

Missing high-impact checks:

- End-to-end integration assertion: ingest -> smart-retag -> DB -> fetch outcome quality in one automated test.
- Artifact monotonicity test: checkpoint counters/timestamps should only move forward during active runs.
- DB parity guard test: simulate partial in-memory DB and verify stale-delete guard behavior remains safe.
- Fetch diversity regression test under real `fetch_history` contamination and cooldown edge cases.
- Concurrency test for cache persistence on external volumes (score cache/fingerprint cache).

## 6) Baseline Inspection (2026-04-06)

Snapshot generated from live artifacts and one deterministic fetch-fitness audit.

### Process + artifact liveness

- Smart-retag process detected (`scripts/smart_retag.py --resume`), but CPU near idle at sample time.
- Ingest watcher process detected (`scripts/ingest_downloads.py --watch --interval 120`).
- `retag_checkpoint.last_updated`: `2026-04-06T00:35:17.656958` (stale vs active process at capture time).
- Ingest log latest event: `2026-04-05T21:44:25.990153` (`Doc zip: murdercrab-main.zip`).

### DB integrity baseline

- Row parity: loader `31103`, SQLite `31103`, JSON `31103` (PASS).
- Missing file paths: `0` (PASS).
- Excluded/triage path contamination (`_RAW-DOWNLOADS`, `_DUPES`, `_QUARANTINE`, `_LONG-HOLD`, `Stems`): `0` (PASS).
- Forbidden legacy type `SMP`: `0` (PASS).

### Enrichment quality baseline

- Dimensional coverage:
  - `vibe/texture/genre/energy/instrument_hint`: `100%` rows populated.
  - `quality_score`: `558 / 31103` (`1.79%`).
  - `sonic_description`: `558 / 31103` (`1.79%`).
- Interpretation: broad dimensions are fully populated, but high-value smart fields remain sparse (FAIL by scorecard threshold).

### Fetch fitness baseline

- Command: `.venv/bin/python3 scripts/low_rank_audit.py --deterministic --out data/audit_reports/low_rank_baseline.json --out-md data/audit_reports/low_rank_baseline.md`
- Summary:
  - total pads: `108`
  - severity: `red=1`, `yellow=2`, `green=105`
  - avg top score: `22.458`
  - avg top2 gap: `2.602`
  - avg type match ratio: `0.981`
  - avg conversion success rate: `1.0`
- Flagged pads:
  - `B10` (RED): `FX block lo-fi one-shot`
  - `B01` (YELLOW): `KIK lo-fi rock one-shot`
  - `B02` (YELLOW): `SNR rock aggressive one-shot`

### Prioritized findings backlog

1. **P1 - Smart enrichment depth gap**
  - `quality_score` and `sonic_description` only `1.79%` coverage.
  - Action: run/monitor controlled smart-retag batches focused on unscored rows and verify coverage increases by checkpoint deltas.
2. **P1 - Retag liveness ambiguity**
  - Active process exists but checkpoint timestamp appears stale.
  - Action: enforce heartbeat expectation in runbook (fail if active process + stale checkpoint >120m), inspect terminal output for hang/blocked I/O.
3. **P2 - Single red pad fetch-risk**
  - `B10` remains red in deterministic low-rank audit.
  - Action: targeted pad prompt/type tightening and candidate pool cleanup, then re-audit.
4. **P2 - Cache persistence reliability**
  - Baseline run initially failed on score cache atomic replace on external volume.
  - Action: keep the new temp-file retry path in `scripts/jambox_cache.py` and observe recurrence frequency.