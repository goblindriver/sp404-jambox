#!/usr/bin/env python3
"""Ingest multitrack session stems from QNAP into the sample library.

Scans Pro Tools / DAW session directories for individual stem WAVs,
converts to FLAC, auto-tags with artist/song/instrument metadata,
and routes to appropriate library categories.

Stem name → type_code mapping uses fuzzy matching on common
recording session naming conventions.

Usage:
    python scripts/ingest_multitracks.py --scan                    # list sessions
    python scripts/ingest_multitracks.py --artist "Marvin Gaye"    # one artist
    python scripts/ingest_multitracks.py --all --limit 5           # batch
    python scripts/ingest_multitracks.py --dry-run --all           # preview
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings_for_script, load_tag_db, save_tag_db

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
FFMPEG = SETTINGS["FFMPEG_BIN"]

SESSIONS_ROOT = SETTINGS["MULTITRACK_SESSIONS_ROOT"]
H4N_ROOT = SETTINGS["MULTITRACK_H4N_ROOT"]
FILM_ROOT = SETTINGS["MULTITRACK_FILM_ROOT"]

# Skip non-audio directories
SKIP_DIRS = {'Session File Backups', 'Plug-In Settings', 'Fade Files',
             'Rendered Files', 'Adobe Premiere Pro Auto-Save',
             'Adobe Premiere Pro Preview Files', 'Adobe Premiere Pro Video Previews',
             'Structure Files'}

# Stem filename → type_code mapping (case-insensitive fuzzy match)
STEM_TYPE_MAP = {
    # Drums
    'kick': 'KIK', 'kik': 'KIK', 'bd': 'KIK',
    'snare': 'SNR', 'snr': 'SNR', 'sd': 'SNR',
    'hat': 'HAT', 'hh': 'HAT', 'hihat': 'HAT', 'hi-hat': 'HAT',
    'cymbal': 'HAT', 'cym': 'HAT', 'ride': 'HAT', 'crash': 'HAT',
    'tom': 'PRC', 'perc': 'PRC', 'conga': 'PRC', 'bongo': 'PRC',
    'tambourine': 'PRC', 'tamb': 'PRC', 'shaker': 'PRC', 'clap': 'PRC',
    'drum': 'BRK', 'drums': 'BRK', 'beat': 'BRK', 'loop': 'BRK',
    'overhead': 'BRK', 'oh': 'BRK', 'room': 'BRK',
    'kicktrigger': 'KIK',
    'drumsreverb': 'BRK',
    'reversecymbal': 'FX',
    # Bass
    'bass': 'BAS', 'bas': 'BAS',
    # Guitar
    'guitar': 'GTR', 'gtr': 'GTR', 'elecgtr': 'GTR', 'acgtr': 'GTR',
    'rhythm guitar': 'GTR', 'rythm guitar': 'GTR',
    'other guitar': 'GTR', 'lead guitar': 'GTR',
    # Keys
    'piano': 'KEY', 'keys': 'KEY', 'organ': 'KEY', 'clav': 'KEY',
    'rhodes': 'KEY', 'wurlitzer': 'KEY', 'clavinet': 'KEY',
    'vibes': 'KEY', 'bells': 'KEY',
    # Synth
    'synth': 'SYN', 'pad': 'PAD', 'siren': 'SYN',
    # Strings / Horns
    'strings': 'STR', 'strg': 'STR', 'hi strg': 'STR', 'lo strg': 'STR',
    'violin': 'STR', 'cello': 'STR', 'viola': 'STR',
    'horn': 'HRN', 'brass': 'HRN', 'trumpet': 'HRN', 'sax': 'HRN',
    'reed': 'HRN', 'trombone': 'HRN',
    # Vocals
    'vox': 'VOX', 'vocal': 'VOX', 'voice': 'VOX', 'lead': 'VOX',
    'leadvox': 'VOX', 'leadvoxdt': 'VOX',
    'backingvox': 'VOX', 'bv': 'VOX', 'bgv': 'VOX',
    'harmony': 'VOX', 'group': 'VOX', 'choir': 'VOX',
    'voice dry': 'VOX', 'lead master': 'VOX',
    # FX
    'fx': 'FX', 'sfx': 'FX', 'noise': 'FX',
}

# type_code → library category
TYPE_TO_CATEGORY = {
    'KIK': 'Drums/Kicks', 'SNR': 'Drums/Snares-Claps', 'HAT': 'Drums/Hi-Hats',
    'PRC': 'Drums/Percussion', 'BRK': 'Drums/Drum-Loops',
    'BAS': 'Melodic/Bass', 'GTR': 'Melodic/Guitar',
    'KEY': 'Melodic/Keys-Piano', 'SYN': 'Melodic/Synths-Pads', 'PAD': 'Melodic/Synths-Pads',
    'STR': 'Melodic/Keys-Piano', 'HRN': 'Melodic/Keys-Piano',
    'VOX': 'Vocals/Chops', 'FX': 'SFX/Stabs-Hits',
    'SMP': 'Loops/Instrument-Loops',
}

# Known artist BPMs (approximate, for tagging)
ARTIST_BPM = {
    'Marvin Gaye': 100, 'Stevie Wonder': 100, 'Bob Marley': 76,
    'Queen': 72, 'Nirvana': 116, 'Nine Inch Nails': 118,
    'Phoenix': 104, 'Def Leppard': 98, 'Counting Crows': 108,
    'Doobie Brothers 1973': 112, 'Switchfoot': 134,
    'The Beatles': 104,
}

# Artist genre hints
ARTIST_GENRE = {
    'Marvin Gaye': ['soul', 'funk'], 'Stevie Wonder': ['soul', 'funk'],
    'Bob Marley': ['reggae', 'dub'], 'Queen': ['rock'],
    'Nirvana': ['rock', 'punk'], 'Nine Inch Nails': ['industrial', 'electronic'],
    'Phoenix': ['rock', 'electronic'], 'Def Leppard': ['rock'],
    'Counting Crows': ['rock'], 'Doobie Brothers 1973': ['rock', 'funk'],
    'Switchfoot': ['rock'], 'The Beatles': ['rock', 'pop'],
    'Fdeluxe': ['funk', 'electronic'],
}

# Artist vibe hints (per Chat review — production profile aware)
ARTIST_VIBE = {
    'Marvin Gaye': ['soulful', 'warm', 'nostalgic'],
    'Stevie Wonder': ['soulful', 'hype', 'warm'],         # Superstition is HIGH energy
    'Bob Marley': ['soulful', 'mellow', 'warm'],
    'Queen': ['hype', 'nostalgic', 'triumphant'],
    'Nirvana': ['gritty', 'aggressive', 'raw'],            # consumption-side: texture/FX pads
    'Nine Inch Nails': ['aggressive', 'dark'],              # consumption-side: texture/FX pads
    'Phoenix': ['hype', 'playful'],                         # core Tiger Dust energy
    'Def Leppard': ['aggressive', 'hype'],
    'Counting Crows': ['nostalgic', 'soulful'],
    'Doobie Brothers 1973': ['soulful', 'warm', 'nostalgic'],
    'Switchfoot': ['hype'],
    'The Beatles': ['nostalgic', 'warm', 'playful'],
    'Fdeluxe': ['hype', 'playful'],
}


def classify_stem(filename):
    """Map a stem filename to a type_code."""
    name = os.path.splitext(filename)[0].lower()
    # Remove L/R channel suffixes
    name = re.sub(r'\.(l|r)$', '', name)
    # Remove trailing numbers and underscores
    name = re.sub(r'[-_ ]*\d+$', '', name).strip()
    # Remove "audio" prefix
    name = re.sub(r'^audio\s*', '', name)

    # Direct match
    if name in STEM_TYPE_MAP:
        return STEM_TYPE_MAP[name]

    # Substring match (longer matches first)
    sorted_keys = sorted(STEM_TYPE_MAP.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in name:
            return STEM_TYPE_MAP[key]

    # Unknown stems default to SMP (sampled phrase)
    return 'SMP'


def is_stereo_pair(filename, all_files):
    """Check if this is the R channel of a stereo pair (skip it, keep L)."""
    name = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1]
    if name.endswith('.R') or name.endswith('.r'):
        l_name = name[:-2] + '.L' + ext
        if l_name in all_files or (name[:-2] + '.l' + ext) in all_files:
            return True
    return False


def scan_sessions(root=None):
    """Scan for multitrack session directories. Returns list of session dicts."""
    root = root or SESSIONS_ROOT
    if not os.path.isdir(root):
        return []

    sessions = []
    for artist_dir in sorted(os.listdir(root)):
        artist_path = os.path.join(root, artist_dir)
        if not os.path.isdir(artist_path):
            continue
        if artist_dir in SKIP_DIRS or artist_dir.startswith('.'):
            continue
        if artist_dir == 'MIXDOWNS':
            continue

        # Find WAV files recursively
        wavs = []
        for dirpath, dirs, files in os.walk(artist_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.lower().endswith('.wav') and not f.startswith('.'):
                    wavs.append(os.path.join(dirpath, f))

        if not wavs:
            continue

        # Detect songs (subdirectories)
        songs = set()
        for w in wavs:
            rel = os.path.relpath(w, artist_path)
            parts = rel.split(os.sep)
            if len(parts) > 1:
                songs.add(parts[0])

        sessions.append({
            'artist': artist_dir,
            'path': artist_path,
            'wav_count': len(wavs),
            'songs': sorted(songs) if songs else [artist_dir],
            'wavs': wavs,
        })

    return sessions


def ingest_session(session, dry_run=False, merge_stereo=True):
    """Ingest all stems from a multitrack session.

    Converts to FLAC, classifies by instrument, tags with provenance.
    Returns count of files ingested.
    """
    artist = session['artist']
    wavs = session['wavs']
    ingested = 0

    # Build set of all filenames for stereo pair detection
    all_filenames = {os.path.basename(w) for w in wavs}

    db = load_tag_db(TAGS_FILE)

    for wav_path in wavs:
        filename = os.path.basename(wav_path)

        # Skip R channel of stereo pairs (we'll mono-downmix the L)
        if merge_stereo and is_stereo_pair(filename, all_filenames):
            continue

        # Classify the stem
        type_code = classify_stem(filename)
        category = TYPE_TO_CATEGORY.get(type_code, 'Loops/Instrument-Loops')

        # Determine song name from path
        rel = os.path.relpath(wav_path, session['path'])
        parts = rel.split(os.sep)
        song = parts[0] if len(parts) > 1 else artist

        # Build destination filename
        safe_artist = re.sub(r'[^\w\s-]', '', artist).strip()[:30]
        safe_song = re.sub(r'[^\w\s-]', '', song).strip()[:30]
        safe_stem = re.sub(r'[^\w\s.-]', '', os.path.splitext(filename)[0]).strip()[:30]
        dest_name = f"{safe_artist}_{safe_song}_{safe_stem}.flac"
        dest_name = re.sub(r'\s+', '_', dest_name)

        dest_dir = os.path.join(LIBRARY, category)
        dest_path = os.path.join(dest_dir, dest_name)
        rel_path = os.path.relpath(dest_path, LIBRARY)

        # Skip if already ingested
        if os.path.exists(dest_path) or rel_path in db:
            continue

        if dry_run:
            print(f"  [{type_code}] {dest_name}")
            ingested += 1
            continue

        # Convert to FLAC (44.1kHz mono)
        os.makedirs(dest_dir, exist_ok=True)
        result = subprocess.run([
            FFMPEG, '-y', '-i', wav_path,
            '-ar', '44100', '-ac', '1', '-sample_fmt', 's16',
            '-c:a', 'flac', dest_path,
        ], capture_output=True, timeout=30)

        if result.returncode != 0 or not os.path.exists(dest_path):
            continue

        # Get duration
        dur = 0
        try:
            probe = subprocess.run([
                SETTINGS["FFPROBE_BIN"], '-v', 'quiet', '-print_format', 'json',
                '-show_format', dest_path,
            ], capture_output=True, text=True, timeout=10)
            if probe.returncode == 0:
                dur = float(json.loads(probe.stdout).get('format', {}).get('duration', 0))
        except Exception:
            pass

        # Determine playability
        if type_code in ('KIK', 'SNR', 'HAT', 'PRC'):
            playability = 'one-shot'
        elif dur > 4:
            playability = 'chop-ready'
        elif dur > 2:
            playability = 'loop'
        else:
            playability = 'one-shot'

        # Build tags
        genres = ARTIST_GENRE.get(artist, [])
        vibes = ARTIST_VIBE.get(artist, ['raw'])
        bpm = ARTIST_BPM.get(artist)
        instrument = os.path.splitext(filename)[0].lower()
        instrument = re.sub(r'\.(l|r)$', '', instrument)
        instrument = re.sub(r'[-_ ]*\d+$', '', instrument).strip()

        entry = {
            'type_code': type_code,
            'vibe': vibes[:3],
            'texture': ['raw'],
            'genre': genres[:2],
            'energy': 'mid',
            'source': 'personal',
            'playability': playability,
            'duration': round(dur, 3),
            'bpm': bpm,
            'instrument_hint': instrument,
            'tags': sorted(set(
                [type_code, playability, 'personal', 'raw', 'multitrack'] +
                genres[:2] + vibes[:3]
            )),
            'multitrack_source': {
                'artist': artist,
                'song': song,
                'stem': filename,
                'original_path': wav_path,
            },
            'mtime': time.time(),
        }

        db[rel_path] = entry
        ingested += 1

        print(f"  [{type_code}] {dest_name} ({dur:.1f}s)")

    if not dry_run and ingested > 0:
        save_tag_db(TAGS_FILE, db)

    return ingested


def scan_field_recordings():
    """Find H4N field recordings."""
    if not os.path.isdir(H4N_ROOT):
        return []

    recordings = []
    for dirpath, dirs, files in os.walk(H4N_ROOT):
        for f in files:
            if f.lower().endswith('.wav'):
                full = os.path.join(dirpath, f)
                recordings.append(full)
    return recordings


def main():
    parser = argparse.ArgumentParser(description='Ingest multitrack session stems')
    parser.add_argument('--scan', action='store_true', help='List available sessions')
    parser.add_argument('--artist', type=str, help='Ingest one artist')
    parser.add_argument('--all', action='store_true', help='Ingest all sessions')
    parser.add_argument('--limit', type=int, default=0, help='Max sessions to process')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    parser.add_argument('--field-recordings', action='store_true',
                        help='Also ingest H4N field recordings')
    args = parser.parse_args()

    if not os.path.isdir(SESSIONS_ROOT):
        print(f"Sessions root not found: {SESSIONS_ROOT}")
        print("Is the QNAP mounted?")
        return

    sessions = scan_sessions()

    if args.scan:
        print(f"\n{'='*60}")
        print(f"MULTITRACK SESSIONS — {len(sessions)} artists, "
              f"{sum(s['wav_count'] for s in sessions)} stems")
        print(f"{'='*60}")
        for s in sessions:
            songs = ', '.join(s['songs'][:3])
            if len(s['songs']) > 3:
                songs += f' +{len(s["songs"]) - 3} more'
            print(f"  {s['wav_count']:4d} stems  {s['artist']}")
            print(f"           Songs: {songs}")
        return

    # Select sessions to process
    targets = []
    if args.artist:
        targets = [s for s in sessions if args.artist.lower() in s['artist'].lower()]
        if not targets:
            print(f"Artist not found: {args.artist}")
            print("Available:", ', '.join(s['artist'] for s in sessions))
            return
    elif args.all:
        targets = sessions
    else:
        parser.print_help()
        return

    if args.limit:
        targets = targets[:args.limit]

    print(f"\n{'='*60}")
    print(f"MULTITRACK INGEST — {len(targets)} sessions")
    print(f"{'='*60}")

    total = 0
    t0 = time.time()

    for session in targets:
        print(f"\n[{session['artist']}] {session['wav_count']} stems, "
              f"{len(session['songs'])} songs")
        count = ingest_session(session, dry_run=args.dry_run)
        total += count
        if count > 0:
            print(f"  → {count} stems ingested")

    if args.field_recordings:
        recordings = scan_field_recordings()
        if recordings:
            print(f"\n[H4N Field Recordings] {len(recordings)} files")
            # TODO: ingest field recordings

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"{'DRY RUN ' if args.dry_run else ''}COMPLETE")
    print(f"  Sessions: {len(targets)}")
    print(f"  Stems ingested: {total}")
    print(f"  Time: {elapsed:.1f}s")


if __name__ == '__main__':
    main()
