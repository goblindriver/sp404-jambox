"""Media browser — Plex-powered movie/TV/anime library for clip extraction.

Extends the Plex integration beyond music to the full media library.
Provides browsing, taste profiling, and audio clip extraction from
movies and TV shows for sampling on the SP-404.
"""
import os
import sys
import threading
import time
from flask import Blueprint, jsonify, request, current_app

media_bp = Blueprint('media', __name__)

_scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            '..', 'scripts')
if os.path.isdir(_scripts_dir):
    sys.path.insert(0, os.path.abspath(_scripts_dir))

_plex_media = None
_plex_media_last_check = 0
_plex_media_last_error = None
_RETRY_SECONDS = 60

# Background extraction jobs
_extract_jobs = {}
_extract_lock = threading.Lock()
_EXTRACT_JOB_MAX_AGE = 600


def _update_extract_job(job_id, **fields):
    with _extract_lock:
        job = _extract_jobs.get(job_id)
        if not job:
            return
        job.update(fields)


def _get_extract_job(job_id):
    with _extract_lock:
        job = _extract_jobs.get(job_id)
        return dict(job) if isinstance(job, dict) else None


def _get_media_db():
    """Lazy-init PlexMediaDB, returns None if unavailable."""
    global _plex_media, _plex_media_last_check, _plex_media_last_error
    now = time.time()
    if _plex_media is not None:
        return _plex_media
    if now - _plex_media_last_check < _RETRY_SECONDS:
        return None
    _plex_media_last_check = now
    try:
        from plex_client import PlexMediaDB
        p = PlexMediaDB()
        _plex_media = p
        _plex_media_last_error = None
    except Exception as exc:
        _plex_media_last_error = str(exc)
        current_app.logger.warning("Plex media init failed: %s", exc)
    return _plex_media


@media_bp.route('/media/status')
def media_status():
    """Check media library availability and counts."""
    db = _get_media_db()
    if not db:
        payload = {'available': False}
        if _plex_media_last_error:
            payload['error'] = _plex_media_last_error
        return jsonify(payload), 503
    try:
        s = db.stats()
        return jsonify({'available': True, **s})
    except Exception as e:
        return jsonify({'available': False, 'error': str(e)})


@media_bp.route('/media/movies')
def list_movies():
    """Browse movies. ?genre=Horror&sort=rating&search=alien&limit=50"""
    db = _get_media_db()
    if not db:
        return jsonify({'ok': False, 'error': 'Plex not available'}), 503
    try:
        genre = request.args.get('genre')
        sort = request.args.get('sort', 'rating')
        search = request.args.get('search')
        limit = min(int(request.args.get('limit', 50)), 200)
        movies = db.movies(limit=limit, genre=genre, sort=sort, search=search)
        return jsonify({'movies': movies, 'count': len(movies)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@media_bp.route('/media/movie/<int:movie_id>')
def movie_detail(movie_id):
    """Full movie detail: cast, file path, extras, media info."""
    db = _get_media_db()
    if not db:
        return jsonify({'ok': False, 'error': 'Plex not available'}), 503
    try:
        movie = db.movie(movie_id)
        if not movie:
            return jsonify({'error': 'Movie not found'}), 404
        return jsonify(movie)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@media_bp.route('/media/shows')
def list_shows():
    """Browse TV shows and anime. ?search=cowboy&section=4"""
    db = _get_media_db()
    if not db:
        return jsonify({'ok': False, 'error': 'Plex not available'}), 503
    try:
        search = request.args.get('search')
        section_id = request.args.get('section')
        section_id = int(section_id) if section_id else None
        limit = min(int(request.args.get('limit', 50)), 200)
        shows = db.shows(section_id=section_id, limit=limit, search=search)
        return jsonify({'shows': shows, 'count': len(shows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@media_bp.route('/media/show/<int:show_id>/episodes')
def show_episodes(show_id):
    """List episodes for a show. ?season=1&limit=50"""
    db = _get_media_db()
    if not db:
        return jsonify({'ok': False, 'error': 'Plex not available'}), 503
    try:
        season = request.args.get('season')
        season = int(season) if season else None
        limit = min(int(request.args.get('limit', 50)), 200)
        eps = db.episodes(show_id, season=season, limit=limit)
        return jsonify({'episodes': eps, 'count': len(eps)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@media_bp.route('/media/taste')
def taste_profile():
    """Build taste profile from full library for RL training."""
    db = _get_media_db()
    if not db:
        return jsonify({'ok': False, 'error': 'Plex not available'}), 503
    try:
        profile = db.taste_profile()
        return jsonify(profile)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@media_bp.route('/media/genres')
def movie_genres():
    """List all movie genres with counts."""
    db = _get_media_db()
    if not db:
        return jsonify({'ok': False, 'error': 'Plex not available'}), 503
    try:
        profile = db.taste_profile()
        return jsonify({
            'movie_genres': profile.get('movie_genres', {}),
            'tv_genres': profile.get('tv_genres', {}),
            'anime_genres': profile.get('anime_genres', {}),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@media_bp.route('/media/extract', methods=['POST'])
def extract_clips():
    """Extract audio clips from a movie or episode.

    POST body:
        movie_id: int (or)
        show_id: int + season: int (optional)
        scan_minutes: int (default 10)
        max_clips: int (default 20)
    """
    db = _get_media_db()
    if not db:
        return jsonify({'ok': False, 'error': 'Plex not available'}), 503

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'ok': False, 'error': 'Request body must be a JSON object'}), 400
    movie_id = data.get('movie_id')
    show_id = data.get('show_id')
    season = data.get('season')
    try:
        scan_minutes = min(int(data.get('scan_minutes', 10)), 60)
        max_clips = min(int(data.get('max_clips', 20)), 50)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'scan_minutes and max_clips must be integers'}), 400

    # Collect sources
    sources = []
    if movie_id:
        detail = db.movie(int(movie_id))
        if detail and detail.get('file_path'):
            sources.append(detail)
    elif show_id:
        shows = db.shows(search=None, limit=100)
        show = None
        for s in shows:
            if s['id'] == int(show_id):
                show = s
                break
        if show:
            eps = db.episodes(int(show_id), season=int(season) if season else None, limit=5)
            for ep in eps:
                ep['genres'] = show.get('genres', [])
            sources = eps

    if not sources:
        return jsonify({'ok': False, 'error': 'No sources found with accessible files'}), 404

    import uuid

    with _extract_lock:
        # Prune finished jobs older than 10 minutes
        now = time.time()
        stale = [jid for jid, j in _extract_jobs.items()
                 if j['status'] in ('complete', 'error')
                 and now - j.get('finished_at', 0) > _EXTRACT_JOB_MAX_AGE]
        for jid in stale:
            del _extract_jobs[jid]

        job_id = str(uuid.uuid4())[:8]
        _extract_jobs[job_id] = {
            'status': 'running',
            'sources': len(sources),
            'clips': 0,
            'started': now,
        }

    def _run_extract():
        try:
            from extract_clips import extract_from_source, tag_extracted_clips
            all_clips = []
            for source in sources:
                clips = extract_from_source(source, scan_minutes=scan_minutes,
                                            max_clips=max_clips)
                all_clips.extend(clips)
                _update_extract_job(job_id, clips=len(all_clips))

            tag_extracted_clips(all_clips)
            _update_extract_job(
                job_id,
                status='complete',
                total_clips=len(all_clips),
                clip_details=all_clips,
                finished_at=time.time(),
            )
        except Exception as e:
            _update_extract_job(job_id, status='error', error=str(e), finished_at=time.time())

    thread = threading.Thread(target=_run_extract, daemon=True)
    thread.start()

    return jsonify({
        'ok': True,
        'job_id': job_id,
        'sources': len(sources),
        'message': f'Extracting clips from {len(sources)} source(s)',
    })


@media_bp.route('/media/extract-status/<job_id>')
def extract_status(job_id):
    """Poll extraction job status."""
    job = _get_extract_job(job_id)
    if not job:
        return jsonify({'ok': False, 'error': 'Job not found'}), 404
    return jsonify(job)
