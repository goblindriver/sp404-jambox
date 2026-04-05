"""SD card status, scan, and Bank A sync API."""
import os, shutil, struct
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
            wavs = [f for f in os.listdir(sd_smpl) if f.upper().endswith('.WAV')]
            info['sample_count'] = len(wavs)
            bank_a = [f for f in wavs if f.startswith('A')]
            info['bank_a_count'] = len(bank_a)
        except Exception:
            pass
    return jsonify(info)


BANKS = 'ABCDEFGHIJ'


def _decode_padinfo(path):
    """Decode PAD_INFO.BIN into per-pad metadata.

    Returns dict: {(bank_letter, pad_num): {volume, loop, gate, reverse, bpm, has_sample}}
    """
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except (OSError, IOError):
        return {}

    if len(data) < 3840:
        return {}

    result = {}
    for bank_idx, bank_letter in enumerate(BANKS):
        for pad_num in range(1, 13):
            offset = (bank_idx * 12 + (pad_num - 1)) * 32
            record = data[offset:offset + 32]
            if len(record) < 32:
                continue

            # Big-endian: 4 uint32 (sample boundaries), 8 uint8 (settings), 2 uint32 (tempos)
            fields = struct.unpack('>IIII BBBBBBBB II', record)
            sample_start = fields[0]
            sample_end = fields[1]
            volume = fields[4]
            lofi = bool(fields[5])
            loop = bool(fields[6])
            gate = bool(fields[7])
            reverse = bool(fields[8])
            channels = fields[10]
            tempo_mode = fields[11]
            bpm_raw = fields[12]
            bpm = round(bpm_raw / 10, 1) if bpm_raw else 0

            has_sample = sample_end > sample_start

            result[(bank_letter, pad_num)] = {
                'volume': volume,
                'lofi': lofi,
                'loop': loop,
                'gate': gate,
                'reverse': reverse,
                'channels': channels,
                'tempo_mode': tempo_mode,
                'bpm': bpm,
                'has_sample': has_sample,
            }

    return result


@sdcard_bp.route('/sdcard/scan')
def scan_card():
    """Full scan of SD card contents: WAVs per bank/pad, PAD_INFO settings, patterns."""
    sd_smpl = _sd_smpl_dir()
    if not os.path.isdir(sd_smpl):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400

    # Decode PAD_INFO.BIN from card
    padinfo_path = os.path.join(sd_smpl, 'PAD_INFO.BIN')
    pad_settings = _decode_padinfo(padinfo_path)

    # Scan WAV files on card
    try:
        all_files = os.listdir(sd_smpl)
    except OSError:
        all_files = []

    wav_files = {f.upper() for f in all_files if f.upper().endswith('.WAV')}

    banks = {}
    for bank_letter in BANKS:
        pads = []
        for pad_num in range(1, 13):
            fname = f"{bank_letter}{pad_num:07d}.WAV"
            wav_exists = fname in wav_files
            size = 0
            if wav_exists:
                try:
                    size = os.path.getsize(os.path.join(sd_smpl, fname))
                except OSError:
                    pass

            settings = pad_settings.get((bank_letter, pad_num), {})
            pads.append({
                'num': pad_num,
                'on_card': wav_exists,
                'size': size,
                'loop': settings.get('loop', False),
                'gate': settings.get('gate', False),
                'reverse': settings.get('reverse', False),
                'bpm': settings.get('bpm', 0),
                'volume': settings.get('volume', 0),
            })

        filled = sum(1 for p in pads if p['on_card'])
        banks[bank_letter] = {
            'pads': pads,
            'filled_count': filled,
        }

    # Count pattern files
    sd_card = _sd_card()
    ptn_dir = os.path.join(sd_card, 'ROLAND', 'SP-404SX', 'PTN')
    pattern_count = 0
    if os.path.isdir(ptn_dir):
        pattern_count = len([f for f in os.listdir(ptn_dir) if f.upper().endswith('.BIN')])

    # Disk usage
    try:
        usage = shutil.disk_usage(sd_card)
        free_mb = round(usage.free / (1024 * 1024))
        total_mb = round(usage.total / (1024 * 1024))
    except Exception:
        free_mb = total_mb = 0

    total_samples = sum(b['filled_count'] for b in banks.values())

    return jsonify({
        'ok': True,
        'banks': banks,
        'total_samples': total_samples,
        'pattern_count': pattern_count,
        'free_mb': free_mb,
        'total_mb': total_mb,
    })


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
