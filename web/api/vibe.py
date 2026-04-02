"""Natural-language vibe generation API."""

import json
import os
import subprocess
import sys

from flask import Blueprint, current_app, jsonify, request

from jambox_config import build_subprocess_env


vibe_bp = Blueprint("vibe", __name__)


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
