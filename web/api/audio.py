"""Audio file serving for preview playback and pad assignment."""
import os
import subprocess
import sys
from flask import Blueprint, send_file, current_app, abort, request, jsonify

audio_bp = Blueprint('audio', __name__)

LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
FFMPEG = "/opt/homebrew/bin/ffmpeg"


@audio_bp.route('/audio/preview/<bank>/<int:pad>')
def preview_pad(bank, pad):
    """Serve a pad's WAV file for browser playback."""
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
    full = os.path.join(LIBRARY, filepath)
    # Security: ensure path stays within library
    full = os.path.realpath(full)
    if not full.startswith(os.path.realpath(LIBRARY)):
        abort(403)
    if not os.path.isfile(full):
        abort(404)
    ext = os.path.splitext(full)[1].lower()
    mime = {'wav': 'audio/wav', '.aif': 'audio/aiff', '.aiff': 'audio/aiff', '.mp3': 'audio/mpeg'}.get(ext, 'audio/wav')
    return send_file(full, mimetype=mime)


def _convert_to_pad(source, bank, pad):
    """Convert source audio to SP-404 format and place in SMPL dir.

    Returns (target_path, error_string). error_string is None on success.
    """
    fname = f"{bank.upper()}{int(pad):07d}.WAV"
    smpl_dir = os.path.join(current_app.config['REPO_DIR'], 'sd-card-template', 'ROLAND', 'SP-404SX', 'SMPL')
    os.makedirs(smpl_dir, exist_ok=True)
    target = os.path.join(smpl_dir, fname)

    try:
        subprocess.run([
            FFMPEG, '-y', '-i', source,
            '-ar', '44100', '-ac', '1', '-sample_fmt', 's16',
            '-c:a', 'pcm_s16le', target,
        ], capture_output=True, text=True, timeout=30, check=True)
    except subprocess.CalledProcessError as e:
        return None, f'Convert failed: {e.stderr[:200]}'
    except FileNotFoundError:
        return None, 'ffmpeg not found'

    try:
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from wav_utils import inject_rlnd, trim_silence
        bank_idx = ord(bank.upper()) - ord('A')
        pad_idx = bank_idx * 12 + (int(pad) - 1)
        trim_silence(target)
        inject_rlnd(target, pad_idx)
    except Exception:
        pass  # Non-fatal: file still works without RLND

    return target, None


@audio_bp.route('/audio/assign', methods=['POST'])
def assign_to_pad():
    """Assign a library file to a pad: convert to SP-404 format and copy."""
    data = request.get_json()
    bank = data.get('bank', '').lower()
    pad = data.get('pad')
    library_path = data.get('library_path', '')

    if not bank or not pad or not library_path:
        return jsonify({'error': 'Missing bank, pad, or library_path'}), 400

    source = os.path.join(LIBRARY, library_path)
    source = os.path.realpath(source)
    if not source.startswith(os.path.realpath(LIBRARY)) or not os.path.isfile(source):
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
    bank = request.form.get('bank', '').lower()
    pad = request.form.get('pad')
    file = request.files.get('file')

    if not bank or not pad or not file:
        return jsonify({'error': 'Missing bank, pad, or file'}), 400

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
