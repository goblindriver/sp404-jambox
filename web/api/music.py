"""My Music — Plex-powered personal music library browser API.

Reads from the local Plex database for rich metadata: moods, styles,
genres, album art, artist bios, play counts. Falls back to the old
ID3-based index if Plex isn't available.
"""
import json
import os
import sys
import threading
import uuid
from flask import Blueprint, jsonify, request, send_file, Response, current_app

from api._helpers import json_object_body as _json_object_body

music_bp = Blueprint('music', __name__)

# Add scripts dir to path for plex_client
_scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            '..', 'scripts')
if os.path.isdir(_scripts_dir):
    sys.path.insert(0, os.path.abspath(_scripts_dir))

_plex = None
_plex_last_check = 0
_plex_last_error = None
_PLEX_RETRY_SECONDS = 60


def _index_file():
    return current_app.config['MUSIC_INDEX_FILE']


def _stems_dir():
    return current_app.config['STEMS_DIR']


def _parse_track_id(value):
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('track_id must be an integer') from exc


def _get_plex():
    """Lazy-init Plex client, returns None if unavailable. Retries every 60s."""
    global _plex, _plex_last_check, _plex_last_error
    import time
    now = time.time()
    if _plex is not None:
        return _plex
    if now - _plex_last_check < _PLEX_RETRY_SECONDS:
        return None
    _plex_last_check = now
    try:
        from plex_client import PlexMusicDB
        p = PlexMusicDB()
        if p.is_available():
            _plex = p
            _plex_last_error = None
    except Exception as exc:
        _plex_last_error = str(exc)
        current_app.logger.warning('Plex music init failed: %s', exc)
    return _plex


def _plex_thumb_to_url(thumb):
    """Convert Plex metadata:// thumb URL to a proxied URL."""
    if not thumb:
        return None
    # We'll serve album art through our own proxy endpoint
    # Strip the metadata:// prefix and encode
    return f"/api/music/art?thumb={thumb}"


@music_bp.route('/music/status')
def music_status():
    """Check if music library is accessible and indexed."""
    plex = _get_plex()
    if plex:
        try:
            s = plex.stats()
            return jsonify({
                'available': True,
                'source': 'plex',
                'indexed': True,
                'track_count': s['tracks'],
                'artist_count': s['artists'],
                'album_count': s['albums'],
                'mood_count': s['moods'],
                'style_count': s['styles'],
                'library_path': s['root_path'],
            })
        except Exception as e:
            current_app.logger.warning('Plex music status failed: %s', e)

    # Fallback to old index
    try:
        with open(_index_file()) as f:
            index = json.load(f)
        count = len(index.get('tracks', index))
        return jsonify({
            'available': True,
            'source': 'id3',
            'indexed': count > 0,
            'track_count': count,
        })
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({'available': False, 'source': None, 'indexed': False})


@music_bp.route('/music/browse')
def browse():
    """Browse music library. Returns artists, genres, moods, styles, decades."""
    plex = _get_plex()
    if plex:
        try:
            data = plex.browse()
            # Add thumb proxy URLs
            for artist in data.get('artists', []):
                artist['thumb'] = None  # Artist thumbs need API, skip for now
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Plex not available and no index found'}), 404


@music_bp.route('/music/artist/<path:artist_name>')
def artist_detail(artist_name):
    """Get full artist detail: bio, albums, tracks with moods/vibes."""
    plex = _get_plex()
    if not plex:
        return jsonify({'error': 'Plex not available'}), 404

    try:
        data = plex.artist(artist_name)
        if not data:
            return jsonify({'error': f'Artist not found: {artist_name}'}), 404

        # Add art proxy URLs
        for album in data.get('albums', []):
            album['thumb_url'] = _plex_thumb_to_url(album.get('thumb'))

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@music_bp.route('/music/artist_by_id/<int:artist_id>')
def artist_detail_by_id(artist_id):
    """Get artist by Plex ID."""
    plex = _get_plex()
    if not plex:
        return jsonify({'error': 'Plex not available'}), 404

    try:
        data = plex.artist(artist_id=artist_id)
        if not data:
            return jsonify({'error': 'Artist not found'}), 404

        for album in data.get('albums', []):
            album['thumb_url'] = _plex_thumb_to_url(album.get('thumb'))

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@music_bp.route('/music/track/<int:track_id>')
def track_detail(track_id):
    """Get full metadata for a single track."""
    plex = _get_plex()
    if not plex:
        return jsonify({'error': 'Plex not available'}), 404

    try:
        data = plex.track(track_id)
        if not data:
            return jsonify({'error': 'Track not found'}), 404
        data['album_thumb_url'] = _plex_thumb_to_url(data.get('album_thumb'))
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@music_bp.route('/music/search')
def search():
    """Search music library by text query."""
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'results': []})

    plex = _get_plex()
    if plex:
        try:
            results = plex.search(q, limit=100)
            for r in results:
                r['thumb_url'] = _plex_thumb_to_url(r.get('thumb'))
            return jsonify({'results': results, 'total': len(results), 'query': q})
        except Exception as e:
            return jsonify({'ok': False, 'results': [], 'error': str(e)}), 500

    return jsonify({'results': []})


@music_bp.route('/music/mood/<mood>')
def by_mood(mood):
    """Find tracks by Plex mood tag."""
    plex = _get_plex()
    if not plex:
        return jsonify({'error': 'Plex not available'}), 404

    try:
        results = plex.search_by_mood(mood, limit=100)
        for r in results:
            r['thumb_url'] = _plex_thumb_to_url(r.get('thumb'))
        return jsonify({'results': results, 'mood': mood})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@music_bp.route('/music/style/<path:style>')
def by_style(style):
    """Find tracks by Plex style tag."""
    plex = _get_plex()
    if not plex:
        return jsonify({'error': 'Plex not available'}), 404

    try:
        results = plex.search_by_style(style, limit=100)
        for r in results:
            r['thumb_url'] = _plex_thumb_to_url(r.get('thumb'))
        return jsonify({'results': results, 'style': style})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@music_bp.route('/music/playlists')
def playlists():
    """List Plex playlists."""
    plex = _get_plex()
    if not plex:
        return jsonify({'playlists': []})

    try:
        return jsonify({'playlists': plex.playlists()})
    except Exception as e:
        return jsonify({'playlists': [], 'error': str(e)})


@music_bp.route('/music/most-played')
def most_played():
    """Get most-played tracks."""
    plex = _get_plex()
    if not plex:
        return jsonify({'tracks': []})

    try:
        return jsonify({'tracks': plex.most_played(limit=50)})
    except Exception as e:
        return jsonify({'tracks': [], 'error': str(e)})


@music_bp.route('/music/art')
def album_art():
    """Proxy album art from Plex metadata store.

    Plex stores album art as metadata://posters/HASH — we need to look up
    the actual blob in the Plex blobs database or filesystem.
    """
    thumb = request.args.get('thumb', '')
    if not thumb:
        return jsonify({'error': 'No thumb parameter'}), 404

    # Plex stores art in the metadata directory
    # Format: metadata://posters/<hash>
    # Actual file: ~/Library/Application Support/Plex Media Server/Metadata/
    #              Artists/<hash[0]>/<hash>.bundle/Contents/_stored/<hash>
    # But it's easier to check the blobs database

    try:
        import sqlite3
        blobs_db = os.path.expanduser(
            "~/Library/Application Support/Plex Media Server/"
            "Plug-in Support/Databases/com.plexapp.plugins.library.blobs.db"
        )
        if not os.path.exists(blobs_db):
            return jsonify({'error': 'Plex blobs database not found'}), 404

        # Extract the hash from the metadata:// URL
        # Format: metadata://posters/<hash> or tv.plex.agents.music_<hash>
        hash_part = thumb.split('/')[-1] if '/' in thumb else thumb

        uri = f"file:{blobs_db}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row

        try:
            row = conn.execute("""
                SELECT blob_data FROM blobs
                WHERE linked_id IN (
                    SELECT id FROM metadata_items WHERE user_thumb_url = ?
                ) LIMIT 1
            """, (thumb,)).fetchone()
        finally:
            conn.close()

        if row and row['blob_data']:
            # Detect image type from magic bytes
            data = row['blob_data']
            content_type = 'image/jpeg'  # default
            if data[:4] == b'\x89PNG':
                content_type = 'image/png'
            elif data[:4] == b'RIFF':
                content_type = 'image/webp'

            return Response(data, mimetype=content_type,
                            headers={'Cache-Control': 'public, max-age=86400'})
    except Exception:
        pass

    # Fallback: try Plex metadata filesystem
    try:
        meta_base = os.path.realpath(os.path.expanduser(
            "~/Library/Application Support/Plex Media Server/Metadata"
        ))
        # The hash is in the URL — sanitize to alphanumeric only
        if 'posters/' in thumb:
            poster_hash = thumb.split('posters/')[-1]
        else:
            poster_hash = thumb.split('_')[-1] if '_' in thumb else thumb

        # Validate hash is alphanumeric (no path traversal)
        import re as _re
        if not _re.match(r'^[a-zA-Z0-9]+$', poster_hash):
            return jsonify({'error': 'Invalid art hash'}), 404

        if len(poster_hash) >= 2:
            for sub in ['Albums', 'Artists']:
                art_path = os.path.realpath(os.path.join(
                    meta_base, sub,
                    poster_hash[0],
                    f"{poster_hash}.bundle",
                    "Contents", "_stored", poster_hash
                ))
                if not art_path.startswith(meta_base):
                    continue  # path traversal
                if os.path.exists(art_path):
                    return send_file(art_path, mimetype='image/jpeg',
                                     max_age=86400)
    except Exception:
        pass

    return jsonify({'error': 'Album art not found'}), 404


@music_bp.route('/music/preview/<int:track_id>')
def preview_track(track_id):
    """Stream a track from the music library for preview."""
    plex = _get_plex()
    if not plex:
        return jsonify({'error': 'Plex not available'}), 404

    try:
        t = plex.track(track_id)
        if not t or not t.get('file_path'):
            return jsonify({'error': 'Track not found'}), 404

        full = os.path.realpath(t['file_path'])
        stats = plex.stats()
        root = os.path.realpath(stats.get('root_path', ''))
        if not root or not full.startswith(root + os.sep):
            return jsonify({'error': 'Access denied'}), 403

        if not os.path.isfile(full):
            return jsonify({'error': 'Track file not found'}), 404

        ext = os.path.splitext(full)[1].lower()
        mimes = {
            '.mp3': 'audio/mpeg', '.flac': 'audio/flac',
            '.m4a': 'audio/mp4', '.wav': 'audio/wav',
            '.ogg': 'audio/ogg', '.aif': 'audio/aiff',
            '.aiff': 'audio/aiff',
        }
        return send_file(full, mimetype=mimes.get(ext, 'audio/mpeg'))
    except Exception:
        return jsonify({'error': 'Preview unavailable'}), 404


# ── Stem splitting ──

from api._helpers import JobTracker
_split_tracker = JobTracker(max_age=600)


def _update_split_job(job_id, **fields):
    _split_tracker.update(job_id, **fields)


def _get_split_job(job_id):
    return _split_tracker.get(job_id)


def _run_split(job_id, track_data):
    """Background thread: run demucs and tag stems with Plex metadata."""
    try:
        _update_split_job(job_id, status='splitting')

        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   '..', 'scripts')
        scripts_dir = os.path.abspath(scripts_dir)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from stem_split import (run_demucs, copy_stem_to_library, tag_stem,
                                source_id, get_duration, load_tag_db, save_tag_db,
                                STEM_TYPE_MAP)
        from plex_client import MOOD_TO_VIBE, STYLE_TO_GENRE

        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="demucs_web_")

        track_path = track_data['file_path']
        artist = track_data.get('artist', 'Unknown')
        title = track_data.get('title', os.path.splitext(os.path.basename(track_path))[0])
        source_name = f"{artist} - {title}"
        src_id = source_id(track_path)

        # Run demucs
        stems = run_demucs(track_path, tmp_dir, model="htdemucs")
        if not stems:
            _update_split_job(job_id, status='error', result='Demucs produced no output')
            return

        # Build parent tags from Plex metadata
        moods = track_data.get('moods', [])
        vibes = track_data.get('vibes', [])
        styles = track_data.get('styles', [])
        plex_genres = track_data.get('genres', [])

        # Map Plex styles to our genre dimension
        our_genres = set()
        for s in styles:
            g = STYLE_TO_GENRE.get(s.lower())
            if g:
                our_genres.add(g)
        for g in plex_genres:
            our_genres.add(g.lower())

        # Infer texture from moods
        texture = []
        if any(m.lower() in ('visceral', 'raw', 'brash', 'abrasive') for m in moods):
            texture.append('raw')
        elif any(m.lower() in ('warm', 'tender', 'intimate') for m in moods):
            texture.append('warm')
        elif any(m.lower() in ('ethereal', 'shimmering', 'atmospheric') for m in moods):
            texture.append('airy')

        # Infer energy
        energy = 'mid'
        high_moods = {'aggressive', 'energetic', 'intense', 'fiery', 'rousing',
                      'boisterous', 'volatile', 'hostile'}
        low_moods = {'mellow', 'calm', 'peaceful', 'serene', 'gentle', 'meditative'}
        mood_lower = {m.lower() for m in moods}
        if mood_lower & high_moods:
            energy = 'high'
        elif mood_lower & low_moods:
            energy = 'low'

        parent_tags = {
            'bpm': None,
            'key': None,
            'genre': sorted(our_genres),
            'vibe': vibes,
            'texture': texture,
            'energy': energy,
            'source': 'personal',
        }

        db = load_tag_db()
        created_stems = []

        for stem_name, stem_path in stems:
            dur = get_duration(stem_path)
            if dur < 1.0:
                continue

            stem_rel = copy_stem_to_library(stem_path, source_name, stem_name)

            stem_entry = tag_stem(stem_rel, stem_name, parent_tags, src_id, dur)
            stem_entry['source'] = 'personal'
            stem_entry['source_artist'] = artist
            stem_entry['source_album'] = track_data.get('album')
            stem_entry['source_title'] = title
            stem_entry['source_year'] = track_data.get('year')
            stem_entry['plex_moods'] = moods
            stem_entry['plex_styles'] = styles
            stem_entry['plex_id'] = track_data.get('id')

            if 'personal' not in stem_entry.get('tags', []):
                stem_entry.setdefault('tags', []).append('personal')
                stem_entry['tags'] = sorted(stem_entry['tags'])

            db[stem_rel] = stem_entry
            tc = STEM_TYPE_MAP.get(stem_name, 'BRK')
            created_stems.append({
                'stem': stem_name,
                'type_code': tc,
                'path': stem_rel,
                'duration': dur,
            })

        save_tag_db(db)

        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

        import time as _time
        _update_split_job(
            job_id,
            status='done',
            finished_at=_time.time(),
            result={
                'stems': created_stems,
                'source': source_name,
                'source_id': src_id,
            },
        )

    except Exception as e:
        import time as _time
        _update_split_job(job_id, status='error', finished_at=_time.time(), result=str(e))


@music_bp.route('/music/split', methods=['POST'])
def split_track():
    """Split a track into stems via Demucs. Accepts Plex track ID."""
    try:
        data = _json_object_body()
        raw_track_id = data.get('track_id') or data.get('id')
        if raw_track_id in (None, ''):
            return jsonify({'ok': False, 'error': 'No track ID provided'}), 400
        track_id = _parse_track_id(raw_track_id)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    plex = _get_plex()
    if not plex:
        return jsonify({'ok': False, 'error': 'Plex not available'}), 503

    try:
        track_data = plex.track(track_id)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    if not track_data:
        return jsonify({'ok': False, 'error': 'Track not found'}), 404

    if not track_data.get('file_path') or not os.path.isfile(track_data['file_path']):
        return jsonify({'ok': False, 'error': 'Track file not accessible'}), 404

    if _split_tracker.has_active('starting', 'splitting'):
        return jsonify({'ok': False, 'error': 'Already splitting'}), 409
    job_id = _split_tracker.create(
        status='starting',
        track_id=track_id,
        track=f"{track_data.get('artist', '?')} — {track_data.get('title', '?')}",
        result=None,
    )

    t = threading.Thread(target=_run_split, args=(job_id, track_data))
    t.daemon = True
    t.start()

    job = _get_split_job(job_id) or {}
    return jsonify({'ok': True, 'job_id': job_id, 'track': job.get('track')})


@music_bp.route('/music/split/status/<job_id>')
def split_status(job_id):
    """Check status of a stem split job."""
    job = _get_split_job(job_id)
    if not job:
        return jsonify({'ok': False, 'error': 'Job not found'}), 404
    return jsonify(job)
