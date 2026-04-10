"""Subprocess integration helpers with structured failures.

Used by non-LLM integrations that shell out to external binaries (Magenta,
fpcalc, etc.). For LLM calls see `llm_client.py` (LLMError, call_llm_chat).
"""

from __future__ import annotations

import subprocess


class IntegrationFailure(RuntimeError):
    """Structured failure from a subprocess integration (Magenta, fpcalc, ...)."""

    def __init__(self, code, message, *, detail=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or ""


def run_command(command, *, cwd, timeout, settings=None, env=None):
    if env is None and settings is not None:
        from jambox_config import build_subprocess_env
        env = build_subprocess_env(settings)
    try:
        result = subprocess.run(command, capture_output=True, text=True, cwd=cwd, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        raise IntegrationFailure("timeout", "Integration timed out") from exc
    except OSError as exc:
        raise IntegrationFailure("start_failed", f"Integration failed to start: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Command failed").strip()
        raise IntegrationFailure("command_failed", "Integration command failed", detail=detail)
    return result
