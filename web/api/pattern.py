"""Pattern generation API — Magenta-based and scale-mapped algorithmic patterns."""

import json
import os
import subprocess
import sys

from flask import Blueprint, current_app, jsonify, request

from api._helpers import (
    json_object_body as _json_object_body,
    parse_script_json as _parse_script_json,
    script_error_payload as _script_error_payload,
)
from jambox_config import build_subprocess_env


pattern_bp = Blueprint("pattern", __name__)


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
            return jsonify(_script_error_payload(result, "Pattern generation failed")), 500
        return jsonify(_parse_script_json(result.stdout))
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Pattern generation timed out"}), 500
    except (json.JSONDecodeError, ValueError) as exc:
        return jsonify({"ok": False, "error": f"Invalid script output: {exc}"}), 500
    except OSError as exc:
        return jsonify({"ok": False, "error": f"Pattern generation failed to start: {exc}"}), 500


@pattern_bp.route("/pattern/scale-generate", methods=["POST"])
def scale_generate():
    """Generate scale-mapped patterns from a preset."""
    try:
        payload = _json_object_body()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    repo_dir = current_app.config["REPO_DIR"]
    script = os.path.join(repo_dir, "scripts", "scale_pattern.py")
    try:
        result = subprocess.run(
            [sys.executable, script, "--json"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=repo_dir,
            env=build_subprocess_env(current_app.config),
            timeout=90,
        )
        if result.returncode != 0:
            return jsonify(_script_error_payload(result, "Scale pattern generation failed")), 500
        return jsonify(_parse_script_json(result.stdout))
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Scale pattern generation timed out"}), 500
    except (json.JSONDecodeError, ValueError) as exc:
        return jsonify({"ok": False, "error": f"Invalid script output: {exc}"}), 500
    except OSError as exc:
        return jsonify({"ok": False, "error": f"Scale pattern generation failed to start: {exc}"}), 500
