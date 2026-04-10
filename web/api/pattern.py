"""Pattern generation API — Magenta-based and scale-mapped algorithmic patterns."""

import json
import subprocess

from flask import Blueprint, current_app, jsonify

from api._helpers import (
    json_object_body as _json_object_body,
    run_json_script,
    ScriptError,
)

pattern_bp = Blueprint("pattern", __name__)


@pattern_bp.route("/pattern/generate", methods=["POST"])
def generate_pattern():
    try:
        payload = _json_object_body()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    try:
        result = run_json_script("generate_patterns.py", payload,
                                 timeout=90, config=current_app.config)
        return jsonify(result)
    except ScriptError as exc:
        return jsonify(exc.payload), 500
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
    try:
        result = run_json_script("scale_pattern.py", payload,
                                 timeout=90, config=current_app.config,
                                 extra_args=["--json"])
        return jsonify(result)
    except ScriptError as exc:
        return jsonify(exc.payload), 500
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Scale pattern generation timed out"}), 500
    except (json.JSONDecodeError, ValueError) as exc:
        return jsonify({"ok": False, "error": f"Invalid script output: {exc}"}), 500
    except OSError as exc:
        return jsonify({"ok": False, "error": f"Scale pattern generation failed to start: {exc}"}), 500
