"""File watcher daemon for auto-ingesting new downloads."""
import os
import time
import threading
from datetime import datetime

from . import _state
from .archive import should_ignore, archive_has_audio
from .orchestration import ingest_single_file, ingest_archive_file


def ingest_ready_file(filepath):
    """Ingest one stable download. Never raises: one bad file is logged and
    skipped so it can't stop the watcher. Returns the number of samples added."""
    fname = os.path.basename(filepath)
    ext = os.path.splitext(fname)[1].lower()
    print(f"\n[WATCHER] New file ready: {fname}")
    try:
        if ext in _state.ARCHIVE_EXTENSIONS:
            if not archive_has_audio(filepath):
                print(f"[WATCHER] Skipping {fname} — no audio inside")
                return 0
            count = ingest_archive_file(filepath)
        elif ext in _state.AUDIO_EXTENSIONS:
            count = ingest_single_file(filepath)
        else:
            count = 0
    except Exception as e:
        print(f"[WATCHER] Failed to ingest {fname}: {e}")
        return 0
    if count > 0:
        print(f"[WATCHER] Ingested {count} sample(s) from {fname}")
    return count


def start_watcher(dedupe=False):
    """Start the background file watcher daemon."""
    if not os.path.isdir(_state.DOWNLOADS):
        print(f"ERROR: downloads path not found: {_state.DOWNLOADS}")
        return False
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("ERROR: watchdog not installed. Run: pip install watchdog")
        return False

    with _state._watcher_lock:
        if _state._watcher_state.get('_observer_active') or (
            _state._watcher_thread is not None and _state._watcher_thread.is_alive()
        ):
            print("Watcher already running")
            return True

    _state._watcher_stop.clear()

    class IngestHandler(FileSystemEventHandler):
        """Handle new files appearing in ~/Downloads."""

        def __init__(self):
            super().__init__()
            self._pending = {}
            self._processed = set()

        def on_created(self, event):
            if event.is_directory:
                return
            filepath = event.src_path
            if should_ignore(filepath):
                return
            self._pending[filepath] = time.time()

        def on_moved(self, event):
            """Handle files moved into Downloads (e.g., browser moves .crdownload -> .zip)."""
            if event.is_directory:
                return
            filepath = event.dest_path
            if should_ignore(filepath):
                return
            self._pending[filepath] = time.time()

        def process_pending(self):
            """Check pending files and ingest stable ones."""
            to_remove = []

            for filepath, first_seen in list(self._pending.items()):
                if filepath in self._processed:
                    to_remove.append(filepath)
                    continue

                if not os.path.exists(filepath):
                    to_remove.append(filepath)
                    continue

                if time.time() - first_seen < 5:
                    continue

                try:
                    size1 = os.path.getsize(filepath)
                    time.sleep(2)
                    size2 = os.path.getsize(filepath)
                except OSError:
                    to_remove.append(filepath)
                    continue

                if size1 != size2 or size1 == 0:
                    continue

                ingest_ready_file(filepath)
                self._processed.add(filepath)
                to_remove.append(filepath)

            for fp in to_remove:
                self._pending.pop(fp, None)

    handler = IngestHandler()
    observer = Observer()
    observer.schedule(handler, _state.DOWNLOADS, recursive=False)

    def watcher_loop():
        observer.start()
        with _state._watcher_lock:
            _state._watcher_state['running'] = True
            _state._watcher_state['_observer_active'] = True
            _state._watcher_state['stats'] = {'files': 0, 'packs': 0, 'since': datetime.now().isoformat()}
        print(f"[WATCHER] Monitoring {_state.DOWNLOADS} for new samples...")

        try:
            while not _state._watcher_stop.is_set():
                try:
                    handler.process_pending()
                except Exception as e:
                    print(f"[WATCHER] Error: {e}")
                _state._watcher_stop.wait(timeout=3)
        finally:
            observer.stop()
            observer.join()
            with _state._watcher_lock:
                _state._watcher_state['running'] = False
                _state._watcher_state['_observer_active'] = False
            print("[WATCHER] Stopped")

    _state._watcher_thread = threading.Thread(target=watcher_loop, daemon=True)
    _state._watcher_thread.start()
    return True


def stop_watcher():
    """Stop the background file watcher.

    Returns False if the watcher thread is still busy ingesting after the
    timeout; it stops (and clears its own running flags) when that file is done.
    """
    if not _state._watcher_state['running']:
        return True
    _state._watcher_stop.set()
    thread = _state._watcher_thread
    if thread:
        thread.join(timeout=10)
        if thread.is_alive():
            print("[WATCHER] Still finishing the current file; it will stop when done")
            return False
    return True
