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
import yaml

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

# Genre → melodic instrument mapping for pads 7-8
_GENRE_INSTRUMENTS = {
    "funk":        [("GTR", "guitar"),   ("KEY", "clavinet")],
    "disco":       [("KEY", "piano"),    ("STR", "strings")],
    "soul":        [("KEY", "organ"),    ("BRS", "brass")],
    "rock":        [("GTR", "guitar"),   ("GTR", "guitar")],
    "electronic":  [("SYN", "synth"),    ("SYN", "synth")],
    "ambient":     [("PAD", "pad"),      ("SYN", "synth")],
    "house":       [("SYN", "synth"),    ("KEY", "piano")],
    "techno":      [("SYN", "synth"),    ("SYN", "lead")],
    "hip-hop":     [("KEY", "piano"),    ("SYN", "synth")],
    "lo-fi":       [("KEY", "piano"),    ("GTR", "guitar")],
    "industrial":  [("SYN", "synth"),    ("SYN", "lead")],
    "pop":         [("SYN", "synth"),    ("KEY", "piano")],
}
_DEFAULT_INSTRUMENTS = [("SYN", "synth"), ("KEY", "keys")]


def _generate_pad_descriptions(llm_tags, bpm=None, key=None):
    """Build 12 pad descriptions from LLM-parsed tags using templates.

    Uses the proven pad layout (1-4 drums, 5-12 loops/melodic) and fills
    in genre/vibe/texture keywords from the LLM response.
    """
    genres = llm_tags.get("genre", [])
    vibes = llm_tags.get("vibe", [])
    textures = llm_tags.get("texture", [])
    keywords = llm_tags.get("keywords", [])

    # Pick the best genre for instrument selection
    primary_genre = genres[0] if genres else ""
    instruments = _GENRE_INSTRUMENTS.get(primary_genre, _DEFAULT_INSTRUMENTS)

    # Build a pool of flavor words (2-3 per pad, no repeats across pads)
    flavor_pool = []
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


def build_bank_from_vibe(prompt_data):
    """Turn a vibe prompt into a full 12-pad bank preset.

    Args:
        prompt_data: dict with 'prompt', optional 'bpm', 'key'

    Returns:
        dict with 'preset' (ready for save_preset), 'llm_tags', 'query'
    """
    prompt = prompt_data["prompt"]
    bpm = prompt_data.get("bpm") or 120
    key = prompt_data.get("key") or "Am"

    # 1. Parse vibe via LLM
    llm_tags = _call_llm(prompt, bpm=bpm, key=key)

    # 2. Generate 12 pad descriptions from templates + LLM tags
    pads = _generate_pad_descriptions(llm_tags, bpm=bpm, key=key)

    # 3. Build the query for display
    query = _build_query(prompt_data, llm_tags)

    # 4. Build slug from prompt
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower().strip())[:40].strip("-")
    if not slug:
        slug = "vibe-bank"

    # 5. Assemble tags list
    all_tags = list(dict.fromkeys(  # dedupe preserving order
        llm_tags.get("keywords", [])
        + llm_tags.get("genre", [])
        + llm_tags.get("vibe", [])
    ))[:12]

    preset = {
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

    return {
        "preset": preset,
        "llm_tags": llm_tags,
        "query": query,
    }


def generate_vibe_suggestions(prompt_data):
    limit = _coerce_int(prompt_data.get("limit"), 12, minimum=1)
    min_score = _coerce_int(prompt_data.get("min_score"), 4, minimum=0)
    llm_tags = _call_llm(
        prompt_data["prompt"],
        bpm=prompt_data.get("bpm"),
        key=prompt_data.get("key"),
    )
    query = _build_query(prompt_data, llm_tags)
    matches = fetch_samples.rank_library_matches(
        query,
        bank_config={"bpm": prompt_data.get("bpm"), "key": prompt_data.get("key")},
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
    }


def main():
    prompt_data = _read_input()
    result = generate_vibe_suggestions(prompt_data)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
