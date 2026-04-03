"""Retrieve in-domain context for vibe parsing and draft generation."""

from __future__ import annotations

import json
import re

import fetch_samples
import preset_utils
import vibe_training_store as vts


STOP_WORDS = {"a", "an", "the", "and", "or", "with", "for", "of", "to", "in", "on"}


def _tokenize(text):
    return {token for token in re.findall(r"[a-z0-9][a-z0-9\-]+", (text or "").lower()) if token not in STOP_WORDS}


def _score_text(tokens, text):
    haystack = _tokenize(text)
    if not tokens or not haystack:
        return 0
    return len(tokens & haystack)


def _load_json_field(raw, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def retrieve_session_examples(prompt, limit=4):
    tokens = _tokenize(prompt)
    rows = vts.list_sessions(limit=250)
    results = []
    for row in rows:
        score = _score_text(tokens, row.get("prompt", ""))
        if score <= 0:
            continue
        results.append({
            "prompt": row.get("prompt", ""),
            "score": score,
            "parsed": _load_json_field(row.get("reviewed_parsed_json") or row.get("parsed_json"), {}),
            "draft_preset": _load_json_field(row.get("reviewed_preset_json") or row.get("draft_preset_json"), {}),
            "dataset_status": row.get("dataset_status", "raw"),
        })
    results.sort(key=lambda item: (item["score"], item["dataset_status"] == "reviewed"), reverse=True)
    return results[:limit]


def retrieve_preset_examples(prompt, limit=4):
    tokens = _tokenize(prompt)
    results = []
    for preset in preset_utils.list_presets():
        searchable = " ".join([
            preset.get("name", ""),
            preset.get("vibe", ""),
            " ".join(str(tag) for tag in preset.get("tags", [])),
        ])
        score = _score_text(tokens, searchable)
        if score <= 0:
            continue
        results.append({
            "ref": preset.get("ref"),
            "name": preset.get("name"),
            "score": score,
            "tags": preset.get("tags", []),
            "bpm": preset.get("bpm"),
            "key": preset.get("key"),
        })
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]


def library_hints(prompt, limit=6):
    tokens = _tokenize(prompt)
    if not tokens:
        return {"type_codes": [], "genres": [], "vibes": []}

    try:
        tag_db = fetch_samples.load_tag_db()
    except (FileNotFoundError, OSError, ValueError):
        return {"type_codes": [], "genres": [], "vibes": []}
    if not isinstance(tag_db, dict):
        return {"type_codes": [], "genres": [], "vibes": []}

    type_counts = {}
    genre_counts = {}
    vibe_counts = {}

    for entry in tag_db.values():
        search_space = set()
        for key in ("tags", "genre", "vibe", "texture"):
            for value in entry.get(key, []):
                search_space.add(str(value).lower())
        if not (tokens & search_space):
            continue
        type_code = entry.get("type_code")
        if type_code:
            type_counts[type_code] = type_counts.get(type_code, 0) + 1
        for genre in entry.get("genre", []):
            genre = str(genre).lower()
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
        for vibe in entry.get("vibe", []):
            vibe = str(vibe).lower()
            vibe_counts[vibe] = vibe_counts.get(vibe, 0) + 1

    sort_counts = lambda data: [key for key, _count in sorted(data.items(), key=lambda item: item[1], reverse=True)[:limit]]
    return {
        "type_codes": sort_counts(type_counts),
        "genres": sort_counts(genre_counts),
        "vibes": sort_counts(vibe_counts),
    }


def build_retrieval_context(prompt, limit=4):
    return {
        "historical_examples": retrieve_session_examples(prompt, limit=limit),
        "preset_examples": retrieve_preset_examples(prompt, limit=limit),
        "library_hints": library_hints(prompt, limit=limit),
    }
