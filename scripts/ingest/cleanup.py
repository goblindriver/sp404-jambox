"""Download cleanup, archive purging, and disk usage reporting."""
import os
import shutil

from . import _state


def cleanup_downloads(dry_run=False):
    """Remove already-ingested packs and archives from ~/Downloads."""
    freed = 0
    removed = 0

    if not os.path.isdir(_state.DOWNLOADS):
        print("Downloads path not found.")
        return freed, removed

    print(f"Scanning {_state.DOWNLOADS} for already-ingested items...")

    for item in _state._download_entries():
        full_path = os.path.join(_state.DOWNLOADS, item)

        if os.path.isdir(full_path):
            marker = os.path.join(full_path, _state.MARKER)
            if os.path.exists(marker):
                size = _state._dir_size(full_path)
                print(f"  {'Would remove' if dry_run else 'Removing'}: {item} ({_state._human_size(size)})")
                if not dry_run:
                    shutil.rmtree(full_path, ignore_errors=True)
                freed += size
                removed += 1
        else:
            ext = os.path.splitext(item)[1].lower()
            if ext in _state.ARCHIVE_EXTENSIONS:
                name_no_ext = os.path.splitext(item)[0]
                archive_dest = os.path.join(_state.RAW_ARCHIVE, name_no_ext)
                if os.path.exists(archive_dest):
                    size = os.path.getsize(full_path)
                    print(f"  {'Would remove' if dry_run else 'Removing'}: {item} ({_state._human_size(size)})")
                    if not dry_run:
                        os.remove(full_path)
                    freed += size
                    removed += 1

    print(f"\n{'Would free' if dry_run else 'Freed'}: {_state._human_size(freed)} ({removed} items)")
    return freed, removed


def purge_raw_archive(dry_run=False):
    """Purge _RAW-DOWNLOADS to free disk space. These are originals kept after ingest."""
    if not os.path.isdir(_state.RAW_ARCHIVE):
        print("No _RAW-DOWNLOADS directory found.")
        return 0, 0

    size = _state._dir_size(_state.RAW_ARCHIVE)
    count = sum(1 for _ in os.scandir(_state.RAW_ARCHIVE))
    print(f"_RAW-DOWNLOADS: {_state._human_size(size)} ({count} items)")

    if dry_run:
        print(f"Would free: {_state._human_size(size)}")
        return size, count

    for item in os.listdir(_state.RAW_ARCHIVE):
        full = os.path.join(_state.RAW_ARCHIVE, item)
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)
        else:
            os.remove(full)

    print(f"Freed: {_state._human_size(size)} ({count} items)")
    return size, count


def disk_usage_report():
    """Report disk usage for Downloads and library."""
    import shutil as sh
    total, used, free = sh.disk_usage('/')

    downloads_size = _state._dir_size(_state.DOWNLOADS) if os.path.isdir(_state.DOWNLOADS) else 0
    archive_size = _state._dir_size(_state.RAW_ARCHIVE) if os.path.isdir(_state.RAW_ARCHIVE) else 0
    library_size = _state._dir_size(_state.LIBRARY) if os.path.isdir(_state.LIBRARY) else 0

    cleanable = 0
    cleanable_count = 0
    for item in _state._download_entries():
        full = os.path.join(_state.DOWNLOADS, item)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, _state.MARKER)):
            cleanable += _state._dir_size(full)
            cleanable_count += 1
        elif os.path.isfile(full):
            ext = os.path.splitext(item)[1].lower()
            if ext in _state.ARCHIVE_EXTENSIONS:
                name_no_ext = os.path.splitext(item)[0]
                if os.path.exists(os.path.join(_state.RAW_ARCHIVE, name_no_ext)):
                    cleanable += os.path.getsize(full)
                    cleanable_count += 1

    return {
        'disk_free': free,
        'disk_free_str': _state._human_size(free),
        'disk_total': total,
        'downloads_size': downloads_size,
        'downloads_str': _state._human_size(downloads_size),
        'archive_size': archive_size,
        'archive_str': _state._human_size(archive_size),
        'library_size': library_size,
        'library_str': _state._human_size(library_size),
        'cleanable_size': cleanable,
        'cleanable_str': _state._human_size(cleanable),
        'cleanable_count': cleanable_count,
        'downloads_path': _state.DOWNLOADS,
    }
