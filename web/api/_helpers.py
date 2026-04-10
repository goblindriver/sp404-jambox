"""Shared helpers for Flask API blueprints."""

import json
import os
import subprocess
import sys
import threading
import time
import uuid

from flask import request


# ═══════════════════════════════════════════════════════════
# Background job tracking
# ═══════════════════════════════════════════════════════════


class JobTracker:
    """Thread-safe in-memory job store with auto-pruning.

    Replaces the copy-pasted dict+lock+update/get/prune pattern found in
    pipeline, library, media, music, and vibe blueprints.

    Args:
        use_rlock: Use RLock instead of Lock (for nested calls within lock scope).
        max_age: Prune finished jobs older than this many seconds (None to disable).
        max_count: Keep at most this many finished jobs (None to disable).
    """

    _TERMINAL = frozenset(("done", "complete", "error"))

    def __init__(self, *, use_rlock=False, max_age=600, max_count=None):
        self._jobs = {}
        self._lock = threading.RLock() if use_rlock else threading.Lock()
        self._max_age = max_age
        self._max_count = max_count

    def create(self, **initial_fields):
        """Create a job with a unique ID. Returns the job_id."""
        job_id = str(uuid.uuid4())[:8]
        with self._lock:
            self.prune()
            initial_fields["id"] = job_id
            self._jobs[job_id] = initial_fields
        return job_id

    def update(self, job_id, **fields):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.update(fields)

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if isinstance(job, dict) else None

    def prune(self):
        """Remove stale finished jobs. Call inside lock or from create()."""
        if self._max_age is not None:
            now = time.time()
            stale = [jid for jid, j in self._jobs.items()
                     if j.get("status") in self._TERMINAL
                     and now - j.get("finished_at", 0) > self._max_age]
            for jid in stale:
                del self._jobs[jid]
        if self._max_count is not None:
            finished = [(jid, j) for jid, j in self._jobs.items()
                        if j.get("status") in self._TERMINAL]
            if len(finished) > self._max_count:
                for jid, _ in finished[:len(finished) - self._max_count]:
                    self._jobs.pop(jid, None)

    def clear(self):
        """Remove all jobs (for tests)."""
        with self._lock:
            self._jobs.clear()

    def has_active(self, *statuses):
        """Check if any job has one of the given statuses."""
        with self._lock:
            return any(j.get("status") in statuses for j in self._jobs.values())


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


# ═══════════════════════════════════════════════════════════
# Subprocess script runner
# ═══════════════════════════════════════════════════════════


class ScriptError(Exception):
    """Raised by run_json_script when the subprocess exits non-zero."""

    def __init__(self, payload):
        self.payload = payload
        super().__init__(payload.get("error", "Script failed"))


def run_json_script(script_name, payload, *, timeout, config, extra_args=()):
    """Run a scripts/ Python file with JSON on stdin, return parsed JSON stdout.

    Args:
        script_name: Filename inside scripts/ (e.g. 'vibe_generate.py')
        payload: Dict sent as JSON on stdin
        timeout: Subprocess timeout in seconds
        config: Flask app.config dict (for REPO_DIR and build_subprocess_env)
        extra_args: Additional CLI args after the script path

    Returns:
        Parsed dict from script stdout.

    Raises:
        ScriptError: On non-zero exit (payload has structured error fields).
        subprocess.TimeoutExpired: On timeout.
        OSError: If the script can't start.
    """
    from jambox_config import build_subprocess_env

    repo_dir = config["REPO_DIR"]
    script = os.path.join(repo_dir, "scripts", script_name)
    cmd = [sys.executable, script] + list(extra_args)
    result = subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=repo_dir,
        env=build_subprocess_env(config),
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ScriptError(script_error_payload(result, f"{script_name} failed"))
    return parse_script_json(result.stdout)


# ═══════════════════════════════════════════════════════════
# Response helpers
# ═══════════════════════════════════════════════════════════


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
