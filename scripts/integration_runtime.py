"""Shared wrappers for external integrations and structured failures."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request


class IntegrationFailure(RuntimeError):
    """Structured failure for optional external integrations."""

    def __init__(self, code, message, *, detail=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or ""

    def as_dict(self):
        payload = {
            "code": self.code,
            "message": self.message,
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


def call_json_endpoint(url, payload, *, timeout, headers=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise IntegrationFailure("http_error", f"Request failed: {exc.code}", detail=detail) from exc
    except urllib.error.URLError as exc:
        raise IntegrationFailure("connection_error", f"Request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise IntegrationFailure("invalid_json", "Integration returned invalid JSON") from exc


def run_command(command, *, cwd, timeout):
    try:
        result = subprocess.run(command, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise IntegrationFailure("timeout", "Integration timed out") from exc
    except OSError as exc:
        raise IntegrationFailure("start_failed", f"Integration failed to start: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Command failed").strip()
        raise IntegrationFailure("command_failed", "Integration command failed", detail=detail)
    return result
