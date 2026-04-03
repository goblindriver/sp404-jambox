#!/usr/bin/env python3
"""Turn a natural-language vibe prompt into ranked JamBox suggestions.

Usage:
    echo '{"prompt":"dusty disco drums with neon synth stabs","bpm":120,"key":"Am"}' \
        | python scripts/vibe_generate.py
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

from jambox_config import ConfigError, load_settings_for_script
import fetch_samples


SETTINGS = load_settings_for_script(__file__)


def _read_input():
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("Expected JSON on stdin")

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    if not data.get("prompt"):
        raise ValueError("prompt is required")
    return data


def _strip_code_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_content(payload):
    if isinstance(payload, dict):
        if "choices" in payload and payload["choices"]:
            message = payload["choices"][0].get("message", {})
            content = message.get("content", "")
            if isinstance(content, list):
                return "".join(part.get("text", "") for part in content if isinstance(part, dict))
            return content
        if "message" in payload and isinstance(payload["message"], dict):
            return payload["message"].get("content", "")
        if "response" in payload:
            return payload["response"]
    return ""


def _call_llm(prompt, bpm=None, key=None):
    endpoint = SETTINGS.get("LLM_ENDPOINT", "").strip()
    if not endpoint:
        raise ConfigError("SP404_LLM_ENDPOINT is required for vibe generation")

    system_prompt = (
        "You convert creative music prompts into SP-404 sample search tags. "
        "Return JSON only with keys: keywords, type_code, playability, vibe, genre, texture, energy, rationale. "
        "keywords should be a short list of lower-case search terms. "
        "type_code and playability should be strings or null."
    )
    user_prompt = {
        "prompt": prompt,
        "bpm": bpm,
        "key": key,
        "valid_type_codes": sorted(fetch_samples.TYPE_CODES),
        "valid_playability": sorted(fetch_samples.PLAYABILITY_KEYWORDS),
    }
    body = json.dumps({
        "model": SETTINGS.get("LLM_MODEL", "qwen3"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt)},
        ],
        "temperature": 0.3,
    }).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = SETTINGS.get("LLM_TIMEOUT", 30)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc.reason}") from exc

    content = _strip_code_fences(_extract_content(payload))
    if not content:
        raise RuntimeError("LLM response did not include usable content")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM response was not valid JSON: {content[:200]}") from exc

    def _to_list(val):
        """Normalize LLM output to a list of strings.

        Handles: list of strings, comma-separated string, or single string.
        """
        if isinstance(val, list):
            return [str(item).strip().lower() for item in val if str(item).strip()]
        if isinstance(val, str):
            return [part.strip().lower() for part in val.split(",") if part.strip()]
        return []

    return {
        "keywords": _to_list(parsed.get("keywords", [])),
        "type_code": parsed.get("type_code") or None,
        "playability": parsed.get("playability") or None,
        "vibe": _to_list(parsed.get("vibe", [])),
        "genre": _to_list(parsed.get("genre", [])),
        "texture": _to_list(parsed.get("texture", [])),
        "energy": _to_list(parsed.get("energy", [])),
        "rationale": parsed.get("rationale", ""),
    }


def _build_query(prompt_data, llm_tags):
    parts = []
    if llm_tags.get("type_code"):
        parts.append(llm_tags["type_code"])
    parts.extend(llm_tags.get("keywords", []))
    parts.extend(llm_tags.get("vibe", [])[:2])
    parts.extend(llm_tags.get("genre", [])[:2])
    parts.extend(llm_tags.get("texture", [])[:2])
    if prompt_data.get("bpm"):
        parts.append(str(prompt_data["bpm"]))
    if prompt_data.get("key"):
        parts.append(str(prompt_data["key"]))
    if llm_tags.get("playability"):
        parts.append(llm_tags["playability"])

    deduped = []
    for part in parts:
        normalized = str(part).strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return " ".join(deduped)


def _score_banks(query_terms, config):
    results = []
    query_terms = {term.lower() for term in query_terms if term}
    for bank_key, bank in config.items():
        if not bank_key.startswith("bank_") or not isinstance(bank, dict):
            continue

        text = " ".join([
            bank.get("name", ""),
            bank.get("notes", ""),
            " ".join(str(value) for value in bank.get("pads", {}).values()),
        ]).lower()
        score = sum(1 for term in query_terms if term in text)
        if score == 0:
            continue
        results.append({
            "bank": bank_key.split("_", 1)[1],
            "name": bank.get("name", bank_key),
            "score": score,
            "bpm": bank.get("bpm"),
            "key": bank.get("key"),
        })
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:4]


def generate_vibe_suggestions(prompt_data):
    llm_tags = _call_llm(
        prompt_data["prompt"],
        bpm=prompt_data.get("bpm"),
        key=prompt_data.get("key"),
    )
    query = _build_query(prompt_data, llm_tags)
    matches = fetch_samples.rank_library_matches(
        query,
        bank_config={"bpm": prompt_data.get("bpm"), "key": prompt_data.get("key")},
        limit=int(prompt_data.get("limit", 12)),
        min_score=int(prompt_data.get("min_score", 4)),
    )
    config = fetch_samples.load_config()
    bank_query_terms = (
        llm_tags.get("keywords", [])
        + llm_tags.get("vibe", [])
        + llm_tags.get("genre", [])
        + llm_tags.get("texture", [])
    )
    return {
        "prompt": prompt_data["prompt"],
        "query": query,
        "parsed": llm_tags,
        "bank_suggestions": _score_banks(bank_query_terms, config),
        "sample_suggestions": matches,
    }


def main():
    prompt_data = _read_input()
    result = generate_vibe_suggestions(prompt_data)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
