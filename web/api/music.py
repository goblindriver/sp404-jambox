"""My Music — personal music library browser API."""
import json
import os
import re
import sys
import threading
from flask import Blueprint, jsonify, request, send_file, abort

music_bp = Blueprint('music', __name__)

MUSIC_LIBRARY = '/Volumes/Temp QNAP/Music'
SAMPLE_LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
INDEX_FILE = os.path.join(SAMPLE_LIBRARY, "_music_index.json")
STEMS_DIR = os.path.join(SAMPLE_LIBRARY, "Stems")

_index_cache = None
_index_mtime = 0


def _load_index():
    """Load music index with caching."""
    global _index_cache, _index_mtime
    try:
        mtime = os.path.getmtime(INDEX_FILE)
        if _index_cache is None or mtime > _index_mtime:
            with open(INDEX_FILE) as f:
                _index_cache = json.load(f)
            _index_mtime = mtime
        return _index_cache
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@music_bp.route('/music/status')
def music_status():
    """Check if music library is accessible and indexed."""
    available = os.path.isdir(MUSIC_LIBRARY)
    index = _load_index()
    return jsonify({
        'available': available,
        'indexed': len(index) > 0,
        'track_count': len(index),
        'library_path': MUSIC_LIBRARY,
    })


@music_bp.route('/music/browse')
def browse():
    """Browse music library. Returns artists, genres, decades."""
    index = _load_index()
    if not index:
        return jsonify({'error': 'Not indexed. Run: python scripts/index_music.py'}), 404

    artists = {}
    genres = {}
    decades = {}

    for rel_path, entry in index.items():
        artist = entry.get('artist', 'Unknown')
        genre = entry.get('genre')
        year = entry.get('year')

        if artist not in artists:
            artists[artist] = {'track_count': 0, 'albums': set()}
        artists[artist]['track_count'] += 1
        if entry.get('album'):
            artists[artist]['albums'].add(entry['album'])

        if genre:
            genres[genre] = genres.get(genre, 0) + 1

        if year and year >= 1900:
            decade = f"{(year // 10) * 10}s"
            decades[decade] = decades.get(decade, 0) + 1

    # Serialize (sets → counts)
    artist_list = sorted([
        {'name': k, 'track_count': v['track_count'], 'album_count': len(v['albums'])}
        for k, v in artists.items()
    ], key=lambda x: x['name'].lower())

    return jsonify({
        'artists': artist_list,
        'genres': dict(sorted(genres.items(), key=lambda x: -x[1])),
        'decades': dict(sorted(decades.items())),
        'total_tracks': len(index),
    })


@music_bp.route('/music/artist/<path:artist_name>')
def artist_detail(artist_name):
    """Get albums and tracks for an artist."""
    index = _load_index()
    albums = {}

    for rel_path, entry in index.items():
        if (entry.get('artist') or '').lower() != artist_name.lower():
            continue
        album = entry.get('album', 'Unknown')
        if album not in albums:
            albums[album] = {'name': album, 'year': entry.get('year'), 'tracks': []}
        albums[album]['tracks'].append({
            'path': rel_path,
            'title': entry.get('title', os.path.basename(rel_path)),
            'duration': entry.get('duration', 0),
            'track_num': entry.get('track_num'),
            'bpm': entry.get('bpm'),
            'genre': entry.get('genre'),
            'year': entry.get('year'),
        })

    # Sort tracks by track number
    for album in albums.values():
        album['tracks'].sort(key=lambda t: t.get('track_num') or 999)

    album_list = sorted(albums.values(), key=lambda a: a.get('year') or 9999)
    return jsonify({'artist': artist_name, 'albums': album_list})


@music_bp.route('/music/search')
def search():
    """Search music library by text query."""
    q = request.args.get('q', '').strip().lower()
    if not q or len(q) < 2:
        return jsonify({'results': []})

    index = _load_index()
    results = []

    for rel_path, entry in index.items():
        score = 0
        artist = (entry.get('artist') or '').lower()
        album = (entry.get('album') or '').lower()
        title = (entry.get('title') or '').lower()
        genre = (entry.get('genre') or '').lower()

        if q in artist:
            score += 3
        if q in title:
            score += 2
        if q in album:
            score += 1
        if q in genre:
            score += 1

        if score > 0:
            results.append({
                'path': rel_path,
                'artist': entry.get('artist'),
                'album': entry.get('album'),
                'title': entry.get('title', os.path.basename(rel_path)),
                'genre': entry.get('genre'),
                'year': entry.get('year'),
                'duration': entry.get('duration', 0),
                'bpm': entry.get('bpm'),
                'score': score,
            })

    results.sort(key=lambda r: (-r['score'], r.get('artist', '').lower()))
    return jsonify({'results': results[:100], 'total': len(results), 'query': q})


@music_bp.route('/music/preview/<path:rel_path>')
def preview_track(rel_path):
    """Stream a track from the music library for preview."""
    full = os.path.join(MUSIC_LIBRARY, rel_path)
    full = os.path.realpath(full)
    if not full.startswith(os.path.realpath(MUSIC_LIBRARY)) or not os.path.isfile(full):
        abort(404)
    ext = os.path.splitext(full)[1].lower()
    mimes = {'.mp3': 'audio/mpeg', '.flac': 'audio/flac', '.m4a': 'audio/mp4',
             '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.aif': 'audio/aiff'}
    return send_file(full, mimetype=mimes.get(ext, 'audio/mpeg'))


# ── Stem splitting ──

_split_jobs = {}
_split_lock = threading.Lock()


def _run_split(job_id, track_path, rel_path, entry):
    """Background thread: run demucs and tag stems."""
    try:
        _split_jobs[job_id]['status'] = 'splitting'

        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from stem_split import (run_demucs, copy_stem_to_library, tag_stem,
                                source_id, get_duration, load_tag_db, save_tag_db,
                                STEM_TYPE_MAP)

        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="demucs_web_")

        # Build source name from metadata
        artist = entry.get('artist', 'Unknown')
        title = entry.get('title', os.path.splitext(os.path.basename(track_path))[0])
        source_name = f"{artist} - {title}"
        src_id = source_id(track_path)

        # Run demucs
        stems = run_demucs(track_path, tmp_dir, model="htdemucs")
        if not stems:
            _split_jobs[job_id]['status'] = 'error'
            _split_jobs[job_id]['result'] = 'Demucs produced no output'
            return

        # Build parent tags from ID3 metadata
        parent_tags = {
            'bpm': entry.get('bpm'),
            'key': None,
            'genre': [entry['genre'].lower()] if entry.get('genre') else [],
            'vibe': [],
            'texture': [],
            'energy': 'mid',
            'source': 'personal',
        }

        # Enrich vibe/texture from genre
        genre_lower = (entry.get('genre') or '').lower()
        if any(w in genre_lower for w in ['punk', 'metal', 'hard', 'industrial']):
            parent_tags['vibe'] = ['aggressive']
            parent_tags['texture'] = ['raw']
        elif any(w in genre_lower for w in ['soul', 'jazz', 'r&b', 'gospel']):
            parent_tags['vibe'] = ['soulful']
            parent_tags['texture'] = ['warm']
        elif any(w in genre_lower for w in ['electronic', 'techno', 'house', 'electro']):
            parent_tags['vibe'] = ['hype']
            parent_tags['texture'] = ['clean']
        elif any(w in genre_lower for w in ['ambient', 'chill', 'lo-fi']):
            parent_tags['vibe'] = ['chill']
            parent_tags['texture'] = ['lo-fi']
        elif any(w in genre_lower for w in ['funk', 'disco']):
            parent_tags['vibe'] = ['playful']
            parent_tags['texture'] = ['warm']

        db = load_tag_db()
        created_stems = []

        for stem_name, stem_path in stems:
            dur = get_duration(stem_path)
            if dur < 1.0:
                continue

            stem_rel = copy_stem_to_library(stem_path, source_name, stem_name)

            # Tag with personal source
            stem_entry = tag_stem(stem_rel, stem_name, parent_tags, src_id, dur)
            stem_entry['source'] = 'personal'
            stem_entry['source_artist'] = artist
            stem_entry['source_album'] = entry.get('album')
            stem_entry['source_title'] = title
            stem_entry['source_year'] = entry.get('year')

            # Add 'personal' to flat tags
            if 'personal' not in stem_entry.get('tags', []):
                stem_entry.setdefault('tags', []).append('personal')
                stem_entry['tags'] = sorted(stem_entry['tags'])

            db[stem_rel] = stem_entry
            tc = STEM_TYPE_MAP.get(stem_name, 'SMP')
            created_stems.append({
                'stem': stem_name,
                'type_code': tc,
                'path': stem_rel,
                'duration': dur,
            })

        save_tag_db(db)

        # Cleanup
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

        _split_jobs[job_id]['status'] = 'done'
        _split_jobs[job_id]['result'] = {
            'stems': created_stems,
            'source': source_name,
            'source_id': src_id,
        }

    except Exception as e:
        _split_jobs[job_id]['status'] = 'error'
        _split_jobs[job_id]['result'] = str(e)


@music_bp.route('/music/split', methods=['POST'])
def split_track():
    """Split a track from the music library into stems via Demucs."""
    data = request.get_json()
    track_path_rel = data.get('path', '')

    if not track_path_rel:
        return jsonify({'error': 'No track path provided'}), 400

    full_path = os.path.join(MUSIC_LIBRARY, track_path_rel)
    if not os.path.isfile(full_path):
        return jsonify({'error': 'Track not found'}), 404

    # Check if already splitting
    with _split_lock:
        for j in _split_jobs.values():
            if j['status'] in ('splitting',) and j.get('track') == track_path_rel:
                return jsonify({'error': 'Already splitting this track', 'job_id': j['id']}), 409

    # Get track metadata from index
    index = _load_index()
    entry = index.get(track_path_rel, {})

    import uuid
    job_id = str(uuid.uuid4())[:8]
    _split_jobs[job_id] = {
        'id': job_id,
        'status': 'starting',
        'track': track_path_rel,
        'result': None,
    }

    t = threading.Thread(target=_run_split, args=(job_id, full_path, track_path_rel, entry))
    t.daemon = True
    t.start()

    return jsonify({'job_id': job_id, 'track': track_path_rel})


@music_bp.route('/music/split/status/<job_id>')
def split_status(job_id):
    """Check status of a stem split job."""
    job = _split_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)
