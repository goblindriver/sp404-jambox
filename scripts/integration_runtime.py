"""Shared wrappers for external integrations and structured failures.

LLM call helpers live in llm_client.py — this module re-exports them for
backward compatibility and adds subprocess helpers for non-LLM integrations.
"""

from __future__ import annotations

import subprocess

from llm_client import LLMError as IntegrationFailure  # noqa: F401 — re-export
from llm_client import call_json_endpoint  # noqa: F401 — re-export


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
