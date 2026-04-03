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
import os, sys, re, shutil, glob, time, argparse, subprocess, json, threading, fcntl, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import yaml

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import build_subprocess_env, load_settings_for_script

SETTINGS = load_settings_for_script(__file__)
DOWNLOADS = SETTINGS["DOWNLOADS_PATH"]
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
RAW_ARCHIVE = SETTINGS["RAW_ARCHIVE"]
INGEST_LOG = SETTINGS["INGEST_LOG"]
FFMPEG = SETTINGS["FFMPEG_BIN"]

# File extensions we care about
AUDIO_EXTENSIONS = {'.wav', '.mp3', '.aiff', '.aif', '.flac', '.ogg'}
ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z'}
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | ARCHIVE_EXTENSIONS

# Extensions to always ignore
IGNORE_EXTENSIONS = {
    '.dmg', '.pkg', '.app', '.exe', '.msi', '.iso',  # installers
    '.pdf', '.doc', '.docx',                           # non-deliverable documents
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', # images
    '.mp4', '.mov', '.avi', '.mkv',                    # video
    '.torrent', '.crdownload', '.part',                # incomplete
    '.ds_store',
}

# Doc deliverable patterns — Chat/Cowork drop these in ~/Downloads for Code to pick up
DOC_DELIVERABLE_PATTERNS = {
    'CODE_BRIEF_':      'docs',     # Code briefs → docs/
    'COWORK_BRIEF_':    'docs',     # Cowork briefs → docs/
    'HANDOFF':          'docs',     # Session handoffs → docs/
    'BUG_HUNT_':        'docs',     # Bug hunt reports → docs/
    '_SOURCE':          'docs',     # Source research docs → docs/
    '_SOURCES':         'docs',     # Source lists → docs/
    'SOURCES_':         'docs',     # Source lists → docs/
    '_Reference':       'docs',     # Sound design reference docs → docs/
    '_Sound_Design':    'docs',     # Sound design docs → docs/
    'Playlist_Mining':  'docs',     # Playlist analysis → docs/
    'Sample_Pack_':     'docs',     # Sample pack research → docs/
    'playlist_':        'docs',     # Playlist data → docs/
    'sound_design_':    'docs',     # Sound design references → docs/
    'WEBAPP_':          'docs',     # Web app specs → docs/
}

# Special doc files that go to repo root instead of docs/
DOC_ROOT_FILES = {'CLAUDE.md'}

# Background stem splitting — single worker to avoid overwhelming the system
_stem_executor = ThreadPoolExecutor(max_workers=1)
_stem_futures = []

# Recent fingerprints for fast inline dedup (capped)
_recent_fingerprints = {}
_RECENT_FP_CAP = 1000

REPO_DIR = os.path.dirname(SCRIPTS_DIR)

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


def _download_entries():
    try:
        return sorted(os.listdir(DOWNLOADS))
    except OSError:
        return []


def get_watcher_state():
    """Get current watcher state (thread-safe)."""
    with _watcher_lock:
        return dict(_watcher_state)


def _is_doc_deliverable(filename):
    """Check if a file is a Chat/Cowork doc deliverable based on naming convention."""
    name = os.path.basename(filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in ('.md', '.txt'):
        return None
    if name in DOC_ROOT_FILES:
        return REPO_DIR  # goes to repo root
    for pattern, dest_dir in DOC_DELIVERABLE_PATTERNS.items():
        if pattern in name:
            return os.path.join(REPO_DIR, dest_dir)
    return None


def ingest_doc_deliverables(dry_run=False):
    """Scan ~/Downloads for Chat/Cowork doc deliverables and copy to repo.

    Returns (copied, skipped) counts.
    """
    if not os.path.isdir(DOWNLOADS):
        return 0, 0

    copied = 0
    skipped = 0

    for item in _download_entries():
        filepath = os.path.join(DOWNLOADS, item)
        if os.path.isdir(filepath):
            continue

        dest_dir = _is_doc_deliverable(item)
        if dest_dir is None:
            continue

        dest_path = os.path.join(dest_dir, item)

        # Skip if identical file already exists in repo
        if os.path.exists(dest_path):
            try:
                if os.path.getsize(filepath) == os.path.getsize(dest_path):
                    if not dry_run:
                        os.remove(filepath)
                    print(f"  Already in repo, {'would clean' if dry_run else 'cleaned'}: {item}")
                    skipped += 1
                    continue
            except OSError:
                pass

        rel_dest = os.path.relpath(dest_path, REPO_DIR)
        print(f"  {'Would copy' if dry_run else 'Copying'}: {item} → {rel_dest}")
        if not dry_run:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(filepath, dest_path)
            os.remove(filepath)
        copied += 1

    return copied, skipped


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

    # Step 2: Fingerprint and inline dedup check
    is_dup = False
    try:
        from deduplicate_samples import compute_fingerprint, similarity
        fp = compute_fingerprint(library_path)
        if fp:
            # Check against recent fingerprints
            for other_path, other_fp in _recent_fingerprints.items():
                if other_path == rel_path:
                    continue
                sim = similarity(fp, other_fp)
                if sim is not None and sim >= 0.95:
                    print(f"  [ROUTE] Duplicate detected ({sim:.2f}): {rel_path}")
                    print(f"          Matches: {other_path}")
                    is_dup = True
                    break

            # Add to recent set (cap it)
            if len(_recent_fingerprints) >= _RECENT_FP_CAP:
                oldest = next(iter(_recent_fingerprints))
                del _recent_fingerprints[oldest]
            _recent_fingerprints[rel_path] = fp
    except Exception as e:
        print(f"  [ROUTE] Fingerprint skipped: {e}")

    if is_dup:
        # Move to _DUPES instead of keeping
        dupes_dir = os.path.join(LIBRARY, "_DUPES")
        os.makedirs(dupes_dir, exist_ok=True)
        try:
            dupe_dest = os.path.join(dupes_dir, os.path.basename(library_path))
            shutil.move(library_path, dupe_dest)
        except Exception:
            pass
        return 'duplicate'

    # Step 3: Duration-based routing
    duration = entry.get('duration', 0) or 0
    type_code = entry.get('type_code', 'UNK')

    if duration > 60 and type_code != 'VOX':
        # Full track — queue background stem split
        _queue_stem_split(library_path, rel_path, entry)
        return 'stem-queued'

    return 'keep'


def _queue_stem_split(library_path, rel_path, tag_entry):
    """Submit a stem split job to the background executor."""
    future = _stem_executor.submit(_stem_split_task, library_path, rel_path, tag_entry)
    _stem_futures.append(future)
    print(f"  [ROUTE] Queued stem split: {os.path.basename(library_path)} ({tag_entry.get('duration', 0):.0f}s)")


def _stem_split_task(library_path, rel_path, parent_tags):
    """Background task: run Demucs stem separation and ingest stems.

    Uses htdemucs for 4-stem separation (drums, bass, vocals, other).
    Each stem gets tagged with parent metadata.
    """
    import tempfile

    print(f"\n[STEMS] Starting split: {os.path.basename(library_path)}")

    # Check for demucs
    try:
        subprocess.run(['demucs', '--help'], capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("[STEMS] Demucs not installed — skipping stem split")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                ['demucs', '--two-stems=drums', '-n', 'htdemucs',
                 '-o', tmpdir, library_path],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                print(f"[STEMS] Demucs failed: {result.stderr[:200]}")
                # Try simpler 4-stem
                result = subprocess.run(
                    ['demucs', '-n', 'htdemucs', '-o', tmpdir, library_path],
                    capture_output=True, text=True, timeout=600,
                )
                if result.returncode != 0:
                    print(f"[STEMS] Demucs retry failed: {result.stderr[:200]}")
                    return
        except subprocess.TimeoutExpired:
            print("[STEMS] Demucs timed out (10min)")
            return

        # Find output stems
        stem_base = os.path.splitext(os.path.basename(library_path))[0]
        stem_dir = None
        for root, dirs, files in os.walk(tmpdir):
            if any(f.endswith('.wav') for f in files):
                stem_dir = root
                break

        if not stem_dir:
            print("[STEMS] No stems produced")
            return

        # Map stems to library categories
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

            dest_dir = os.path.join(LIBRARY, category)
            os.makedirs(dest_dir, exist_ok=True)
            dest_fname = "{}_stem-{}.flac".format(stem_base, stem_name)
            dest_path = os.path.join(dest_dir, dest_fname)

            if os.path.exists(dest_path):
                continue

            src_path = os.path.join(stem_dir, stem_file)
            _copy_as_flac(src_path, os.path.join(dest_dir, "{}_stem-{}.wav".format(stem_base, stem_name)))
            ingested += 1

        if ingested > 0:
            print(f"[STEMS] Split {os.path.basename(library_path)} → {ingested} stems")

            # Tag the new stems
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
                    stem_full = os.path.join(LIBRARY, stem_rel)
                    if os.path.exists(stem_full):
                        stem_entry = tag_file(stem_rel, stem_full, get_dur=True, use_librosa=True)
                        # Carry parent metadata
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

            _log_ingest(
                "{} (stems)".format(os.path.basename(library_path)),
                ingested,
                {'stems': ingested},
                source_type='stem-split',
            )


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
    try:
        return any(f.endswith('.rar') for f in os.listdir(folder))
    except OSError:
        return False


def archive_has_audio(filepath):
    """Quick check if a zip archive contains audio files (without extracting)."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.zip':
        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                for name in zf.namelist():
                    if os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
                        return True
            return False
        except Exception:
            return True  # If we can't peek, let the full extract path handle it
    # For .rar/.7z we can't easily peek — let them through
    return True


def check_chat_delivery(filepath):
    """Check if a zip contains a _DELIVERY.yaml manifest from Chat.

    Chat drops zips into ~/Downloads with a _DELIVERY.yaml inside that tells
    the watcher what to do with the contents (install presets, update tags, etc.)

    Returns the delivery manifest dict, or None if not a Chat delivery.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext != '.zip':
        return None
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            names = zf.namelist()
            # Look for _DELIVERY.yaml at any level
            manifest_name = None
            for name in names:
                if os.path.basename(name) == '_DELIVERY.yaml':
                    manifest_name = name
                    break
            if not manifest_name:
                return None
            with zf.open(manifest_name) as mf:
                manifest = yaml.safe_load(mf)
            if isinstance(manifest, dict) and manifest.get('from') == 'chat':
                return manifest
    except Exception:
        return None
    return None


def handle_chat_delivery(filepath, manifest):
    """Process a Chat delivery zip based on its manifest.

    Supported delivery types:
      - presets: Install preset YAML files into presets/<category>/
      - tags: (future) Update tag mappings
      - config: (future) Update bank_config or other settings

    Returns number of items installed, or 0 on failure.
    """
    # Import preset_utils here to avoid circular imports at module level
    sys.path.insert(0, SCRIPTS_DIR) if SCRIPTS_DIR not in sys.path else None
    from preset_utils import save_preset, CATEGORIES

    delivery_type = manifest.get('type', '')
    message = manifest.get('message', '')
    category = manifest.get('category', 'community')

    print(f"\n{'='*60}")
    print(f"[DELIVERY] 📬 Message in a bottle from Chat!")
    if message:
        print(f"[DELIVERY] \"{message}\"")
    print(f"[DELIVERY] Type: {delivery_type}")

    if delivery_type == 'presets':
        return _install_preset_delivery(filepath, category)
    else:
        print(f"[DELIVERY] Unknown delivery type: {delivery_type} — skipping")
        return 0


def _install_preset_delivery(filepath, default_category='community'):
    """Extract and install preset YAML files from a Chat delivery zip."""
    from preset_utils import save_preset, CATEGORIES

    count = 0
    installed = []

    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            for name in zf.namelist():
                # Only process .yaml files, skip the manifest itself
                if not name.endswith('.yaml') or os.path.basename(name) == '_DELIVERY.yaml':
                    continue

                try:
                    with zf.open(name) as yf:
                        preset = yaml.safe_load(yf)
                except Exception as e:
                    print(f"[DELIVERY] Failed to parse {name}: {e}")
                    continue

                if not isinstance(preset, dict) or 'name' not in preset:
                    print(f"[DELIVERY] Skipping {name} — not a valid preset (missing 'name')")
                    continue

                # Determine category: from the preset file, from path, or from manifest default
                cat = preset.get('category', None)
                if not cat:
                    # Try to infer from zip path (e.g., genre/big-beat-blowout.yaml)
                    parts = name.replace('\\', '/').split('/')
                    if len(parts) >= 2 and parts[-2] in CATEGORIES:
                        cat = parts[-2]
                    else:
                        cat = default_category

                ref = save_preset(preset, category=cat)
                preset_name = preset.get('name', name)
                installed.append(f"{cat}/{preset.get('slug', name)}")
                count += 1
                print(f"[DELIVERY] ✅ Installed preset: {preset_name} → presets/{cat}/")

    except Exception as e:
        print(f"[DELIVERY] Error processing delivery: {e}")
        return 0

    if count > 0:
        print(f"[DELIVERY] 📦 {count} preset(s) installed: {', '.join(installed)}")

        # Log the delivery
        _log_delivery(filepath, 'presets', installed)

    return count


def _log_delivery(filepath, delivery_type, items):
    """Log a Chat delivery using the standard ingest log + watcher feed."""
    _log_ingest(
        source_name=f"📬 Chat delivery: {os.path.basename(filepath)}",
        num_samples=len(items),
        categories={delivery_type: len(items)},
        source_type='chat-delivery',
    )


def extract_archive(filepath, dest):
    """Extract zip/rar archive to destination."""
    os.makedirs(dest, exist_ok=True)
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.zip':
        print(f"  Extracting ZIP: {os.path.basename(filepath)}...")
        command = ['unzip', '-o', '-q', filepath, '-d', dest]
    elif ext == '.rar':
        print(f"  Extracting RAR: {os.path.basename(filepath)}...")
        command = [SETTINGS["UNAR_BIN"], '-o', dest, '-f', filepath]
    elif ext == '.7z':
        print(f"  Extracting 7z: {os.path.basename(filepath)}...")
        command = ['7z', 'x', filepath, f'-o{dest}', '-y']
    else:
        return False

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        print(f"  Extract failed: command not found for {ext} archives")
        return False
    except subprocess.TimeoutExpired:
        print(f"  Extract failed: timed out for {os.path.basename(filepath)}")
        return False

    if result.returncode != 0:
        print(f"  Extract failed: {result.stderr[:200]}")
        return False
    return True


def _copy_as_flac(src_path, dest_path):
    """Copy an audio file to the library, converting to FLAC for storage.
    Returns the actual destination path (with .flac extension)."""
    # Change extension to .flac
    flac_dest = os.path.splitext(dest_path)[0] + '.flac'
    if os.path.exists(flac_dest):
        return flac_dest  # already exists

    try:
        result = subprocess.run(
            [FFMPEG, '-y', '-i', src_path, '-c:a', 'flac', '-compression_level', '5', flac_dest],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and os.path.exists(flac_dest):
            return flac_dest
    except (subprocess.TimeoutExpired, Exception):
        pass

    # Fallback: just copy the original if FLAC conversion fails
    if not os.path.exists(dest_path):
        shutil.copy2(src_path, dest_path)
    return dest_path


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

    # Check for both WAV and FLAC versions
    flac_dest = os.path.splitext(dest_path)[0] + '.flac'
    if os.path.exists(dest_path) or os.path.exists(flac_dest):
        print(f"  Already exists: {category}/{fname}")
        return 0

    if dry_run:
        print(f"  Would copy: {fname} → {category}")
        return 1

    os.makedirs(dest_dir, exist_ok=True)
    actual_dest = _copy_as_flac(filepath, dest_path)
    print(f"  → {category}/{os.path.basename(actual_dest)}")

    # Store source context if available
    if source_context:
        _store_source_context(actual_dest, source_context)

    # Unified pipeline: tag + fingerprint + dedup + route
    rel_path = os.path.relpath(actual_dest, LIBRARY)
    route_result = _route_and_process(actual_dest, rel_path)
    if route_result == 'duplicate':
        print(f"  Duplicate — moved to _DUPES")
        return 0

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

            # Unified pipeline: tag + fingerprint + dedup + route
            rel = os.path.relpath(actual, LIBRARY)
            route_result = _route_and_process(actual, rel)
            if route_result == 'duplicate':
                counts[category] = counts.get(category, 0) - 1

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
        print(f"  No audio files in archive — skipping (not a sample pack)")
        # Clean up the extracted non-audio content
        shutil.rmtree(extract_dest, ignore_errors=True)
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

            # Unified pipeline: tag + fingerprint + dedup + route
            rel = os.path.relpath(actual, LIBRARY)
            route_result = _route_and_process(actual, rel)
            if route_result == 'duplicate':
                counts[category] = counts.get(category, 0) - 1

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
    for item in _download_entries():
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
            env=build_subprocess_env(SETTINGS),
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


def run_auto_dedupe(clean=False):
    """Run duplicate analysis after tagging so _tags.json is up to date."""
    dedupe_script = os.path.join(SCRIPTS_DIR, 'deduplicate_samples.py')
    if not os.path.exists(dedupe_script):
        print("  deduplicate_samples.py not found, skipping dedupe")
        return

    print("  Running duplicate analysis...")
    command = [sys.executable, dedupe_script, '--report-json']
    if clean:
        command.append('--clean')

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            env=build_subprocess_env(SETTINGS),
        )
        if result.returncode == 0:
            print("  Duplicate analysis complete")
        else:
            print(f"  Dedupe warning: {(result.stderr or result.stdout)[:200]}")
    except subprocess.TimeoutExpired:
        print("  Dedupe timed out (3min)")
    except Exception as e:
        print(f"  Dedupe error: {e}")


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

def start_watcher(dedupe=False):
    """Start the background file watcher daemon."""
    global _watcher_thread
    if not os.path.isdir(DOWNLOADS):
        print(f"ERROR: downloads path not found: {DOWNLOADS}")
        return False
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
                    # Check for Chat delivery first
                    delivery = check_chat_delivery(filepath)
                    if delivery:
                        count = handle_chat_delivery(filepath, delivery)
                    elif not archive_has_audio(filepath):
                        print(f"[WATCHER] Skipping {fname} — no audio files inside")
                        self._processed.add(filepath)
                        to_remove.append(filepath)
                        continue
                    else:
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

            # Tagging + fingerprint + dedup now happen inline via _route_and_process()

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


def one_shot_ingest(dry_run=False, dedupe=False):
    """Run a single ingest pass (original behavior)."""
    os.makedirs(LIBRARY, exist_ok=True)
    os.makedirs(RAW_ARCHIVE, exist_ok=True)
    if not os.path.isdir(DOWNLOADS):
        print(f"Downloads path not found: {DOWNLOADS}")
        return 0

    # Process doc deliverables first (Chat/Cowork .md and .txt files)
    doc_copied, doc_skipped = ingest_doc_deliverables(dry_run=dry_run)
    if doc_copied or doc_skipped:
        print(f"Docs: {doc_copied} copied to repo, {doc_skipped} already present (cleaned)")

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
    for item in _download_entries():
        filepath = os.path.join(DOWNLOADS, item)
        if os.path.isdir(filepath):
            continue
        if should_ignore(filepath):
            continue

        ext = os.path.splitext(item)[1].lower()
        if ext in ARCHIVE_EXTENSIONS:
            # Check for Chat delivery first
            delivery = check_chat_delivery(filepath)
            if delivery:
                total += handle_chat_delivery(filepath, delivery)
            else:
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

        # Note: tagging, fingerprinting, and dedup now happen inline
        # via _route_and_process() during ingest. run_auto_tag() and
        # run_auto_dedupe() are kept for standalone/CLI use but are
        # no longer needed in the ingest pipeline.

    return total


def cleanup_downloads(dry_run=False):
    """Remove already-ingested packs, archives, and doc deliverables from ~/Downloads."""
    freed = 0
    removed = 0

    # Clean up doc deliverables first
    doc_copied, doc_skipped = ingest_doc_deliverables(dry_run=dry_run)
    removed += doc_copied + doc_skipped

    print(f"Scanning {DOWNLOADS} for already-ingested items...")
    if not os.path.isdir(DOWNLOADS):
        print("Downloads path not found.")
        return 0, 0

    for item in _download_entries():
        full_path = os.path.join(DOWNLOADS, item)

        # Skip non-directories and non-archives at top level
        if os.path.isdir(full_path):
            marker = os.path.join(full_path, MARKER)
            if os.path.exists(marker):
                size = _dir_size(full_path)
                print(f"  {'Would remove' if dry_run else 'Removing'}: {item} ({_human_size(size)})")
                if not dry_run:
                    shutil.rmtree(full_path, ignore_errors=True)
                freed += size
                removed += 1
        else:
            ext = os.path.splitext(item)[1].lower()
            if ext in ARCHIVE_EXTENSIONS:
                # Check if this archive was already extracted to _RAW-DOWNLOADS
                name_no_ext = os.path.splitext(item)[0]
                archive_dest = os.path.join(RAW_ARCHIVE, name_no_ext)
                if os.path.exists(archive_dest):
                    size = os.path.getsize(full_path)
                    print(f"  {'Would remove' if dry_run else 'Removing'}: {item} ({_human_size(size)})")
                    if not dry_run:
                        os.remove(full_path)
                    freed += size
                    removed += 1

    print(f"\n{'Would free' if dry_run else 'Freed'}: {_human_size(freed)} ({removed} items)")
    return freed, removed


def purge_raw_archive(dry_run=False):
    """Purge _RAW-DOWNLOADS to free disk space. These are originals kept after ingest."""
    if not os.path.isdir(RAW_ARCHIVE):
        print("No _RAW-DOWNLOADS directory found.")
        return 0, 0

    size = _dir_size(RAW_ARCHIVE)
    count = sum(1 for _ in os.scandir(RAW_ARCHIVE))
    print(f"_RAW-DOWNLOADS: {_human_size(size)} ({count} items)")

    if dry_run:
        print(f"Would free: {_human_size(size)}")
        return size, count

    for item in os.listdir(RAW_ARCHIVE):
        full = os.path.join(RAW_ARCHIVE, item)
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)
        else:
            os.remove(full)

    print(f"Freed: {_human_size(size)} ({count} items)")
    return size, count


def disk_usage_report():
    """Report disk usage for Downloads and library."""
    import shutil as sh
    total, used, free = sh.disk_usage('/')

    downloads_size = _dir_size(DOWNLOADS) if os.path.isdir(DOWNLOADS) else 0
    archive_size = _dir_size(RAW_ARCHIVE) if os.path.isdir(RAW_ARCHIVE) else 0
    library_size = _dir_size(LIBRARY) if os.path.isdir(LIBRARY) else 0

    # Count cleanable items in Downloads
    cleanable = 0
    cleanable_count = 0
    for item in _download_entries():
        full = os.path.join(DOWNLOADS, item)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, MARKER)):
            cleanable += _dir_size(full)
            cleanable_count += 1
        elif os.path.isfile(full):
            ext = os.path.splitext(item)[1].lower()
            if ext in ARCHIVE_EXTENSIONS:
                name_no_ext = os.path.splitext(item)[0]
                if os.path.exists(os.path.join(RAW_ARCHIVE, name_no_ext)):
                    cleanable += os.path.getsize(full)
                    cleanable_count += 1

    return {
        'disk_free': free,
        'disk_free_str': _human_size(free),
        'disk_total': total,
        'downloads_size': downloads_size,
        'downloads_str': _human_size(downloads_size),
        'archive_size': archive_size,
        'archive_str': _human_size(archive_size),
        'library_size': library_size,
        'library_str': _human_size(library_size),
        'cleanable_size': cleanable,
        'cleanable_str': _human_size(cleanable),
        'cleanable_count': cleanable_count,
        'downloads_path': DOWNLOADS,
    }


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


def set_downloads_path(path):
    """Change the downloads watch path (runtime only)."""
    global DOWNLOADS
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        raise ValueError(f"Not a directory: {path}")
    DOWNLOADS = path
    return DOWNLOADS


def main():
    parser = argparse.ArgumentParser(description='Ingest sample packs from Downloads')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen')
    parser.add_argument('--watch', action='store_true', help='Run as background watcher daemon')
    parser.add_argument('--cleanup', action='store_true', help='Remove already-ingested items from Downloads')
    parser.add_argument('--purge-archive', action='store_true', help='Delete _RAW-DOWNLOADS to free space')
    parser.add_argument('--disk-report', action='store_true', help='Show disk usage report')
    parser.add_argument('--downloads-path', type=str, help='Override downloads folder path')
    parser.add_argument('--dedupe', action='store_true', help='Run duplicate analysis after tagging')
    args = parser.parse_args()

    if args.downloads_path:
        set_downloads_path(args.downloads_path)

    os.makedirs(LIBRARY, exist_ok=True)
    os.makedirs(RAW_ARCHIVE, exist_ok=True)

    if args.disk_report:
        report = disk_usage_report()
        print(f"Disk free:      {report['disk_free_str']}")
        print(f"Downloads:      {report['downloads_str']}")
        print(f"  Cleanable:    {report['cleanable_str']} ({report['cleanable_count']} items)")
        print(f"Archive:        {report['archive_str']}")
        print(f"Library:        {report['library_str']}")
        print(f"Downloads path: {report['downloads_path']}")
        return

    if args.cleanup:
        cleanup_downloads(dry_run=args.dry_run)
        return

    if args.purge_archive:
        purge_raw_archive(dry_run=args.dry_run)
        return

    if args.watch:
        print("Running initial ingest pass...")
        one_shot_ingest(dry_run=args.dry_run, dedupe=args.dedupe)

        if args.dry_run:
            print("\nDry run — not starting watcher")
            return

        if not start_watcher(dedupe=args.dedupe):
            sys.exit(1)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping watcher...")
            stop_watcher()
    else:
        one_shot_ingest(dry_run=args.dry_run, dedupe=args.dedupe)


if __name__ == '__main__':
    main()
