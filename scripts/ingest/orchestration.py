"""Core ingest functions: single files, packs, archives, and one-shot pass."""
import os
import shutil
import time

from . import _state
from .archive import (
    categorize_wav, make_prefix, read_source_context,
    extract_rar, has_rar_files, extract_archive, _copy_as_flac,
    is_sample_pack, should_ignore, archive_has_audio,
)
from .enrichment import _route_and_process


def _store_source_context(wav_path, context):
    """Store Cowork source context in tag DB for a file."""
    from jambox_config import load_tag_db, save_tag_db
    tags_path = os.path.join(_state.LIBRARY, '_tags.json')
    try:
        tags = load_tag_db(tags_path)
        rel = os.path.relpath(wav_path, _state.LIBRARY)
        if rel in tags:
            tags[rel]['cowork_source'] = context
        else:
            tags[rel] = {'cowork_source': context}
        save_tag_db(tags_path, tags)
    except Exception:
        pass


def ingest_single_file(filepath, dry_run=False):
    """Ingest a single audio file (not a pack) into the library."""
    fname = os.path.basename(filepath)
    ext = os.path.splitext(fname)[1].lower()

    if ext not in _state.AUDIO_EXTENSIONS:
        return 0

    source_context = read_source_context(filepath)

    category = categorize_wav(filepath, fname)
    dest_dir = os.path.join(_state.LIBRARY, category)
    dest_path = os.path.join(dest_dir, fname)

    flac_dest = os.path.splitext(dest_path)[0] + '.flac'
    if os.path.exists(dest_path) or os.path.exists(flac_dest):
        print(f"  Already exists: {category}/{fname}")
        return 0

    if dry_run:
        print(f"  Would copy: {fname} \u2192 {category}")
        return 1

    os.makedirs(dest_dir, exist_ok=True)
    actual_dest = _copy_as_flac(filepath, dest_path)
    print(f"  \u2192 {category}/{os.path.basename(actual_dest)}")

    if source_context:
        _store_source_context(actual_dest, source_context)

    rel_path = os.path.relpath(actual_dest, _state.LIBRARY)
    route_result = _route_and_process(actual_dest, rel_path)
    if route_result == 'duplicate':
        print(f"  Duplicate \u2014 moved to _DUPES")
        return 0

    archive_dest = os.path.join(_state.RAW_ARCHIVE, fname)
    if filepath.startswith(_state.DOWNLOADS):
        try:
            shutil.move(filepath, archive_dest)
            for suffix in ['_SOURCE.txt', '_source.txt', '.source.txt']:
                src = os.path.splitext(filepath)[0] + suffix
                if os.path.exists(src):
                    shutil.move(src, os.path.join(_state.RAW_ARCHIVE, os.path.basename(src)))
        except Exception as e:
            print(f"  Could not move: {e}")

    _state._log_ingest(fname, 1, {category: 1}, source_type='file')
    return 1


def ingest_pack(pack_dir, dry_run=False):
    """Process one sample pack folder."""
    pack_name = os.path.basename(pack_dir)
    marker_path = os.path.join(pack_dir, _state.MARKER)

    if os.path.exists(marker_path):
        return 0

    print(f"\n{'='*60}")
    print(f"Processing: {pack_name}")

    extract_dir = pack_dir
    if has_rar_files(pack_dir):
        extract_dir = os.path.join(_state.RAW_ARCHIVE, pack_name)
        if not os.path.exists(extract_dir) or not any(
            f.endswith('.wav') for _, _, files in os.walk(extract_dir) for f in files
        ):
            if dry_run:
                print(f"  Would extract RAR to: {extract_dir}")
            else:
                if not extract_rar(pack_dir, extract_dir):
                    return 0
        else:
            print(f"  Already extracted to: {extract_dir}")

    wav_files = []
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if os.path.splitext(f)[1].lower() in _state.AUDIO_EXTENSIONS:
                wav_files.append(os.path.join(root, f))

    if not wav_files:
        print(f"  No audio files found")
        return 0

    print(f"  Found {len(wav_files)} audio files")

    source_context = read_source_context(pack_dir)

    prefix = make_prefix(pack_name)
    counts = {}
    for wav in wav_files:
        category = categorize_wav(wav, pack_name)
        dest_dir = os.path.join(_state.LIBRARY, category)
        fname = os.path.basename(wav)
        dest_path = os.path.join(dest_dir, f"{prefix}_{fname}")

        flac_check = os.path.splitext(dest_path)[0] + '.flac'
        if os.path.exists(dest_path) or os.path.exists(flac_check):
            continue

        if dry_run:
            counts[category] = counts.get(category, 0) + 1
        else:
            os.makedirs(dest_dir, exist_ok=True)
            actual = _copy_as_flac(wav, dest_path)
            counts[category] = counts.get(category, 0) + 1

            if source_context:
                _store_source_context(actual, source_context)

            rel = os.path.relpath(actual, _state.LIBRARY)
            route_result = _route_and_process(actual, rel)
            if route_result == 'duplicate':
                counts[category] = counts.get(category, 0) - 1

    for cat in sorted(counts):
        print(f"  \u2192 {cat}: {counts[cat]} files")
    total = sum(counts.values())
    print(f"  Total: {total} files {'would be ' if dry_run else ''}organized")

    if not dry_run and total > 0:
        try:
            if os.path.isdir(pack_dir):
                with open(marker_path, 'w') as f:
                    f.write(f"Ingested {total} files at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        except OSError as e:
            print(f"  Could not write marker: {e}")

        archive_dest = os.path.join(_state.RAW_ARCHIVE, pack_name)
        if os.path.isdir(pack_dir) and pack_dir.startswith(_state.DOWNLOADS) and not os.path.exists(archive_dest):
            try:
                shutil.move(pack_dir, archive_dest)
                print(f"  Moved to: {archive_dest}")
            except Exception as e:
                print(f"  Could not move pack: {e}")

        _state._log_ingest(pack_name, total, counts, source_type='pack')

    return total


def ingest_archive_file(filepath, dry_run=False):
    """Ingest a standalone archive file (.zip, .rar, .7z)."""
    fname = os.path.basename(filepath)
    name_no_ext = os.path.splitext(fname)[0]

    extract_dest = os.path.join(_state.RAW_ARCHIVE, name_no_ext)
    if os.path.exists(extract_dest):
        print(f"  Already extracted: {name_no_ext}")
        return 0

    print(f"\n{'='*60}")
    print(f"Processing archive: {fname}")

    if dry_run:
        print(f"  Would extract to: {extract_dest}")
        return 1

    if not extract_archive(filepath, extract_dest):
        return 0

    wav_files = []
    for root, dirs, files in os.walk(extract_dest):
        for f in files:
            if os.path.splitext(f)[1].lower() in _state.AUDIO_EXTENSIONS:
                wav_files.append(os.path.join(root, f))

    if not wav_files:
        print(f"  No audio files in archive \u2014 skipping (not a sample pack)")
        shutil.rmtree(extract_dest, ignore_errors=True)
        return 0

    print(f"  Found {len(wav_files)} audio files")

    source_context = read_source_context(filepath)
    prefix = make_prefix(name_no_ext)
    counts = {}

    for wav in wav_files:
        category = categorize_wav(wav, name_no_ext)
        dest_dir = os.path.join(_state.LIBRARY, category)
        wav_fname = os.path.basename(wav)
        dest_path = os.path.join(dest_dir, f"{prefix}_{wav_fname}")

        flac_check = os.path.splitext(dest_path)[0] + '.flac'
        if os.path.exists(dest_path) or os.path.exists(flac_check):
            continue

        if dry_run:
            counts[category] = counts.get(category, 0) + 1
        else:
            os.makedirs(dest_dir, exist_ok=True)
            actual = _copy_as_flac(wav, dest_path)
            counts[category] = counts.get(category, 0) + 1
            if source_context:
                _store_source_context(actual, source_context)

            rel = os.path.relpath(actual, _state.LIBRARY)
            route_result = _route_and_process(actual, rel)
            if route_result == 'duplicate':
                counts[category] = counts.get(category, 0) - 1

    for cat in sorted(counts):
        print(f"  \u2192 {cat}: {counts[cat]} files")
    total = sum(counts.values())
    print(f"  Total: {total} files {'would be ' if dry_run else ''}organized")

    if not dry_run and filepath.startswith(_state.DOWNLOADS):
        try:
            shutil.move(filepath, os.path.join(_state.RAW_ARCHIVE, fname))
            print(f"  Moved archive to _RAW-DOWNLOADS")
            for suffix in ['_SOURCE.txt', '_source.txt', '.source.txt']:
                src = os.path.splitext(filepath)[0] + suffix
                if os.path.exists(src):
                    shutil.move(src, os.path.join(_state.RAW_ARCHIVE, os.path.basename(src)))
        except Exception as e:
            print(f"  Could not move: {e}")

    if total > 0:
        _state._log_ingest(fname, total, counts, source_type='pack')

    return total


def find_sample_packs():
    """Find sample pack folders in Downloads."""
    packs = []
    for item in _state._download_entries():
        full_path = os.path.join(_state.DOWNLOADS, item)
        if not os.path.isdir(full_path):
            continue
        if is_sample_pack(item):
            packs.append(full_path)
    return packs


def one_shot_ingest(dry_run=False, dedupe=False):
    """Run a single ingest pass (original behavior)."""
    os.makedirs(_state.LIBRARY, exist_ok=True)
    os.makedirs(_state.RAW_ARCHIVE, exist_ok=True)
    if not os.path.isdir(_state.DOWNLOADS):
        print(f"Downloads path not found: {_state.DOWNLOADS}")
        return 0

    packs = find_sample_packs()
    total = 0
    pack_count = 0

    if packs:
        for pack in packs:
            count = ingest_pack(pack, dry_run=dry_run)
            total += count
            if count > 0:
                pack_count += 1

    for item in _state._download_entries():
        filepath = os.path.join(_state.DOWNLOADS, item)
        if os.path.isdir(filepath):
            continue
        if should_ignore(filepath):
            continue

        ext = os.path.splitext(item)[1].lower()
        if ext in _state.ARCHIVE_EXTENSIONS:
            if not archive_has_audio(filepath):
                continue
            total += ingest_archive_file(filepath, dry_run=dry_run)
            pack_count += 1
        elif ext in _state.AUDIO_EXTENSIONS:
            total += ingest_single_file(filepath, dry_run=dry_run)

    if total == 0 and not packs:
        print("No sample packs or audio files found in Downloads.")
    else:
        print(f"\n{'='*60}")
        print(f"Processed {pack_count} packs, {total} files organized")
        print(f"Library: {_state.LIBRARY}")

    return total
