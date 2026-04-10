# CODE BRIEF: Post-Ship Bug Fixes & Doc Sync

**Date:** April 3, 2026
**Agent:** Code (Cursor)
**Source:** Bug hunt audit from Chat Session 3
**Priority:** Fix in order listed

---

## Fix 1: PAD_MAP.txt (Root) — ACTIVELY WRONG ON HARDWARE

The root `PAD_MAP.txt` is v1 (numpy-synthesized banks: Lo-Fi Hip-Hop, Witch House, etc.) but `copy_to_sd.sh` copies it to the SD card. Users see completely wrong bank names.

**Action:** Replace root `PAD_MAP.txt` contents with `docs/PAD_MAP.txt` (the v3 layout). Verify `copy_to_sd.sh` line ~40 still references the correct path.

---

## Fix 2: CLAUDE.md Refresh — CODE AGENT READS THIS FIRST

CLAUDE.md is missing everything from Session 2 and 3. Code agent reads this on every session and will make wrong decisions based on stale context.

**Add these sections/updates:**

### New Key Paths
```
training/vibe/             # Vibe training/eval/export/serving scripts
training/vibe/configs/     # QLoRA training configs
training/pattern/          # Pattern training readiness gates
data/evals/                # Seed eval suite (prompt_to_parse, prompt_to_draft, prompt_to_ranking)
data/vibe_sessions.sqlite  # Vibe session store (runtime, gitignored)
scripts/vibe_retrieval.py  # RAG retrieval for vibe parsing
scripts/vibe_training_store.py  # Session persistence (SQLite)
```

### New Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `SP404_VIBE_PARSER_MODE` | Parser mode: base, rag, fine_tuned | `base` |
| `SP404_FINE_TUNED_LLM_ENDPOINT` | Endpoint for fine-tuned model | (disabled) |
| `SP404_FINE_TUNED_LLM_MODEL` | Fine-tuned model name | (disabled) |
| `SP404_VIBE_RETRIEVAL_LIMIT` | Max retrieval examples per query | `4` |

### Vibe Pipeline (NEW)
The personalized vibe intelligence pipeline is on main:
- Parser modes: `base` (keyword fallback), `rag` (retrieval-grounded), `fine_tuned` (LoRA adapter)
- Session logging: every vibe generation creates a session in `data/vibe_sessions.sqlite`
- Editable parsed tags: UI lets user review and correct parsed tags before applying
- Retrieval grounding: prior sessions, preset examples, and library hints inform parsing
- Training pipeline: `training/vibe/` has prepare_dataset, train_lora, eval_model, compare_modes, serve_model

### Updated Bank Layout
Add new presets (once MISSING-1 is resolved):
- riot-mode, minneapolis-machine, outlaw-country-kitchen, karaoke-metal, french-filter-house
- purity-ring-dreams, crystal-chaos, ween-machine, azealia-mode
- big-beat-blowout, synth-pop-dreams, brat-mode (already in repo)

### Library Format
Library is now FLAC (not WAV). 15 GB, ~20,925 files. Ingest converts to FLAC on arrival.

---

## Fix 3: Install 9 Session 2 Presets

Check if `chat_playlist_mining_presets_delivery.zip` was ingested. If not, create the 9 preset YAML files manually in `presets/genre/`. Specs from Session 2 handoff:

| Preset | BPM | Key |
|--------|-----|-----|
| riot-mode | 160 | E |
| minneapolis-machine | 90 | Db |
| outlaw-country-kitchen | 95 | G |
| karaoke-metal | 140 | Em |
| french-filter-house | 122 | Dm |
| purity-ring-dreams | 108 | Ab |
| crystal-chaos | 135 | Fm |
| ween-machine | 110 | C |
| azealia-mode | 130 | Bbm |

Each needs 12 pad descriptions following the established format (pads 1-4 = drum one-shots, 5-12 = loops/melodic). Use the preset template from existing files like `big-beat-blowout.yaml`.

Also create the 5 curated sets in `sets/`:
- songwriting-session, party-mode, genre-explorer, metal-hour, tiger-dust-store

---

## Fix 4: TODO.md Refresh

Replace the entire contents of `docs/TODO.md` with current state from `HANDOFF_SESSION3.md`. Key changes:
- Move Big Beat/Synth-Pop/Brat Mode from "Priority 1" to "Completed" (presets delivered Session 2)
- Move vibe pipeline, training scripts, eval suite, session store to "Completed"
- Add to "Completed": FLAC conversion, storage overhaul, doc patches (Sessions 1-2)
- New "In Progress": Ollama setup, fpcalc install, base vs rag comparison, expand evals
- New "Priority 1": Install Ollama + Qwen3 8B, run baseline metrics
- New "Priority 2": fpcalc dedupe, daily bank smoke test
- New "Priority 3": Download execution (Riot Mode, Minneapolis Machine, Brat Mode, Free Essentials)
- New "Priority 4": Training data pipeline (mine metadata, synthetic examples, human validation)
- Update "Waiting On" with current Cowork brief status

---

## Fix 5: Add Vibe Session History API

Add two endpoints to `web/api/vibe.py`:

```python
@vibe_bp.route("/vibe/sessions")
def list_vibe_sessions():
    """List recent vibe sessions for review and training data curation."""
    limit = request.args.get("limit", 50, type=int)
    status = request.args.get("status")  # optional: raw, reviewed, exported
    rows = vts.list_sessions(limit=limit, dataset_status=status or None)
    return jsonify({"sessions": rows, "total": len(rows)})

@vibe_bp.route("/vibe/sessions/<session_id>/promote", methods=["POST"])
def promote_session(session_id):
    """Change a session's dataset_status (raw → reviewed → exported)."""
    data = request.get_json() or {}
    status = data.get("status", "reviewed")
    if status not in ("raw", "reviewed", "exported"):
        return jsonify({"error": "status must be: raw, reviewed, exported"}), 400
    vts.promote_dataset_status(session_id, status)
    return jsonify({"ok": True, "session_id": session_id, "status": status})
```

This unblocks the "collect real reviewed vibe sessions" workflow.

---

## Fix 6: Training Config Model Alignment

Update `training/vibe/configs/` to use Qwen3 8B (matching the Cowork research recommendation and the default `LLM_MODEL` in config):

- Create `training/vibe/configs/qwen3-8b-qlora.yaml` with `base_model: Qwen/Qwen3-8B-Instruct`
- Create `training/vibe/configs/qwen3-8b-draft-qlora.yaml` with same
- Keep old Qwen2.5 configs as alternatives but update the README/docs to point to Qwen3 as primary

---

## Fix 7: Architecture Doc Update (Low Priority)

Add a "Personalized Vibe Intelligence" section to `docs/ARCHITECTURE.md` covering:
- Session store schema (SQLite, vibe_sessions table)
- Retrieval pipeline (session examples, preset examples, library hints)
- Parser mode switching (base → rag → fine_tuned)
- Training pipeline (prepare_dataset → train_lora → eval_model → serve_model → compare_modes)
- Pattern training readiness gates

---

## Verification Checklist

After fixes, run these to confirm:
```bash
# Tests should all pass
python -m pytest tests/ -v

# Check setup should report no blocking issues
python scripts/check_setup.py

# Eval suite should run clean on base mode
python training/vibe/eval_model.py --mode base

# Verify new presets load
python -c "import preset_utils; print(len(preset_utils.list_presets()))"

# Verify PAD_MAP.txt matches current banks
head -20 PAD_MAP.txt  # should show v3 layout
```
