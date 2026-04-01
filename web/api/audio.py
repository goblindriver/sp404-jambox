"""Audio file serving for preview playback."""
import os
from flask import Blueprint, send_file, current_app, abort

audio_bp = Blueprint('audio', __name__)

LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")


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
