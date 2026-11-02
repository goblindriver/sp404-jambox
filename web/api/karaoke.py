"""Karaoke mode API: prep songs, edit drop sheets, preview, load the karaoke set.

Song packages live in ``KARAOKE_DIR`` (see scripts/karaoke_prep.py). The
Windows deck (deck/karaoke_deck.py) plays the same files at party time; this
blueprint is the kitchen: prep, review, tweak.
"""
import os
import sys
import threading

from flask import Blueprint, current_app, jsonify, send_file

from api._helpers import JobTracker, json_object_body

_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import karaoke_drops  # noqa: E402
import karaoke_lyrics  # noqa: E402

karaoke_bp = Blueprint('karaoke', __name__)

_prep_tracker = JobTracker(max_age=3600)
_prep_lock = threading.Lock()   # one Demucs batch at a time; it saturates the CPU

# Bank layout for karaoke night (A-B internal memory, C onward on the card).
KARAOKE_SET_FIXED = [
    ('a', 'utility/karaoke-drops'),
    ('b', 'genre/weapons-cache'),
    ('c', 'genre/karaoke-metal'),
]
KARAOKE_SET_FILL = ['genre/synth-punk-pogo', 'genre/riot-mode', 'genre/disco-inferno',
                    'genre/funk-muscle', 'genre/electro-sweat', 'genre/neon-rave', 'genre/peak-hour']

AUDIO_FILES = {'backing': 'backing.flac', 'guide': 'guide.flac'}


def _prep_module():
    import karaoke_prep
    return karaoke_prep


def _root():
    return current_app.config['KARAOKE_DIR']


def _song_dir(name):
    """Resolve a song folder name inside KARAOKE_DIR, refusing traversal."""
    if not name or name.startswith('.') or name.startswith('_') or '/' in name or '\\' in name:
        raise ValueError('invalid song')
    root = os.path.realpath(_root())
    path = os.path.realpath(os.path.join(root, name))
    if os.path.dirname(path) != root or not os.path.isfile(os.path.join(path, 'song.json')):
        raise FileNotFoundError(name)
    return path


def _read_song(name):
    path = _song_dir(name)
    data = _prep_module().load_song_json(path) or {}
    return path, data


def _get_plex():
    from api.music import _get_plex as music_plex
    return music_plex()


def _tool_status():
    import importlib.util
    import shutil
    kp = _prep_module()
    return {
        'demucs': importlib.util.find_spec('demucs') is not None,
        'librosa': importlib.util.find_spec('librosa') is not None,
        'plex': _get_plex() is not None,
        # Without SP404_KARAOKE_GEN in this process's environment every karaoke-gen prep fails.
        'karaoke_gen': shutil.which(kp.KARAOKE_GEN) is not None,
        'backend': kp.KARAOKE_BACKEND,
        # Configured, not checked: lane.free() goes over ssh, too slow for a status poll.
        'remote_lane': kp.KARAOKE_REMOTE_HOST or None,
        # Music videos (prep option); SP404_YTDLP must be in this process's environment too.
        'ytdlp': shutil.which(kp.karaoke_video.YTDLP) is not None,
    }


# ── Read ─────────────────────────────────────────────────────────────

@karaoke_bp.route('/karaoke/status')
def status():
    songs = _prep_module().rebuild_index(_root()) if os.path.isdir(_root()) else []
    return jsonify({
        'ok': True,
        'karaoke_dir': _root(),
        'songs': len(songs),
        'tools': _tool_status(),
        'drop_pads': karaoke_drops.DROP_PADS,
        'drop_bank': karaoke_drops.DROP_BANK,
    })


@karaoke_bp.route('/karaoke/songs')
def songs():
    return jsonify({'ok': True, 'songs': _prep_module().rebuild_index(_root())})


@karaoke_bp.route('/karaoke/song/<name>')
def song(name):
    try:
        path, data = _read_song(name)
    except (ValueError, FileNotFoundError):
        return jsonify({'ok': False, 'error': 'Song not found'}), 404
    lines = []
    lrc = os.path.join(path, 'lyrics.lrc')
    if os.path.isfile(lrc):
        with open(lrc, encoding='utf-8', errors='replace') as fh:
            lines = [{'t': ln.t, 'text': ln.text} for ln in karaoke_lyrics.parse_lrc(fh.read())]
    plain = None
    txt = os.path.join(path, 'lyrics.txt')
    if not lines and os.path.isfile(txt):
        with open(txt, encoding='utf-8', errors='replace') as fh:
            plain = fh.read()
    return jsonify({
        'ok': True,
        'dir': name,
        'song': data,
        'lyrics': lines,
        'plain_lyrics': plain,
        'has_guide': os.path.isfile(os.path.join(path, 'guide.flac')),
        'has_cover': os.path.isfile(os.path.join(path, 'cover.jpg')),
        'has_video': bool(data.get('video')) and os.path.isfile(os.path.join(path, data['video'].get('file') or '')),
    })


@karaoke_bp.route('/karaoke/audio/<name>/<kind>')
def audio(name, kind):
    if kind not in AUDIO_FILES:
        return jsonify({'ok': False, 'error': 'unknown stem'}), 404
    try:
        path = _song_dir(name)
    except (ValueError, FileNotFoundError):
        return jsonify({'ok': False, 'error': 'Song not found'}), 404
    f = os.path.join(path, AUDIO_FILES[kind])
    if not os.path.isfile(f):
        return jsonify({'ok': False, 'error': 'Audio not found'}), 404
    return send_file(f, mimetype='audio/flac', conditional=True)


@karaoke_bp.route('/karaoke/cover/<name>')
def cover(name):
    try:
        path = _song_dir(name)
    except (ValueError, FileNotFoundError):
        return jsonify({'ok': False, 'error': 'Song not found'}), 404
    f = os.path.join(path, 'cover.jpg')
    if not os.path.isfile(f):
        return jsonify({'ok': False, 'error': 'No cover'}), 404
    return send_file(f, mimetype='image/jpeg', max_age=3600)


@karaoke_bp.route('/karaoke/playlists')
def playlists():
    plex = _get_plex()
    if plex is None:
        return jsonify({'ok': False, 'error': 'Plex not available', 'playlists': []}), 503
    return jsonify({'ok': True, 'playlists': plex.playlists()})


# ── Drop sheets ──────────────────────────────────────────────────────

@karaoke_bp.route('/karaoke/song/<name>/drops', methods=['PUT'])
def save_drops(name):
    """Save a hand-edited drop sheet. Locks it so re-prep won't overwrite."""
    try:
        path, data = _read_song(name)
    except (ValueError, FileNotFoundError):
        return jsonify({'ok': False, 'error': 'Song not found'}), 404
    try:
        body = json_object_body()
        drops = karaoke_drops.validate_drops(body.get('drops'))
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    data['drops'] = drops
    data['drops_locked'] = bool(body.get('locked', True))
    if body.get('preset') is not None:
        data['preset'] = body.get('preset') or None
    _prep_module().write_json(os.path.join(path, 'song.json'), data)
    return jsonify({'ok': True, 'drops': drops, 'drops_locked': data['drops_locked']})


@karaoke_bp.route('/karaoke/song/<name>/redraft', methods=['POST'])
def redraft(name):
    """Throw away edits and re-draft the drop sheet from the song's structure."""
    try:
        path, data = _read_song(name)
    except (ValueError, FileNotFoundError):
        return jsonify({'ok': False, 'error': 'Song not found'}), 404
    lines = []
    lrc = os.path.join(path, 'lyrics.lrc')
    if os.path.isfile(lrc):
        with open(lrc, encoding='utf-8', errors='replace') as fh:
            lines = karaoke_lyrics.parse_lrc(fh.read())
    sung = [ln.t for ln in lines if ln.text.strip()]
    data['drops'] = karaoke_drops.draft_drop_sheet(
        duration_s=data.get('duration_s'), bpm=data.get('bpm'),
        first_beat_s=data.get('beat_offset_s'),
        choruses=[tuple(c) for c in data.get('choruses') or []],
        first_vocal_s=sung[0] if sung else None, last_vocal_s=sung[-1] if sung else None,
        energy=data.get('energy'))
    data['drops_locked'] = False
    _prep_module().write_json(os.path.join(path, 'song.json'), data)
    return jsonify({'ok': True, 'drops': data['drops'], 'drops_locked': False})


# ── Prep jobs ────────────────────────────────────────────────────────

def _run_prep(app, job_id, tracks, opts):
    with app.app_context():
        kp = _prep_module()
        root = _root()
        if not _prep_lock.acquire(blocking=False):
            _prep_tracker.update(job_id, status='error', error='Another karaoke prep is running')
            return
        try:
            log, counts, counts_lock = [], {'started': 0, 'done': 0, 'failed': 0, 'videos': 0}, threading.Lock()
            lane = (kp.RemoteLane(kp.KARAOKE_REMOTE_HOST)
                    if kp.KARAOKE_REMOTE_HOST and opts['backend'] == 'karaoke-gen' else None)

            # Both lanes call these from their own threads.
            def on_start(meta, where):
                label = f"{meta.get('artist') or '?'} - {meta.get('title') or '?'}"
                with counts_lock:
                    index = counts['started']
                    counts['started'] += 1
                _prep_tracker.update(job_id, status='running', current=f"{label} ({where})", index=index)

            def on_done(meta, error):
                with counts_lock:
                    counts['failed' if error else 'done'] += 1
                    done, failed = counts['done'], counts['failed']
                _prep_tracker.update(job_id, done=done, failed=failed, log=log[-40:])

            def on_video(meta, video, error):
                with counts_lock:
                    counts['videos'] += 1 if video else 0
                    videos = counts['videos']
                _prep_tracker.update(job_id, videos=videos, log=log[-40:])

            # Songs run on the remote GPU lane and this machine at once; a song the
            # lane yields to a game is re-queued (see karaoke_prep.prep_batch).
            kp.prep_batch(tracks, lane=lane, on_start=on_start, on_done=on_done, log=log.append,
                          videos=opts['videos'], revideo=opts['revideo'], on_video=on_video,
                          out_root=root, model=opts['model'], refresh=opts['refresh'],
                          force=opts['force'], online=True, backend=opts['backend'])
            kp.rebuild_index(root)
            _prep_tracker.update(job_id, status='done', current=None)
        except Exception as exc:
            _prep_tracker.update(job_id, status='error', error=str(exc))
        finally:
            _prep_lock.release()


@karaoke_bp.route('/karaoke/prep', methods=['POST'])
def prep():
    """Start a prep job. Body: one of {playlist}, {track_id}, {track_ids: []}, {dir} (re-prep)
    plus optional model ('karaoke-gen'|'htdemucs'|'htdemucs_ft'; the Demucs ones pick
    the Demucs backend), refresh, force, videos (fetch a music video per song) and
    revideo (re-fetch it; with {dir} alone that's all it does)."""
    try:
        body = json_object_body()
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    if _prep_lock.locked():
        return jsonify({'ok': False, 'error': 'A karaoke prep job is already running'}), 409
    default = 'karaoke-gen' if _prep_module().KARAOKE_BACKEND == 'karaoke-gen' else 'htdemucs'
    model = body.get('model') or default
    if model not in ('karaoke-gen', 'htdemucs', 'htdemucs_ft'):
        return jsonify({'ok': False, 'error': 'model must be karaoke-gen, htdemucs or htdemucs_ft'}), 400
    opts = {'backend': 'karaoke-gen' if model == 'karaoke-gen' else 'demucs',
            'model': 'htdemucs' if model == 'karaoke-gen' else model,
            'refresh': bool(body.get('refresh')), 'force': bool(body.get('force')),
            'videos': bool(body.get('videos') or body.get('revideo')), 'revideo': bool(body.get('revideo'))}

    tracks = []
    if body.get('dir'):
        try:
            _, data = _read_song(str(body['dir']))
        except (ValueError, FileNotFoundError):
            return jsonify({'ok': False, 'error': 'Song not found'}), 404
        tracks = [{'file_path': data.get('source_path'), 'artist': data.get('artist'),
                   'title': data.get('title'), 'album': data.get('album'), 'id': data.get('plex_id'),
                   'moods': data.get('moods'), 'styles': data.get('styles'),
                   'duration_s': data.get('duration_s')}]
        if not opts['force'] and not opts['revideo']:
            opts['refresh'] = True
    else:
        plex = _get_plex()
        if plex is None:
            return jsonify({'ok': False, 'error': 'Plex not available'}), 503
        if body.get('playlist'):
            items = plex.playlist_tracks(body['playlist'])
            if items is None:
                return jsonify({'ok': False, 'error': f"No playlist {body['playlist']!r}"}), 404
            ids = [it['id'] for it in items]
        else:
            ids = body.get('track_ids') or ([body['track_id']] if body.get('track_id') else [])
        for tid in ids[:200]:
            try:
                t = plex.track(int(tid))
            except (TypeError, ValueError):
                t = None
            if t:
                tracks.append(t)
    if not tracks:
        return jsonify({'ok': False, 'error': 'No tracks to prep'}), 400

    job_id = _prep_tracker.create(status='queued', total=len(tracks), done=0, failed=0, log=[])
    app = current_app._get_current_object()
    threading.Thread(target=_run_prep, args=(app, job_id, tracks, opts), daemon=True).start()
    return jsonify({'ok': True, 'job_id': job_id, 'total': len(tracks)})


@karaoke_bp.route('/karaoke/prep-status/<job_id>')
def prep_status(job_id):
    job = _prep_tracker.get(job_id)
    if not job:
        return jsonify({'ok': False, 'error': 'Job not found'}), 404
    return jsonify({'ok': True, **job})


# ── Karaoke set ──────────────────────────────────────────────────────

def plan_karaoke_set(song_presets):
    """Banks for karaoke night: A drops, B weapons, C metal, then D-J from the
    presets the prepped songs suggest (most common first), topped up with
    dance-floor defaults. Returns [(bank_letter, preset_ref), ...]."""
    from collections import Counter
    plan = list(KARAOKE_SET_FIXED)
    used = {ref for _, ref in plan}
    ranked = [ref for ref, _ in Counter(p for p in song_presets if p).most_common()]
    for ref in ranked + KARAOKE_SET_FILL:
        if len(plan) >= 10:
            break
        if ref not in used:
            plan.append(('abcdefghij'[len(plan)], ref))
            used.add(ref)
    return plan


@karaoke_bp.route('/karaoke/set-plan')
def set_plan():
    songs = _prep_module().rebuild_index(_root())
    return jsonify({'ok': True, 'plan': [{'bank': b, 'preset': r}
                                         for b, r in plan_karaoke_set([s.get('preset') for s in songs])]})


@karaoke_bp.route('/karaoke/load-set', methods=['POST'])
def load_set():
    """Load the karaoke-night banks into bank_config.yaml (then Fetch All + Export)."""
    import preset_utils as pu
    songs = _prep_module().rebuild_index(_root())
    loaded, errors = [], []
    for bank, ref in plan_karaoke_set([s.get('preset') for s in songs]):
        try:
            result = pu.load_preset_to_bank(ref, bank)
            loaded.append({'bank': bank, 'preset': ref, 'name': result.get('name')})
        except Exception as exc:
            errors.append({'bank': bank, 'preset': ref, 'error': str(exc)})
    return jsonify({'ok': not errors, 'loaded': loaded, 'errors': errors})
