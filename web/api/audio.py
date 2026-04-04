"""Audio file serving for preview playback and pad assignment."""
import os
import subprocess
import sys
from flask import Blueprint, send_file, current_app, abort, request, jsonify
from werkzeug.exceptions import HTTPException

audio_bp = Blueprint('audio', __name__)


def _library_root():
    return current_app.config['SAMPLE_LIBRARY']


def _ffmpeg_bin():
    return current_app.config['FFMPEG_BIN']


def _json_object_body():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        raise ValueError('Request body must be a JSON object')
    return data


def _normalize_bank(value):
    bank = str(value or '').strip().lower()
    if len(bank) != 1 or bank < 'a' or bank > 'j':
        raise ValueError('bank must be a single letter from A to J')
    return bank


def _normalize_pad(value):
    try:
        pad = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('pad must be an integer') from exc
    if pad < 1 or pad > 12:
        raise ValueError('pad must be between 1 and 12')
    return pad


@audio_bp.route('/audio/preview/<bank>/<int:pad>')
def preview_pad(bank, pad):
    """Serve a pad's WAV file for browser playback."""
    try:
        bank = _normalize_bank(bank)
        pad = _normalize_pad(pad)
    except ValueError:
        abort(404)
    fname = f"{bank.upper()}{pad:07d}.WAV"
    smpl = os.path.join(current_app.config['REPO_DIR'], 'sd-card-template', 'ROLAND', 'SP-404SX', 'SMPL', fname)
    if os.path.exists(smpl):
        return send_file(smpl, mimetype='audio/wav')

    staging = os.path.join(current_app.config['REPO_DIR'], '_CARD_STAGING', fname)
    if os.path.exists(staging):
        return send_file(staging, mimetype='audio/wav')

    abort(404)


@audio_bp.route('/audio/library/<path:filepath>')
def preview_library(filepath):
    """Serve a library file for preview. Path is relative to library root."""
    library_root = _library_root()
    full = os.path.join(library_root, filepath)
    # Security: ensure path stays within library
    full = os.path.realpath(full)
    if not full.startswith(os.path.realpath(library_root)):
        abort(403)
    if not os.path.isfile(full):
        abort(404)
    ext = os.path.splitext(full)[1].lower()
    mime = {'.wav': 'audio/wav', '.aif': 'audio/aiff', '.aiff': 'audio/aiff',
            '.mp3': 'audio/mpeg', '.flac': 'audio/flac'}.get(ext, 'audio/wav')
    return send_file(full, mimetype=mime)


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
        abort(404)
    import struct
    fname = f"{bank.upper()}{pad:07d}.WAV"
    smpl = os.path.join(current_app.config['REPO_DIR'], 'sd-card-template', 'ROLAND', 'SP-404SX', 'SMPL', fname)
    if not os.path.exists(smpl):
        staging = os.path.join(current_app.config['REPO_DIR'], '_CARD_STAGING', fname)
        if os.path.exists(staging):
            smpl = staging
        else:
            abort(404)

    try:
        with open(smpl, 'rb') as f:
            data = f.read()

        # Find 'data' chunk in WAV — skip RLND and other chunks
        data_offset = data.find(b'data')
        if data_offset < 0:
            abort(404)
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
    if not source.startswith(os.path.realpath(library_root)) or not os.path.isfile(source):
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
