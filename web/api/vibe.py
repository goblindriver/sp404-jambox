"""Natural-language vibe generation API."""

import json
import os
import subprocess
import sys
import threading
import uuid

from flask import Blueprint, current_app, jsonify, request

from jambox_config import build_subprocess_env


vibe_bp = Blueprint("vibe", __name__)

# Job tracking for populate-bank (shared with pipeline.py pattern)
_vibe_jobs = {}
_vibe_lock = threading.Lock()


@vibe_bp.route("/vibe/generate", methods=["POST"])
def generate_vibe():
    payload = request.get_json() or {}
    if not payload.get("prompt"):
        return jsonify({"ok": False, "error": "prompt is required"}), 400

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
            error_message = (result.stderr or result.stdout or "Vibe generation failed").strip()
            return jsonify({"ok": False, "error": error_message}), 500
        return jsonify({"ok": True, "result": json.loads(result.stdout)})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Vibe generation timed out"}), 500
    except json.JSONDecodeError as exc:
        return jsonify({"ok": False, "error": f"Invalid script output: {exc}"}), 500


def _run_populate_bank(job_id, repo_dir, settings, prompt_data):
    """Background worker: generate preset from vibe, load into bank, fetch samples."""
    try:
        scripts_dir = os.path.join(repo_dir, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import vibe_generate
        import preset_utils as pu
        import fetch_samples as fs

        _vibe_jobs[job_id]["status"] = "generating"
        _vibe_jobs[job_id]["progress"] = "Asking LLM to parse your vibe..."

        # Step 1: Generate preset from vibe prompt
        result = vibe_generate.build_bank_from_vibe(prompt_data)
        preset = result["preset"]
        _vibe_jobs[job_id]["progress"] = f"Generated {len(preset['pads'])} pad descriptions"

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
                tag_db = fs.load_tag_db()
                used_files = set()
                os.makedirs(fs.STAGING, exist_ok=True)

                fetched = 0
                total = len(bank_config["pads"])
                for pad_num, pad_query in bank_config["pads"].items():
                    pad_num = int(pad_num)
                    _vibe_jobs[job_id]["progress"] = f"Fetching Pad {pad_num}/{total}: {pad_query[:30]}"
                    result_path = fs.fetch_pad(bank, pad_num, pad_query, bank_config, tag_db, used_files)
                    if result_path:
                        fetched += 1

                _vibe_jobs[job_id]["fetched"] = f"{fetched}/{total}"
                _vibe_jobs[job_id]["progress"] = f"Fetched {fetched}/{total} samples"

        _vibe_jobs[job_id]["status"] = "done"
        _vibe_jobs[job_id]["progress"] = "Bank populated!"

    except Exception as e:
        _vibe_jobs[job_id]["status"] = "error"
        _vibe_jobs[job_id]["progress"] = str(e)


@vibe_bp.route("/vibe/populate-bank", methods=["POST"])
def populate_bank():
    """Generate a full bank from a vibe prompt: LLM parse → preset → load → fetch."""
    payload = request.get_json() or {}
    if not payload.get("prompt"):
        return jsonify({"ok": False, "error": "prompt is required"}), 400

    bank = payload.get("bank", "a").lower().strip()
    if bank not in "abcdefghij":
        return jsonify({"ok": False, "error": f"Invalid bank: {bank}"}), 400

    # Only one populate at a time
    with _vibe_lock:
        for j in _vibe_jobs.values():
            if j.get("status") in ("generating", "saving", "loading", "fetching"):
                return jsonify({"ok": False, "error": "A vibe populate is already running"}), 409

    job_id = str(uuid.uuid4())[:8]
    _vibe_jobs[job_id] = {
        "id": job_id,
        "status": "starting",
        "progress": "",
        "prompt": payload["prompt"],
        "bank": bank,
        "preset_ref": None,
        "fetched": None,
    }

    prompt_data = {
        "prompt": payload["prompt"],
        "bpm": payload.get("bpm"),
        "key": payload.get("key"),
        "bank": bank,
        "fetch": payload.get("fetch", True),
    }

    repo_dir = current_app.config["REPO_DIR"]
    settings = dict(current_app.config)
    t = threading.Thread(target=_run_populate_bank, args=(job_id, repo_dir, settings, prompt_data))
    t.daemon = True
    t.start()

    return jsonify({"ok": True, "job_id": job_id})


@vibe_bp.route("/vibe/populate-status/<job_id>")
def populate_status(job_id):
    """Poll populate-bank job progress."""
    job = _vibe_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)
