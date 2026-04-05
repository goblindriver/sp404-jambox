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


def _json_object_body():
    payload = request.get_json() or {}
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


def _run_populate_bank(job_id, repo_dir, prompt_data, preset_override=None, session_id=None):
    """Background worker: generate preset from vibe, load into bank, fetch samples."""
    try:
        scripts_dir = os.path.join(repo_dir, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import vibe_generate
        import preset_utils as pu
        import fetch_samples as fs

        if preset_override is None:
            _vibe_jobs[job_id]["status"] = "generating"
            _vibe_jobs[job_id]["progress"] = "Asking LLM to parse your vibe..."
            result = vibe_generate.build_bank_from_vibe(prompt_data)
            preset = result["preset"]
            _vibe_jobs[job_id]["fallback_used"] = result.get("fallback_used", False)
            _vibe_jobs[job_id]["fallback_reason"] = result.get("fallback_reason")
            _vibe_jobs[job_id]["progress"] = f"Generated {len(preset['pads'])} pad descriptions"
        else:
            preset = preset_override
            _vibe_jobs[job_id]["status"] = "reviewed"
            _vibe_jobs[job_id]["progress"] = f"Applying reviewed draft with {len(preset['pads'])} pads"

        # Step 2: Save as preset
        _vibe_jobs[job_id]["status"] = "saving"
        ref = pu.save_preset(preset, category="auto")
        _vibe_jobs[job_id]["preset_ref"] = ref
        _vibe_jobs[job_id]["progress"] = f"Saved preset: {ref}"

        # Step 3: Load into bank
        bank = prompt_data.get("bank", "a").lower()
        _vibe_jobs[job_id]["status"] = "loading"
        pu.load_preset_to_bank(ref, bank)
        _vibe_jobs[job_id]["progress"] = f"Loaded into Bank {bank.upper()}"

        # Step 4: Fetch samples
        if prompt_data.get("fetch", True):
            _vibe_jobs[job_id]["status"] = "fetching"
            config = fs.load_config()
            bank_key = f"bank_{bank}"
            bank_config = config.get(bank_key, {})

            if bank_config and bank_config.get("pads"):
                from jambox_cache import load_score_cache, save_score_cache
                tag_db = fs.load_tag_db()
                used_files = set()
                score_cache = load_score_cache(fs.LIBRARY)
                os.makedirs(fs.STAGING, exist_ok=True)

                fetched = 0
                total = len(bank_config["pads"])
                for pad_num, pad_query in bank_config["pads"].items():
                    pad_num = int(pad_num)
                    _vibe_jobs[job_id]["progress"] = f"Fetching Pad {pad_num}/{total}: {pad_query[:30]}"
                    result_path = fs.fetch_pad(bank, pad_num, pad_query, bank_config, tag_db, used_files, cache_entries=score_cache)
                    if result_path:
                        fetched += 1
                save_score_cache(fs.LIBRARY, score_cache)

                _vibe_jobs[job_id]["fetched"] = f"{fetched}/{total}"
                _vibe_jobs[job_id]["progress"] = f"Fetched {fetched}/{total} samples"

        _vibe_jobs[job_id]["status"] = "done"
        _vibe_jobs[job_id]["progress"] = "Bank populated!"
        if session_id:
            vts.complete_apply(
                session_id,
                preset,
                ref,
                {"fetched": _vibe_jobs[job_id].get("fetched")},
                _vibe_jobs[job_id]["progress"],
            )

    except Exception as e:
        _vibe_jobs[job_id]["status"] = "error"
        _vibe_jobs[job_id]["progress"] = str(e)
        if session_id:
            vts.fail_apply(session_id, str(e))


def _create_vibe_job(bank, prompt):
    job_id = str(uuid.uuid4())[:8]
    _vibe_jobs[job_id] = {
        "id": job_id,
        "status": "starting",
        "progress": "",
        "prompt": prompt,
        "bank": bank,
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
    if not payload.get("prompt"):
        return jsonify({"ok": False, "error": "prompt is required"}), 400

    try:
        bank = _normalize_bank(payload.get("bank", "a"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    with _vibe_lock:
        for j in _vibe_jobs.values():
            if j.get("status") in ("starting", "generating", "saving", "loading", "fetching"):
                return jsonify({"ok": False, "error": "A vibe populate is already running"}), 409
        job_id = _create_vibe_job(bank, payload["prompt"])

    prompt_data = {
        "prompt": payload["prompt"],
        "bpm": payload.get("bpm"),
        "key": payload.get("key"),
        "bank": bank,
        "fetch": payload.get("fetch", True),
    }

    repo_dir = current_app.config["REPO_DIR"]
    t = threading.Thread(target=_run_populate_bank, args=(job_id, repo_dir, prompt_data))
    t.daemon = True
    t.start()

    return jsonify({"ok": True, "job_id": job_id})


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
    thread = threading.Thread(target=_run_populate_bank, args=(job_id, repo_dir, prompt_data, preset, session_id))
    thread.daemon = True
    thread.start()

    return jsonify({"ok": True, "job_id": job_id})


@vibe_bp.route("/vibe/populate-status/<job_id>")
def populate_status(job_id):
    """Poll populate-bank job progress."""
    job = _vibe_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)
