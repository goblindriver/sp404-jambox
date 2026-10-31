"""Archive extraction, audio file categorization, and file detection utilities."""
import os
import re
import shutil
import subprocess
import time
import zipfile

from jambox_config import ffmpeg_atomic

from . import _state


def _run_extractor(filepath, dest):
    ext = os.path.splitext(filepath)[1].lower()
    name = os.path.basename(filepath)
    if ext == '.zip':
        print(f"  Extracting ZIP: {name}...")
        try:
            with zipfile.ZipFile(filepath) as zf:
                zf.extractall(dest)  # ZipFile.extract strips absolute and '..' paths
        except (zipfile.BadZipFile, OSError) as e:
            print(f"  Extract failed: {e}")
            return False
        return True

    if ext == '.rar':
        print(f"  Extracting RAR: {name}...")
        command = [_state.SETTINGS["UNAR_BIN"], '-o', dest, '-f', filepath]
    elif ext == '.7z':
        print(f"  Extracting 7z: {name}...")
        command = ['7z', 'x', filepath, f'-o{dest}', '-y']
    else:
        return False

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        print(f"  Extract failed: command not found for {ext} archives")
        return False
    except subprocess.TimeoutExpired:
        print(f"  Extract failed: timed out for {name}")
        return False

    if result.returncode != 0:
        print(f"  Extract failed: {result.stderr[:200]}")
        return False
    return True


def extract_archive(filepath, dest):
    """Extract a zip/rar/7z archive to *dest*, atomically.

    Extracts into a hidden ``.<name>.partial`` sibling and renames it to
    *dest* only on success, so a failed or timed-out extraction never leaves
    a folder that later runs (or Downloads cleanup) mistake for a finished one.
    """
    parent = os.path.dirname(dest)
    partial = os.path.join(parent, f".{os.path.basename(dest)}.partial")
    shutil.rmtree(partial, ignore_errors=True)
    os.makedirs(partial)
    ok = False
    try:
        ok = _run_extractor(filepath, partial)
        if ok:
            if os.path.exists(dest):
                shutil.rmtree(dest)  # earlier attempt that never finished ingest
            os.replace(partial, dest)
    finally:
        if not ok:
            shutil.rmtree(partial, ignore_errors=True)
    return ok


def is_ingested(folder):
    """True once every file in *folder* went through ingest (marker written)."""
    return os.path.exists(os.path.join(folder, _state.MARKER))


def mark_ingested(folder, count):
    try:
        with open(os.path.join(folder, _state.MARKER), 'w', encoding='utf-8') as f:
            f.write(f"Ingested {count} files at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    except OSError as e:
        print(f"  Could not write marker: {e}")


def _copy_as_flac(src_path, dest_path):
    """Copy an audio file to the library, converting to FLAC for storage.

    Returns the actual destination path (with .flac extension), or the plain
    copy at *dest_path* if FLAC conversion isn't possible. Both are written
    via a temp file, so an interrupted copy never leaves a partial output.
    """
    flac_dest = os.path.splitext(dest_path)[0] + '.flac'
    if os.path.exists(flac_dest):
        return flac_dest

    if ffmpeg_atomic(_state.FFMPEG, src_path, flac_dest,
                     ['-c:a', 'flac', '-compression_level', '5'], fmt='flac', timeout=60):
        return flac_dest

    if not os.path.exists(dest_path):
        part = dest_path + '.part'
        shutil.copy2(src_path, part)
        os.replace(part, dest_path)
    return dest_path


def extract_rar(folder, dest):
    """Extract RAR archive from a folder using unar."""
    rar_file = None
    for f in os.listdir(folder):
        if f.lower().endswith('.rar'):
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
                with open(source_path, encoding='utf-8') as f:
                    return f.read().strip()
            except IOError:
                pass
    dir_source = os.path.join(os.path.dirname(filepath), '_SOURCE.txt')
    if os.path.exists(dir_source):
        try:
            with open(dir_source, encoding='utf-8') as f:
                return f.read().strip()
        except IOError:
            pass
    return None


def is_sample_pack(dirname):
    """Check if a directory name looks like a sample pack."""
    for suffix in _state.SAMPLE_PACK_SUFFIXES:
        if suffix in dirname:
            return True
    name_lower = dirname.lower()
    if any(kw in name_lower for kw in ['prime loops', 'sample magic', 'loopmasters',
                                        'sampleradar', 'musicradar', 'samples']):
        return True

    full_path = os.path.join(_state.DOWNLOADS, dirname)
    if os.path.isdir(full_path):
        try:
            for item in os.listdir(full_path):
                if os.path.splitext(item)[1].lower() in _state.AUDIO_EXTENSIONS:
                    return True
                sub = os.path.join(full_path, item)
                if os.path.isdir(sub):
                    for f in os.listdir(sub):
                        if os.path.splitext(f)[1].lower() in _state.AUDIO_EXTENSIONS:
                            return True
        except OSError:
            pass

    return False


def has_rar_files(folder):
    """Check if folder contains RAR archives."""
    try:
        return any(f.lower().endswith('.rar') for f in os.listdir(folder))
    except OSError:
        return False


def archive_has_audio(filepath):
    """Quick check if a zip archive contains audio files (without extracting)."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.zip':
        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                for name in zf.namelist():
                    if os.path.splitext(name)[1].lower() in _state.AUDIO_EXTENSIONS:
                        return True
            return False
        except Exception:
            return True
    return True


def should_ignore(filepath):
    """Check if a file should be ignored."""
    fname = os.path.basename(filepath)
    ext = os.path.splitext(fname)[1].lower()

    if ext in _state.IGNORE_EXTENSIONS:
        return True

    if ext not in _state.ALLOWED_EXTENSIONS:
        return True

    if fname.startswith('.'):
        return True

    if _state.RAW_ARCHIVE in filepath:
        return True

    return False
