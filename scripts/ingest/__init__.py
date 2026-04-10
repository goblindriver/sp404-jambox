"""Ingest package — split from ingest_downloads.py monolith.

Public API re-exports for backward compatibility.
"""
from . import _state
from ._state import (
    AUDIO_EXTENSIONS, ARCHIVE_EXTENSIONS,
    _watcher_state, _watcher_lock,
    get_watcher_state, set_downloads_path,
    _human_size, _dir_size, _download_entries,
)

# Path constants are re-assignable at runtime (set_downloads_path), so
# delegate attribute access to _state to avoid stale local bindings.
_DELEGATED_ATTRS = frozenset(('DOWNLOADS', 'LIBRARY', 'RAW_ARCHIVE', 'INGEST_LOG', 'SETTINGS'))

def __getattr__(name):
    if name in _DELEGATED_ATTRS:
        return getattr(_state, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
from .archive import extract_archive
from .orchestration import (
    one_shot_ingest, ingest_single_file, ingest_pack, ingest_archive_file,
)
from .watcher import start_watcher, stop_watcher
from .cleanup import cleanup_downloads, purge_raw_archive, disk_usage_report
