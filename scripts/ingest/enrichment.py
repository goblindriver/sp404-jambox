"""Post-ingest enrichment: tagging, fingerprinting, dedup, and stem splitting."""
import os
import sys
import shutil
import subprocess

from . import _state
from .archive import _copy_as_flac


def _route_and_process(library_path, rel_path):
    """Unified post-ingest processing: tag, fingerprint, dedup check, stem split.

    Called after a file has been copied into the library. Runs the full
    enrichment pipeline inline (tag + fingerprint + dedup) and queues
    background stem splitting for full tracks.

    Returns 'keep', 'duplicate', or 'stem-queued'.
    """
    # Step 1: Tag the file (with librosa enrichment)
    try:
        from tag_library import tag_file, load_existing_tags, save_tags
        tags_db = load_existing_tags()
        entry = tag_file(rel_path, library_path, get_dur=True, use_librosa=True)
        tags_db[rel_path] = entry
        save_tags(tags_db)
    except Exception as e:
        print(f"  [ROUTE] Tag failed for {rel_path}: {e}")
        entry = {'duration': 0, 'type_code': 'UNK'}

    # Step 1.5: Smart retag via LLM (if available)
    try:
        from smart_retag import retag_single
        enriched = retag_single(rel_path, library_path, existing_entry=entry)
        if enriched:
            entry = enriched
            tags_db = load_existing_tags()
            tags_db[rel_path] = entry
            save_tags(tags_db)
            q = entry.get('quality_score', '?')
            tc = entry.get('type_code', '?')
            print(f"  [ROUTE] Smart tagged: {tc} q={q} \u2014 {os.path.basename(rel_path)}")
    except Exception as e:
        pass

    # Step 1.7: CLAP audio embedding (if engine available)
    try:
        from clap_engine import embed_audio_file, EmbeddingStore
        store = EmbeddingStore(_state.LIBRARY)
        emb = embed_audio_file(library_path)
        store.add(rel_path, emb)
        store.save()
    except Exception:
        pass

    # Step 1.8: Discogs genre classification (if engine available)
    try:
        from discogs_engine import classify_styles
        result = classify_styles(library_path)
        if result.get("styles"):
            entry = tags_db.get(rel_path, {})
            entry["discogs_styles"] = result["styles"]
            entry["parent_genre"] = result["parent_genre"]
            entry["danceability"] = result["danceability"]
            tags_db[rel_path] = entry
            save_tags(tags_db)
    except Exception:
        pass

    # Step 2: Fingerprint and inline dedup check
    is_dup = False
    try:
        from deduplicate_samples import compute_fingerprint, similarity
        fp = compute_fingerprint(library_path)
        if fp:
            with _state._fingerprint_lock:
                for other_path, other_fp in list(_state._recent_fingerprints.items()):
                    if other_path == rel_path:
                        continue
                    sim = similarity(fp, other_fp)
                    if sim is not None and sim >= 0.95:
                        print(f"  [ROUTE] Duplicate detected ({sim:.2f}): {rel_path}")
                        print(f"          Matches: {other_path}")
                        is_dup = True
                        break

                if len(_state._recent_fingerprints) >= _state._RECENT_FP_CAP:
                    oldest = next(iter(_state._recent_fingerprints))
                    del _state._recent_fingerprints[oldest]
                _state._recent_fingerprints[rel_path] = fp
    except Exception as e:
        print(f"  [ROUTE] Fingerprint skipped: {e}")

    if is_dup:
        dupes_dir = os.path.join(_state.LIBRARY, "_DUPES")
        os.makedirs(dupes_dir, exist_ok=True)
        try:
            dupe_dest = os.path.join(dupes_dir, os.path.basename(library_path))
            shutil.move(library_path, dupe_dest)
        except Exception as exc:
            print(f"  [ROUTE] Failed to move duplicate to _DUPES: {exc}")
            return 'keep'
        return 'duplicate'

    # Step 3: Duration-based routing
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
    print(f"  [ROUTE] Queued stem split: {os.path.basename(library_path)} ({tag_entry.get('duration', 0):.0f}s)")


def _stem_split_task(library_path, rel_path, parent_tags):
    """Background task: run Demucs stem separation and ingest stems."""
    import tempfile

    print(f"\n[STEMS] Starting split: {os.path.basename(library_path)}")

    try:
        import demucs as _demucs_check  # noqa: F811
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
        for root, dirs, files in os.walk(tmpdir):
            if any(f.endswith('.wav') for f in files):
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

        ingested = 0
        for stem_file in os.listdir(stem_dir):
            if not stem_file.endswith('.wav'):
                continue

            stem_name = os.path.splitext(stem_file)[0].lower()
            category = stem_category_map.get(stem_name, 'Loops/Instrument-Loops')

            dest_dir = os.path.join(_state.LIBRARY, category)
            os.makedirs(dest_dir, exist_ok=True)
            dest_fname = "{}_stem-{}.flac".format(stem_base, stem_name)
            dest_path = os.path.join(dest_dir, dest_fname)

            if os.path.exists(dest_path):
                continue

            src_path = os.path.join(stem_dir, stem_file)
            _copy_as_flac(src_path, os.path.join(dest_dir, "{}_stem-{}.wav".format(stem_base, stem_name)))
            ingested += 1

        if ingested > 0:
            print(f"[STEMS] Split {os.path.basename(library_path)} \u2192 {ingested} stems")

            try:
                from tag_library import tag_file, load_existing_tags, save_tags
                tags_db = load_existing_tags()
                for stem_file in os.listdir(stem_dir):
                    if not stem_file.endswith('.wav'):
                        continue
                    stem_name = os.path.splitext(stem_file)[0].lower()
                    category = stem_category_map.get(stem_name, 'Loops/Instrument-Loops')
                    dest_fname = "{}_stem-{}.flac".format(stem_base, stem_name)
                    stem_rel = os.path.join(category, dest_fname)
                    stem_full = os.path.join(_state.LIBRARY, stem_rel)
                    if os.path.exists(stem_full):
                        stem_entry = tag_file(stem_rel, stem_full, get_dur=True, use_librosa=True)
                        stem_entry['source'] = 'processed'
                        stem_entry['parent'] = rel_path
                        if parent_tags.get('genre'):
                            stem_entry['genre'] = parent_tags['genre']
                        if parent_tags.get('bpm'):
                            stem_entry['bpm'] = parent_tags['bpm']
                        tags_db[stem_rel] = stem_entry
                save_tags(tags_db)
            except Exception as e:
                print(f"[STEMS] Tag enrichment failed: {e}")

            _state._log_ingest(
                "{} (stems)".format(os.path.basename(library_path)),
                ingested,
                {'stems': ingested},
                source_type='stem-split',
            )
