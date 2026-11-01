#!/usr/bin/env python3
"""Library trim: profile, audit, and aggressively prune the sample library.

Modes:
  profile   Audit: duration buckets, type distribution, quality scores,
            dedup potential, audio quality flags, projected trim summary.
  execute   Trim passes (duration → dedup → audio quality → quality_score).
            Dry run by default; --apply moves cut files to
            LIBRARY/_TRASH/<run-id>/ (nothing is ever deleted outright).
  restore   Undo a trim run: files and their tag rows go back.

Usage:
    python scripts/library_trim.py profile
    python scripts/library_trim.py execute --min-duration 30            # preview
    python scripts/library_trim.py execute --min-duration 30 --apply    # trim
    python scripts/library_trim.py restore                              # list runs
    python scripts/library_trim.py restore 20261031-142500              # undo
"""

import argparse
import collections
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import (
    TRASH_DIRNAME,
    build_subprocess_env,
    delete_tag_paths,
    is_excluded_rel_path,
    load_settings_for_script,
    load_tag_db,
    merge_tag_fields,
    resolve_command,
    upsert_tag_entries,
)
from tag_library import get_duration

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
FFMPEG = SETTINGS["FFMPEG_BIN"]
REPO_DIR = os.path.dirname(SCRIPTS_DIR)

DURATION_BUCKETS = [
    (0, 2, "0-2s (micro one-shots)"),
    (2, 5, "2-5s (one-shots)"),
    (5, 15, "5-15s (short loops)"),
    (15, 30, "15-30s (long loops)"),
    (30, 60, "30-60s (extended loops)"),
    (60, 120, "60-120s (breaks/tracks)"),
    (120, float("inf"), "120s+ (full tracks)"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_size(rel_path):
    full = os.path.join(LIBRARY, rel_path)
    try:
        return os.path.getsize(full)
    except OSError:
        return 0


def _format_bytes(n):
    if n >= 1 << 30:
        return "%.1f GB" % (n / (1 << 30))
    if n >= 1 << 20:
        return "%.1f MB" % (n / (1 << 20))
    return "%.1f KB" % (n / (1 << 10))


def _duration_for_entry(rel_path, entry):
    """Get duration from tag DB entry, falling back to ffprobe."""
    raw = entry.get("duration")
    if raw is not None:
        try:
            d = float(raw)
            if d > 0:
                return d
        except (TypeError, ValueError):
            pass
    full_path = os.path.join(LIBRARY, rel_path)
    if os.path.exists(full_path):
        return float(get_duration(full_path) or 0.0)
    return 0.0


def _batch_resolve_durations(db, active_keys, workers=8):
    """Resolve duration for all active entries, using parallel ffprobe where needed.

    Updates the db entries in-place with the resolved duration. Returns a
    dict of rel_path -> duration.
    """
    durations = {}
    need_ffprobe = []

    for rel_path in active_keys:
        entry = db.get(rel_path, {})
        raw = entry.get("duration")
        if raw is not None:
            try:
                d = float(raw)
                if d > 0:
                    durations[rel_path] = d
                    continue
            except (TypeError, ValueError):
                pass
        need_ffprobe.append(rel_path)

    if not need_ffprobe:
        return durations

    print("  Resolving duration for %d files via ffprobe (%d workers)..." % (
        len(need_ffprobe), workers), flush=True)

    def _probe(rel_path):
        full_path = os.path.join(LIBRARY, rel_path)
        dur = float(get_duration(full_path) or 0.0)
        return rel_path, dur

    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe, rp): rp for rp in need_ffprobe}
        for fut in as_completed(futures):
            rel_path, dur = fut.result()
            durations[rel_path] = dur
            if dur > 0:
                entry = db.get(rel_path)
                if entry is not None:
                    entry["duration"] = dur
            done += 1
            if done % 2000 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed else 0
                print("    [%d/%d] %.0f files/sec" % (done, len(need_ffprobe), rate),
                      flush=True)

    elapsed = time.time() - t0
    print("    Duration resolved in %.1fs (%.0f files/sec)" % (
        elapsed, len(need_ffprobe) / max(elapsed, 0.01)), flush=True)
    return durations


def _read_pcm_short(filepath, max_seconds=10):
    """Decode a short PCM snippet for audio quality checks."""
    import numpy as np
    try:
        cmd = [
            FFMPEG, "-y", "-i", filepath,
            "-t", str(max_seconds),
            "-ar", "44100", "-ac", "1", "-f", "s16le", "-acodec", "pcm_s16le",
            "pipe:1",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        if result.returncode != 0 or len(result.stdout) < 4:
            return None
        samples = np.frombuffer(result.stdout, dtype=np.int16)
        return samples.astype(np.float32) / 32768.0
    except Exception:
        return None


def _check_audio_quality(samples):
    """Returns set of issue strings: 'silent', 'clipping', 'dc_offset'."""
    import numpy as np
    issues = set()
    if samples is None:  # undecodable: no verdict (callers skip these)
        return issues
    if len(samples) == 0:
        issues.add("silent")
        return issues
    abs_samples = np.abs(samples)
    if np.sum(abs_samples < 0.005) / len(samples) > 0.95:
        issues.add("silent")
    if np.sum(abs_samples >= 0.99) / len(samples) > 0.01:
        issues.add("clipping")
    if abs(float(np.mean(samples))) > 0.02:
        issues.add("dc_offset")
    return issues


# ---------------------------------------------------------------------------
# Profile mode
# ---------------------------------------------------------------------------

def run_profile(args):
    db = load_tag_db(TAGS_FILE)
    active = {k: v for k, v in db.items() if not is_excluded_rel_path(k)}
    print("=" * 70)
    print("LIBRARY TRIM PROFILE")
    print("=" * 70)
    print("  Library: %s" % LIBRARY)
    print("  Total tag DB entries: %d" % len(db))
    print("  Active (non-excluded): %d" % len(active))
    print()

    # --- Duration distribution ---
    print("--- Duration Distribution ---")
    stored = {k: v.get("duration") for k, v in db.items() if isinstance(v, dict)}
    durations = _batch_resolve_durations(db, set(active.keys()))

    bucket_counts = {label: [] for _, _, label in DURATION_BUCKETS}
    no_duration = []
    for rel_path in active:
        dur = durations.get(rel_path, 0.0)
        if dur <= 0:
            no_duration.append(rel_path)
            continue
        for lo, hi, label in DURATION_BUCKETS:
            if lo <= dur < hi:
                bucket_counts[label].append((rel_path, dur))
                break

    for _, _, label in DURATION_BUCKETS:
        paths = bucket_counts[label]
        total_size = sum(_file_size(p) for p, _ in paths)
        print("  %-30s  %6d files  %s" % (label, len(paths), _format_bytes(total_size)))
    if no_duration:
        print("  %-30s  %6d files" % ("(no duration)", len(no_duration)))
    print()

    # Save resolved durations back to tag DB so subsequent runs are fast
    merge_tag_fields(TAGS_FILE, {
        rp: {"duration": d} for rp, d in durations.items() if d > 0 and stored.get(rp) != d
    })

    cut_threshold = args.min_duration
    cut_candidates = [rp for rp in active if durations.get(rp, 0) >= cut_threshold]
    cut_size = sum(_file_size(p) for p in cut_candidates)
    print("  Duration cut (>= %ds): %d files, %s" % (cut_threshold, len(cut_candidates), _format_bytes(cut_size)))
    print()

    # --- Type code distribution ---
    print("--- Type Code Distribution ---")
    type_counter = collections.Counter()
    for entry in active.values():
        tc = entry.get("type_code", "NONE")
        type_counter[tc] += 1
    for tc, count in type_counter.most_common():
        print("  %-8s %6d" % (tc, count))
    print()

    # --- Quality score distribution ---
    print("--- Quality Score Coverage ---")
    qs_counter = collections.Counter()
    has_qs = 0
    has_sonic = 0
    has_features = 0
    for entry in active.values():
        qs = entry.get("quality_score")
        if qs is not None:
            qs_counter[qs] += 1
            has_qs += 1
        if (entry.get("sonic_description") or "").strip():
            has_sonic += 1
        if entry.get("features"):
            has_features += 1

    print("  quality_score: %d / %d (%.1f%%)" % (has_qs, len(active), has_qs / max(len(active), 1) * 100))
    print("  sonic_description: %d / %d (%.1f%%)" % (has_sonic, len(active), has_sonic / max(len(active), 1) * 100))
    print("  features (librosa): %d / %d (%.1f%%)" % (has_features, len(active), has_features / max(len(active), 1) * 100))
    if qs_counter:
        print("  Score histogram:")
        for score in sorted(qs_counter):
            print("    %d: %d" % (score, qs_counter[score]))
        low_q = sum(qs_counter.get(s, 0) for s in (1, 2))
        print("  Scores 1-2 (trim candidates): %d" % low_q)
    print()

    # --- Dedup potential ---
    print("--- Dedup Potential ---")
    fingerprinted = sum(1 for e in active.values() if e.get("features", {}).get("mfcc"))
    print("  Files with MFCC vectors: %d / %d" % (fingerprinted, len(active)))
    print("  (Full dedup scan requires --execute; estimate based on prior runs)")
    print()

    # --- Triage dirs ---
    print("--- Triage Directory Sizes ---")
    for dirname in ("_DUPES", "_QUARANTINE", "_LONG-HOLD"):
        dirpath = os.path.join(LIBRARY, dirname)
        if os.path.isdir(dirpath):
            count = 0
            total = 0
            for root, dirs, files in os.walk(dirpath):
                for f in files:
                    fp = os.path.join(root, f)
                    count += 1
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
            print("  %-15s %6d files  %s" % (dirname, count, _format_bytes(total)))
        else:
            print("  %-15s (empty)" % dirname)
    print()

    # --- Projected trim summary ---
    print("--- Projected Trim (cumulative) ---")
    remaining = len(active)
    print("  Start:                %6d files" % remaining)
    remaining -= len(cut_candidates)
    print("  After duration cut:   %6d files  (-%d)" % (remaining, len(cut_candidates)))
    low_q = sum(qs_counter.get(s, 0) for s in (1, 2))
    if low_q:
        remaining -= low_q
        print("  After quality cut:    %6d files  (-%d scored 1-2)" % (remaining, low_q))
    print()
    print("  Target range: 15,000 - 20,000")
    if 15000 <= remaining <= 20000:
        print("  --> ON TARGET")
    elif remaining > 20000:
        print("  --> Still %d above target. Dedup + audio quality + smart retag quality pass needed." % (remaining - 20000))
    else:
        print("  --> Below target floor. Consider raising --min-duration threshold.")


# ---------------------------------------------------------------------------
# Execute mode
# ---------------------------------------------------------------------------

class TrashRun:
    """Moves trimmed files to LIBRARY/_TRASH/<run-id>/ and records how to undo it.

    Every move appends a line to manifest.jsonl (rel_path, reason, tag_row)
    before the tag row is deleted, so `library_trim.py restore <run-id>` can
    put both the file and its tags back, even after a crash mid-run.
    """

    def __init__(self, run_id=None):
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.root = os.path.join(LIBRARY, TRASH_DIRNAME, self.run_id)
        self.manifest = os.path.join(self.root, "manifest.jsonl")
        self._pending_deletes = []

    def move(self, rel_path, entry, reason):
        src = os.path.join(LIBRARY, rel_path)
        os.makedirs(self.root, exist_ok=True)
        if os.path.exists(src):
            dest = os.path.join(self.root, rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
        with open(self.manifest, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"rel_path": rel_path, "reason": reason, "tag_row": entry}) + "\n")
        self._pending_deletes.append(rel_path)
        if len(self._pending_deletes) >= 200:
            self.flush()

    def flush(self):
        if self._pending_deletes:
            delete_tag_paths(TAGS_FILE, self._pending_deletes)
            self._pending_deletes = []


def _new_stats():
    return {"trashed": 0, "would_trash": 0, "would_free": 0, "errors": 0}


def _trash_file_and_entry(rel_path, db, stats, trash, reason=""):
    """Move a file to the trash run and drop its tag row (count only when trash is None)."""
    if trash is None:
        stats["would_trash"] += 1
        stats["would_free"] += _file_size(rel_path)
        return
    try:
        trash.move(rel_path, db.get(rel_path), reason)
        db.pop(rel_path, None)
        stats["trashed"] += 1
    except OSError as e:
        print("  ERROR trashing %s: %s" % (rel_path, e), file=sys.stderr)
        stats["errors"] += 1


def _print_pass_result(stats, trash):
    if trash is None:
        print("  Would trash: %d files (%s)" % (stats["would_trash"], _format_bytes(stats["would_free"])))
    else:
        print("  Moved to trash: %d files  Errors: %d" % (stats["trashed"], stats["errors"]))


def _pass_duration(db, active_keys, min_duration, trash):
    """Pass 1: trash files >= min_duration seconds."""
    print("\n--- Pass 1: Duration Cut (>= %ds) ---" % min_duration)
    stats = _new_stats()

    durations = _batch_resolve_durations(db, active_keys)
    for rel_path in list(active_keys):
        if durations.get(rel_path, 0.0) >= min_duration:
            _trash_file_and_entry(rel_path, db, stats, trash, reason="duration")
            active_keys.discard(rel_path)

    _print_pass_result(stats, trash)
    return stats


def _pass_dedup(db, active_keys, threshold, trash):
    """Pass 2: fingerprint-based dedup, keep best quality."""
    print("\n--- Pass 2: Dedup (threshold=%.2f) ---" % threshold)
    stats = _new_stats()

    try:
        from deduplicate_samples import find_duplicate_groups
    except ImportError:
        print("  SKIP: deduplicate_samples not importable")
        return stats

    subset_db = {k: db[k] for k in active_keys if k in db}
    groups = find_duplicate_groups(subset_db, threshold=threshold)
    print("  Found %d duplicate groups" % len(groups))

    for group in groups:
        for dupe_path in group["duplicates"]:
            if dupe_path in active_keys:
                _trash_file_and_entry(dupe_path, db, stats, trash, reason="dedup")
                active_keys.discard(dupe_path)

    _print_pass_result(stats, trash)
    return stats


def _pass_audio_quality(db, active_keys, trash):
    """Pass 3: trash silent/clipping/DC-offset files. Unreadable files are skipped."""
    print("\n--- Pass 3: Audio Quality ---")
    stats = _new_stats()
    stats["unreadable"] = 0

    try:
        import numpy as np  # noqa: F401
    except ImportError:
        print("  SKIP: numpy not available")
        return stats

    issue_counts = collections.Counter()
    checked = 0
    t0 = time.time()

    keys_snapshot = list(active_keys)
    for i, rel_path in enumerate(keys_snapshot):
        full_path = os.path.join(LIBRARY, rel_path)
        if not os.path.exists(full_path):
            _trash_file_and_entry(rel_path, db, stats, trash, reason="missing")
            active_keys.discard(rel_path)
            continue

        samples = _read_pcm_short(full_path)
        if samples is None:
            # A decode failure says nothing about the audio: never cut on it.
            stats["unreadable"] += 1
            continue
        issues = _check_audio_quality(samples)
        checked += 1

        if issues:
            for iss in issues:
                issue_counts[iss] += 1
            _trash_file_and_entry(rel_path, db, stats, trash, reason=",".join(sorted(issues)))
            active_keys.discard(rel_path)

        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed else 0
            print("  [%d/%d] %.0f files/sec" % (i + 1, len(keys_snapshot), rate))

    elapsed = time.time() - t0
    print("  Checked %d files in %.1fs (%d unreadable, skipped)" % (checked, elapsed, stats["unreadable"]))
    for iss, cnt in issue_counts.most_common():
        print("    %s: %d" % (iss, cnt))

    _print_pass_result(stats, trash)
    return stats


def _pass_quality_score(db, active_keys, min_score, trash):
    """Pass 4: trash files with quality_score below min_score."""
    print("\n--- Pass 4: Quality Score (trash score < %d) ---" % min_score)
    stats = _new_stats()

    for rel_path in list(active_keys):
        entry = db.get(rel_path, {})
        qs = entry.get("quality_score")
        if qs is not None and qs < min_score:
            _trash_file_and_entry(rel_path, db, stats, trash, reason="quality_%d" % qs)
            active_keys.discard(rel_path)

    _print_pass_result(stats, trash)
    return stats


def _cleanup_empty_dirs(root):
    """Remove empty directories left after files moved to the trash."""
    removed = 0
    for dirpath, dirs, files in os.walk(root, topdown=False):
        if dirpath == root:
            continue
        if not dirs and not files:
            try:
                os.rmdir(dirpath)
                removed += 1
            except OSError:
                pass
    return removed


def run_execute(args):
    apply = bool(getattr(args, "apply", False)) and not args.dry_run
    if not args.skip_audio_quality and not resolve_command(FFMPEG, build_subprocess_env(SETTINGS)):
        print("ERROR: ffmpeg not found (%s). The audio-quality pass needs it; "
              "set SP404_FFMPEG or pass --skip-audio-quality." % FFMPEG, file=sys.stderr)
        sys.exit(2)

    db = load_tag_db(TAGS_FILE)
    active_keys = {k for k in db if not is_excluded_rel_path(k)}
    trash = TrashRun() if apply else None

    print("=" * 70)
    print("LIBRARY TRIM%s" % ("" if apply else " (DRY RUN)"))
    print("=" * 70)
    print("  Library: %s" % LIBRARY)
    print("  Active files: %d" % len(active_keys))
    print("  Min duration: %ds" % args.min_duration)
    if apply:
        print("  Mode: APPLY (files move to %s; undo with: library_trim.py restore %s)"
              % (trash.root, trash.run_id))
    else:
        print("  Mode: DRY RUN (nothing is moved; pass --apply to trim)")
    print()

    starting = len(active_keys)
    all_stats = {}

    all_stats["duration"] = _pass_duration(db, active_keys, args.min_duration, trash)
    if not args.skip_dedup:
        all_stats["dedup"] = _pass_dedup(db, active_keys, args.dedup_threshold, trash)
    if not args.skip_audio_quality:
        all_stats["audio_quality"] = _pass_audio_quality(db, active_keys, trash)
    all_stats["quality_score"] = _pass_quality_score(db, active_keys, args.min_quality, trash)

    if trash is not None:
        trash.flush()
        empty_removed = _cleanup_empty_dirs(LIBRARY)
        if empty_removed:
            print("\n  Cleaned up %d empty directories" % empty_removed)

    final = len(active_keys)
    total_trashed = sum(s.get("trashed", 0) for s in all_stats.values())
    total_would = sum(s.get("would_trash", 0) for s in all_stats.values())
    total_errors = sum(s.get("errors", 0) for s in all_stats.values())

    print("\n" + "=" * 70)
    print("TRIM SUMMARY")
    print("=" * 70)
    print("  Starting files:  %6d" % starting)
    for name, stats in all_stats.items():
        cut = stats.get("trashed", 0) or stats.get("would_trash", 0)
        if cut:
            print("    %-18s -%d" % (name, cut))
    print("  Final files:     %6d" % final)

    if trash is None:
        total_free = sum(s.get("would_free", 0) for s in all_stats.values())
        print("\n  DRY RUN: would move %d files to the trash, freeing %s" % (total_would, _format_bytes(total_free)))
        print("  Re-run with --apply to trim.")
    else:
        print("\n  Moved to trash: %d  Errors: %d" % (total_trashed, total_errors))
        print("  Undo with: python scripts/library_trim.py restore %s" % trash.run_id)

    report = {
        "generated_at": datetime.now().isoformat(),
        "mode": "apply" if trash is not None else "dry_run",
        "trash_run": trash.run_id if trash is not None else None,
        "starting_files": starting,
        "final_files": final,
        "passes": {name: dict(s) for name, s in all_stats.items()},
        "min_duration": args.min_duration,
        "dedup_threshold": args.dedup_threshold,
        "min_quality": args.min_quality,
    }
    report_dir = os.path.join(REPO_DIR, "data", "audit_reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "trim_report_latest.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("\n  Report: %s" % report_path)


def run_restore(args):
    """Move a trash run's files back into the library and restore their tag rows."""
    trash_root = os.path.join(LIBRARY, TRASH_DIRNAME)
    if not args.run_id:
        runs = sorted(os.listdir(trash_root)) if os.path.isdir(trash_root) else []
        print("Trash runs:" if runs else "No trash runs in %s" % trash_root)
        for run in runs:
            print("  %s" % run)
        return 0

    run = TrashRun(args.run_id)
    if not os.path.isfile(run.manifest):
        print("ERROR: no manifest at %s" % run.manifest, file=sys.stderr)
        return 1

    restored, conflicts, rows = 0, [], {}
    with open(run.manifest, encoding="utf-8") as fh:
        items = [json.loads(line) for line in fh if line.strip()]
    for item in items:
        rel_path = item["rel_path"]
        trashed = os.path.join(run.root, rel_path)
        if not os.path.exists(trashed):
            continue  # was already missing when trimmed
        dest = os.path.join(LIBRARY, rel_path)
        if os.path.exists(dest):
            conflicts.append(rel_path)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(trashed, dest)
        if isinstance(item.get("tag_row"), dict):
            rows[rel_path] = item["tag_row"]
        restored += 1

    upsert_tag_entries(TAGS_FILE, rows)
    print("Restored %d files (%d tag rows) from %s" % (restored, len(rows), run.root))
    if conflicts:
        print("Left %d in the trash because the library already has a file at that path:" % len(conflicts))
        for rel_path in conflicts[:20]:
            print("  %s" % rel_path)
    else:
        os.remove(run.manifest)
        _cleanup_empty_dirs(run.root)
        try:
            os.rmdir(run.root)
        except OSError:
            pass
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Library trim: profile and prune the sample library"
    )
    sub = parser.add_subparsers(dest="command")

    # -- profile --
    p_profile = sub.add_parser("profile", aliases=["--profile"], help="Audit library composition")
    p_profile.add_argument("--min-duration", type=int, default=30,
                           help="Duration threshold for cut projection (default: 30)")

    # -- execute --
    p_exec = sub.add_parser("execute", aliases=["--execute"],
                            help="Trim passes (dry run unless --apply)")
    p_exec.add_argument("--min-duration", type=int, default=30,
                        help="Trash files >= this duration in seconds (default: 30)")
    p_exec.add_argument("--dedup-threshold", type=float, default=0.93,
                        help="Fingerprint similarity threshold for dedup (default: 0.93)")
    p_exec.add_argument("--min-quality", type=int, default=3,
                        help="Trash files with quality_score < this (default: 3, trashes 1-2)")
    p_exec.add_argument("--skip-dedup", action="store_true",
                        help="Skip the dedup pass")
    p_exec.add_argument("--skip-audio-quality", action="store_true",
                        help="Skip the audio quality pass")
    p_exec.add_argument("--apply", action="store_true",
                        help="Actually move files to _TRASH/<run-id>/ (default: dry run)")
    p_exec.add_argument("--dry-run", action="store_true",
                        help="Preview only (the default; overrides --apply)")

    # -- restore --
    p_restore = sub.add_parser("restore", help="Undo a trim run (lists runs when no id is given)")
    p_restore.add_argument("run_id", nargs="?", help="Trash run id, e.g. 20261031-142500")

    # Handle --profile / --execute as flags too (backward compat with plan CLI examples)
    parser.add_argument("--profile", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execute", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--min-duration", type=int, default=30, help=argparse.SUPPRESS)
    parser.add_argument("--dedup-threshold", type=float, default=0.93, help=argparse.SUPPRESS)
    parser.add_argument("--min-quality", type=int, default=3, help=argparse.SUPPRESS)
    parser.add_argument("--skip-dedup", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-audio-quality", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--apply", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Reconcile subcommand vs flag style
    if args.command == "restore":
        sys.exit(run_restore(args))
    elif args.command in ("profile", "--profile") or getattr(args, "profile", False):
        run_profile(args)
    elif args.command in ("execute", "--execute") or getattr(args, "execute", False):
        run_execute(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
