"""Retrieve in-domain context for vibe parsing and draft generation."""

from __future__ import annotations

import json
import os
import re

import fetch_samples
import preset_utils
import vibe_training_store as vts
from jambox_config import is_excluded_rel_path


STOP_WORDS = {"a", "an", "the", "and", "or", "with", "for", "of", "to", "in", "on"}

_tag_freq_cache = {"mtime": 0, "index": None}


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


def _build_tag_freq_index(tag_db):
    """Pre-compute per-keyword → {type_code, genre, vibe} frequency maps.

    Returns a dict: keyword → {"types": Counter, "genres": Counter, "vibes": Counter}
    Built once, reused across requests until DB changes.
    """
    index = {}
    for rel_path, entry in tag_db.items():
        if is_excluded_rel_path(rel_path):
            continue
        keywords = set()
        for key in ("tags", "genre", "vibe", "texture"):
            for value in entry.get(key, []):
                keywords.add(str(value).lower())

        tc = entry.get("type_code")
        genres = [str(g).lower() for g in entry.get("genre", [])]
        vibes = [str(v).lower() for v in entry.get("vibe", [])]

        for kw in keywords:
            if kw not in index:
                index[kw] = {"types": {}, "genres": {}, "vibes": {}}
            bucket = index[kw]
            if tc:
                bucket["types"][tc] = bucket["types"].get(tc, 0) + 1
            for g in genres:
                bucket["genres"][g] = bucket["genres"].get(g, 0) + 1
            for v in vibes:
                bucket["vibes"][v] = bucket["vibes"].get(v, 0) + 1
    return index


def _get_tag_freq_index():
    """Return cached frequency index, rebuilding only when tag DB file changes."""
    tags_path = fetch_samples.TAGS_FILE
    try:
        current_mtime = os.path.getmtime(tags_path)
    except OSError:
        _tag_freq_cache["index"] = None
        _tag_freq_cache["mtime"] = 0
        return {}

    if _tag_freq_cache["index"] is not None and _tag_freq_cache["mtime"] >= current_mtime:
        return _tag_freq_cache["index"]

    try:
        tag_db = fetch_samples.load_tag_db()
    except (FileNotFoundError, OSError, ValueError):
        _tag_freq_cache["index"] = None
        _tag_freq_cache["mtime"] = 0
        return {}
    if not isinstance(tag_db, dict):
        _tag_freq_cache["index"] = None
        _tag_freq_cache["mtime"] = 0
        return {}

    index = _build_tag_freq_index(tag_db)
    _tag_freq_cache["mtime"] = current_mtime
    _tag_freq_cache["index"] = index
    return index


def library_hints(prompt, limit=6):
    tokens = _tokenize(prompt)
    if not tokens:
        return {"type_codes": [], "genres": [], "vibes": []}

    index = _get_tag_freq_index()
    if not index:
        return {"type_codes": [], "genres": [], "vibes": []}

    type_counts = {}
    genre_counts = {}
    vibe_counts = {}

    for token in tokens:
        bucket = index.get(token)
        if not bucket:
            continue
        for tc, count in bucket["types"].items():
            type_counts[tc] = type_counts.get(tc, 0) + count
        for g, count in bucket["genres"].items():
            genre_counts[g] = genre_counts.get(g, 0) + count
        for v, count in bucket["vibes"].items():
            vibe_counts[v] = vibe_counts.get(v, 0) + count

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
