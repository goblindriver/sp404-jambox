"""Shared library walker for audio file discovery.

Used by clap_engine, discogs_engine, and any script that needs to iterate
audio files in the sample library with consistent skip-directory handling.
"""

import os

from jambox_config import LIBRARY_SKIP_DIRS as SKIP_DIRS

AUDIO_EXTENSIONS = {".flac", ".wav", ".mp3", ".aif", ".aiff", ".ogg"}
APPLEDOUBLE_MAGIC = b"\x00\x05\x16\x07"


def is_appledouble(path):
    """True for a macOS resource-fork stub that only looks like audio.

    Zips made on a Mac carry ._name files with the real file's extension, and
    ingest used to flatten them into Pack_._name.mp3, past every dot-file check.
    """
    if "._" not in os.path.basename(path):
        return False
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == APPLEDOUBLE_MAGIC
    except OSError:
        return False


def walk_library_audio(library_root, skip_dirs=None, extensions=None):
    """Yield (rel_path, abs_path) for all audio files in the library.

    Args:
        library_root: absolute path to sample library root
        skip_dirs: set of directory names to skip (defaults to SKIP_DIRS)
        extensions: set of file extensions to include (defaults to AUDIO_EXTENSIONS)
    """
    skip = skip_dirs if skip_dirs is not None else SKIP_DIRS
    exts = extensions if extensions is not None else AUDIO_EXTENSIONS

    for dirpath, dirnames, filenames in os.walk(library_root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if not fn.startswith(".") and os.path.splitext(fn)[1].lower() in exts:
                abs_path = os.path.join(dirpath, fn)
                if is_appledouble(abs_path):
                    continue
                rel_path = os.path.relpath(abs_path, library_root).replace(os.sep, "/")
                yield rel_path, abs_path
