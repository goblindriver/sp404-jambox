#!/usr/bin/env python3
"""
Ingest sample packs from ~/Downloads into the SP-404 sample library.

Modes:
    python scripts/ingest_downloads.py              # one-shot: process everything now
    python scripts/ingest_downloads.py --dry-run     # show what would happen
    python scripts/ingest_downloads.py --watch       # background watcher daemon

The watcher uses watchdog to monitor ~/Downloads for new audio files and
sample packs. It waits for downloads to finish (stable file size), ingests
them, auto-tags with tag_library.py --update, and logs everything.
"""
import os, sys, re, shutil, glob, time, argparse, subprocess, json, threading, fcntl
from datetime import datetime

DOWNLOADS = os.path.expanduser("~/Downloads")
LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
RAW_ARCHIVE = os.path.join(LIBRARY, "_RAW-DOWNLOADS")
INGEST_LOG = os.path.join(LIBRARY, "_ingest_log.json")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# File extensions we care about
AUDIO_EXTENSIONS = {'.wav', '.mp3', '.aiff', '.aif', '.flac', '.ogg'}
ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z'}
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | ARCHIVE_EXTENSIONS

# Extensions to always ignore
IGNORE_EXTENSIONS = {
    '.dmg', '.pkg', '.app', '.exe', '.msi', '.iso',  # installers
    '.pdf', '.doc', '.docx', '.txt', '.md',           # documents
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', # images
    '.mp4', '.mov', '.avi', '.mkv',                    # video
    '.torrent', '.crdownload', '.part',                # incomplete
    '.ds_store',
}

# Patterns that identify sample pack folders (vs. music albums)
SAMPLE_PACK_SUFFIXES = [
    'WAV-MASCHiNE', 'WAV-FMASCHiNE', 'WAV-EXPANSION', 'WAV-SONiTUS',
    'MULTiFORMAT-MASCHiNE', 'WAV-DISCOVER', 'WAV-FANTASTiC',
    'WAV-DECiBEL', 'WAV-PHOTONE', 'WAV-AUDIOSTRiKE',
]

# Already-processed marker file
MARKER = '.sp404-ingested'

# Watcher state — shared with web API
_watcher_state = {
    'running': False,
    'recent': [],       # last 50 ingested items
    'stats': {'files': 0, 'packs': 0, 'since': None},
}
_watcher_lock = threading.Lock()
_watcher_thread = None
_watcher_stop = threading.Event()


def get_watcher_state():
    """Get current watcher state (thread-safe)."""
    with _watcher_lock:
        return dict(_watcher_state)


def _log_ingest(source_name, num_samples, categories, source_type='pack'):
    """Write to ingest log and update watcher state."""
    entry = {
        'timestamp': datetime.now().isoformat(),
        'source': source_name,
        'type': source_type,
        'samples': num_samples,
        'categories': categories,
    }

    # Append to log file (with file locking to prevent concurrent clobber)
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

    # Update watcher state
    with _watcher_lock:
        _watcher_state['recent'].append(entry)
        _watcher_state['recent'] = _watcher_state['recent'][-50:]
        _watcher_state['stats']['files'] += num_samples
        if source_type == 'pack':
            _watcher_state['stats']['packs'] += 1


def is_sample_pack(dirname):
    """Check if a directory name looks like a sample pack."""
    for suffix in SAMPLE_PACK_SUFFIXES:
        if suffix in dirname:
            return True
    name_lower = dirname.lower()
    if any(kw in name_lower for kw in ['prime loops', 'sample magic', 'loopmasters',
                                        'sampleradar', 'musicradar', 'samples']):
        return True
    return False


def has_rar_files(folder):
    """Check if folder contains RAR archives."""
    return any(f.endswith('.rar') for f in os.listdir(folder))


def extract_archive(filepath, dest):
    """Extract zip/rar archive to destination."""
    os.makedirs(dest, exist_ok=True)
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.zip':
        print(f"  Extracting ZIP: {os.path.basename(filepath)}...")
        result = subprocess.run(
            ['unzip', '-o', '-q', filepath, '-d', dest],
            capture_output=True, text=True
        )
    elif ext == '.rar':
        print(f"  Extracting RAR: {os.path.basename(filepath)}...")
        result = subprocess.run(
            ['/opt/homebrew/bin/unar', '-o', dest, '-f', filepath],
            capture_output=True, text=True
        )
    elif ext == '.7z':
        print(f"  Extracting 7z: {os.path.basename(filepath)}...")
        result = subprocess.run(
            ['7z', 'x', filepath, f'-o{dest}', '-y'],
            capture_output=True, text=True
        )
    else:
        return False

    if result.returncode != 0:
        print(f"  Extract failed: {result.stderr[:200]}")
        return False
    return True


def extract_rar(folder, dest):
    """Extract RAR archive from a folder using unar."""
    rar_file = None
    for f in os.listdir(folder):
        if f.endswith('.rar'):
            rar_file = os.path.join(folder, f)
            break
    if not rar_file:
        return False
    return extract_archive(rar_file, dest)


def categorize_wav(filepath, pack_name):
    """Determine library category for a WAV file based on filename and path."""
    fname = os.path.basename(filepath).lower()
    dirpath = os.path.dirname(filepath).lower()
    parts = (fname + ' ' + dirpath).lower()

    # Drum hits
    if re.search(r'\bkick|bd\b|bassdrum', parts):
        return 'Drums/Kicks'
    if re.search(r'\bsnare|snr|sd\b|rimshot', parts):
        return 'Drums/Snares-Claps'
    if re.search(r'\bclap|handclap', parts):
        return 'Drums/Snares-Claps'
    if re.search(r'\bhi.?hat|hh\b|closed.?hat|open.?hat|hihat', parts):
        return 'Drums/Hi-Hats'
    if re.search(r'\bcymbal|crash|ride|splash', parts):
        return 'Drums/Percussion'
    if re.search(r'\bperc|shaker|tamb|conga|bongo|tom\b|cowbell|clave|rim', parts):
        return 'Drums/Percussion'

    # Drum loops
    if re.search(r'\bdrum.?loop|beat.?loop|break|drum.?break|full.?loop|top.?loop', parts):
        return 'Drums/Drum-Loops'
    if re.search(r'\b(loop|groove|pattern)\b', parts) and re.search(r'\b(drum|beat|perc|hat)\b', parts):
        return 'Drums/Drum-Loops'

    # Vocals
    if re.search(r'\bvocal|voice|vox|sing|choir|spoken|whisper|shout', parts):
        return 'Vocals/Chops'

    # Bass
    if re.search(r'\bbass|sub\b|808\b', parts) and not re.search(r'\bdrum', parts):
        return 'Melodic/Bass'

    # Guitar
    if re.search(r'\bguitar|gtr|riff\b|strum', parts):
        return 'Melodic/Guitar'

    # Keys / Piano
    if re.search(r'\bpiano|keys|rhodes|organ|clav|ep\b|electric.?piano', parts):
        return 'Melodic/Keys-Piano'

    # Synths and pads
    if re.search(r'\bsynth|pad\b|lead\b|arp\b|pluck|stab|chord', parts):
        return 'Melodic/Synths-Pads'

    # Ambient / textural
    if re.search(r'\bambient|atmosphere|atmos|texture|drone|field|foley|noise|space', parts):
        return 'Ambient-Textural/Atmospheres'

    # FX / SFX
    if re.search(r'\bfx|sfx|effect|riser|sweep|impact|down|transition|reverse', parts):
        return 'SFX/Stabs-Hits'

    # If it has "loop" in name, put in instrument loops
    if re.search(r'\bloop\b', parts):
        return 'Loops/Instrument-Loops'

    # Default: use pack context
    pack_lower = pack_name.lower()
    if 'drum' in pack_lower:
        return 'Drums/Percussion'
    if 'vocal' in pack_lower:
        return 'Vocals/Chops'
    if 'guitar' in pack_lower:
        return 'Melodic/Guitar'
    if 'piano' in pack_lower or 'keys' in pack_lower:
        return 'Melodic/Keys-Piano'
    if 'synth' in pack_lower or 'wave' in pack_lower:
        return 'Melodic/Synths-Pads'
    if 'ambient' in pack_lower or 'space' in pack_lower:
        return 'Ambient-Textural/Atmospheres'
    if 'funk' in pack_lower or 'soul' in pack_lower:
        return 'Loops/Instrument-Loops'
    if 'bass' in pack_lower:
        return 'Melodic/Bass'

    return 'Loops/Instrument-Loops'


def make_prefix(pack_name):
    """Create a short prefix from the pack name for organized files."""
    clean = pack_name.split('.WAV')[0].split('.MULTi')[0]
    clean = clean.replace('.', ' ').replace('-', ' ').replace('_', ' ')
    words = clean.split()
    skip = {'wav', 'maschine', 'expansion', 'sonitus', 'loops', 'samples', 'and', 'the', 'for'}
    words = [w for w in words if w.lower() not in skip]
    if len(words) > 4:
        words = words[:4]
    return '-'.join(words)


def read_source_context(filepath):
    """Check for a _SOURCE.txt alongside a file (from Cowork)."""
    base = os.path.splitext(filepath)[0]
    for suffix in ['_SOURCE.txt', '_source.txt', '.source.txt']:
        source_path = base + suffix
        if os.path.exists(source_path):
            try:
                with open(source_path) as f:
                    return f.read().strip()
            except IOError:
                pass
    # Also check same directory for a general _SOURCE.txt
    dir_source = os.path.join(os.path.dirname(filepath), '_SOURCE.txt')
    if os.path.exists(dir_source):
        try:
            with open(dir_source) as f:
                return f.read().strip()
        except IOError:
            pass
    return None


def ingest_single_file(filepath, dry_run=False):
    """Ingest a single audio file (not a pack) into the library."""
    fname = os.path.basename(filepath)
    ext = os.path.splitext(fname)[1].lower()

    if ext not in AUDIO_EXTENSIONS:
        return 0

    # Read any source context from Cowork
    source_context = read_source_context(filepath)

    category = categorize_wav(filepath, fname)
    dest_dir = os.path.join(LIBRARY, category)
    dest_path = os.path.join(dest_dir, fname)

    if os.path.exists(dest_path):
        print(f"  Already exists: {category}/{fname}")
        return 0

    if dry_run:
        print(f"  Would copy: {fname} → {category}")
        return 1

    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(filepath, dest_path)
    print(f"  → {category}/{fname}")

    # Store source context if available
    if source_context:
        _store_source_context(dest_path, source_context)

    # Move original out of Downloads
    archive_dest = os.path.join(RAW_ARCHIVE, fname)
    if filepath.startswith(DOWNLOADS):
        try:
            shutil.move(filepath, archive_dest)
            # Also move source file if it exists
            for suffix in ['_SOURCE.txt', '_source.txt', '.source.txt']:
                src = os.path.splitext(filepath)[0] + suffix
                if os.path.exists(src):
                    shutil.move(src, os.path.join(RAW_ARCHIVE, os.path.basename(src)))
        except Exception as e:
            print(f"  Could not move: {e}")

    _log_ingest(fname, 1, {category: 1}, source_type='file')
    return 1


def _store_source_context(wav_path, context):
    """Store Cowork source context in _tags.json for a file (with file locking)."""
    tags_path = os.path.join(LIBRARY, '_tags.json')
    if not os.path.exists(tags_path):
        return
    try:
        with open(tags_path, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            tags = json.load(f)
            rel = os.path.relpath(wav_path, LIBRARY)
            if rel in tags:
                tags[rel]['cowork_source'] = context
            else:
                tags[rel] = {'cowork_source': context}
            f.seek(0)
            f.truncate()
            json.dump(tags, f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, IOError):
        pass


def ingest_pack(pack_dir, dry_run=False):
    """Process one sample pack folder."""
    pack_name = os.path.basename(pack_dir)
    marker_path = os.path.join(pack_dir, MARKER)

    if os.path.exists(marker_path):
        return 0  # Already processed

    print(f"\n{'='*60}")
    print(f"Processing: {pack_name}")

    # Step 1: Extract if needed
    extract_dir = pack_dir
    if has_rar_files(pack_dir):
        extract_dir = os.path.join(RAW_ARCHIVE, pack_name)
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

    # Step 2: Find all audio files
    wav_files = []
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                wav_files.append(os.path.join(root, f))

    if not wav_files:
        print(f"  No audio files found")
        return 0

    print(f"  Found {len(wav_files)} audio files")

    # Read source context
    source_context = read_source_context(pack_dir)

    # Step 3: Categorize and copy
    prefix = make_prefix(pack_name)
    counts = {}
    for wav in wav_files:
        category = categorize_wav(wav, pack_name)
        dest_dir = os.path.join(LIBRARY, category)
        fname = os.path.basename(wav)
        dest_path = os.path.join(dest_dir, f"{prefix}_{fname}")

        if os.path.exists(dest_path):
            continue

        if dry_run:
            counts[category] = counts.get(category, 0) + 1
        else:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(wav, dest_path)
            counts[category] = counts.get(category, 0) + 1

            if source_context:
                _store_source_context(dest_path, source_context)

    for cat in sorted(counts):
        print(f"  → {cat}: {counts[cat]} files")
    total = sum(counts.values())
    print(f"  Total: {total} files {'would be ' if dry_run else ''}organized")

    # Mark as processed and move out of Downloads
    if not dry_run and total > 0:
        with open(marker_path, 'w') as f:
            f.write(f"Ingested {total} files at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Move the processed pack folder to _RAW-DOWNLOADS
        archive_dest = os.path.join(RAW_ARCHIVE, pack_name)
        if pack_dir.startswith(DOWNLOADS) and not os.path.exists(archive_dest):
            try:
                shutil.move(pack_dir, archive_dest)
                print(f"  Moved to: {archive_dest}")
            except Exception as e:
                print(f"  Could not move pack: {e}")

        _log_ingest(pack_name, total, counts, source_type='pack')

    return total


def ingest_archive_file(filepath, dry_run=False):
    """Ingest a standalone archive file (.zip, .rar, .7z)."""
    fname = os.path.basename(filepath)
    name_no_ext = os.path.splitext(fname)[0]

    # Extract to temp location
    extract_dest = os.path.join(RAW_ARCHIVE, name_no_ext)
    if os.path.exists(extract_dest):
        print(f"  Already extracted: {name_no_ext}")
        return 0

    print(f"\n{'='*60}")
    print(f"Processing archive: {fname}")

    if dry_run:
        print(f"  Would extract to: {extract_dest}")
        return 1  # Approximate

    if not extract_archive(filepath, extract_dest):
        return 0

    # Find audio files in extracted content
    wav_files = []
    for root, dirs, files in os.walk(extract_dest):
        for f in files:
            if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                wav_files.append(os.path.join(root, f))

    if not wav_files:
        print(f"  No audio files in archive")
        return 0

    print(f"  Found {len(wav_files)} audio files")

    source_context = read_source_context(filepath)
    prefix = make_prefix(name_no_ext)
    counts = {}

    for wav in wav_files:
        category = categorize_wav(wav, name_no_ext)
        dest_dir = os.path.join(LIBRARY, category)
        wav_fname = os.path.basename(wav)
        dest_path = os.path.join(dest_dir, f"{prefix}_{wav_fname}")

        if os.path.exists(dest_path):
            continue

        if dry_run:
            counts[category] = counts.get(category, 0) + 1
        else:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(wav, dest_path)
            counts[category] = counts.get(category, 0) + 1
            if source_context:
                _store_source_context(dest_path, source_context)

    for cat in sorted(counts):
        print(f"  → {cat}: {counts[cat]} files")
    total = sum(counts.values())
    print(f"  Total: {total} files {'would be ' if dry_run else ''}organized")

    # Move original archive to _RAW-DOWNLOADS
    if not dry_run and filepath.startswith(DOWNLOADS):
        try:
            shutil.move(filepath, os.path.join(RAW_ARCHIVE, fname))
            print(f"  Moved archive to _RAW-DOWNLOADS")
            # Also move source file if exists
            for suffix in ['_SOURCE.txt', '_source.txt', '.source.txt']:
                src = os.path.splitext(filepath)[0] + suffix
                if os.path.exists(src):
                    shutil.move(src, os.path.join(RAW_ARCHIVE, os.path.basename(src)))
        except Exception as e:
            print(f"  Could not move: {e}")

    if total > 0:
        _log_ingest(fname, total, counts, source_type='pack')

    return total


def find_sample_packs():
    """Find sample pack folders in Downloads."""
    packs = []
    for item in sorted(os.listdir(DOWNLOADS)):
        full_path = os.path.join(DOWNLOADS, item)
        if not os.path.isdir(full_path):
            continue
        if is_sample_pack(item):
            packs.append(full_path)
    return packs


def run_auto_tag():
    """Run tag_library.py --update on new files."""
    tag_script = os.path.join(SCRIPTS_DIR, 'tag_library.py')
    if not os.path.exists(tag_script):
        print("  tag_library.py not found, skipping auto-tag")
        return
    print("  Auto-tagging new files...")
    try:
        result = subprocess.run(
            [sys.executable, tag_script, '--update'],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, 'PATH': f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"},
        )
        if result.returncode == 0:
            # Count tagged
            for line in result.stdout.split('\n'):
                if 'tagged' in line.lower() or 'updated' in line.lower():
                    print(f"  {line.strip()}")
        else:
            print(f"  Tag update warning: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print("  Tag update timed out (2min)")
    except Exception as e:
        print(f"  Tag update error: {e}")


def wait_for_stable(filepath, poll_interval=2.0, stable_count=3):
    """Wait for a file to stop growing (download complete)."""
    last_size = -1
    stable = 0
    for _ in range(60):  # Max ~2 minutes
        try:
            size = os.path.getsize(filepath)
        except OSError:
            return False  # File disappeared

        if size == last_size and size > 0:
            stable += 1
            if stable >= stable_count:
                return True
        else:
            stable = 0
        last_size = size
        time.sleep(poll_interval)
    return False


def should_ignore(filepath):
    """Check if a file should be ignored."""
    fname = os.path.basename(filepath)
    ext = os.path.splitext(fname)[1].lower()

    # Ignore by extension
    if ext in IGNORE_EXTENSIONS:
        return True

    # Not in our allowlist
    if ext not in ALLOWED_EXTENSIONS:
        return True

    # Hidden files
    if fname.startswith('.'):
        return True

    # Already in _RAW-DOWNLOADS
    if RAW_ARCHIVE in filepath:
        return True

    return False


# ── Watchdog Watcher ──

def start_watcher():
    """Start the background file watcher daemon."""
    global _watcher_thread
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("ERROR: watchdog not installed. Run: pip install watchdog")
        return False

    if _watcher_state['running']:
        print("Watcher already running")
        return True

    _watcher_stop.clear()

    class IngestHandler(FileSystemEventHandler):
        """Handle new files appearing in ~/Downloads."""

        def __init__(self):
            super().__init__()
            self._pending = {}  # filepath -> first_seen_time
            self._processed = set()

        def on_created(self, event):
            if event.is_directory:
                return
            filepath = event.src_path
            if should_ignore(filepath):
                return
            self._pending[filepath] = time.time()

        def on_moved(self, event):
            """Handle files moved into Downloads (e.g., browser moves .crdownload → .zip)."""
            if event.is_directory:
                return
            filepath = event.dest_path
            if should_ignore(filepath):
                return
            self._pending[filepath] = time.time()

        def process_pending(self):
            """Check pending files and ingest stable ones."""
            to_remove = []
            ingested_any = False

            for filepath, first_seen in list(self._pending.items()):
                if filepath in self._processed:
                    to_remove.append(filepath)
                    continue

                if not os.path.exists(filepath):
                    to_remove.append(filepath)
                    continue

                # Wait at least 5 seconds before checking
                if time.time() - first_seen < 5:
                    continue

                # Check if file is stable
                try:
                    size1 = os.path.getsize(filepath)
                    time.sleep(2)
                    size2 = os.path.getsize(filepath)
                except OSError:
                    to_remove.append(filepath)
                    continue

                if size1 != size2 or size1 == 0:
                    continue  # Still downloading

                # File is stable — ingest it
                fname = os.path.basename(filepath)
                ext = os.path.splitext(fname)[1].lower()
                print(f"\n[WATCHER] New file ready: {fname}")

                if ext in ARCHIVE_EXTENSIONS:
                    count = ingest_archive_file(filepath)
                elif ext in AUDIO_EXTENSIONS:
                    count = ingest_single_file(filepath)
                else:
                    count = 0

                if count > 0:
                    ingested_any = True
                    print(f"[WATCHER] Ingested {count} sample(s) from {fname}")

                self._processed.add(filepath)
                to_remove.append(filepath)

            for fp in to_remove:
                self._pending.pop(fp, None)

            # Auto-tag after ingesting
            if ingested_any:
                run_auto_tag()

    handler = IngestHandler()
    observer = Observer()
    observer.schedule(handler, DOWNLOADS, recursive=False)

    def watcher_loop():
        observer.start()
        with _watcher_lock:
            _watcher_state['running'] = True
            _watcher_state['stats']['since'] = datetime.now().isoformat()
        print(f"[WATCHER] Monitoring {DOWNLOADS} for new samples...")

        try:
            while not _watcher_stop.is_set():
                handler.process_pending()
                _watcher_stop.wait(timeout=3)
        except Exception as e:
            print(f"[WATCHER] Error: {e}")
        finally:
            observer.stop()
            observer.join()
            with _watcher_lock:
                _watcher_state['running'] = False
            print("[WATCHER] Stopped")

    _watcher_thread = threading.Thread(target=watcher_loop, daemon=True)
    _watcher_thread.start()
    return True


def stop_watcher():
    """Stop the background file watcher."""
    if not _watcher_state['running']:
        return
    _watcher_stop.set()
    if _watcher_thread:
        _watcher_thread.join(timeout=10)
    with _watcher_lock:
        _watcher_state['running'] = False


def one_shot_ingest(dry_run=False):
    """Run a single ingest pass (original behavior)."""
    os.makedirs(LIBRARY, exist_ok=True)
    os.makedirs(RAW_ARCHIVE, exist_ok=True)

    # Process sample pack folders
    packs = find_sample_packs()
    total = 0
    pack_count = 0

    if packs:
        for pack in packs:
            count = ingest_pack(pack, dry_run=dry_run)
            total += count
            if count > 0:
                pack_count += 1

    # Also check for standalone audio files and archives in Downloads
    for item in sorted(os.listdir(DOWNLOADS)):
        filepath = os.path.join(DOWNLOADS, item)
        if os.path.isdir(filepath):
            continue
        if should_ignore(filepath):
            continue

        ext = os.path.splitext(item)[1].lower()
        if ext in ARCHIVE_EXTENSIONS:
            total += ingest_archive_file(filepath, dry_run=dry_run)
            pack_count += 1
        elif ext in AUDIO_EXTENSIONS:
            total += ingest_single_file(filepath, dry_run=dry_run)

    if total == 0 and not packs:
        print("No sample packs or audio files found in Downloads.")
    else:
        print(f"\n{'='*60}")
        print(f"Processed {pack_count} packs, {total} files organized")
        print(f"Library: {LIBRARY}")

        # Auto-tag new files
        if total > 0 and not dry_run:
            run_auto_tag()

    return total


def main():
    parser = argparse.ArgumentParser(description='Ingest sample packs from Downloads')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen')
    parser.add_argument('--watch', action='store_true', help='Run as background watcher daemon')
    args = parser.parse_args()

    os.makedirs(LIBRARY, exist_ok=True)
    os.makedirs(RAW_ARCHIVE, exist_ok=True)

    if args.watch:
        # Watcher mode — run one pass first, then watch
        print("Running initial ingest pass...")
        one_shot_ingest(dry_run=args.dry_run)

        if args.dry_run:
            print("\nDry run — not starting watcher")
            return

        if not start_watcher():
            sys.exit(1)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping watcher...")
            stop_watcher()
    else:
        one_shot_ingest(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
