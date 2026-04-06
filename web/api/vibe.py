"""Natural-language vibe generation API."""

import json
import os
import subprocess
import sys
import threading
import uuid

from flask import Blueprint, current_app, jsonify, request

from jambox_config import build_subprocess_env
import vibe_training_store as vts


vibe_bp = Blueprint("vibe", __name__)

# Job tracking for populate-bank (shared with pipeline.py pattern)
_vibe_jobs = {}
_vibe_lock = threading.Lock()


def _update_vibe_job(job_id, **fields):
    with _vibe_lock:
        job = _vibe_jobs.get(job_id)
        if not job:
            return
        job.update(fields)


def _get_vibe_job(job_id):
    with _vibe_lock:
        job = _vibe_jobs.get(job_id)
        return dict(job) if isinstance(job, dict) else None


def _json_object_body():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


def _normalize_prompt(payload):
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required")
    payload = dict(payload)
    payload["prompt"] = prompt.strip()
    return payload


def _normalize_bank(bank):
    bank = str(bank or "a").lower().strip()
    if len(bank) != 1 or bank not in "abcdefghij":
        raise ValueError(f"Invalid bank: {bank}")
    return bank


def _build_metadata_prompt(bank, repo_dir):
    """Build a metadata-first prompt from current bank + preset context."""
    scripts_dir = os.path.join(repo_dir, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import preset_utils as pu

    config = pu._load_config()
    bank_key = f"bank_{bank}"
    bank_data = config.get(bank_key, {}) if isinstance(config, dict) else {}
    preset_ref = str(bank_data.get("preset") or "").strip()
    preset_data = None
    if preset_ref:
        try:
            preset_data = pu.load_preset(preset_ref, require_full_pads=True)
        except ValueError:
            preset_data = None

    parts = [
        f"Bank {bank.upper()}",
        f"name: {bank_data.get('name') or ''}",
        f"notes: {bank_data.get('notes') or ''}",
        f"bpm: {bank_data.get('bpm') or ''}",
        f"key: {bank_data.get('key') or ''}",
    ]
    if preset_ref:
        parts.append(f"preset: {preset_ref}")
    if preset_data:
        parts.append(f"preset_vibe: {preset_data.get('vibe') or ''}")
        tags = preset_data.get("tags") or []
        if tags:
            parts.append(f"preset_tags: {', '.join(str(t) for t in tags[:12])}")
    return " | ".join(part for part in parts if str(part).strip())


def _normalize_preset_payload(payload):
    preset = payload.get("preset")
    if not isinstance(preset, dict):
        raise ValueError("preset is required")

    pads = preset.get("pads")
    if not isinstance(pads, dict) or not pads:
        raise ValueError("preset.pads must be an object")

    normalized_pads = {}
    for key, value in pads.items():
        try:
            pad_num = int(key)
        except (TypeError, ValueError) as exc:
            raise ValueError("preset.pads keys must be pad numbers") from exc
        if pad_num < 1 or pad_num > 12:
            raise ValueError("preset.pads keys must be between 1 and 12")
        if not isinstance(value, str):
            raise ValueError("preset.pads values must be strings")
        normalized_pads[pad_num] = value.strip()

    return {
        "name": str(preset.get("name") or "Vibe Draft").strip() or "Vibe Draft",
        "slug": str(preset.get("slug") or "vibe-draft").strip() or "vibe-draft",
        "author": str(preset.get("author") or "jambox-vibe").strip() or "jambox-vibe",
        "bpm": preset.get("bpm"),
        "key": preset.get("key"),
        "vibe": str(preset.get("vibe") or "").strip(),
        "notes": str(preset.get("notes") or "").strip(),
        "source": str(preset.get("source") or "vibe-generated").strip() or "vibe-generated",
        "tags": preset.get("tags") if isinstance(preset.get("tags"), list) else [],
        "pads": normalized_pads,
    }


def _normalize_reviewed_parsed(payload):
    reviewed = payload.get("reviewed_parsed")
    if reviewed is None:
        return None
    if not isinstance(reviewed, dict):
        raise ValueError("reviewed_parsed must be an object")

    normalized = {}
    for key in ("keywords", "vibe", "genre", "texture", "energy"):
        value = reviewed.get(key, [])
        if value is None:
            normalized[key] = []
            continue
        if isinstance(value, str):
            normalized[key] = [item.strip().lower() for item in value.split(",") if item.strip()]
            continue
        if isinstance(value, list):
            normalized[key] = [str(item).strip().lower() for item in value if str(item).strip()]
            continue
        raise ValueError(f"reviewed_parsed.{key} must be a list or comma-separated string")

    for key in ("type_code", "playability"):
        value = reviewed.get(key)
        normalized[key] = str(value).strip() if value not in (None, "") else None

    rationale = reviewed.get("rationale", "")
    normalized["rationale"] = str(rationale).strip() if rationale is not None else ""
    return normalized


def _parse_script_json(stdout):
    payload = json.loads((stdout or "").strip())
    if not isinstance(payload, dict):
        raise ValueError("Script output must be a JSON object")
    return payload


def _script_error_payload(result, default_message):
    try:
        payload = _parse_script_json(result.stdout)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    error_message = payload.get("error")
    if not isinstance(error_message, str) or not error_message.strip():
        error_message = (result.stderr or result.stdout or default_message).strip()

    response = {
        "ok": False,
        "error": error_message,
    }
    if payload.get("error_code"):
        response["error_code"] = payload["error_code"]
    if payload.get("detail"):
        response["detail"] = payload["detail"]
    return response


@vibe_bp.route("/vibe/generate", methods=["POST"])
def generate_vibe():
    try:
        payload = _normalize_prompt(_json_object_body())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    repo_dir = current_app.config["REPO_DIR"]
    script = os.path.join(repo_dir, "scripts", "vibe_generate.py")
    try:
        result = subprocess.run(
            [sys.executable, script],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=repo_dir,
            env=build_subprocess_env(current_app.config),
            timeout=current_app.config.get("LLM_TIMEOUT", 30) + 5,
        )
        if result.returncode != 0:
            return jsonify(_script_error_payload(result, "Vibe generation failed")), 500
        result_payload = _parse_script_json(result.stdout)
        session_id = vts.create_session(payload, result_payload, current_app.config)
        return jsonify({"ok": True, "session_id": session_id, "result": result_payload})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Vibe generation timed out"}), 500
    except (json.JSONDecodeError, ValueError) as exc:
        return jsonify({"ok": False, "error": f"Invalid script output: {exc}"}), 500
    except OSError as exc:
        return jsonify({"ok": False, "error": f"Vibe generation failed to start: {exc}"}), 500


def _run_populate_bank(job_id, repo_dir, prompt_data, settings, preset_override=None, session_id=None):
    """Background worker: generate preset from vibe, load into bank, fetch samples."""
    try:
        scripts_dir = os.path.join(repo_dir, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import vibe_generate
        import preset_utils as pu
        from api import pipeline as pipeline_api

        if preset_override is None:
            _update_vibe_job(job_id, status="generating", progress="Asking LLM to parse your vibe...")
            result = vibe_generate.build_bank_from_vibe(prompt_data)
            preset = result["preset"]
            if session_id:
                vts.update_generated(session_id, result, settings)
            else:
                # Capture generated parse/draft even if initial session creation failed.
                try:
                    session_id = vts.create_session(prompt_data, result, settings)
                    _update_vibe_job(job_id, session_id=session_id)
                except Exception as exc:
                    print(f"[VIBE] Failed to backfill session for job {job_id}: {exc}")
            _update_vibe_job(
                job_id,
                fallback_used=result.get("fallback_used", False),
                fallback_reason=result.get("fallback_reason"),
                progress=f"Generated {len(preset['pads'])} pad descriptions",
            )
        else:
            preset = preset_override
            _update_vibe_job(
                job_id,
                status="reviewed",
                progress=f"Applying reviewed draft with {len(preset['pads'])} pads",
            )

        # Step 2: Save as preset
        _update_vibe_job(job_id, status="saving")
        ref = pu.save_preset(preset, category="auto")
        _update_vibe_job(job_id, preset_ref=ref, progress=f"Saved preset: {ref}")

        # Step 3: Load into bank
        bank = prompt_data.get("bank", "a").lower()
        _update_vibe_job(job_id, status="loading")
        pu.load_preset_to_bank(ref, bank, preserve_notes=True)
        _update_vibe_job(job_id, progress=f"Loaded into Bank {bank.upper()}")

        # Step 4: Fetch samples
        if prompt_data.get("fetch", True):
            _update_vibe_job(job_id, status="fetching")
            summary = pipeline_api.execute_fetch_scope(
                settings,
                bank=bank,
                progress_callback=lambda progress, _percent: _update_vibe_job(job_id, progress=progress),
            )
            fetched = summary.get("total_fetched", 0)
            total = summary.get("total_pads", 0)
            _update_vibe_job(job_id, fetched=f"{fetched}/{total}", progress=f"Fetched {fetched}/{total} samples")

        _update_vibe_job(job_id, status="done", progress="Bank populated!")
        if session_id:
            final_job = _get_vibe_job(job_id) or {}
            vts.complete_apply(
                session_id,
                preset,
                ref,
                {"fetched": final_job.get("fetched")},
                final_job.get("progress", "Bank populated!"),
            )

    except Exception as e:
        _update_vibe_job(job_id, status="error", progress=str(e))
        if session_id:
            vts.fail_apply(session_id, str(e))


_MAX_JOBS = 50


def _prune_finished_jobs():
    """Remove oldest finished jobs when over the limit. Call inside _vibe_lock."""
    finished = [(jid, j) for jid, j in _vibe_jobs.items() if j.get("status") in ("done", "error")]
    if len(finished) > _MAX_JOBS:
        for jid, _ in finished[:len(finished) - _MAX_JOBS]:
            _vibe_jobs.pop(jid, None)


def _create_vibe_job(bank, prompt):
    _prune_finished_jobs()
    job_id = str(uuid.uuid4())[:8]
    _vibe_jobs[job_id] = {
        "id": job_id,
        "status": "starting",
        "progress": "",
        "prompt": prompt,
        "bank": bank,
        "session_id": None,
        "preset_ref": None,
        "fetched": None,
        "fallback_used": False,
        "fallback_reason": "",
    }
    return job_id


@vibe_bp.route("/vibe/populate-bank", methods=["POST"])
def populate_bank():
    """Generate a full bank from a vibe prompt: LLM parse → preset → load → fetch."""
    try:
        payload = _json_object_body()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not isinstance(payload.get("prompt"), str) or not payload["prompt"].strip():
        return jsonify({"ok": False, "error": "prompt must be a non-empty string"}), 400

    try:
        bank = _normalize_bank(payload.get("bank", "a"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    with _vibe_lock:
        for j in _vibe_jobs.values():
            if j.get("status") in ("starting", "generating", "saving", "loading", "fetching"):
                return jsonify({"ok": False, "error": "A vibe populate is already running"}), 409
        job_id = _create_vibe_job(bank, payload["prompt"])

    prompt = str(payload["prompt"]).strip()
    if not prompt:
        return jsonify({"ok": False, "error": "prompt is required"}), 400

    prompt_data = {
        "prompt": prompt,
        "bpm": payload.get("bpm"),
        "key": payload.get("key"),
        "bank": bank,
        "fetch": payload.get("fetch", True),
    }

    session_id = None
    session_error = None
    try:
        session_id = vts.create_session(prompt_data, {}, current_app.config)
    except Exception as exc:
        session_error = str(exc)
        current_app.logger.warning("Failed to create vibe populate session: %s", exc)

    repo_dir = current_app.config["REPO_DIR"]
    settings = dict(current_app.config)
    _update_vibe_job(job_id, session_id=session_id)
    t = threading.Thread(target=_run_populate_bank, args=(job_id, repo_dir, prompt_data, settings, None, session_id))
    t.daemon = True
    t.start()

    response = {"ok": True, "job_id": job_id, "session_id": session_id}
    if session_error:
        response["session_warning"] = "Session logging unavailable for this job"
    return jsonify(response)


@vibe_bp.route("/vibe/generate-fetch-bank", methods=["POST"])
def generate_fetch_bank():
    """Metadata-first generation+fetch for one bank."""
    try:
        payload = _json_object_body()
        bank = _normalize_bank(payload.get("bank", "a"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    with _vibe_lock:
        for job in _vibe_jobs.values():
            if job.get("status") in ("starting", "generating", "reviewed", "saving", "loading", "fetching"):
                return jsonify({"ok": False, "error": "A vibe populate is already running"}), 409
        prompt_for_job = str(payload.get("prompt") or "").strip() or f"Bank {bank.upper()} metadata"
        job_id = _create_vibe_job(bank, prompt_for_job)

    repo_dir = current_app.config["REPO_DIR"]
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        prompt = _build_metadata_prompt(bank, repo_dir)
    if not prompt:
        return jsonify({"ok": False, "error": "Unable to derive bank metadata prompt"}), 400

    prompt_data = {
        "prompt": prompt,
        "bpm": payload.get("bpm"),
        "key": payload.get("key"),
        "bank": bank,
        "fetch": payload.get("fetch", True),
    }

    # Merge bpm/key from bank_config when not provided in the request
    if not prompt_data["bpm"] or not prompt_data["key"]:
        scripts_dir = os.path.join(repo_dir, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import preset_utils as pu
        config = pu._load_config()
        bank_data = config.get(f"bank_{bank}", {})
        if isinstance(bank_data, dict):
            if not prompt_data["bpm"]:
                prompt_data["bpm"] = bank_data.get("bpm")
            if not prompt_data["key"]:
                prompt_data["key"] = bank_data.get("key")

    session_id = None
    session_error = None
    try:
        session_id = vts.create_session(prompt_data, {}, current_app.config)
    except Exception as exc:
        session_error = str(exc)
        current_app.logger.warning("Failed to create metadata generate/fetch session: %s", exc)

    settings = dict(current_app.config)
    _update_vibe_job(job_id, session_id=session_id)
    worker = threading.Thread(target=_run_populate_bank, args=(job_id, repo_dir, prompt_data, settings, None, session_id))
    worker.daemon = True
    worker.start()

    response = {"ok": True, "job_id": job_id, "session_id": session_id}
    if session_error:
        response["session_warning"] = "Session logging unavailable for this job"
    return jsonify(response)


@vibe_bp.route("/vibe/inspire-bank", methods=["POST"])
def inspire_bank_route():
    """Generate bank-level metadata (name, notes, bpm, key) from an optional seed."""
    try:
        payload = _json_object_body()
        bank = _normalize_bank(payload.get("bank", "c"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    seed = str(payload.get("seed") or "").strip()
    repo_dir = current_app.config["REPO_DIR"]
    scripts_dir = os.path.join(repo_dir, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import vibe_generate
    import preset_utils as pu

    try:
        result = vibe_generate.inspire_bank(seed=seed or None, bank_letter=bank)
    except Exception:
        return jsonify({"ok": False, "error": "Inspire failed"}), 500

    # Apply to bank via same logic as PUT /api/banks/<letter>
    try:
        config = pu._load_config()
        bank_key = f"bank_{bank}"
        if bank_key not in config or not isinstance(config[bank_key], dict):
            config[bank_key] = {}
        config[bank_key]["name"] = result["name"]
        config[bank_key]["notes"] = result["notes"]
        config[bank_key]["bpm"] = int(result["bpm"])
        config[bank_key]["key"] = result["key"]
        pu._save_config(config)
    except Exception:
        return jsonify({"ok": False, "error": "Failed to update bank config"}), 500

    return jsonify({"ok": True, "bank": result})


@vibe_bp.route("/vibe/apply-bank", methods=["POST"])
def apply_bank():
    try:
        payload = _json_object_body()
        bank = _normalize_bank(payload.get("bank", "a"))
        preset = _normalize_preset_payload(payload)
        reviewed_parsed = _normalize_reviewed_parsed(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    with _vibe_lock:
        for j in _vibe_jobs.values():
            if j.get("status") in ("starting", "generating", "reviewed", "saving", "loading", "fetching"):
                return jsonify({"ok": False, "error": "A vibe populate is already running"}), 409
        job_id = _create_vibe_job(bank, preset.get("vibe", ""))

    repo_dir = current_app.config["REPO_DIR"]
    prompt_data = {
        "prompt": preset.get("vibe", ""),
        "bpm": preset.get("bpm"),
        "key": preset.get("key"),
        "bank": bank,
        "fetch": payload.get("fetch", True),
    }
    session_id = payload.get("session_id")
    if session_id:
        vts.update_review(session_id, preset, reviewed_parsed, payload.get("fetch", True), bank)
    settings = dict(current_app.config)
    _update_vibe_job(job_id, session_id=session_id)
    thread = threading.Thread(target=_run_populate_bank, args=(job_id, repo_dir, prompt_data, settings, preset, session_id))
    thread.daemon = True
    thread.start()

    return jsonify({"ok": True, "job_id": job_id})


@vibe_bp.route("/vibe/populate-status/<job_id>")
def populate_status(job_id):
    """Poll populate-bank job progress."""
    job = _get_vibe_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found"}), 404
    return jsonify(job)
