"""Small JSON-backed caches for library scoring and fingerprints."""

from __future__ import annotations

import json
import os
import tempfile


SCORE_CACHE_NAME = "_score_cache.json"
FINGERPRINT_CACHE_NAME = "_fingerprint_cache.json"


def _cache_path(library_root, filename):
    return os.path.join(library_root, filename)


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_json(path, payload):
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)

        try:
            os.replace(temp_path, path)
        except FileNotFoundError:
            # Rare race on external volumes: retry with a fresh temp file.
            os.makedirs(parent, exist_ok=True)
            fd2, temp_path2 = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=parent)
            try:
                with os.fdopen(fd2, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2, sort_keys=True)
                os.replace(temp_path2, path)
            finally:
                if os.path.exists(temp_path2):
                    os.unlink(temp_path2)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def file_marker(path):
    try:
        stat = os.stat(path)
    except OSError:
        return {}
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def tags_freshness_marker(tags_path):
    """Return a marker reflecting the most recent tag DB write.

    Checks both JSON and SQLite (whichever is newer) so cache invalidates
    correctly even when JSON writes are skipped for large databases.
    """
    json_marker = file_marker(tags_path)
    sqlite_path = tags_path.rsplit(".", 1)[0] + ".sqlite"
    sqlite_marker = file_marker(sqlite_path)
    if sqlite_marker.get("mtime_ns", 0) > json_marker.get("mtime_ns", 0):
        return sqlite_marker
    return json_marker


def score_cache_key(parsed_query, bank_config, *, score_version, tags_marker, weights_hash=None):
    normalized = {
        "parsed_query": {
            "type_code": parsed_query.get("type_code"),
            "playability": parsed_query.get("playability"),
            "bpm": parsed_query.get("bpm"),
            "key": parsed_query.get("key"),
            "keywords": sorted(parsed_query.get("keywords", [])),
        },
        "bank_config": {
            "bpm": bank_config.get("bpm"),
            "key": bank_config.get("key"),
        },
        "score_version": score_version,
        "tags_marker": tags_marker,
        "weights_hash": weights_hash,
    }
    return json.dumps(normalized, sort_keys=True)


def load_score_cache(library_root):
    payload = _load_json(_cache_path(library_root, SCORE_CACHE_NAME))
    entries = payload.get("entries")
    return entries if isinstance(entries, dict) else {}


MAX_SCORE_CACHE_ENTRIES = 200


def save_score_cache(library_root, entries):
    # Prune to keep only the most recent entries
    if len(entries) > MAX_SCORE_CACHE_ENTRIES:
        keys = list(entries.keys())
        for k in keys[:-MAX_SCORE_CACHE_ENTRIES]:
            del entries[k]
    _save_json(_cache_path(library_root, SCORE_CACHE_NAME), {"entries": entries})


def load_fingerprint_cache(library_root):
    payload = _load_json(_cache_path(library_root, FINGERPRINT_CACHE_NAME))
    entries = payload.get("entries")
    return entries if isinstance(entries, dict) else {}


def save_fingerprint_cache(library_root, entries):
    _save_json(_cache_path(library_root, FINGERPRINT_CACHE_NAME), {"entries": entries})


def get_cached_fingerprint(entries, rel_path, marker, backend):
    entry = entries.get(rel_path)
    if not isinstance(entry, dict):
        return None
    if entry.get("marker") != marker:
        return None
    backends = entry.get("backends")
    if not isinstance(backends, dict):
        return None
    payload = backends.get(backend)
    return payload if isinstance(payload, dict) else None


def put_cached_fingerprint(entries, rel_path, marker, backend, payload):
    entry = entries.setdefault(rel_path, {})
    entry["marker"] = marker
    entry.setdefault("backends", {})[backend] = payload
