#!/usr/bin/env python3
"""Index a personal music library by reading ID3/metadata tags.

Fast scan — reads tags only, no audio analysis. Creates a lightweight
JSON index that the web UI can browse by artist, album, genre, year.

Usage:
    python scripts/index_music.py                              # full scan
    python scripts/index_music.py --update                     # only new files
    python scripts/index_music.py --path "/Volumes/My NAS/Music"  # custom path
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

MUSIC_LIBRARY = '/Volumes/Temp QNAP/Music'
INDEX_FILE = os.path.join(
    os.path.expanduser("~/Music/SP404-Sample-Library"),
    "_music_index.json"
)

AUDIO_EXTS = {'.mp3', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma',
              '.wav', '.aif', '.aiff', '.alac', '.ape', '.wv'}


def _normalize_index_data(payload):
    return payload if isinstance(payload, dict) else {}


def read_tags(filepath):
    """Read ID3/metadata tags from an audio file using mutagen.

    Returns dict with: artist, album, title, genre, year, bpm, duration, track_num
    """
    try:
        from mutagen import File as MutagenFile
        from mutagen.easyid3 import EasyID3
        from mutagen.mp3 import MP3
        from mutagen.flac import FLAC
        from mutagen.mp4 import MP4

        audio = MutagenFile(filepath, easy=True)
        if audio is None:
            return None

        def first(tag_list):
            if tag_list and len(tag_list) > 0:
                return str(tag_list[0]).strip()
            return None

        tags = {
            'artist': first(audio.get('artist') or audio.get('albumartist')),
            'album': first(audio.get('album')),
            'title': first(audio.get('title')),
            'genre': first(audio.get('genre')),
            'year': None,
            'bpm': None,
            'track_num': None,
            'duration': 0,
        }

        # Year — try 'date' first, then 'year'
        date_str = first(audio.get('date') or audio.get('year'))
        if date_str:
            # Extract 4-digit year from various formats
            import re
            m = re.search(r'(\d{4})', date_str)
            if m:
                tags['year'] = int(m.group(1))

        # BPM
        bpm_str = first(audio.get('bpm'))
        if bpm_str:
            try:
                tags['bpm'] = int(float(bpm_str))
            except (ValueError, TypeError):
                pass

        # Track number
        track_str = first(audio.get('tracknumber'))
        if track_str:
            try:
                tags['track_num'] = int(track_str.split('/')[0])
            except (ValueError, TypeError):
                pass

        # Duration
        if hasattr(audio, 'info') and audio.info:
            try:
                tags['duration'] = round(float(audio.info.length), 1)
            except (TypeError, ValueError):
                tags['duration'] = 0

        return tags

    except Exception:
        return None


def infer_from_path(filepath, music_root):
    """Infer artist/album from directory structure as fallback.

    Typical structure: Music/Artist/Album/track.ext
    """
    rel = os.path.relpath(filepath, music_root)
    parts = rel.split(os.sep)

    result = {}
    if len(parts) >= 3:
        result['artist'] = parts[0]
        result['album'] = parts[1]
    elif len(parts) >= 2:
        result['artist'] = parts[0]

    # Infer title from filename
    fname = os.path.splitext(parts[-1])[0]
    # Strip track number prefix like "01 - ", "01. ", "1-"
    import re
    fname = re.sub(r'^\d{1,3}[\s\-\.]+', '', fname).strip()
    if fname:
        result['title'] = fname

    return result


def scan_library(music_root, existing_index=None, update_only=False):
    """Scan music library and build index.

    Returns dict: { relative_path: { artist, album, title, genre, year, ... } }
    """
    index = _normalize_index_data(existing_index)
    scanned = 0
    new = 0
    errors = 0

    t0 = time.time()
    total_files = 0

    # First pass: count files for progress
    print(f"Counting files in {music_root}...")
    for root, dirs, files in os.walk(music_root):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in AUDIO_EXTS:
                total_files += 1
    print(f"Found {total_files} audio files")

    # Second pass: read tags
    for root, dirs, files in os.walk(music_root):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in AUDIO_EXTS:
                continue

            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, music_root)

            # Skip if already indexed and in update mode
            if update_only and rel_path in index:
                scanned += 1
                continue

            scanned += 1

            # Read ID3 tags
            tags = read_tags(full_path)
            if tags is None:
                tags = {}
                errors += 1

            # Fill in from directory structure where ID3 is missing
            path_info = infer_from_path(full_path, music_root)
            for key in ['artist', 'album', 'title']:
                if not tags.get(key) and path_info.get(key):
                    tags[key] = path_info[key]

            # Add file metadata
            tags['path'] = rel_path
            tags['ext'] = ext
            try:
                tags['size'] = os.path.getsize(full_path)
            except OSError:
                tags['size'] = 0

            index[rel_path] = tags
            new += 1

            if scanned % 1000 == 0:
                elapsed = time.time() - t0
                rate = scanned / elapsed if elapsed > 0 else 0
                print(f"  [{scanned}/{total_files}] {rate:.0f} files/sec — {new} indexed")

    elapsed = time.time() - t0
    print(f"\nScanned {scanned} files in {elapsed:.1f}s")
    print(f"  New entries: {new}")
    print(f"  Errors: {errors}")
    print(f"  Total index: {len(index)} tracks")

    return index


def build_browse_index(index):
    """Build aggregated browse data: artists, albums, genres, decades."""
    index = _normalize_index_data(index)
    artists = {}  # artist -> { albums: {album: [tracks]}, track_count }
    genres = {}   # genre -> count
    decades = {}  # decade -> count

    for rel_path, entry in index.items():
        if not isinstance(entry, dict):
            continue
        artist = entry.get('artist', 'Unknown')
        album = entry.get('album', 'Unknown')
        genre = entry.get('genre', 'Unknown')
        year = entry.get('year')

        # Artists
        if artist not in artists:
            artists[artist] = {'albums': {}, 'track_count': 0}
        if album not in artists[artist]['albums']:
            artists[artist]['albums'][album] = []
        artists[artist]['albums'][album].append(rel_path)
        artists[artist]['track_count'] += 1

        # Genres
        if genre:
            genres[genre] = genres.get(genre, 0) + 1

        # Decades
        if year and year >= 1900:
            decade = f"{(year // 10) * 10}s"
            decades[decade] = decades.get(decade, 0) + 1

    return {
        'artists': {k: {'album_count': len(v['albums']), 'track_count': v['track_count']}
                    for k, v in sorted(artists.items())},
        'genres': dict(sorted(genres.items(), key=lambda x: -x[1])),
        'decades': dict(sorted(decades.items())),
        'total_tracks': len(index),
        'total_artists': len(artists),
    }


def main():
    parser = argparse.ArgumentParser(description='Index personal music library')
    parser.add_argument('--path', default=MUSIC_LIBRARY, help='Path to music library')
    parser.add_argument('--update', action='store_true', help='Only index new files')
    parser.add_argument('--stats', action='store_true', help='Show stats only')
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        print(f"ERROR: Music library not found at {args.path}")
        print("Mount the QNAP or specify --path")
        sys.exit(1)

    # Load existing index
    existing = {}
    if args.update or args.stats:
        try:
            with open(INDEX_FILE) as f:
                existing = _normalize_index_data(json.load(f))
            print(f"Loaded existing index: {len(existing)} tracks")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    if args.stats:
        browse = build_browse_index(existing)
        print(f"\n{'='*50}")
        print(f"MUSIC LIBRARY STATS")
        print(f"{'='*50}")
        print(f"Total tracks: {browse['total_tracks']}")
        print(f"Total artists: {browse['total_artists']}")
        print(f"\nTop genres:")
        for g, c in list(browse['genres'].items())[:20]:
            print(f"  {g}: {c}")
        print(f"\nBy decade:")
        for d, c in browse['decades'].items():
            print(f"  {d}: {c}")
        return

    # Scan
    index = scan_library(args.path, existing, args.update)

    # Save
    os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
    with open(INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=1, sort_keys=True)
    print(f"Saved index to {INDEX_FILE}")

    # Print summary
    browse = build_browse_index(index)
    print(f"\nTop 10 genres:")
    for g, c in list(browse['genres'].items())[:10]:
        print(f"  {g}: {c}")
    print(f"\nBy decade:")
    for d, c in browse['decades'].items():
        print(f"  {d}: {c}")


if __name__ == '__main__':
    main()
