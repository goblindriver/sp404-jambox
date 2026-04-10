"""Ingest package — split from ingest_downloads.py monolith.

Public API re-exports for backward compatibility.
"""
from ._state import (
    DOWNLOADS, LIBRARY, RAW_ARCHIVE, INGEST_LOG, SETTINGS,
    AUDIO_EXTENSIONS, ARCHIVE_EXTENSIONS,
    _watcher_state, _watcher_lock,
    get_watcher_state, set_downloads_path,
    _human_size, _dir_size, _download_entries,
)
from .archive import extract_archive
from .docs import ingest_doc_deliverables
from .orchestration import (
    one_shot_ingest, ingest_single_file, ingest_pack, ingest_archive_file,
)
from .watcher import start_watcher, stop_watcher
from .cleanup import cleanup_downloads, purge_raw_archive, disk_usage_report
