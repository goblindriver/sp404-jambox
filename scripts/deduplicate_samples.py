#!/usr/bin/env python3
"""Detect and optionally move duplicate samples using fpcalc or Python fallback.

Usage:
    python scripts/deduplicate_samples.py --report-json
    python scripts/deduplicate_samples.py --dedupe --clean
"""

import numpy as np
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from jambox_cache import file_marker, get_cached_fingerprint, load_fingerprint_cache, put_cached_fingerprint, save_fingerprint_cache
from jambox_config import build_subprocess_env, load_settings_for_script
from llm_client import LLMError, call_llm_chat
import dedup_library


SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
DUPES_DIR = os.path.join(LIBRARY, "_DUPES")
REPORT_PATH = os.path.join(LIBRARY, "_dedupe_report.json")
DEFAULT_WORKERS = min(8, os.cpu_count() or 4)

# Only files of about the same length can be duplicates (a one-shot is not a
# copy of the loop it was chopped from): two durations are comparable when
# they differ by at most max(0.5s, 10% of the longer one).
DURATION_TOLERANCE_SECONDS = 0.5
DURATION_TOLERANCE_RATIO = 0.10
# A chromaprint match alone never moves a file: a held note fingerprints to a
# near-constant hash, so different instruments on related notes score ~0.93.
# A copy also has the same length and the same stored timbre (MFCC means,
# leaving out the gain-dependent MFCC 0). On the iMac library every pair that
# passed this scored 1.000 and was the same file under two pack names.
COPY_DURATION_SECONDS = 0.1
COPY_DURATION_RATIO = 0.02
COPY_MFCC_DISTANCE = 0.5
_BLOCK_ELEMENTS = 1 << 22  # rows x cols x frames scored per numpy step (~16 MB of uint32)
_CACHE_SAVE_SECONDS = 120  # checkpoint the fingerprint cache so a killed run keeps its work


def load_tag_db():
    from jambox_config import load_tag_db as _load
    return _load(TAGS_FILE)


def _fingerprint_with_fpcalc(filepath):
    tool = SETTINGS.get("FINGERPRINT_TOOL", "fpcalc")
    if not tool:
        return None

    try:
        result = subprocess.run(
            [tool, "-raw", filepath],
            capture_output=True,
            text=True,
            timeout=20,
            env=build_subprocess_env(SETTINGS),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None  # fpcalc missing or hung: compute_fingerprint falls back to Python
    if result.returncode != 0:
        return None

    fingerprint = ""
    duration = 0.0
    for line in result.stdout.splitlines():
        if line.startswith("FINGERPRINT="):
            fingerprint = line.split("=", 1)[1].strip()
        elif line.startswith("DURATION="):
            try:
                duration = float(line.split("=", 1)[1].strip())
            except ValueError:
                duration = 0.0
    if not fingerprint:
        return None
    return {"kind": "fpcalc", "value": fingerprint, "duration": duration}


def _fingerprint_with_python(filepath):
    vector = dedup_library.compute_fingerprint(filepath)
    if vector is None:
        return None
    # Plain list so the fingerprint cache stays JSON-serializable.
    return {"kind": "python", "value": vector.tolist() if hasattr(vector, "tolist") else list(vector)}


def compute_fingerprint(filepath):
    return _fingerprint_with_fpcalc(filepath) or _fingerprint_with_python(filepath)


def _log(message):
    # stderr, so the CLI's JSON report on stdout stays parseable
    print(message, file=sys.stderr, flush=True)


def _fingerprint_job(full_path, cached_python, python_only):
    """Thread-pool worker: fpcalc first, then the cached or a fresh Python fingerprint.

    Returns (backend to cache the result under or None, fingerprint or None).
    """
    if not python_only:
        fingerprint = _fingerprint_with_fpcalc(full_path)
        if fingerprint is not None:
            return "fpcalc", fingerprint
    if cached_python is not None:
        return None, cached_python
    return "python", _fingerprint_with_python(full_path)


def _fingerprint_files(rel_paths, cache_entries, workers, python_only=False):
    """Fingerprint files in parallel, reusing and refilling the fingerprint cache.

    Cache lookups and writes stay on this thread; workers only run fpcalc and
    ffmpeg. Files neither backend can read are left out of the result.
    """
    found, jobs = {}, {}
    for rel_path in rel_paths:
        full_path = os.path.join(LIBRARY, rel_path)
        marker = file_marker(full_path)
        if not marker:
            continue
        cached = get_cached_fingerprint(cache_entries, rel_path, marker, "python" if python_only else "fpcalc")
        if cached is not None:
            found[rel_path] = cached
        else:
            cached_python = None if python_only else get_cached_fingerprint(cache_entries, rel_path, marker, "python")
            jobs[rel_path] = (full_path, marker, cached_python)
    if not jobs:
        return found

    _log("  Fingerprinting %d files (%d cached, %d workers)..." % (len(jobs), len(found), workers))
    t0 = last_save = time.time()
    unsaved = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_fingerprint_job, full_path, cached_python, python_only): rel_path
                   for rel_path, (full_path, _marker, cached_python) in jobs.items()}
        for done, future in enumerate(as_completed(futures), 1):
            rel_path = futures[future]
            try:
                backend, fingerprint = future.result()
            except Exception as e:  # an unreadable file is skipped, never a duplicate
                _log("    WARNING: could not fingerprint %s: %s" % (rel_path, e))
                continue
            if fingerprint is None:
                continue
            found[rel_path] = fingerprint
            if backend:
                put_cached_fingerprint(cache_entries, rel_path, jobs[rel_path][1], backend, fingerprint)
                unsaved += 1
            if unsaved and time.time() - last_save >= _CACHE_SAVE_SECONDS:
                save_fingerprint_cache(LIBRARY, cache_entries)
                last_save, unsaved = time.time(), 0
            if done % 2000 == 0:
                _log("    [%d/%d] %.0f files/sec" % (done, len(jobs), done / max(time.time() - t0, 0.01)))
    if unsaved:
        save_fingerprint_cache(LIBRARY, cache_entries)
    elapsed = time.time() - t0
    _log("    Fingerprinted %d files in %.1fs (%.0f files/sec)" % (len(jobs), elapsed, len(jobs) / max(elapsed, 0.01)))
    return found


def _fpcalc_frames(value):
    """fpcalc -raw fingerprint (comma-separated, possibly signed ints) as uint32."""
    if isinstance(value, str):
        value = [int(x) for x in value.split(",") if x.strip()]
    return (np.asarray(value, dtype=np.int64) & 0xFFFFFFFF).astype(np.uint32)


def fingerprint_similarity(a, b, max_offset=3):
    """1 - bit error rate of the best alignment within +/-max_offset frames.

    Chromaprint frames are 32-bit feature hashes: the same audio re-encoded
    differs in a few bits per frame (similarity ~0.9-1.0), unrelated audio in
    about half of them (~0.5). Text diffing the comma-separated string scored
    near-identical fingerprints around 0.05.
    """
    best = 0.0
    for offset in range(-max_offset, max_offset + 1):
        x = a[max(0, offset):]
        y = b[max(0, -offset):]
        n = min(len(x), len(y))
        if n == 0:
            continue
        differing = int(np.unpackbits(np.bitwise_xor(x[:n], y[:n]).view(np.uint8)).sum())
        best = max(best, 1.0 - differing / (32.0 * n))
    return best


def similarity(a, b):
    if a["kind"] == "fpcalc" and b["kind"] == "fpcalc":
        return fingerprint_similarity(_fpcalc_frames(a["value"]), _fpcalc_frames(b["value"]))
    if a["kind"] == "python" and b["kind"] == "python":
        return float(dedup_library.cosine_similarity(a["value"], b["value"]))
    return None


def _entry_duration(entry):
    try:
        duration = float((entry or {}).get("duration") or 0)
    except (TypeError, ValueError):
        return 0.0
    return duration if duration > 0 else 0.0


def _stored_mfcc(entry):
    mfcc = ((entry or {}).get("features") or {}).get("mfcc")
    if not isinstance(mfcc, (list, tuple)) or len(mfcc) < 2:
        return None
    try:
        return np.asarray(mfcc, dtype=np.float64)
    except (TypeError, ValueError):
        return None


def _confirmed_copy(entry_a, entry_b):
    """Same length and same stored timbre: what makes a chromaprint match safe to act on."""
    da, db_ = _entry_duration(entry_a), _entry_duration(entry_b)
    if da <= 0 or db_ <= 0 or abs(da - db_) > max(COPY_DURATION_SECONDS, COPY_DURATION_RATIO * max(da, db_)):
        return False
    ma, mb = _stored_mfcc(entry_a), _stored_mfcc(entry_b)
    if ma is None or mb is None or len(ma) != len(mb):
        return False
    return float(np.linalg.norm(ma[1:] - mb[1:])) <= COPY_MFCC_DISTANCE


def _comparable(d1, d2):
    return np.abs(d1 - d2) <= np.maximum(DURATION_TOLERANCE_SECONDS,
                                         DURATION_TOLERANCE_RATIO * np.maximum(d1, d2))


def _duration_bounds(durations):
    """Shortest and longest durations comparable with each one (padded, so a superset)."""
    lower = durations - np.maximum(DURATION_TOLERANCE_SECONDS, DURATION_TOLERANCE_RATIO * durations)
    upper = np.maximum(durations + DURATION_TOLERANCE_SECONDS, durations / (1.0 - DURATION_TOLERANCE_RATIO))
    return lower - 1e-6, upper + 1e-6


def _has_comparable(durations, others):
    """Per duration: is any of `others` comparable with it? (0 = unknown, matches unknown)"""
    result = np.zeros(len(durations), dtype=bool)
    known = durations > 0
    known_others = np.sort(others[others > 0])
    if len(known_others) and known.any():
        lower, upper = _duration_bounds(durations[known])
        result[known] = (np.searchsorted(known_others, upper, side="right")
                         > np.searchsorted(known_others, lower, side="left"))
    result[~known] = bool((others <= 0).any())
    return result


def _matching_pairs(durations, score_block, pair_cost, threshold):
    """Index pairs (i, j), i < j, of comparable length that score >= threshold.

    Items are sorted by duration, so each one only meets the window of
    slightly longer items it is comparable with; blocks of rows are scored
    against their window in one numpy call. Unknown durations (0) are only
    compared with each other. pair_cost(items) is the numpy work per pair.
    """
    pairs = []
    for known in (True, False):
        idx = np.flatnonzero(durations > 0 if known else durations <= 0)
        n = len(idx)
        if n < 2:
            continue
        idx = idx[np.argsort(durations[idx], kind="stable")]
        d = durations[idx]
        hi = np.searchsorted(d, _duration_bounds(d)[1], side="right") if known else np.full(n, n)
        start = 0
        while start < n - 1:
            rows = 1
            while rows < 1024 and start + rows < n:
                grown = min(rows * 2, n - start)
                end = hi[start + grown - 1]
                if grown * (end - start) * pair_cost(idx[start:end]) > _BLOCK_ELEMENTS:
                    break
                rows = grown
            stop, end = start + rows, hi[start + rows - 1]
            r, c = np.nonzero(score_block(idx[start:stop], idx[start:end]) >= threshold)
            r, c = r + start, c + start
            keep = c > r
            if known:
                keep &= _comparable(d[r], d[c])
            pairs.extend(zip(idx[r[keep]].tolist(), idx[c[keep]].tolist()))
            start = stop
    return pairs


def _popcount32_swar(x):
    """Set bits in each uint32 element, without np.bitwise_count.

    np.bitwise_count is numpy 2.0+, and laion_clap pins numpy<2 on the iMac.
    """
    x = x - ((x >> 1) & np.uint32(0x55555555))
    x = (x & np.uint32(0x33333333)) + ((x >> 2) & np.uint32(0x33333333))
    x = (x + (x >> 4)) & np.uint32(0x0F0F0F0F)
    return (x * np.uint32(0x01010101)) >> 24


_popcount32 = getattr(np, "bitwise_count", _popcount32_swar)


def _chromaprint_scorer(frame_arrays, max_offset=3):
    """fingerprint_similarity() for whole blocks of fingerprints at once."""
    lengths = np.array([len(f) for f in frame_arrays], dtype=np.int64)
    padded = np.zeros((len(frame_arrays), int(lengths.max(initial=0)) + max_offset), dtype=np.uint32)
    for i, frames in enumerate(frame_arrays):
        padded[i, :len(frames)] = frames

    def pair_cost(items):  # one offset is scored at a time
        return max(1, int(lengths[items].max()))

    def score_block(rows, cols):
        lr, lc = lengths[rows], lengths[cols]
        width = int(max(lr.max(), lc.max()))
        a_all, b_all = padded[rows, :width + max_offset], padded[cols, :width + max_offset]
        frame = np.arange(width)
        best = np.zeros((len(rows), len(cols)))
        for offset in range(-max_offset, max_offset + 1):
            a, b = max(0, offset), max(0, -offset)
            n = np.minimum(lr[:, None] - a, lc[None, :] - b)
            x = a_all[:, None, a:a + width] ^ b_all[None, :, b:b + width]
            differing = _popcount32(x).sum(axis=2, where=frame < n[:, :, None], dtype=np.int64)
            with np.errstate(divide="ignore", invalid="ignore"):
                score = np.where(n > 0, 1.0 - differing / (32.0 * n), 0.0)
            np.maximum(best, score, out=best)
        return best

    return score_block, pair_cost


def _cosine_scorer(vectors):
    """dedup_library.cosine_similarity() for whole blocks of vectors at once."""
    matrix = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1)

    def score_block(rows, cols):
        denom = norms[rows][:, None] * norms[cols][None, :]
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(denom > 0, (matrix[rows] @ matrix[cols].T) / denom, 0.0)

    return score_block, lambda items: matrix.shape[1]


def _duplicate_pairs(paths, fingerprints, durations, threshold, cache_entries, workers):
    """(path, path, match) for pairs scoring >= threshold, comparing only files of comparable length.

    fpcalc fingerprints are compared with each other: match "fpcalc". Python
    fingerprints (files fpcalc could not read) are compared with each other
    and with a Python fingerprint of each fpcalc file of comparable length:
    match "fallback".
    """
    chroma, frames = [], []
    for i, p in enumerate(paths):
        if fingerprints[p].get("kind") == "fpcalc":
            try:
                frames.append(_fpcalc_frames(fingerprints[p]["value"]))
                chroma.append(i)
            except (TypeError, ValueError):  # corrupt cache entry: skip the file
                pass
    python = [i for i, p in enumerate(paths) if fingerprints[p].get("kind") == "python"]
    pairs = []

    if len(chroma) > 1:
        score_block, pair_cost = _chromaprint_scorer(frames)
        for a, b in _matching_pairs(durations[chroma], score_block, pair_cost, threshold):
            pairs.append((paths[chroma[a]], paths[chroma[b]], "fpcalc"))

    if python:
        near = [chroma[k] for k in np.flatnonzero(_has_comparable(durations[chroma], durations[python]))] if chroma else []
        derived = _fingerprint_files([paths[i] for i in near], cache_entries, workers, python_only=True)
        vectors = {paths[i]: fingerprints[paths[i]]["value"] for i in python}
        vectors.update({p: fp["value"] for p, fp in derived.items()})
        by_dim = {}
        for i in python + near:
            if paths[i] in vectors:
                by_dim.setdefault(len(vectors[paths[i]]), []).append(i)
        native = set(python)
        for members in by_dim.values():
            score_block, pair_cost = _cosine_scorer([vectors[paths[i]] for i in members])
            for a, b in _matching_pairs(durations[members], score_block, pair_cost, threshold):
                if members[a] in native or members[b] in native:  # fpcalc pairs were scored above
                    pairs.append((paths[members[a]], paths[members[b]], "fallback"))
    return pairs


def _connected_groups(paths, adjacency):
    groups = []
    visited = set()
    for rel_path in paths:
        if rel_path in visited or not adjacency[rel_path]:
            continue
        stack = [rel_path]
        group = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            group.append(current)
            stack.extend(sorted(adjacency[current] - visited, reverse=True))
        if len(group) > 1:
            groups.append(group)
    return groups


def _direct_groups(paths, adjacency, rank):
    """Each best-ranked file with the files that match it directly.

    Never through a chain: A~B and B~C does not make C a copy of A, which is
    how a connected component once grouped a violin with a CZ pad.
    """
    groups = []
    for component in _connected_groups(paths, adjacency):
        assigned = set()
        for keeper in sorted(component, key=rank, reverse=True):
            if keeper in assigned:
                continue
            assigned.add(keeper)
            copies = sorted(adjacency[keeper] - assigned, key=rank, reverse=True)
            assigned.update(copies)
            if copies:
                groups.append([keeper] + copies)
    return groups


def _llm_tag_filename(rel_path):
    endpoint = SETTINGS.get("LLM_ENDPOINT", "").strip()
    if not endpoint:
        return []

    try:
        parsed = call_llm_chat(
            endpoint,
            SETTINGS.get("LLM_MODEL", "qwen3.5:9b"),
            [
                {
                    "role": "system",
                    "content": 'Suggest up to 5 lower-case descriptive sample tags as JSON: {"tags":[...]}',
                },
                {
                    "role": "user",
                    "content": json.dumps({"filename": rel_path, "directory": os.path.dirname(rel_path)}),
                },
            ],
            timeout=SETTINGS.get("LLM_TIMEOUT", 30),
            temperature=0.2,
            json_mode=True,
            max_tokens=SETTINGS.get("DEDUP_TAG_MAX_TOKENS", 200),
            backend=SETTINGS.get("LLM_BACKEND", "auto"),
        )
    except LLMError:
        return []

    if not isinstance(parsed, dict):
        return []
    return [str(tag).lower() for tag in parsed.get("tags", []) if str(tag).strip()]


def find_duplicate_groups(db, threshold=0.93, limit=0, type_code=None, workers=DEFAULT_WORKERS, stats=None):
    """Group files whose fingerprints score >= threshold; keep the best-tagged copy.

    Only files of comparable duration (tag row "duration") are compared.
    Files neither fpcalc nor the Python fallback can read are skipped and
    counted in stats["unreadable"], never reported as duplicates.

    Each group's "match" says what found it. "fpcalc" groups are the only
    ones safe to move files on: each duplicate matches the kept file directly
    on chromaprint and is also a confirmed copy (_confirmed_copy). Other
    chromaprint matches are "fpcalc_review". "fallback" groups come from the
    Python fingerprint, which calls most short one-shots alike. Report both
    for review; never act on them.
    """
    entries = list(db.items())
    if type_code:
        entries = [(path, entry) for path, entry in entries if entry.get("type_code") == type_code.upper()]
    if limit:
        entries = entries[:limit]
    stats = {} if stats is None else stats

    t0 = time.time()
    cache_entries = load_fingerprint_cache(LIBRARY)
    present = [rel_path for rel_path, _entry in entries if os.path.exists(os.path.join(LIBRARY, rel_path))]
    found = _fingerprint_files(present, cache_entries, workers)
    fingerprints = {rel_path: found[rel_path] for rel_path in present if rel_path in found}  # db order
    stats.update(fingerprinted=len(fingerprints), unreadable=len(present) - len(fingerprints),
                 fingerprint_seconds=round(time.time() - t0, 1))

    t0 = time.time()
    paths = list(fingerprints.keys())
    durations = np.array([_entry_duration(db.get(rel_path)) for rel_path in paths], dtype=np.float64)
    # Separate graphs: a review match never joins files into a group that moves files.
    adjacency = {match: {rel_path: set() for rel_path in paths} for match in ("fpcalc", "fpcalc_review", "fallback")}
    for rel_path, compare_path, match in _duplicate_pairs(paths, fingerprints, durations, threshold, cache_entries, workers):
        if match == "fpcalc" and not _confirmed_copy(db.get(rel_path), db.get(compare_path)):
            match = "fpcalc_review"
        adjacency[match][rel_path].add(compare_path)
        adjacency[match][compare_path].add(rel_path)
    stats["compare_seconds"] = round(time.time() - t0, 1)

    sizes = {}

    def member(rel_path):
        if rel_path not in sizes:
            full_path = os.path.join(LIBRARY, rel_path)
            sizes[rel_path] = os.path.getsize(full_path) if os.path.exists(full_path) else 0
        entry = db.get(rel_path, {})
        return {"path": rel_path, "size": sizes[rel_path], "tag_count": len(entry.get("tags", [])),
                "type_code": entry.get("type_code")}

    def rank(rel_path):
        item = member(rel_path)
        return item["tag_count"], item["size"]

    groups = [("fpcalc", group) for group in _direct_groups(paths, adjacency["fpcalc"], rank)]
    groups += [(match, group) for match in ("fpcalc_review", "fallback")
               for group in _connected_groups(paths, adjacency[match])]
    reports = []
    for match, group in groups:
        members = [member(rel_path) for rel_path in group]
        # Stable: a direct group's keeper stays first among equally ranked files.
        members.sort(key=lambda item: (item["tag_count"], item["size"]), reverse=True)
        reports.append({
            "keep": members[0]["path"],
            "duplicates": [item["path"] for item in members[1:]],
            "members": members,
            "match": match,
        })
    return reports


def apply_clean(report_groups, db):
    """Move each chromaprint group's duplicates into _DUPES. Fallback groups are left alone."""
    from jambox_config import delete_tag_paths
    os.makedirs(DUPES_DIR, exist_ok=True)
    updated_db = dict(db)
    removed = []
    for group in report_groups:
        if group.get("match") != "fpcalc":
            continue
        for rel_path in group["duplicates"]:
            src = os.path.join(LIBRARY, rel_path)
            if not os.path.exists(src):
                updated_db.pop(rel_path, None)
                removed.append(rel_path)
                continue
            dst = os.path.join(DUPES_DIR, rel_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.move(src, dst)
            except OSError as e:
                print(f"  WARNING: could not move {rel_path}: {e}")
                continue
            updated_db.pop(rel_path, None)
            removed.append(rel_path)

    delete_tag_paths(TAGS_FILE, removed)
    return updated_db


def build_report(args, db=None):
    db = load_tag_db() if db is None else db
    groups = find_duplicate_groups(db, threshold=args.threshold, limit=args.limit, type_code=args.type)
    unknown_tags = {}
    if args.llm_tag_unknown:
        for rel_path, entry in db.items():
            if entry.get("tags"):
                continue
            try:
                unknown_tags[rel_path] = _llm_tag_filename(rel_path)
            except (TypeError, ValueError):
                unknown_tags[rel_path] = []

    duplicates = [group for group in groups if group["match"] == "fpcalc"]
    possible = [group for group in groups if group["match"] != "fpcalc"]  # review only, never moved
    report = {
        "created_at": datetime.now().isoformat(),
        "library": LIBRARY,
        "threshold": args.threshold,
        "duplicate_groups": duplicates,
        "duplicates_found": sum(len(group["duplicates"]) for group in duplicates),
        "possible_duplicate_groups": possible,
        "possible_duplicates_found": sum(len(group["duplicates"]) for group in possible),
        "llm_tag_suggestions": unknown_tags,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Detect duplicate samples with fpcalc or Python fallback")
    parser.add_argument("--threshold", type=float, default=0.93)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--type")
    parser.add_argument("--clean", action="store_true", help="Move duplicates into _DUPES")
    parser.add_argument("--report-json", action="store_true", help="Write a JSON report to the library root")
    parser.add_argument("--llm-tag-unknown", action="store_true", help="Ask the local LLM for tags on untagged files")
    args = parser.parse_args()

    db = load_tag_db()
    report = build_report(args, db=db)
    if args.clean:
        db = apply_clean(report["duplicate_groups"], db)

    if args.report_json or args.clean:
        with open(REPORT_PATH, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
