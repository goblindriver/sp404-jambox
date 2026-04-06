"""SD card status, scan, and Bank A sync API."""
import os, shutil, struct
from flask import Blueprint, jsonify, request, current_app

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
INTERNAL_BANKS = frozenset('AB')


def _get_card_intelligence():
    """Lazy import card_intelligence to avoid circular imports at module load."""
    mod = getattr(_get_card_intelligence, '_mod', None)
    if mod is not None:
        return mod
    import sys
    sys.path.insert(0, os.path.join(current_app.config['REPO_DIR'], 'scripts'))
    import card_intelligence
    _get_card_intelligence._mod = card_intelligence
    return card_intelligence


def _decode_padinfo(path):
    return _get_card_intelligence().decode_padinfo(path)


def _wav_identity(wav_path, chunk_size=65536):
    return _get_card_intelligence().wav_identity(wav_path, chunk_size)


def _wav_provenance(wav_path):
    return _get_card_intelligence().wav_provenance(wav_path)


@sdcard_bp.route('/sdcard/scan')
def scan_card():
    """Full scan of SD card contents with three-tier awareness.

    Returns per-pad: identity hash, full settings (user BPM, trim,
    reverse, lofi), provenance, and pattern stats when available.
    """
    sd_smpl = _sd_smpl_dir()
    if not os.path.isdir(sd_smpl):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400

    padinfo_path = os.path.join(sd_smpl, 'PAD_INFO.BIN')
    pad_settings = _decode_padinfo(padinfo_path)

    # Load pattern analytics if card_intelligence is available
    ptn_stats = {}
    try:
        import sys
        sys.path.insert(0, os.path.join(current_app.config['REPO_DIR'], 'scripts'))
        from card_intelligence import read_all_patterns
        sd_card = _sd_card()
        ptn_dir = os.path.join(sd_card, 'ROLAND', 'SP-404SX', 'PTN')
        if os.path.isdir(ptn_dir):
            ptn_stats = read_all_patterns(ptn_dir)
    except (ImportError, Exception):
        pass

    try:
        all_files = os.listdir(sd_smpl)
    except OSError:
        all_files = []

    wav_files = {f.upper() for f in all_files if f.upper().endswith('.WAV')}

    banks = {}
    adjustments = []
    for bank_letter in BANKS:
        tier = 'bed' if bank_letter == 'A' else ('toolkit' if bank_letter == 'B' else 'session')
        pads = []
        for pad_num in range(1, 13):
            fname = f"{bank_letter}{pad_num:07d}.WAV"
            wav_exists = fname in wav_files
            size = 0
            identity = None
            provenance = None
            mtime = None

            if wav_exists:
                fpath = os.path.join(sd_smpl, fname)
                try:
                    stat = os.stat(fpath)
                    size = stat.st_size
                    mtime = stat.st_mtime
                except OSError:
                    pass
                identity = _wav_identity(fpath)
                provenance = _wav_provenance(fpath)

            settings = pad_settings.get((bank_letter, pad_num), {})
            pad_entry = {
                'num': pad_num,
                'on_card': wav_exists,
                'size': size,
                'identity': identity,
                'provenance': provenance,
                'mtime': mtime,
                'loop': settings.get('loop', False),
                'gate': settings.get('gate', False),
                'reverse': settings.get('reverse', False),
                'lofi': settings.get('lofi', False),
                'bpm': settings.get('bpm', 0),
                'bpm_original': settings.get('bpm_original', 0),
                'bpm_user': settings.get('bpm_user', 0),
                'bpm_adjusted': settings.get('bpm_adjusted', False),
                'trimmed': settings.get('trimmed', False),
                'volume': settings.get('volume', 0),
                'padinfo_reliable': settings.get('padinfo_reliable', bank_letter != 'A'),
            }

            # Merge pattern stats for this pad
            pad_key = f"{bank_letter}{pad_num}"
            if pad_key in ptn_stats:
                pad_entry['pattern_stats'] = ptn_stats[pad_key]

            if settings.get('bpm_adjusted'):
                adjustments.append({
                    'bank': bank_letter, 'pad': pad_num,
                    'field': 'bpm',
                    'original': settings['bpm_original'],
                    'user': settings['bpm_user'],
                })

            pads.append(pad_entry)

        filled = sum(1 for p in pads if p['on_card'])
        banks[bank_letter] = {
            'pads': pads,
            'filled_count': filled,
            'tier': tier,
        }

    sd_card = _sd_card()
    ptn_dir = os.path.join(sd_card, 'ROLAND', 'SP-404SX', 'PTN')
    pattern_count = 0
    if os.path.isdir(ptn_dir):
        pattern_count = len([f for f in os.listdir(ptn_dir) if f.upper().endswith('.BIN')])

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
        'adjustments': adjustments,
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


@sdcard_bp.route('/sdcard/pull-intelligence', methods=['POST'])
def pull_intelligence():
    """Run full card intelligence pull: decode PAD_INFO, read patterns,
    scan WAV provenance, archive session, diff against last pull."""
    sd_smpl = _sd_smpl_dir()
    if not os.path.isdir(sd_smpl):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400

    import sys
    sys.path.insert(0, os.path.join(current_app.config['REPO_DIR'], 'scripts'))
    from card_intelligence import (
        pull_intelligence as _pull, save_session, load_latest_session,
        diff_sessions,
    )

    sd_card = _sd_card()
    previous = load_latest_session()
    session = _pull(sd_card=sd_card, sd_smpl=sd_smpl)
    if 'error' in session:
        return jsonify({'ok': False, 'error': session['error']}), 400

    path = save_session(session)
    changes = diff_sessions(session, previous)

    return jsonify({
        'ok': True,
        'session': session,
        'session_file': os.path.basename(path),
        'changes': changes,
    })


@sdcard_bp.route('/sdcard/reorganize', methods=['POST'])
def reorganize():
    """Move samples between pad slots on the SD card.

    Accepts a JSON body::

        {"moves": [{"from": {"bank": "D", "pad": 1}, "to": {"bank": "F", "pad": 3}}, ...]}

    Renames WAV files on card and regenerates PAD_INFO.BIN so that each
    sample's user settings (BPM, loop/gate, reverse, lofi) follow it to
    the new slot.
    """
    sd_smpl = _sd_smpl_dir()
    if not os.path.isdir(sd_smpl):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400

    data = request.get_json(silent=True) or {}
    moves = data.get('moves', [])
    if not moves:
        return jsonify({'ok': False, 'error': 'No moves specified'}), 400

    padinfo_path = os.path.join(sd_smpl, 'PAD_INFO.BIN')
    pad_settings = _decode_padinfo(padinfo_path)

    errors = []
    completed = []
    temp_suffix = '.REORG_TMP'

    # Phase 1: rename to temp names (avoid collisions on swaps)
    for move in moves:
        src = move.get('from', {})
        dst = move.get('to', {})
        src_bank, src_pad = src.get('bank', ''), src.get('pad', 0)
        dst_bank, dst_pad = dst.get('bank', ''), dst.get('pad', 0)

        src_fname = f"{src_bank.upper()}{int(src_pad):07d}.WAV"
        src_path = os.path.join(sd_smpl, src_fname)
        if not os.path.isfile(src_path):
            errors.append(f'{src_fname} not found on card')
            continue

        tmp_path = src_path + temp_suffix
        try:
            os.rename(src_path, tmp_path)
            completed.append({
                'src_fname': src_fname, 'tmp_path': tmp_path,
                'dst_bank': dst_bank.upper(), 'dst_pad': int(dst_pad),
                'src_settings_key': (src_bank.upper(), int(src_pad)),
            })
        except OSError as e:
            errors.append(f'Failed to move {src_fname}: {e}')

    # Phase 2: rename temp files to final destinations
    for item in completed:
        dst_fname = f"{item['dst_bank']}{item['dst_pad']:07d}.WAV"
        dst_path = os.path.join(sd_smpl, dst_fname)
        try:
            if os.path.exists(dst_path):
                os.remove(dst_path)
            os.rename(item['tmp_path'], dst_path)
            item['dst_fname'] = dst_fname
        except OSError as e:
            errors.append(f'Failed to place {dst_fname}: {e}')

    # Phase 3: rebuild PAD_INFO.BIN with settings following each sample
    try:
        with open(padinfo_path, 'rb') as f:
            padinfo_data = bytearray(f.read())

        for item in completed:
            src_key = item['src_settings_key']
            src_info = pad_settings.get(src_key, {})
            if not src_info:
                continue

            dst_idx = (ord(item['dst_bank']) - ord('A')) * 12 + (item['dst_pad'] - 1)
            offset = dst_idx * 32

            # Reconstruct the 32-byte record with the source pad's settings
            orig_start = src_info.get('trim_start', 512) or 512
            orig_end = src_info.get('trim_end', 512) or 512
            # For non-trimmed pads, keep original boundaries from source
            src_idx = (ord(src_key[0]) - ord('A')) * 12 + (src_key[1] - 1)
            src_offset = src_idx * 32
            src_record = struct.unpack('>IIII BBBBBBBB II',
                                       bytes(padinfo_data[src_offset:src_offset + 32]))

            # Write source record into destination slot
            padinfo_data[offset:offset + 32] = struct.pack(
                '>IIII BBBBBBBB II', *src_record)

        with open(padinfo_path, 'wb') as f:
            f.write(padinfo_data)
    except (OSError, struct.error) as e:
        errors.append(f'PAD_INFO rebuild failed: {e}')

    return jsonify({
        'ok': len(errors) == 0,
        'moved': len(completed),
        'errors': errors,
    })


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
