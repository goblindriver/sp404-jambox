"""Unified LLM client for Jambox.

Single source of truth for calling local LLM endpoints (Ollama, llama.cpp, etc.).
Handles retries, JSON repair, markdown stripping, and structured failures.

Replaces:
  - smart_retag._call_llm() (custom requests + retry + JSON repair)
  - integration_runtime.call_json_endpoint() (urllib wrapper)
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    """Structured failure from LLM call."""

    def __init__(self, code, message, *, detail=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or ""

    def as_dict(self):
        payload = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


def call_json_endpoint(url, payload, *, timeout, headers=None):
    """Low-level POST returning parsed JSON. Raises LLMError on failure.

    Backward-compat shim for integration_runtime.call_json_endpoint.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise LLMError("timeout", "Request timed out") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMError("http_error", f"Request failed: {exc.code}", detail=detail) from exc
    except urllib.error.URLError as exc:
        raise LLMError("connection_error", f"Request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise LLMError("invalid_json", "Endpoint returned invalid JSON") from exc


def _strip_response_text(content):
    """Clean common LLM response artifacts: markdown fences, think blocks."""
    if not content:
        return ""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```\w*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
        content = content.strip()
    # Strip <think>...</think> reasoning blocks (qwen3, deepseek)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


def _extract_balanced_json(text):
    """Find first balanced {...} object in text. Returns dict or None."""
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, c in enumerate(text[start:], start):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start:i + 1]
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    return None
    return None


def _repair_and_parse(content):
    """Try to parse content as JSON, with several repair strategies."""
    content = _strip_response_text(content)
    if not content:
        return None

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Trailing comma / missing close brace
    fixed = content.rstrip().rstrip(",")
    if not fixed.endswith("}"):
        fixed += "}"
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Last resort: find first balanced object
    return _extract_balanced_json(content)


def call_llm_chat(
    endpoint,
    model,
    messages,
    *,
    timeout=30,
    retries=0,
    json_mode=True,
    temperature=0.3,
    max_tokens=2048,
    on_stat=None,
):
    """Call a chat-completions endpoint with retries and JSON repair.

    Args:
        endpoint: Full URL to chat completions endpoint
        model: Model name (e.g. 'qwen3.5:9b')
        messages: List of {role, content} dicts
        timeout: HTTP read timeout in seconds (or tuple of (connect, read))
        retries: Extra attempts after first failure (0 = no retry)
        json_mode: Request structured JSON output if True
        temperature: Sampling temperature
        max_tokens: Max output tokens
        on_stat: Optional callback(stat_key) for stats tracking

    Returns:
        Parsed dict from model output, or None on parse failure.

    Raises:
        LLMError: For network/HTTP failures after exhausting retries.
    """
    if not endpoint:
        return None

    # Auto-route Ollama OpenAI-compat URLs to the native /api/chat endpoint.
    # The native endpoint honors `think: false` cleanly (no reasoning tokens),
    # while the OpenAI compat layer still generates them and tags them in a
    # separate `reasoning` field, dramatically increasing latency.
    use_ollama_native = False
    call_endpoint = endpoint
    if "/v1/chat/completions" in endpoint:
        use_ollama_native = True
        call_endpoint = endpoint.replace("/v1/chat/completions", "/api/chat")
    elif endpoint.endswith("/api/chat"):
        use_ollama_native = True

    if use_ollama_native:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,  # Disable reasoning for qwen3/qwen3.5/qwq/deepseek-r1
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"
    else:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

    last_error = None
    for attempt in range(retries + 1):
        if on_stat:
            on_stat("calls")
        try:
            data = call_json_endpoint(call_endpoint, payload, timeout=timeout)
            content = ""
            if use_ollama_native:
                # Native Ollama shape: {message: {content: "..."}}
                message = data.get("message") or {}
                content = message.get("content", "")
            else:
                # OpenAI shape: {choices: [{message: {content: "..."}}]}
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
            if not content:
                if on_stat:
                    on_stat("empty")
                return None
            result = _repair_and_parse(content)
            if result is not None:
                if on_stat:
                    on_stat("success")
                return result
            if on_stat:
                on_stat("parse_fail")
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return None

        except LLMError as exc:
            last_error = exc
            stat_key = exc.code  # 'timeout', 'http_error', 'connection_error', 'invalid_json'
            if on_stat:
                on_stat(stat_key)
            if attempt < retries:
                wait = 3 * (attempt + 1) if exc.code != "timeout" else 5 * (attempt + 1)
                time.sleep(wait)
                continue
            raise

    if last_error:
        raise last_error
    return None
