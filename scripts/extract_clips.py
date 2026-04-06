#!/usr/bin/env python3
"""Extract audio clips from movies/TV for sampling on the SP-404.

Pulls dialog, sound effects, ambient textures, and score moments from
the Plex media library. Uses ffmpeg for extraction and silence detection.

Clips land in ~/Music/SP404-Sample-Library/ under appropriate categories
and get auto-tagged with movie context (genre, director, vibe).

Usage:
    python scripts/extract_clips.py --movie "Blade Runner"           # extract from one film
    python scripts/extract_clips.py --genre Horror --limit 5         # 5 random horror films
    python scripts/extract_clips.py --show "Cowboy Bebop" --season 1 # anime episodes
    python scripts/extract_clips.py --taste                          # auto-pick from taste profile
    python scripts/extract_clips.py --list-movies --genre Sci-Fi     # browse candidates
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings_for_script
from plex_client import PlexMediaDB, MOVIE_GENRE_TO_VIBE

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
FFMPEG = SETTINGS["FFMPEG_BIN"]
FFPROBE = SETTINGS["FFPROBE_BIN"]

# Output categories for extracted clips
CLIP_CATEGORIES = {
    'dialog': 'Vocals/Chops',
    'effect': 'SFX/Stabs-Hits',
    'ambient': 'Ambient-Textural/Atmospheres',
    'score': 'Loops/Instrument-Loops',
}

# Clip extraction parameters
MIN_CLIP_DURATION = 0.5   # seconds
MAX_CLIP_DURATION = 15.0  # seconds
SILENCE_THRESHOLD = -35   # dB — what counts as silence
MIN_SILENCE_GAP = 0.3     # seconds of silence between clips
MAX_CLIPS_PER_SOURCE = 30 # cap per movie/episode


def get_duration(filepath):
    """Get media duration in seconds via ffprobe."""
    try:
        result = subprocess.run([
            FFPROBE, '-v', 'quiet', '-print_format', 'json',
            '-show_format', filepath
        ], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get('format', {}).get('duration', 0))
    except Exception:
        pass
    return 0


def detect_interesting_segments(filepath, scan_minutes=None):
    """Find non-silent audio segments in a media file.

    Uses ffmpeg's silencedetect filter to find gaps between silence,
    which correspond to dialog, sound effects, and score moments.

    Returns list of (start_sec, end_sec, duration) tuples.
    """
    # Build ffmpeg command for silence detection
    cmd = [
        FFMPEG, '-i', filepath,
        '-af', f'silencedetect=noise={SILENCE_THRESHOLD}dB:d={MIN_SILENCE_GAP}',
        '-f', 'null', '-'
    ]

    if scan_minutes:
        # Only scan first N minutes + a chunk from the middle + end
        duration = get_duration(filepath)
        if duration > 0:
            # Scan three windows: opening, a middle chunk, climax region
            # For now, just limit total scan time
            cmd.insert(3, '-t')
            cmd.insert(4, str(scan_minutes * 60))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        stderr = result.stderr or ''
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []

    # Parse silence start/end from ffmpeg output
    silence_starts = []
    silence_ends = []
    for line in stderr.split('\n'):
        if 'silence_start:' in line:
            m = re.search(r'silence_start:\s*([\d.]+)', line)
            if m:
                silence_starts.append(float(m.group(1)))
        elif 'silence_end:' in line:
            m = re.search(r'silence_end:\s*([\d.]+)', line)
            if m:
                silence_ends.append(float(m.group(1)))

    # Build segments from silence boundaries
    segments = []

    # First segment: from silence_end[0] to silence_start[1]
    for i in range(len(silence_ends)):
        seg_start = silence_ends[i]
        # Find next silence start after this end
        seg_end = None
        for ss in silence_starts:
            if ss > seg_start + MIN_CLIP_DURATION:
                seg_end = ss
                break

        if seg_end is None:
            continue

        duration = seg_end - seg_start
        if MIN_CLIP_DURATION <= duration <= MAX_CLIP_DURATION:
            segments.append((seg_start, seg_end, duration))

    return segments


def extract_audio_clip(source_path, start_sec, duration_sec, output_path):
    """Extract an audio clip from a video file as FLAC.

    Converts to 44.1kHz mono 16-bit (SP-404 compatible base format).
    """
    cmd = [
        FFMPEG, '-y',
        '-ss', str(start_sec),
        '-i', source_path,
        '-t', str(duration_sec),
        '-vn',                          # no video
        '-ar', '44100', '-ac', '1',     # 44.1kHz mono
        '-sample_fmt', 's16',
        '-c:a', 'flac',
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def classify_clip(filepath, features=None):
    """Classify a clip as dialog, effect, ambient, or score.

    Uses spectral features if available, otherwise duration heuristics.
    """
    try:
        from audio_analysis import extract_features as _extract
        features = _extract(filepath)
    except ImportError:
        features = None

    if features:
        centroid = features.get('spectral_centroid', 0)
        zcr = features.get('zero_crossing_rate', 0)
        onsets = features.get('onset_count', 0)
        duration = features.get('duration', 0)
        rms_mean = features.get('rms_mean', 0)

        # Heuristic classification
        if duration < 1.5 and onsets <= 2:
            return 'effect'  # short, percussive = sound effect
        if centroid > 2000 and zcr > 0.1:
            return 'dialog'  # mid-high frequency, noisy = speech
        if rms_mean < 0.02 and duration > 3:
            return 'ambient'  # quiet and long = ambient
        if onsets > 4 and duration > 2:
            return 'score'   # rhythmic and longer = music
        if centroid < 1500 and duration > 3:
            return 'ambient'  # low frequency, sustained

    # Fallback: duration-based
    dur = get_duration(filepath) if not features else features.get('duration', 0)
    if dur < 2:
        return 'effect'
    elif dur > 5:
        return 'ambient'
    else:
        return 'dialog'


def safe_filename(title, max_len=40):
    """Clean a title for use as a filename."""
    clean = re.sub(r'[^\w\s-]', '', title).strip()
    clean = re.sub(r'\s+', '_', clean)
    return clean[:max_len]


def extract_from_source(source_info, scan_minutes=10, max_clips=None):
    """Extract clips from a single movie or episode.

    Returns list of extracted clip paths.
    """
    file_path = source_info.get('file_path')
    title = source_info.get('title', 'unknown')
    genres = source_info.get('genres', [])

    if not file_path or not os.path.exists(file_path):
        print(f"  File not found: {file_path}")
        return []

    max_clips = max_clips or MAX_CLIPS_PER_SOURCE
    safe_title = safe_filename(title)

    print(f"\n  Scanning: {title} ({source_info.get('year', '?')})")
    print(f"  File: {os.path.basename(file_path)}")

    # Detect interesting audio segments
    segments = detect_interesting_segments(file_path, scan_minutes=scan_minutes)
    if not segments:
        print(f"  No segments found (silence detection returned empty)")
        return []

    print(f"  Found {len(segments)} candidate segments")

    # Score segments by duration (prefer 1-5 second clips for SP-404)
    def segment_score(seg):
        dur = seg[2]
        if 1.0 <= dur <= 3.0:
            return 3  # sweet spot for one-shots
        elif 3.0 < dur <= 8.0:
            return 2  # good for loops
        elif dur < 1.0:
            return 1  # very short
        else:
            return 0  # long

    segments.sort(key=segment_score, reverse=True)
    segments = segments[:max_clips]

    extracted = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (start, end, dur) in enumerate(segments):
            # Extract to temp
            tmp_path = os.path.join(tmpdir, f"clip_{i:03d}.flac")
            if not extract_audio_clip(file_path, start, dur, tmp_path):
                continue

            # Classify the clip
            clip_type = classify_clip(tmp_path)
            category = CLIP_CATEGORIES.get(clip_type, 'SFX/Stabs-Hits')

            # Build destination path
            dest_dir = os.path.join(LIBRARY, category)
            os.makedirs(dest_dir, exist_ok=True)

            clip_name = f"{safe_title}_clip{i+1:02d}_{start:.0f}s.flac"
            dest_path = os.path.join(dest_dir, clip_name)

            if os.path.exists(dest_path):
                continue

            shutil.copy2(tmp_path, dest_path)
            extracted.append({
                'path': os.path.relpath(dest_path, LIBRARY),
                'source_title': title,
                'source_year': source_info.get('year'),
                'start_sec': round(start, 2),
                'duration': round(dur, 2),
                'clip_type': clip_type,
                'genres': genres,
            })

            print(f"    [{clip_type}] {clip_name} ({dur:.1f}s @ {start:.0f}s)")

    return extracted


def tag_extracted_clips(clips):
    """Tag extracted clips with movie context in _tags.json."""
    if not clips:
        return

    try:
        from jambox_config import load_tag_db, save_tag_db
        tags_file = SETTINGS["TAGS_FILE"]
        db = load_tag_db(tags_file)

        for clip in clips:
            rel_path = clip['path']
            genres = clip.get('genres', [])
            clip_type = clip.get('clip_type', 'effect')

            # Map clip type to type_code
            type_codes = {
                'dialog': 'VOX',
                'effect': 'FX',
                'ambient': 'PAD',
                'score': 'PAD',
            }

            # Map movie genres to vibes
            vibes = sorted({MOVIE_GENRE_TO_VIBE.get(g.lower(), '')
                           for g in genres} - {''})

            # Map movie genres to our genre tags
            genre_tags = []
            for g in genres:
                gl = g.lower()
                if gl in ('horror', 'thriller'):
                    genre_tags.append('industrial')
                elif gl in ('sci-fi', 'science fiction'):
                    genre_tags.append('electronic')
                elif gl == 'western':
                    genre_tags.append('soul')
                elif gl in ('drama', 'romance'):
                    genre_tags.append('soul')

            entry = {
                'type_code': type_codes.get(clip_type, 'FX'),
                'vibe': vibes[:3],
                'texture': ['raw'],  # movie audio is typically raw
                'genre': genre_tags[:2] if genre_tags else [],
                'energy': 'mid',
                'source': 'personal',
                'playability': 'one-shot' if clip['duration'] < 3 else 'chop-ready',
                'duration': clip['duration'],
                'tags': sorted(set(
                    [type_codes.get(clip_type, 'FX')] + vibes + ['raw', 'personal'] +
                    (['one-shot'] if clip['duration'] < 3 else ['chop-ready'])
                )),
                'clip_source': {
                    'title': clip['source_title'],
                    'year': clip['source_year'],
                    'start_sec': clip['start_sec'],
                    'movie_genres': genres,
                },
                'mtime': time.time(),
            }

            db[rel_path] = entry

        save_tag_db(tags_file, db)
        print(f"\n  Tagged {len(clips)} clips in _tags.json")

    except Exception as e:
        print(f"\n  Tag save failed: {e}")


def main():
    parser = argparse.ArgumentParser(description='Extract audio clips from movies/TV')
    parser.add_argument('--movie', type=str, help='Movie title to extract from')
    parser.add_argument('--show', type=str, help='TV show title')
    parser.add_argument('--season', type=int, help='Season number (with --show)')
    parser.add_argument('--genre', type=str, help='Filter by genre')
    parser.add_argument('--limit', type=int, default=3, help='Max sources to process')
    parser.add_argument('--max-clips', type=int, default=20, help='Max clips per source')
    parser.add_argument('--scan-minutes', type=int, default=10,
                        help='Minutes of audio to scan per source')
    parser.add_argument('--taste', action='store_true',
                        help='Auto-pick sources from taste profile')
    parser.add_argument('--list-movies', action='store_true',
                        help='List available movies (browsing)')
    parser.add_argument('--list-shows', action='store_true',
                        help='List available TV shows')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be extracted')
    args = parser.parse_args()

    plex = PlexMediaDB()

    if args.list_movies:
        movies = plex.movies(limit=50, genre=args.genre, sort='rating')
        print(f"\n{'='*60}")
        print(f"Movies{' — ' + args.genre if args.genre else ''} ({len(movies)} shown)")
        print(f"{'='*60}")
        for m in movies:
            score = m.get('audience_rating') or m.get('rating') or 0
            print(f"  [{score:.1f}] {m['title']} ({m['year']}) — {', '.join(m['genres'][:3])}")
        return

    if args.list_shows:
        shows = plex.shows(limit=50, search=args.genre)
        print(f"\n{'='*60}")
        print(f"TV Shows ({len(shows)} shown)")
        print(f"{'='*60}")
        for s in shows:
            kind = 'ANIME' if s['is_anime'] else 'TV'
            print(f"  [{kind}] {s['title']} ({s['year']}) — {s['episode_count']} eps — {', '.join(s['genres'][:3])}")
        return

    # Collect sources to extract from
    sources = []

    if args.movie:
        results = plex.movies(limit=5, search=args.movie)
        if not results:
            print(f"Movie not found: {args.movie}")
            return
        # Get full detail with file path
        for r in results[:1]:
            detail = plex.movie(r['id'])
            if detail and detail.get('file_path'):
                sources.append(detail)

    elif args.show:
        shows = plex.shows(search=args.show, limit=5)
        if not shows:
            print(f"Show not found: {args.show}")
            return
        show = shows[0]
        eps = plex.episodes(show['id'], season=args.season, limit=args.limit)
        for ep in eps:
            ep['genres'] = show.get('genres', [])
        sources.extend(eps)

    elif args.taste:
        profile = plex.taste_profile()
        # Pick top vibe-weighted genres
        top_vibes = list(profile['vibe_weights'].keys())[:3]
        print(f"Taste profile top vibes: {', '.join(top_vibes)}")

        # Find movies matching top genres
        candidates = plex.clip_candidates(genre=None, limit=args.limit * 3)
        if candidates:
            sources = candidates[:args.limit]

    elif args.genre:
        candidates = plex.clip_candidates(genre=args.genre, limit=args.limit)
        sources = candidates

    else:
        # Random selection
        candidates = plex.clip_candidates(limit=args.limit)
        sources = candidates

    if not sources:
        print("No sources found with accessible files.")
        return

    print(f"\n{'='*60}")
    print(f"CLIP EXTRACTION — {len(sources)} sources")
    print(f"{'='*60}")

    if args.dry_run:
        for s in sources:
            print(f"  Would extract from: {s.get('title', '?')} — {s.get('file_path', 'no path')}")
        return

    total_clips = []
    t0 = time.time()

    for source in sources:
        clips = extract_from_source(
            source,
            scan_minutes=args.scan_minutes,
            max_clips=args.max_clips,
        )
        total_clips.extend(clips)

    # Tag all clips
    tag_extracted_clips(total_clips)

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE")
    print(f"  Sources processed: {len(sources)}")
    print(f"  Clips extracted: {len(total_clips)}")
    print(f"  Time: {elapsed:.1f}s")

    # Breakdown by type
    by_type = {}
    for c in total_clips:
        t = c.get('clip_type', '?')
        by_type[t] = by_type.get(t, 0) + 1
    for t, count in sorted(by_type.items()):
        print(f"    {t}: {count}")


if __name__ == '__main__':
    main()
