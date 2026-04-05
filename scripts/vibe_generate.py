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
import yaml

from jambox_config import ConfigError, load_settings_for_script
from integration_runtime import IntegrationFailure, call_json_endpoint
from jambox_tuning import load_vibe_mappings
from taste_engine import get_system_prompt
from vibe_retrieval import build_retrieval_context
import fetch_samples


SETTINGS = load_settings_for_script(__file__)
VIBE_MAPPINGS = load_vibe_mappings()


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


def _coerce_int(value, default, *, minimum=None):
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def _load_bank_config():
    try:
        config = fetch_samples.load_config()
    except (FileNotFoundError, OSError, yaml.YAMLError, ValueError):
        return {}
    return config if isinstance(config, dict) else {}


def _parser_runtime():
    mode = SETTINGS.get("VIBE_PARSER_MODE", "base")
    endpoint = SETTINGS.get("LLM_ENDPOINT", "").strip()
    model = SETTINGS.get("LLM_MODEL", "qwen3")
    if mode == "fine_tuned":
        endpoint = SETTINGS.get("FINE_TUNED_LLM_ENDPOINT", "").strip() or endpoint
        model = SETTINGS.get("FINE_TUNED_LLM_MODEL", "").strip() or model
    return {
        "mode": mode,
        "endpoint": endpoint,
        "model": model,
        "retrieval_enabled": mode in {"rag", "fine_tuned"},
    }


def _call_llm(prompt, bpm=None, key=None, retrieval_context=None):
    runtime = _parser_runtime()
    endpoint = runtime["endpoint"]
    if not endpoint:
        raise IntegrationFailure("llm_not_configured", "SP404_LLM_ENDPOINT is required for vibe generation")

    system_prompt = get_system_prompt(
        "You convert creative music prompts into SP-404 sample search tags. "
        "Return JSON only with keys: keywords, type_code, playability, vibe, genre, texture, energy, rationale. "
        "keywords should be a short list of lower-case search terms. "
        "type_code and playability should be strings or null. "
        "Use any retrieval context as examples, not hard rules."
    )
    user_prompt = {
        "prompt": prompt,
        "bpm": bpm,
        "key": key,
        "valid_type_codes": sorted(fetch_samples.TYPE_CODES),
        "valid_playability": sorted(fetch_samples.PLAYABILITY_KEYWORDS),
    }
    if retrieval_context:
        user_prompt["retrieval_context"] = retrieval_context
    timeout = SETTINGS.get("LLM_TIMEOUT", 30)
    payload = call_json_endpoint(
        endpoint,
        {
            "model": runtime["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt)},
            ],
            "temperature": 0.3,
        },
        timeout=timeout,
    )

    content = _strip_code_fences(_extract_content(payload))
    if not content:
        raise IntegrationFailure("empty_response", "LLM response did not include usable content")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise IntegrationFailure("invalid_json", f"LLM response was not valid JSON: {content[:200]}") from exc

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


def _fallback_tags(prompt, failure=None):
    parsed = fetch_samples.parse_pad_query(prompt)
    keywords = sorted(parsed["keywords"])
    type_code = parsed["type_code"]
    if not type_code:
        for word in keywords:
            mapped = _TYPE_KEYWORD_ALIASES.get(word)
            if mapped:
                type_code = mapped
                break
    fallback = {
        "keywords": keywords,
        "type_code": type_code,
        "playability": parsed["playability"],
        "vibe": [word for word in keywords if word in _FALLBACK_DIMENSIONS["vibe"]],
        "genre": [word for word in keywords if word in _FALLBACK_DIMENSIONS["genre"]],
        "texture": [word for word in keywords if word in _FALLBACK_DIMENSIONS["texture"]],
        "energy": [word for word in keywords if word in _FALLBACK_DIMENSIONS["energy"]],
        "rationale": "Keyword fallback parser used because the configured LLM integration was unavailable.",
    }
    return {
        "tags": fallback,
        "fallback_used": True,
        "fallback_reason": failure.message if failure else "LLM integration unavailable",
        "fallback_code": failure.code if failure else "llm_unavailable",
    }


def parse_vibe_prompt(prompt, bpm=None, key=None):
    runtime = _parser_runtime()
    retrieval_context = None
    if runtime["retrieval_enabled"]:
        retrieval_context = build_retrieval_context(prompt, limit=SETTINGS.get("VIBE_RETRIEVAL_LIMIT", 4))
    try:
        return {
            "tags": _call_llm(prompt, bpm=bpm, key=key, retrieval_context=retrieval_context),
            "fallback_used": False,
            "fallback_reason": "",
            "fallback_code": "",
            "model_mode": runtime["mode"],
            "model_label": runtime["model"],
            "retrieval_context": retrieval_context,
        }
    except IntegrationFailure as exc:
        fallback = _fallback_tags(prompt, failure=exc)
        fallback["model_mode"] = runtime["mode"]
        fallback["model_label"] = runtime["model"]
        fallback["retrieval_context"] = retrieval_context
        return fallback


def _build_query(prompt_data, llm_tags):
    parts = []
    if llm_tags.get("type_code"):
        parts.append(llm_tags["type_code"])
    parts.extend(llm_tags.get("keywords", []))
    parts.extend(llm_tags.get("vibe", [])[:2])
    parts.extend(llm_tags.get("genre", [])[:2])
    parts.extend(llm_tags.get("texture", [])[:2])
    if llm_tags.get("energy"):
        parts.append(llm_tags["energy"])
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


# ═══════════════════════════════════════════════════════════
# Vibe-to-Bank: generate a full 12-pad bank from a prompt
# ═══════════════════════════════════════════════════════════

# Pad layout template — proven structure from every existing preset
_PAD_TEMPLATES = [
    # (pad_num, type_code, role, playability)
    (1,  "KIK", "kick",       "one-shot"),
    (2,  "SNR", "snare",      "one-shot"),
    (3,  "HAT", "hi-hat",     "one-shot"),
    (4,  "CLP", "clap/perc",  "one-shot"),
    (5,  "BRK", "break",      "loop"),
    (6,  "BAS", "bass",       "loop"),
    (7,  None,  "melodic-a",  "loop"),      # SYN/GTR/KEY varies by genre
    (8,  None,  "melodic-b",  "loop"),      # SYN/KEY varies by genre
    (9,  "PAD", "pad/atmo",   "loop"),
    (10, "FX",  "effect",     "one-shot"),
    (11, "SMP", "sample",     "loop"),
    (12, "VOX", "vocal",      "chop-ready"),
]

_GENRE_INSTRUMENTS = VIBE_MAPPINGS["genre_instruments"]
_DEFAULT_INSTRUMENTS = VIBE_MAPPINGS["default_instruments"]
_FALLBACK_DIMENSIONS = VIBE_MAPPINGS["fallback_dimensions"]
_TYPE_KEYWORD_ALIASES = VIBE_MAPPINGS["type_keyword_aliases"]


def _generate_pad_descriptions(llm_tags, bpm=None, key=None):
    """Build 12 pad descriptions from LLM-parsed tags using templates.

    Uses the proven pad layout (1-4 drums, 5-12 loops/melodic) and fills
    in genre/vibe/texture keywords from the LLM response.
    """
    genres = llm_tags.get("genre", [])
    vibes = llm_tags.get("vibe", [])
    textures = llm_tags.get("texture", [])
    keywords = llm_tags.get("keywords", [])
    energy = llm_tags.get("energy", "")

    # Pick the best genre for instrument selection
    primary_genre = genres[0] if genres else ""
    instruments = _GENRE_INSTRUMENTS.get(primary_genre, _DEFAULT_INSTRUMENTS)

    # Build a pool of flavor words (2-3 per pad, no repeats across pads)
    # Energy goes in early so it appears on most pads — fetch scoring keys on it
    flavor_pool = []
    if energy and energy in ("low", "mid", "high"):
        flavor_pool.append(energy)
    for src in [genres[:2], vibes[:2], textures[:2], keywords[:3]]:
        for word in src:
            if word not in flavor_pool and len(word) > 1:
                flavor_pool.append(word)

    pads = {}
    for pad_num, type_code, role, playability in _PAD_TEMPLATES:
        parts = []

        # Type code — resolve melodic pads by genre
        if type_code is None:
            idx = 0 if role == "melodic-a" else 1
            tc, label = instruments[idx] if idx < len(instruments) else _DEFAULT_INSTRUMENTS[idx]
            parts.append(tc)
            parts.append(label)
        else:
            parts.append(type_code)

        # Add 1-2 flavor words, cycling through the pool
        added = 0
        for word in flavor_pool:
            if word.upper() not in fetch_samples.TYPE_CODES and word not in parts:
                parts.append(word)
                added += 1
                if added >= 2:
                    break
        # Rotate pool so next pad gets different flavors
        if flavor_pool:
            flavor_pool = flavor_pool[1:] + flavor_pool[:1]

        parts.append(playability)
        pads[pad_num] = " ".join(parts)

    return pads


def _build_preset_from_tags(prompt, llm_tags, bpm, key):
    pads = _generate_pad_descriptions(llm_tags, bpm=bpm, key=key)
    query = _build_query({"prompt": prompt, "bpm": bpm, "key": key}, llm_tags)
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower().strip())[:40].strip("-")
    if not slug:
        slug = "vibe-bank"
    all_tags = list(dict.fromkeys(  # dedupe preserving order
        llm_tags.get("keywords", [])
        + llm_tags.get("genre", [])
        + llm_tags.get("vibe", [])
    ))[:12]
    return {
        "name": f"Vibe: {prompt[:50]}",
        "slug": slug,
        "author": "jambox-vibe",
        "bpm": int(bpm),
        "key": key,
        "vibe": prompt,
        "notes": llm_tags.get("rationale", ""),
        "source": "vibe-generated",
        "tags": all_tags,
        "pads": pads,
    }


def build_bank_from_vibe(prompt_data):
    """Turn a vibe prompt into a full 12-pad bank preset."""
    prompt = prompt_data["prompt"]
    bpm = prompt_data.get("bpm") or 120
    key = prompt_data.get("key") or "Am"

    llm_result = parse_vibe_prompt(prompt, bpm=bpm, key=key)
    llm_tags = llm_result["tags"]
    preset = _build_preset_from_tags(prompt, llm_tags, bpm, key)
    query = _build_query(prompt_data, llm_tags)

    return {
        "preset": preset,
        "llm_tags": llm_tags,
        "query": query,
        "fallback_used": llm_result["fallback_used"],
        "fallback_reason": llm_result["fallback_reason"],
        "fallback_code": llm_result["fallback_code"],
        "model_mode": llm_result.get("model_mode", SETTINGS.get("VIBE_PARSER_MODE", "base")),
        "model_label": llm_result.get("model_label", SETTINGS.get("LLM_MODEL", "qwen3")),
        "retrieval_context": llm_result.get("retrieval_context"),
    }


def generate_vibe_suggestions(prompt_data):
    limit = _coerce_int(prompt_data.get("limit"), 12, minimum=1)
    min_score = _coerce_int(prompt_data.get("min_score"), 8, minimum=0)
    bpm = prompt_data.get("bpm")
    key = prompt_data.get("key")
    llm_result = parse_vibe_prompt(
        prompt_data["prompt"],
        bpm=bpm,
        key=key,
    )
    llm_tags = llm_result["tags"]
    query = _build_query(prompt_data, llm_tags)
    matches = fetch_samples.rank_library_matches(
        query,
        bank_config={"bpm": bpm, "key": key},
        limit=limit,
        min_score=min_score,
    )
    config = _load_bank_config()
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
        "draft_preset": _build_preset_from_tags(prompt_data["prompt"], llm_tags, bpm or 120, key or "Am"),
        "fallback_used": llm_result["fallback_used"],
        "fallback_reason": llm_result["fallback_reason"],
        "fallback_code": llm_result["fallback_code"],
        "model_mode": llm_result.get("model_mode", SETTINGS.get("VIBE_PARSER_MODE", "base")),
        "model_label": llm_result.get("model_label", SETTINGS.get("LLM_MODEL", "qwen3")),
        "retrieval_context": llm_result.get("retrieval_context"),
    }


def main():
    try:
        prompt_data = _read_input()
        result = generate_vibe_suggestions(prompt_data)
        print(json.dumps(result, indent=2))
    except (ConfigError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_code": "invalid_input"}))
        raise SystemExit(1)
    except IntegrationFailure as exc:
        print(json.dumps({"ok": False, "error": exc.message, "error_code": exc.code}))
        raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_code": "unexpected_error"}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
