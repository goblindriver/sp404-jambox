"""SD card status and Bank A sync API."""
import os, shutil
from flask import Blueprint, jsonify, current_app

sdcard_bp = Blueprint('sdcard', __name__)


def _sd_card():
    return current_app.config['SD_CARD']


def _sd_smpl_dir():
    return current_app.config['SD_SMPL_DIR']


def _gold_dir():
    return current_app.config['GOLD_BANK_A_DIR']


@sdcard_bp.route('/sdcard/status')
def status():
    sd_card = _sd_card()
    sd_smpl = _sd_smpl_dir()
    mounted = os.path.isdir(sd_smpl)
    info = {'mounted': mounted}
    if mounted:
        try:
            usage = shutil.disk_usage(sd_card)
            info['free_mb'] = round(usage.free / (1024 * 1024))
            info['total_mb'] = round(usage.total / (1024 * 1024))
        except Exception:
            pass
        # Count samples on card
        try:
            wavs = [f for f in os.listdir(sd_smpl) if f.endswith('.WAV')]
            info['sample_count'] = len(wavs)
            bank_a = [f for f in wavs if f.startswith('A')]
            info['bank_a_count'] = len(bank_a)
        except Exception:
            pass
    return jsonify(info)


@sdcard_bp.route('/sdcard/pull-bank-a', methods=['POST'])
def pull_bank_a():
    if not os.path.isdir(_sd_smpl_dir()):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400

    import sys
    sys.path.insert(0, os.path.join(current_app.config['REPO_DIR'], 'scripts'))
    from sync_bank_a import pull_bank_a as _pull
    saved = _pull()
    return jsonify({'ok': True, 'saved': saved})


@sdcard_bp.route('/gold/sessions')
def gold_sessions():
    gold_dir = _gold_dir()
    if not os.path.isdir(gold_dir):
        return jsonify({'sessions': []})
    sessions = []
    try:
        entries = sorted(os.listdir(gold_dir))
    except OSError:
        return jsonify({'sessions': []})
    for d in entries:
        if not d.startswith('session-'):
            continue
        path = os.path.join(gold_dir, d)
        if not os.path.isdir(path):
            continue
        try:
            files = [f for f in os.listdir(path) if f.endswith('.WAV')]
        except OSError:
            continue
        sessions.append({'name': d, 'count': len(files)})
    return jsonify({'sessions': sessions})
