"""Post-ingest enrichment: tagging, fingerprinting, dedup, and stem splitting."""
import os
import posixpath
import shutil
import subprocess
import sys

from . import _state
from .archive import _copy_as_flac


def _is_recent_duplicate(library_path, rel_path):
    """Fingerprint the file and compare it against recently ingested ones.

    Only a chromaprint (fpcalc) match counts. The Python fallback fingerprint
    calls most short one-shots alike, so a match on it is logged and the file
    is kept.
    """
    try:
        from deduplicate_samples import compute_fingerprint, similarity
        fp = compute_fingerprint(library_path)
    except Exception as e:
        print(f"  [ROUTE] Fingerprint skipped: {e}")
        return False
    if not fp:
        return False
    possible = None
    with _state._fingerprint_lock:
        for other_path, other_fp in list(_state._recent_fingerprints.items()):
            if other_path == rel_path:
                continue
            sim = similarity(fp, other_fp)
            if sim is None or sim < 0.95:
                continue
            if fp.get("kind") == other_fp.get("kind") == "fpcalc":
                print(f"  [ROUTE] Duplicate detected ({sim:.2f}): {rel_path}")
                print(f"          Matches: {other_path}")
                return True
            possible = possible or (other_path, sim)
        if len(_state._recent_fingerprints) >= _state._RECENT_FP_CAP:
            oldest = next(iter(_state._recent_fingerprints))
            del _state._recent_fingerprints[oldest]
        _state._recent_fingerprints[rel_path] = fp
    if possible:
        print(f"  [ROUTE] Possible duplicate, kept ({possible[1]:.2f}): {rel_path} ~ {possible[0]}")
    return False


def _unique_path(path):
    """``path`` if free, else ``stem-2.ext``, ``stem-3.ext``, ..."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem}-{n}{ext}"):
        n += 1
    return f"{stem}-{n}{ext}"


def _route_and_process(library_path, rel_path, source_context=None):
    """Unified post-ingest processing: dedup check, tag, enrich, stem split.

    Called after a file has been copied into the library. Duplicates are
    caught first so they skip enrichment and never get a tag row; everything
    else is built into one entry and written to the tag DB once (row-level,
    so concurrent writers are never clobbered).

    Returns 'keep', 'duplicate', or 'stem-queued'.
    """
    if _is_recent_duplicate(library_path, rel_path):
        dupes_dir = os.path.join(_state.LIBRARY, "_DUPES")
        os.makedirs(dupes_dir, exist_ok=True)
        try:
            shutil.move(library_path, _unique_path(os.path.join(dupes_dir, os.path.basename(library_path))))
            return 'duplicate'
        except Exception as exc:
            print(f"  [ROUTE] Failed to move duplicate to _DUPES: {exc}")

    # Step 1: Tag the file (with librosa enrichment)
    try:
        from tag_library import tag_file
        entry = tag_file(rel_path, library_path, get_dur=True, use_librosa=True)
    except Exception as e:
        print(f"  [ROUTE] Tag failed for {rel_path}: {e}")
        entry = {'duration': 0, 'type_code': 'UNK'}
    if source_context:
        entry['cowork_source'] = source_context

    # Step 2: Smart retag via LLM (if available)
    try:
        from smart_retag import retag_single
        enriched = retag_single(rel_path, library_path, existing_entry=entry)
        if enriched:
            entry = enriched
            q = entry.get('quality_score', '?')
            tc = entry.get('type_code', '?')
            print(f"  [ROUTE] Smart tagged: {tc} q={q} \u2014 {os.path.basename(rel_path)}")
    except ImportError:
        pass  # LLM not available
    except Exception as e:
        print(f"  [ROUTE] Smart retag failed: {e}")

    # Step 3: CLAP audio embedding (if engine available)
    try:
        from clap_engine import embed_audio_file, EmbeddingStore
        store = EmbeddingStore(_state.LIBRARY)
        emb = embed_audio_file(library_path)
        store.add(rel_path, emb)
        store.save()
    except ImportError:
        pass  # CLAP not installed
    except Exception as e:
        print(f"  [ROUTE] CLAP embedding failed: {e}")

    # Step 4: Discogs genre classification (if engine available)
    try:
        from discogs_engine import classify_styles
        result = classify_styles(library_path)
        if result.get("styles"):
            entry["discogs_styles"] = result["styles"]
            entry["parent_genre"] = result["parent_genre"]
            entry["danceability"] = result["danceability"]
    except ImportError:
        pass  # Discogs model not available
    except Exception as e:
        print(f"  [ROUTE] Discogs classification failed: {e}")

    try:
        from jambox_config import upsert_tag_entries
        upsert_tag_entries(_state.TAGS_FILE, {rel_path: entry})
    except Exception as e:
        print(f"  [ROUTE] Tag DB write failed for {rel_path}: {e}")

    # Step 5: Duration-based routing
    duration = entry.get('duration', 0) or 0
    type_code = entry.get('type_code', 'UNK')

    if duration > 60 and type_code != 'VOX':
        _queue_stem_split(library_path, rel_path, entry)
        return 'stem-queued'

    return 'keep'


def _queue_stem_split(library_path, rel_path, tag_entry):
    """Submit a stem split job to the background executor."""
    future = _state._stem_executor.submit(_stem_split_task, library_path, rel_path, tag_entry)
    _state._stem_futures.append(future)
    future.add_done_callback(_stem_task_done)
    print(f"  [ROUTE] Queued stem split: {os.path.basename(library_path)} ({tag_entry.get('duration', 0):.0f}s)")


def _stem_task_done(future):
    """Surface background stem-split failures instead of dropping them."""
    try:
        _state._stem_futures.remove(future)
    except ValueError:
        pass
    exc = future.exception()
    if exc is not None:
        print(f"[STEMS] Split task failed: {exc}")


def _stem_split_task(library_path, rel_path, parent_tags):
    """Background task: run Demucs stem separation and ingest stems."""
    import tempfile

    print(f"\n[STEMS] Starting split: {os.path.basename(library_path)}")

    try:
        import demucs  # noqa: F401
    except ImportError:
        print("[STEMS] Demucs not installed \u2014 skipping stem split")
        return

    demucs_cmd = [sys.executable, '-m', 'demucs']

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                demucs_cmd + ['--two-stems=drums', '-n', 'htdemucs',
                 '-o', tmpdir, library_path],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                print(f"[STEMS] Demucs failed: {result.stderr[:200]}")
                result = subprocess.run(
                    demucs_cmd + ['-n', 'htdemucs', '-o', tmpdir, library_path],
                    capture_output=True, text=True, timeout=600,
                )
                if result.returncode != 0:
                    print(f"[STEMS] Demucs retry failed: {result.stderr[:200]}")
                    return
        except subprocess.TimeoutExpired:
            print("[STEMS] Demucs timed out (10min)")
            return

        stem_base = os.path.splitext(os.path.basename(library_path))[0]
        stem_dir = None
        for root, _dirs, files in os.walk(tmpdir):
            if any(f.lower().endswith('.wav') for f in files):
                stem_dir = root
                break

        if not stem_dir:
            print("[STEMS] No stems produced")
            return

        stem_category_map = {
            'drums': 'Drums/Drum-Loops',
            'bass': 'Melodic/Bass',
            'vocals': 'Vocals/Chops',
            'other': 'Melodic/Synths-Pads',
            'no_drums': 'Loops/Instrument-Loops',
        }

        from tag_library import tag_file
        stem_rows = {}
        for stem_file in os.listdir(stem_dir):
            if not stem_file.lower().endswith('.wav'):
                continue

            stem_name = os.path.splitext(stem_file)[0].lower()
            category = stem_category_map.get(stem_name, 'Loops/Instrument-Loops')

            dest_dir = os.path.join(_state.LIBRARY, category)
            os.makedirs(dest_dir, exist_ok=True)
            dest_fname = "{}_stem-{}.flac".format(stem_base, stem_name)
            if os.path.exists(os.path.join(dest_dir, dest_fname)):
                continue

            src_path = os.path.join(stem_dir, stem_file)
            stem_full = _copy_as_flac(src_path, os.path.join(dest_dir, "{}_stem-{}.wav".format(stem_base, stem_name)))
            stem_rel = posixpath.join(category, os.path.basename(stem_full))
            try:
                stem_entry = tag_file(stem_rel, stem_full, get_dur=True, use_librosa=True)
            except Exception as e:
                print(f"[STEMS] Tagging {stem_rel} failed: {e}")
                stem_entry = {'type_code': 'UNK'}
            stem_entry['source'] = 'processed'
            stem_entry['parent'] = rel_path
            if parent_tags.get('genre'):
                stem_entry['genre'] = parent_tags['genre']
            if parent_tags.get('bpm'):
                stem_entry['bpm'] = parent_tags['bpm']
            stem_rows[stem_rel] = stem_entry

        if stem_rows:
            print(f"[STEMS] Split {os.path.basename(library_path)} \u2192 {len(stem_rows)} stems")
            try:
                from jambox_config import upsert_tag_entries
                upsert_tag_entries(_state.TAGS_FILE, stem_rows)
            except Exception as e:
                print(f"[STEMS] Tag DB write failed: {e}")

            _state._log_ingest(
                "{} (stems)".format(os.path.basename(library_path)),
                len(stem_rows),
                {'stems': len(stem_rows)},
                source_type='stem-split',
            )
