# Stabilization Baseline

Date: 2026-04-05

## Environment Snapshot

- Command: `python3 --version`
  - Result: `Python 3.14.3`
- Command: `python3 scripts/check_setup.py`
  - Result: failed with 6 blocking issues (missing Python modules in active interpreter).
  - Missing modules: `Flask`, `mutagen`, `numpy`, `PyYAML`, `requests`, `watchdog`
  - Tooling present: `ffmpeg`, `ffprobe`, `unar`, `fpcalc`
  - LLM endpoint and parser mode configured and reachable.
- Command: `python3 -m pytest -q`
  - Result: `No module named pytest`

## Baseline Test Readiness

- Full automated test run is currently blocked in the active Python environment.
- Existing repository tests cannot be executed until dependencies are installed in the runtime interpreter/venv.

## Known Contract Inconsistencies (Pre-Edit)

- API response envelope is inconsistent across blueprints (`ok` flag present in some routes only).
- Status code semantics vary for similar validation paths (400 vs 404 vs 200 with embedded error payload).
- Multiple user-facing code paths still contain silent `except Exception: pass`.
- Config load behavior differs across CLI/API call sites (`bank_config.yaml` strict vs lenient fallbacks).
- Tag DB read assumptions differ by module (`load_tag_db` usage vs direct `_tags.json` reads).

## High-Risk Interop Zones

- Async in-memory job maps in:
  - `web/api/pipeline.py`
  - `web/api/vibe.py`
  - `web/api/library.py`
  - `web/api/music.py`
  - `web/api/media.py`
- Runtime/training handoff:
  - `web/api/vibe.py`
  - `scripts/vibe_training_store.py`
  - `training/vibe/prepare_dataset.py`
- Data lifecycle + ingest:
  - `scripts/ingest_downloads.py`

## Repro Commands

- `python3 --version`
- `python3 scripts/check_setup.py`
- `python3 -m pytest -q`
