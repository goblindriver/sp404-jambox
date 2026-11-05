"""Audio file serving for preview playback and pad assignment."""
import os
import sys
from flask import Blueprint, send_file, current_app, request, jsonify
from werkzeug.exceptions import HTTPException

from api._helpers import json_object_body as _json_object_body
from api._helpers import normalize_bank as _normalize_bank, normalize_pad as _normalize_pad

audio_bp = Blueprint('audio', __name__)

# (bank, pad, tag-store mtime, bank-config mtime) -> library path or None.
# A miss stays cached only until one of those files changes, so Fetch filling
# the tags (or a bank edit) is heard on the next drop.
_pad_hits = {}


def clear_pad_hits():
    _pad_hits.clear()


def _library_root():
    return current_app.config['SAMPLE_LIBRARY']


def _ffmpeg_bin():
    return current_app.config['FFMPEG_BIN']


def _stamp(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _library_file_path(full):
    """Real path of ``full`` if it is a file inside the sample library."""
    root = _library_root()
    if not root or not full:
        return None
    real_root = os.path.realpath(root)
    real = os.path.realpath(full)
    if real != real_root and not real.startswith(real_root + os.sep):
        return None
    if not os.path.isfile(real):
        return None
    return real


def _send_audio(path):
    ext = os.path.splitext(path)[1].lower()
    mime = {'.wav': 'audio/wav', '.aif': 'audio/aiff', '.aiff': 'audio/aiff',
            '.mp3': 'audio/mpeg', '.flac': 'audio/flac'}.get(ext, 'audio/wav')
    return send_file(path, mimetype=mime)


def _card_wav(bank, pad):
    """The WAV the SP-404A will fire: the card template, else the staging copy."""
    fname = f"{bank.upper()}{pad:07d}.WAV"
    smpl = os.path.join(current_app.config['REPO_DIR'], 'sd-card-template', 'ROLAND', 'SP-404SX', 'SMPL', fname)
    if os.path.exists(smpl):
        return smpl
    staging = os.path.join(current_app.config['REPO_DIR'], '_CARD_STAGING', fname)
    if os.path.exists(staging):
        return staging
    return None


def _pad_query(bank, pad):
    cfg_path = current_app.config.get('CONFIG_PATH') or os.path.join(
        current_app.config.get('REPO_DIR') or '', 'bank_config.yaml')
    try:
        from jambox_config import load_bank_config
        config = load_bank_config(cfg_path, strict=False)
    except Exception:
        return None, {}
    bank_config = config.get(f'bank_{bank}') or {}
    if not isinstance(bank_config, dict):
        return None, {}
    pads = bank_config.get('pads') or {}
    desc = pads.get(pad, pads.get(str(pad), ''))
    if not isinstance(desc, str):
        desc = '' if desc is None else str(desc)
    desc = desc.strip()
    return (desc or None), bank_config


def rank_pad_hit(query, bank_config, tag_db):
    """Top library file for one pad description. Does not write a WAV.

    A scorer that isn't importable, or that raises, is a miss rather than a 500.
    ``tag_db`` is passed in so this does not save the on-disk score cache.
    """
    try:
        import fetch_samples
    except Exception:
        return None
    try:
        matches = fetch_samples.rank_library_matches(
            query,
            bank_config=bank_config,
            tag_db=tag_db if isinstance(tag_db, dict) else {},
            used_files=set(),
            limit=1,
            min_score=0,
            cache_entries={},
        )
    except Exception:
        return None
    if not matches:
        return None
    return matches[0].get('path')


def _load_tags(tags_path):
    if not tags_path:
        return {}
    try:
        from jambox_config import load_tag_db
        db = load_tag_db(tags_path)
    except Exception:
        return {}
    return db if isinstance(db, dict) else {}


def _store_stamps(tags_path, cfg_path):
    """Mtimes of the tag store (json and its sqlite) and the bank config.

    Taken as a tuple so a write to either file forgets a cached miss.
    """
    sibling = os.path.splitext(tags_path)[0] + ".sqlite" if tags_path else ""
    return (_stamp(tags_path), _stamp(sibling), _stamp(cfg_path))


def library_hit_for_pad(bank, pad):
    """Cached top library hit for this pad, or None.

    The key includes the tag store and bank config mtimes, so a miss is
    forgotten when either file changes. The stamp is taken again after the
    tag load, because the first read can migrate a json store to sqlite.
    """
    tags_path = current_app.config.get('TAGS_FILE') or ''
    cfg_path = current_app.config.get('CONFIG_PATH') or os.path.join(
        current_app.config.get('REPO_DIR') or '', 'bank_config.yaml')
    key = (bank, int(pad), _store_stamps(tags_path, cfg_path))
    if key in _pad_hits:
        return _pad_hits[key]
    query, bank_config = _pad_query(bank, pad)
    tags = _load_tags(tags_path) if query else {}
    key = (bank, int(pad), _store_stamps(tags_path, cfg_path))
    if key in _pad_hits:
        return _pad_hits[key]
    hit = rank_pad_hit(query, bank_config, tags) if query else None
    for old in [k for k in _pad_hits if k[0] == bank and k[1] == int(pad) and k != key]:
        _pad_hits.pop(old, None)
    _pad_hits[key] = hit
    return hit


@audio_bp.route('/audio/preview/<bank>/<int:pad>')
def preview_pad(bank, pad):
    """Serve what this pad will play.

    The card WAV first (template, then staging), so rehearsal matches the rig
    once Fetch + Export has run. Otherwise the top library hit for the pad's
    description. Otherwise 404 ``no sample``.
    """
    try:
        bank = _normalize_bank(bank)
        pad = _normalize_pad(pad)
    except ValueError:
        return jsonify({'error': 'Invalid bank or pad'}), 404
    card = _card_wav(bank, pad)
    if card:
        return send_file(card, mimetype='audio/wav')
    hit = _library_file_path(library_hit_for_pad(bank, pad))
    if hit:
        return _send_audio(hit)
    return jsonify({'ok': False, 'error': 'no sample', 'bank': bank, 'pad': pad}), 404


@audio_bp.route('/audio/library/<path:filepath>')
def preview_library(filepath):
    """Serve a library file for preview. Path is relative to library root."""
    library_root = _library_root()
    full = os.path.join(library_root, filepath)
    real = os.path.realpath(full)
    real_root = os.path.realpath(library_root) if library_root else ''
    if not real_root or (real != real_root and not real.startswith(real_root + os.sep)):
        return jsonify({'error': 'Access denied'}), 403
    sent = _send_audio(real) if os.path.isfile(real) else None
    if sent is None:
        return jsonify({'error': 'File not found'}), 404
    return sent


def _convert_to_pad(source, bank, pad):
    """Convert source audio to SP-404 format and place in SMPL dir.

    Returns (target_path, error_string). error_string is None on success.
    """
    fname = f"{bank.upper()}{int(pad):07d}.WAV"
    smpl_dir = os.path.join(current_app.config['REPO_DIR'], 'sd-card-template', 'ROLAND', 'SP-404SX', 'SMPL')
    os.makedirs(smpl_dir, exist_ok=True)
    target = os.path.join(smpl_dir, fname)

    scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    try:
        from wav_utils import convert_and_tag
        if not convert_and_tag(source, target, bank.upper(), int(pad)):
            return None, 'Conversion failed (convert_and_tag returned False)'
    except FileNotFoundError:
        return None, 'ffmpeg not found'
    except Exception as e:
        return None, 'Convert failed: %s' % str(e)[:200]

    return target, None


@audio_bp.route('/audio/waveform/<bank>/<int:pad>')
def waveform_data(bank, pad):
    """Return waveform peak data for rendering on the pad grid.

    Returns JSON with 'peaks' (array of 0.0-1.0 values) and 'duration'.
    Uses raw PCM parsing for SP-404 WAVs (16-bit mono).
    """
    try:
        bank = _normalize_bank(bank)
        pad = _normalize_pad(pad)
    except ValueError:
        return jsonify({'error': 'Invalid bank or pad'}), 404
    import struct
    fname = f"{bank.upper()}{pad:07d}.WAV"
    smpl = os.path.join(current_app.config['REPO_DIR'], 'sd-card-template', 'ROLAND', 'SP-404SX', 'SMPL', fname)
    if not os.path.exists(smpl):
        staging = os.path.join(current_app.config['REPO_DIR'], '_CARD_STAGING', fname)
        if os.path.exists(staging):
            smpl = staging
        else:
            return jsonify({'error': 'Pad audio not found'}), 404

    try:
        with open(smpl, 'rb') as f:
            data = f.read()

        # Find 'data' chunk in WAV — skip RLND and other chunks
        data_offset = data.find(b'data')
        if data_offset < 0:
            return jsonify({'error': 'Invalid WAV file (no data chunk)'}), 404
        data_size = struct.unpack_from('<I', data, data_offset + 4)[0]
        pcm_start = data_offset + 8
        pcm_data = data[pcm_start:pcm_start + data_size]

        # Parse 16-bit signed PCM samples
        num_samples = len(pcm_data) // 2
        if num_samples == 0:
            return jsonify({'peaks': [], 'duration': 0})

        samples = struct.unpack(f'<{num_samples}h', pcm_data[:num_samples * 2])

        # Downsample to ~80 peaks for display
        num_peaks = 80
        chunk_size = max(1, num_samples // num_peaks)
        peaks = []
        max_val = 32768.0
        for i in range(0, num_samples, chunk_size):
            chunk = samples[i:i + chunk_size]
            if chunk:
                peak = max(abs(s) for s in chunk) / max_val
                peaks.append(round(min(peak, 1.0), 3))

        duration = num_samples / 44100.0
        return jsonify({'peaks': peaks, 'duration': round(duration, 2)})

    except HTTPException:
        raise
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@audio_bp.route('/audio/assign', methods=['POST'])
def assign_to_pad():
    """Assign a library file to a pad: convert to SP-404 format and copy."""
    try:
        data = _json_object_body()
        bank = _normalize_bank(data.get('bank'))
        pad = _normalize_pad(data.get('pad'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    library_path = data.get('library_path', '')
    if not isinstance(library_path, str) or not library_path.strip():
        return jsonify({'error': 'library_path is required'}), 400
    library_path = library_path.strip()

    library_root = _library_root()
    source = os.path.join(library_root, library_path)
    source = os.path.realpath(source)
    real_root = os.path.realpath(library_root)
    if not (source.startswith(real_root + os.sep) or source == real_root) or not os.path.isfile(source):
        return jsonify({'error': 'File not found'}), 404

    target, err = _convert_to_pad(source, bank, pad)
    if err:
        return jsonify({'error': err}), 500

    return jsonify({
        'ok': True,
        'file': os.path.basename(target),
        'size': os.path.getsize(target),
        'message': f'Assigned to {bank.upper()} Pad {pad}',
    })


ALLOWED_AUDIO_EXTS = {'.wav', '.aif', '.aiff', '.mp3', '.flac', '.ogg', '.m4a'}


@audio_bp.route('/audio/upload', methods=['POST'])
def upload_to_pad():
    """Upload an audio file from the user's computer and assign to a pad."""
    try:
        bank = _normalize_bank(request.form.get('bank'))
        pad = _normalize_pad(request.form.get('pad'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    file = request.files.get('file')

    if not file:
        return jsonify({'error': 'Missing file'}), 400
    if not file.filename:
        return jsonify({'error': 'Missing filename'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_AUDIO_EXTS:
        return jsonify({'error': f'Unsupported format: {ext}'}), 400

    # Save upload to temp file
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        file.save(tmp.name)
        tmp.close()

        target, err = _convert_to_pad(tmp.name, bank, pad)
        if err:
            return jsonify({'error': err}), 500

        return jsonify({
            'ok': True,
            'file': os.path.basename(target),
            'size': os.path.getsize(target),
            'source': file.filename,
            'message': f'Assigned {file.filename} to {bank.upper()} Pad {pad}',
        })
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
