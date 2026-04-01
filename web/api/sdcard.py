"""SD card status and Bank A sync API."""
import os, shutil
from flask import Blueprint, jsonify, current_app

sdcard_bp = Blueprint('sdcard', __name__)

SD_CARD = "/Volumes/SP-404SX"
SD_SMPL = os.path.join(SD_CARD, "ROLAND", "SP-404SX", "SMPL")
LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
GOLD_DIR = os.path.join(LIBRARY, "_GOLD", "Bank-A")


@sdcard_bp.route('/sdcard/status')
def status():
    mounted = os.path.isdir(SD_SMPL)
    info = {'mounted': mounted}
    if mounted:
        try:
            usage = shutil.disk_usage(SD_CARD)
            info['free_mb'] = round(usage.free / (1024 * 1024))
            info['total_mb'] = round(usage.total / (1024 * 1024))
        except Exception:
            pass
        # Count samples on card
        try:
            wavs = [f for f in os.listdir(SD_SMPL) if f.endswith('.WAV')]
            info['sample_count'] = len(wavs)
            bank_a = [f for f in wavs if f.startswith('A')]
            info['bank_a_count'] = len(bank_a)
        except Exception:
            pass
    return jsonify(info)


@sdcard_bp.route('/sdcard/pull-bank-a', methods=['POST'])
def pull_bank_a():
    if not os.path.isdir(SD_SMPL):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400

    import sys
    sys.path.insert(0, os.path.join(current_app.config['REPO_DIR'], 'scripts'))
    from sync_bank_a import pull_bank_a as _pull
    saved = _pull()
    return jsonify({'ok': True, 'saved': saved})


@sdcard_bp.route('/gold/sessions')
def gold_sessions():
    if not os.path.isdir(GOLD_DIR):
        return jsonify({'sessions': []})
    sessions = []
    for d in sorted(os.listdir(GOLD_DIR)):
        if not d.startswith('session-'):
            continue
        path = os.path.join(GOLD_DIR, d)
        files = [f for f in os.listdir(path) if f.endswith('.WAV')]
        sessions.append({'name': d, 'count': len(files)})
    return jsonify({'sessions': sessions})
