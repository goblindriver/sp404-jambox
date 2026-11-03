"""Karaoke mode API: prep songs, edit drop sheets, preview, load the karaoke set.

Song packages live in ``KARAOKE_DIR`` (see scripts/karaoke_prep.py). The
Windows deck (deck/karaoke_deck.py) plays the same files at party time; this
blueprint is the kitchen: prep, review, tweak.
"""
import hashlib
import os
import sys
import tempfile
import threading

from flask import Blueprint, current_app, jsonify, request, send_file

from api._helpers import JobTracker, json_object_body

_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import karaoke_drops  # noqa: E402
import karaoke_lyrics  # noqa: E402
import karaoke_capabilities  # noqa: E402

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
UPLOAD_EXTS = {'.flac', '.wav', '.aiff', '.aif', '.mp3', '.m4a', '.ogg'}


def _prep_module():
    import karaoke_prep
    return karaoke_prep


def _root():
    return current_app.config['KARAOKE_DIR']


def _source_roots():
    """Directories a ``file_path`` prep is allowed to read."""
    cfg = current_app.config
    roots = []
    for key in ('KARAOKE_DIR', 'SAMPLE_LIBRARY', 'DOWNLOADS_PATH'):
        value = cfg.get(key)
        if value:
            roots.append(os.path.expanduser(str(value)))
    extra = cfg.get('KARAOKE_SOURCES')
    if extra is None:
        extra = os.environ.get('SP404_KARAOKE_SOURCES', '')
    for part in str(extra).split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(os.path.expanduser(part))
    return roots


def _under_root(path, root):
    real_root = os.path.realpath(root)
    real_path = os.path.realpath(path)
    if real_path == real_root:
        return True
    prefix = real_root if real_root.endswith(os.sep) else real_root + os.sep
    return real_path.startswith(prefix)


def resolve_source_file(file_path):
    """Real path of an audio file under a configured root.

    Raises ValueError, PermissionError (outside every root), or FileNotFoundError.
    A path that realpaths back inside a root is allowed. A symlink that
    realpaths out is not.
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError('file_path required')
    expanded = os.path.expanduser(file_path.strip())
    if not any(_under_root(expanded, root) for root in _source_roots()):
        raise PermissionError('file_path is outside the karaoke source roots')
    real = os.path.realpath(expanded)
    if not os.path.isfile(real):
        raise FileNotFoundError(file_path)
    return real


def _store_upload(stream, ext):
    """Stream an upload to ``KARAOKE_DIR/_sources/<sha256[:16]><ext>``.

    The hash is computed while writing, so the bytes are not held twice.
    """
    sources = os.path.join(_root(), '_sources')
    os.makedirs(sources, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.', suffix='.partial', dir=sources)
    hasher = hashlib.sha256()
    replaced = False
    try:
        with os.fdopen(fd, 'wb') as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                out.write(chunk)
        dest = os.path.join(sources, hasher.hexdigest()[:16] + ext)
        os.replace(tmp, dest)
        replaced = True
        return dest
    finally:
        if not replaced:
            try:
                os.remove(tmp)
            except OSError:
                pass


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


def _tool_status(cap):
    kp = _prep_module()
    return {
        'demucs': cap['separate']['demucs'],
        'librosa': cap['extras']['librosa'],
        'plex': cap['sources']['plex'],
        # Config floor (SP404_KARAOKE_BACKEND), not the probe's UI default.
        'karaoke_gen': cap['separate']['karaoke_gen'],
        'backend': kp.KARAOKE_BACKEND,
        # Configured, not checked: lane.free() goes over ssh, too slow for a status poll.
        'remote_lane': cap['separate']['remote_lane'],
        'ytdlp': cap['extras']['ytdlp'],
    }


# ── Read ─────────────────────────────────────────────────────────────

@karaoke_bp.route('/karaoke/status')
def status():
    cap = karaoke_capabilities.capabilities(plex=_get_plex() is not None)
    songs = _prep_module().rebuild_index(_root()) if os.path.isdir(_root()) else []
    return jsonify({
        'ok': True,
        'karaoke_dir': _root(),
        'songs': len(songs),
        'tools': _tool_status(cap),
        'capabilities': cap,
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

def prep_job_status(done, failed):
    """What a finished batch is. An empty batch is ``done``; the route already
    refuses that before the thread starts. A raised exception from ``prep_batch``
    itself stays ``error`` and does not come through here."""
    if failed and done:
        return "partial"
    if failed:
        return "error"
    return "done"


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
                    if kp.KARAOKE_REMOTE_HOST and opts['backend'] == 'karaoke-gen'
                    and not opts['video_only'] else None)

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
            done, failed = kp.prep_batch(
                tracks, lane=lane, on_start=on_start, on_done=on_done, log=log.append,
                videos=opts['videos'], revideo=opts['revideo'], video_only=opts['video_only'],
                on_video=on_video,
                out_root=root, model=opts['model'], refresh=opts['refresh'],
                force=opts['force'], online=True, backend=opts['backend'])
            kp.rebuild_index(root)
            status = prep_job_status(done, failed)
            fields = {'status': status, 'current': None, 'done': done, 'failed': failed}
            if failed:
                fields['error'] = '%d %s failed' % (failed, 'song' if failed == 1 else 'songs')
            _prep_tracker.update(job_id, **fields)
        except Exception as exc:
            _prep_tracker.update(job_id, status='error', error=str(exc))
        finally:
            _prep_lock.release()


def _checked_opts(model, videos, revideo, refresh, force):
    """``(opts, error_response)``. ``error_response`` is ``(body, status)`` or None."""
    cap = karaoke_capabilities.capabilities()
    chosen = model or cap['separate']['default']
    refusal = karaoke_capabilities.reject_prep(cap, chosen, videos)
    if refusal:
        return None, (jsonify({'ok': False, 'error': refusal}), 400)
    return {
        'backend': 'karaoke-gen' if chosen == 'karaoke-gen' else 'demucs',
        'model': 'htdemucs' if chosen == 'karaoke-gen' else chosen,
        'refresh': bool(refresh),
        'force': bool(force),
        'videos': bool(videos),
        'revideo': bool(revideo),
        'video_only': False,
    }, None


def _queue_prep(tracks, opts):
    if not tracks:
        return jsonify({'ok': False, 'error': 'No tracks to prep'}), 400
    job_id = _prep_tracker.create(status='queued', total=len(tracks), done=0, failed=0, log=[])
    app = current_app._get_current_object()
    threading.Thread(target=_run_prep, args=(app, job_id, tracks, opts), daemon=True).start()
    return jsonify({'ok': True, 'job_id': job_id, 'total': len(tracks)})


def _form_flag(name):
    return request.form.get(name, '').strip().lower() in ('1', 'true', 'on', 'yes')


def _clean(value):
    if not isinstance(value, str):
        return None
    return value.strip() or None


@karaoke_bp.route('/karaoke/upload', methods=['POST'])
def upload():
    """Multipart ``file`` plus optional artist, title, album, model, videos.

    The file is stored under ``KARAOKE_DIR/_sources`` and prepped like a local file.
    """
    if _prep_lock.locked():
        return jsonify({'ok': False, 'error': 'A karaoke prep job is already running'}), 409
    opts, err = _checked_opts(
        (request.form.get('model') or '').strip() or None,
        _form_flag('videos') or _form_flag('revideo'),
        _form_flag('revideo'),
        _form_flag('refresh'),
        _form_flag('force'),
    )
    if err:
        return err
    upload_file = request.files.get('file')
    if upload_file is None or not upload_file.filename:
        return jsonify({'ok': False, 'error': 'file required'}), 400
    ext = os.path.splitext(upload_file.filename)[1].lower()
    if ext not in UPLOAD_EXTS:
        return jsonify({'ok': False, 'error': 'file must be flac, wav, aiff, mp3, m4a, or ogg'}), 400
    path = _store_upload(upload_file.stream, ext)
    artist = _clean(request.form.get('artist'))
    title = _clean(request.form.get('title'))
    album = _clean(request.form.get('album'))
    track = {'file_path': path, 'artist': artist, 'title': title, 'album': album, 'source_kind': 'upload'}
    return _queue_prep([track], opts)


@karaoke_bp.route('/karaoke/prep', methods=['POST'])
def prep():
    """Start a prep job. Body: one of {playlist}, {track_id}, {track_ids: []},
    {file_path} (under KARAOKE_DIR, the sample library, downloads, or
    SP404_KARAOKE_SOURCES), or {dir} (re-prep). Optional model
    ('karaoke-gen'|'htdemucs'|'htdemucs_ft'), refresh, force, videos, revideo,
    and artist/title/album for a file_path."""
    try:
        body = json_object_body()
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    if _prep_lock.locked():
        return jsonify({'ok': False, 'error': 'A karaoke prep job is already running'}), 409
    videos = bool(body.get('videos') or body.get('revideo'))
    opts, err = _checked_opts(body.get('model') or None, videos, bool(body.get('revideo')),
                              bool(body.get('refresh')), bool(body.get('force')))
    if err:
        return err

    tracks = []
    if body.get('dir'):
        try:
            _, data = _read_song(str(body['dir']))
        except (ValueError, FileNotFoundError):
            return jsonify({'ok': False, 'error': 'Song not found'}), 404
        kind = data.get('source_kind')
        if kind not in ('file', 'upload', 'plex'):
            kind = 'plex' if data.get('plex_id') else 'file'
        tracks = [{'file_path': data.get('source_path'), 'artist': data.get('artist'),
                   'title': data.get('title'), 'album': data.get('album'), 'id': data.get('plex_id'),
                   'moods': data.get('moods'), 'styles': data.get('styles'),
                   'duration_s': data.get('duration_s'), 'source_kind': kind}]
        # Video button: the song is prepped, so skip prep and the lanes (its source may be offline).
        opts['video_only'] = opts['revideo'] and not opts['force'] and not opts['refresh']
        if not opts['force'] and not opts['revideo']:
            opts['refresh'] = True
    elif body.get('file_path'):
        try:
            path = resolve_source_file(body.get('file_path'))
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 403
        except FileNotFoundError:
            return jsonify({'ok': False, 'error': 'Audio not found'}), 404
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        tracks = [{'file_path': path,
                   'artist': _clean(body.get('artist')),
                   'title': _clean(body.get('title')),
                   'album': _clean(body.get('album')),
                   'source_kind': 'file'}]
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
                tracks.append(dict(t, source_kind='plex'))
    return _queue_prep(tracks, opts)


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
