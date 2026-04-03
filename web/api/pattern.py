"""Pattern generation API."""

import json
import os
import subprocess
import sys

from flask import Blueprint, current_app, jsonify, request

from jambox_config import build_subprocess_env


pattern_bp = Blueprint("pattern", __name__)


def _json_object_body():
    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


def _parse_script_json(stdout):
    payload = json.loads((stdout or "").strip())
    if not isinstance(payload, dict):
        raise ValueError("Script output must be a JSON object")
    return payload


@pattern_bp.route("/pattern/generate", methods=["POST"])
def generate_pattern():
    try:
        payload = _json_object_body()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    repo_dir = current_app.config["REPO_DIR"]
    script = os.path.join(repo_dir, "scripts", "generate_patterns.py")
    try:
        result = subprocess.run(
            [sys.executable, script],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=repo_dir,
            env=build_subprocess_env(current_app.config),
            timeout=90,
        )
        if result.returncode != 0:
            error_message = (result.stderr or result.stdout or "Pattern generation failed").strip()
            return jsonify({"ok": False, "error": error_message}), 500
        return jsonify(_parse_script_json(result.stdout))
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Pattern generation timed out"}), 500
    except (json.JSONDecodeError, ValueError) as exc:
        return jsonify({"ok": False, "error": f"Invalid script output: {exc}"}), 500
    except OSError as exc:
        return jsonify({"ok": False, "error": f"Pattern generation failed to start: {exc}"}), 500
