"""Unified LLM client for Jambox.

Single source of truth for calling local LLM endpoints (Ollama, llama.cpp, etc.).
Handles retries, JSON repair, markdown stripping, and structured failures.
"""

from __future__ import annotations

import http.client
import json
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

# Ollama's default port: only these OpenAI-compat URLs are re-routed to the
# native /api/chat endpoint in backend="auto" mode.
OLLAMA_DEFAULT_PORT = 11434
LLM_BACKENDS = ("auto", "ollama", "openai")
# A fallback endpoint takes over when the primary can't be reached at all
# (refused, offline peer, timed out), never on a reply it didn't like. After
# such a failure the primary is skipped for PRIMARY_RETRY_SECONDS, so a batch
# doesn't wait out a timeout on every file while the primary is away.
FALLBACK_ON = ("connection_error", "timeout")
PRIMARY_RETRY_SECONDS = 300
_primary_down_until = {}
_primary_down_lock = threading.Lock()


class LLMError(RuntimeError):
    """Structured failure from LLM call."""

    def __init__(self, code, message, *, detail=None, status=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or ""
        self.status = status

    @property
    def retryable(self):
        """Worth another attempt: timeouts and server-side (5xx) errors.

        A refused connection (server down) or a 4xx (bad model name, bad
        request) won't fix itself in a few seconds, so retrying only adds sleeps.
        """
        if self.code == "timeout":
            return True
        return self.code == "http_error" and (self.status or 0) >= 500

    def as_dict(self):
        payload = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


def call_json_endpoint(url, payload, *, timeout, headers=None):
    """Low-level POST returning parsed JSON. Raises LLMError on failure."""
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
        raise LLMError("http_error", f"Request failed: {exc.code}", detail=detail, status=exc.code) from exc
    except urllib.error.URLError as exc:
        # urllib wraps only connecting and sending; a reply that's slow to arrive
        # raises a bare TimeoutError above. So a timeout here means the host
        # never answered (asleep, offline peer): server down, not worth retrying.
        raise LLMError("connection_error", f"Request failed: {exc.reason}") from exc
    except (ConnectionError, http.client.HTTPException) as exc:
        # A server that dies mid-request surfaces as a reset or RemoteDisconnected
        # rather than URLError; it is the same "server down" as a refusal.
        raise LLMError("connection_error", f"Connection lost: {exc!r}") from exc
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


def _first_json_object(text):
    """First JSON object embedded anywhere in *text*, or None.

    Uses the real JSON decoder at each '{', so braces inside string values
    ("a } in a description") don't throw it off the way brace counting did.
    """
    if not text:
        return None
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx >= 0:
        try:
            obj, _end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            return obj
        idx = text.find("{", idx + 1)
    return None


def _repair_and_parse(content):
    """Parse model output into a dict, with several repair strategies.

    Always returns a dict or None: callers use .get(), so a bare list or
    string from the model counts as a parse failure.
    """
    content = _strip_response_text(content)
    if not content:
        return None

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Missing close brace (output cut off by the token limit)
    fixed = content.rstrip().rstrip(",")
    if fixed.startswith("{") and not fixed.endswith("}"):
        try:
            parsed = json.loads(fixed + "}")
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Last resort: first object embedded in prose or inside a list
    return _first_json_object(content)


def resolve_backend(endpoint, backend="auto"):
    """(url_to_call, uses_ollama_native_api) for a configured endpoint.

    Ollama's OpenAI-compat route still generates reasoning tokens, so its
    /v1/chat/completions URL is sent to the native /api/chat (which honours
    think=false). Other OpenAI-compatible servers -- llama.cpp
    (training/vibe/serve_model.py), LM Studio, vLLM -- have no /api/chat and
    must be called as-is. backend="auto" treats only Ollama's default port as
    Ollama; set SP404_LLM_BACKEND=ollama or openai to override.
    """
    backend = (backend or "auto").strip().lower()
    if backend not in LLM_BACKENDS:
        backend = "auto"
    if endpoint.rstrip("/").endswith("/api/chat"):
        return endpoint, True
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        parts, port = None, None
    if parts is not None and parts.netloc and not parts.path.strip("/"):
        # A bare base URL ("http://box:11434", the way OLLAMA_HOST is written)
        # would otherwise be POSTed to the server root.
        base = endpoint.rstrip("/")
        if backend == "ollama" or (backend == "auto" and port == OLLAMA_DEFAULT_PORT):
            return base + "/api/chat", True
        return base + "/v1/chat/completions", False
    if backend == "openai" or "/v1/chat/completions" not in endpoint:
        return endpoint, False
    if backend == "ollama" or port == OLLAMA_DEFAULT_PORT:
        return endpoint.replace("/v1/chat/completions", "/api/chat"), True
    return endpoint, False


def _primary_is_down(endpoint):
    with _primary_down_lock:
        return _primary_down_until.get(endpoint, 0) > time.monotonic()


def _mark_primary_down(endpoint):
    with _primary_down_lock:
        _primary_down_until[endpoint] = time.monotonic() + PRIMARY_RETRY_SECONDS


def call_llm_chat(endpoint, model, messages, *, fallback_endpoint=None, on_stat=None, **kwargs):
    """Call a chat-completions endpoint with retries and JSON repair (see _call_endpoint).

    fallback_endpoint, if set, serves the call when the primary can't be
    reached (FALLBACK_ON), and every call for PRIMARY_RETRY_SECONDS after.
    Each fallback use is counted as on_stat("fallback").
    """
    if not endpoint:
        return None
    if not fallback_endpoint or fallback_endpoint == endpoint:
        return _call_endpoint(endpoint, model, messages, on_stat=on_stat, **kwargs)
    if not _primary_is_down(endpoint):
        try:
            return _call_endpoint(endpoint, model, messages, on_stat=on_stat, **kwargs)
        except LLMError as exc:
            if exc.code not in FALLBACK_ON:
                raise
            _mark_primary_down(endpoint)
    if on_stat:
        on_stat("fallback")
    return _call_endpoint(fallback_endpoint, model, messages, on_stat=on_stat, **kwargs)


def _call_endpoint(
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
    backend="auto",
    num_ctx=None,
):
    """Call one chat-completions endpoint with retries and JSON repair.

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
        backend: "auto" | "ollama" | "openai" (see resolve_backend)
        num_ctx: Ollama context window. Ollama silently drops the start of
            prompts longer than its default window, so callers with long
            prompts (RAG context, retag features) should set this.

    Returns:
        Parsed dict from model output, or None on parse failure.

    Raises:
        LLMError: For network/HTTP failures after exhausting retries. Only
            timeouts and 5xx responses are retried (see LLMError.retryable).
    """
    if not endpoint:
        return None

    call_endpoint, use_ollama_native = resolve_backend(endpoint, backend)

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
        if num_ctx:
            payload["options"]["num_ctx"] = int(num_ctx)
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
            if attempt < retries and exc.retryable:
                wait = 3 * (attempt + 1) if exc.code != "timeout" else 5 * (attempt + 1)
                time.sleep(wait)
                continue
            raise

    if last_error:
        raise last_error
    return None
