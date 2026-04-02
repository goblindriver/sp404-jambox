"""Pattern generation API."""

import json
import os
import subprocess
import sys

from flask import Blueprint, current_app, jsonify, request

from jambox_config import build_subprocess_env


pattern_bp = Blueprint("pattern", __name__)


@pattern_bp.route("/pattern/generate", methods=["POST"])
def generate_pattern():
    payload = request.get_json() or {}
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
        return jsonify(json.loads(result.stdout))
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Pattern generation timed out"}), 500
    except json.JSONDecodeError as exc:
        return jsonify({"ok": False, "error": f"Invalid script output: {exc}"}), 500
