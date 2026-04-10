"""Shared helpers for Flask API blueprints.

Home for tiny utility functions that were previously copy-pasted across
multiple blueprints. Only zero-risk extractions live here — anything with
per-blueprint variation (job trackers, subprocess runners, lazy clients)
stays in its own blueprint to keep cross-blueprint coupling low.
"""

import json

from flask import request


def json_object_body():
    """Parse the current request as a JSON object (dict). Raises ValueError otherwise.

    Used by blueprint POST handlers that expect structured input. Returns
    an empty dict if the body is empty or missing — callers should check
    for required keys separately.
    """
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


def parse_script_json(stdout):
    """Parse stdout from a subprocess script as a JSON object. Raises on non-dict."""
    payload = json.loads((stdout or "").strip())
    if not isinstance(payload, dict):
        raise ValueError("Script output must be a JSON object")
    return payload


def script_error_payload(result, default_message):
    """Shape an error response from a failed subprocess script result.

    Prefers structured error fields from stdout JSON; falls back to stderr,
    stdout, or the provided default message. Propagates `error_code` and
    `detail` when present.
    """
    try:
        payload = parse_script_json(result.stdout)
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
