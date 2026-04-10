"""Shared state, constants, configuration, and small utilities for the ingest package."""
import os
import sys
import json
import fcntl
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings_for_script

# Load settings using the original script location (not nested package)
_SCRIPT_PATH = os.path.join(SCRIPTS_DIR, "ingest_downloads.py")
SETTINGS = load_settings_for_script(_SCRIPT_PATH)
DOWNLOADS = SETTINGS["DOWNLOADS_PATH"]
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
RAW_ARCHIVE = SETTINGS["RAW_ARCHIVE"]
INGEST_LOG = SETTINGS["INGEST_LOG"]
FFMPEG = SETTINGS["FFMPEG_BIN"]

REPO_DIR = os.path.dirname(SCRIPTS_DIR)

# File extensions we care about
AUDIO_EXTENSIONS = {'.wav', '.mp3', '.aiff', '.aif', '.flac', '.ogg'}
ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z'}
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | ARCHIVE_EXTENSIONS

# Extensions to always ignore
IGNORE_EXTENSIONS = {
    '.dmg', '.pkg', '.app', '.exe', '.msi', '.iso',  # installers
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', # images
    '.mp4', '.mov', '.avi', '.mkv',                    # video
    '.torrent', '.crdownload', '.part',                # incomplete
    '.ds_store',
}

# Document extensions that get routed to docs/ (not ignored)
DOC_EXTENSIONS = {'.pdf', '.doc', '.docx', '.md', '.txt'}

# Doc deliverable patterns -- Chat/Cowork drop these in ~/Downloads for Code to pick up
DOC_DELIVERABLE_PATTERNS = {
    'CODE_BRIEF_':      'docs/briefs',
    'COWORK_BRIEF_':    'docs/briefs',
    'CHAT_RESPONSE_':   'docs/briefs',
    'HANDOFF_SESSION':  'docs/handoffs',
    'HANDOFF_':         'docs/handoffs',
    'BUG_HUNT_':        'docs/handoffs',
    '_SOURCE':          'docs/sources',
    '_SOURCES':         'docs/sources',
    'SOURCES_':         'docs/sources',
    '_REFERENCE':       'docs/references',
    '_Reference':       'docs/references',
    '_Research':        'docs/research',
    'Research_':        'docs/research',
    '_RESEARCH':        'docs/research',
    '_PITCH':           'docs/briefs',
    'PIPELINE_':        'docs/briefs',
    '_SPEC':            'docs',
    'WEBAPP_':          'docs',
    'Playlist_Mining':  'docs/research',
    'Sample_Pack_':     'docs/research',
}

# Special doc files that go to repo root instead of docs/
DOC_ROOT_FILES = {'CLAUDE.md'}

# Background stem splitting -- single worker to avoid overwhelming the system
_stem_executor = ThreadPoolExecutor(max_workers=1)
_stem_futures = []

# Recent fingerprints for fast inline dedup (capped)
_recent_fingerprints = {}
_fingerprint_lock = threading.Lock()
_RECENT_FP_CAP = 1000

# Patterns that identify sample pack folders (vs. music albums)
SAMPLE_PACK_SUFFIXES = [
    'WAV-MASCHiNE', 'WAV-FMASCHiNE', 'WAV-EXPANSION', 'WAV-SONiTUS',
    'MULTiFORMAT-MASCHiNE', 'WAV-DISCOVER', 'WAV-FANTASTiC',
    'WAV-DECiBEL', 'WAV-PHOTONE', 'WAV-AUDIOSTRiKE',
]

# Already-processed marker file
MARKER = '.sp404-ingested'

# Watcher state -- shared with web API
_watcher_state = {
    'running': False,
    'recent': [],
    'stats': {'files': 0, 'packs': 0, 'since': None},
}
_watcher_lock = threading.Lock()
_watcher_thread = None
_watcher_stop = threading.Event()


def _download_entries():
    try:
        return sorted(os.listdir(DOWNLOADS))
    except OSError:
        return []


def get_watcher_state():
    """Get current watcher state (thread-safe)."""
    with _watcher_lock:
        return dict(_watcher_state)


def set_downloads_path(path):
    """Change the downloads watch path (runtime only)."""
    global DOWNLOADS
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        raise ValueError(f"Not a directory: {path}")
    DOWNLOADS = path
    return DOWNLOADS


def _log_ingest(source_name, num_samples, categories, source_type='pack'):
    """Write to ingest log and update watcher state."""
    entry = {
        'timestamp': datetime.now().isoformat(),
        'source': source_name,
        'type': source_type,
        'samples': num_samples,
        'categories': categories,
    }

    log = []
    try:
        with open(INGEST_LOG, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                log = json.load(f)
            except (json.JSONDecodeError, ValueError):
                log = []
            log.append(entry)
            log = log[-500:]
            f.seek(0)
            f.truncate()
            json.dump(log, f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)
    except FileNotFoundError:
        with open(INGEST_LOG, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump([entry], f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)

    with _watcher_lock:
        _watcher_state['recent'].append(entry)
        _watcher_state['recent'] = _watcher_state['recent'][-50:]
        _watcher_state['stats']['files'] += num_samples
        if source_type == 'pack':
            _watcher_state['stats']['packs'] += 1


def _dir_size(path):
    """Get total size of a directory."""
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _human_size(size):
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
