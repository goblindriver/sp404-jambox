"""SD card status, scan, and Bank A sync API."""
import os, shutil, struct, subprocess
from flask import Blueprint, jsonify, request, current_app
from wav_utils import wav_identity as _wav_identity

from api._helpers import normalize_bank, normalize_pad

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

# Roland SP-404 uses a fixed default date when it creates files on-device
# (resampling, recording). The hardware clock is typically never set.
ROLAND_DEFAULT_YEAR = 2009


def _decode_padinfo(path):
    """Decode PAD_INFO.BIN into per-pad metadata.

    Returns dict keyed by ``(bank_letter, pad_num)`` with full settings
    including user-adjusted tempo and sample trim boundaries.

    Bank A entries are decoded but flagged ``padinfo_reliable: False``
    because the SP-404A stores internal-memory pad state separately.
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

            fields = struct.unpack('>IIII BBBBBBBB II', record)
            orig_start, orig_end = fields[0], fields[1]
            user_start, user_end = fields[2], fields[3]
            volume = fields[4]
            lofi = bool(fields[5])
            loop = bool(fields[6])
            gate = bool(fields[7])
            reverse = bool(fields[8])
            channels = fields[10]
            tempo_mode = fields[11]
            orig_tempo_raw, user_tempo_raw = fields[12], fields[13]
            bpm_original = round(orig_tempo_raw / 10, 1) if orig_tempo_raw else 0
            bpm_user = round(user_tempo_raw / 10, 1) if user_tempo_raw else 0

            has_sample = orig_end > orig_start
            bpm_adjusted = tempo_mode == 2 and bpm_original != bpm_user
            trimmed = (user_start != orig_start or user_end != orig_end) and has_sample

            entry = {
                'volume': volume,
                'lofi': lofi,
                'loop': loop,
                'gate': gate,
                'reverse': reverse,
                'channels': channels,
                'tempo_mode': tempo_mode,
                'bpm_original': bpm_original,
                'bpm_user': bpm_user,
                'bpm': bpm_user if bpm_adjusted else bpm_original,
                'bpm_adjusted': bpm_adjusted,
                'has_sample': has_sample,
                'trimmed': trimmed,
                'trim_start': user_start if trimmed else None,
                'trim_end': user_end if trimmed else None,
                'internal_memory': bank_letter in INTERNAL_BANKS,
                'padinfo_reliable': bank_letter not in INTERNAL_BANKS or bank_letter == 'B',
            }
            result[(bank_letter, pad_num)] = entry

    return result


def decode_padinfo_diffs(path):
    """Return only pads where the user changed settings on the hardware.

    Skips Bank A (unreliable PAD_INFO for internal memory).
    A pad counts as "modified" if any of: BPM adjusted, sample trimmed,
    reverse enabled, lofi enabled, or volume != 127.
    """
    all_pads = _decode_padinfo(path)
    diffs = {}
    for (bank, pad), info in all_pads.items():
        if bank == 'A':
            continue
        modifications = []
        if info['bpm_adjusted']:
            modifications.append({
                'field': 'bpm', 'original': info['bpm_original'],
                'user': info['bpm_user'],
            })
        if info['trimmed']:
            modifications.append({
                'field': 'trim', 'trim_start': info['trim_start'],
                'trim_end': info['trim_end'],
            })
        if info['reverse']:
            modifications.append({'field': 'reverse'})
        if info['lofi']:
            modifications.append({'field': 'lofi'})
        if info['volume'] != 127:
            modifications.append({
                'field': 'volume', 'value': info['volume'],
            })
        if modifications:
            diffs[(bank, pad)] = {
                'settings': info,
                'modifications': modifications,
            }
    return diffs


def _wav_provenance(wav_path):
    """Classify how a WAV ended up on the card.

    Returns one of: ``device-created``, ``jambox``, ``user-loaded``.
    """
    import datetime
    has_rlnd = False
    try:
        with open(wav_path, 'rb') as f:
            header = f.read(12)
            if len(header) < 12:
                return 'user-loaded'
            while True:
                chunk_hdr = f.read(8)
                if len(chunk_hdr) < 8:
                    break
                cid = chunk_hdr[:4]
                csz = struct.unpack('<I', chunk_hdr[4:])[0]
                if cid == b'RLND':
                    has_rlnd = True
                    break
                f.read(csz + (csz % 2))
    except (OSError, struct.error):
        pass

    if has_rlnd:
        return 'jambox'

    try:
        mtime = os.path.getmtime(wav_path)
        dt = datetime.datetime.fromtimestamp(mtime)
        if dt.year <= ROLAND_DEFAULT_YEAR:
            return 'device-created'
    except OSError:
        pass

    return 'user-loaded'


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
    scan WAV provenance, archive session, diff against last pull.
    Also archives Bank A WAVs from the card into the gold library (same as pull-bank-a)."""
    sd_smpl = _sd_smpl_dir()
    if not os.path.isdir(sd_smpl):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400

    import sys
    sys.path.insert(0, os.path.join(current_app.config['REPO_DIR'], 'scripts'))
    from card_intelligence import (
        pull_intelligence as _pull, save_session, load_latest_session,
        diff_sessions,
    )
    from sync_bank_a import pull_bank_a as _pull_bank_a

    sd_card = _sd_card()
    previous = load_latest_session()
    session = _pull(sd_card=sd_card, sd_smpl=sd_smpl)
    if 'error' in session:
        return jsonify({'ok': False, 'error': session['error']}), 400

    path = save_session(session)
    changes = diff_sessions(session, previous)
    gold_saved = _pull_bank_a()

    return jsonify({
        'ok': True,
        'session': session,
        'session_file': os.path.basename(path),
        'changes': changes,
        'gold_saved': gold_saved,
    })


def _slot_fname(slot):
    bank, pad = slot
    return f"{bank}{pad:07d}.WAV"


def _slot_offset(slot):
    bank, pad = slot
    return ((ord(bank) - ord('A')) * 12 + (pad - 1)) * 32


def _plan_reorganize(moves, sd_smpl):
    """Validate a move list and turn it into a full placement {target: origin}.

    Raises ValueError (nothing has been touched yet) for malformed moves, a
    pad named twice, or a source pad with no sample. A destination already
    holding a sample that isn't itself moving is never overwritten: that
    sample moves into a slot the moves vacate (a single move becomes a swap).
    """
    if not isinstance(moves, list) or not moves:
        raise ValueError('No moves specified')
    pairs = []
    for move in moves:
        if not isinstance(move, dict):
            raise ValueError('Each move needs "from" and "to"')
        src, dst = move.get('from') or {}, move.get('to') or {}
        if not isinstance(src, dict) or not isinstance(dst, dict):
            raise ValueError('Each move needs "from" and "to"')
        source = (normalize_bank(src.get('bank')).upper(), normalize_pad(src.get('pad')))
        target = (normalize_bank(dst.get('bank')).upper(), normalize_pad(dst.get('pad')))
        if source != target:
            pairs.append((source, target))

    sources = [s for s, _ in pairs]
    targets = [t for _, t in pairs]
    if len(set(sources)) != len(sources) or len(set(targets)) != len(targets):
        raise ValueError('A pad appears more than once in the moves')
    for source in sources:
        if not os.path.isfile(os.path.join(sd_smpl, _slot_fname(source))):
            raise ValueError(f'{_slot_fname(source)} not found on card')

    placement = {target: source for source, target in pairs}
    vacated = [s for s in sources if s not in placement]
    for source, target in pairs:
        occupied = os.path.isfile(os.path.join(sd_smpl, _slot_fname(target)))
        if target in sources or not occupied:
            continue
        home = source if source in vacated else vacated[0]
        vacated.remove(home)
        placement[home] = target
    return placement, vacated


def _rebuild_padinfo(padinfo_path, placement, vacated):
    """Move each sample's 32-byte PAD_INFO record with it (from the original bytes)."""
    from gen_padinfo import encode_pad

    with open(padinfo_path, 'rb') as f:
        original = f.read()
    if len(original) < 3840:
        raise ValueError('PAD_INFO.BIN is shorter than 3840 bytes')
    updated = bytearray(original)
    for target, origin in placement.items():
        src = _slot_offset(origin)
        dst = _slot_offset(target)
        updated[dst:dst + 32] = original[src:src + 32]
    for slot in vacated:
        off = _slot_offset(slot)
        updated[off:off + 32] = encode_pad()
    tmp = padinfo_path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(updated)
    os.replace(tmp, padinfo_path)


@sdcard_bp.route('/sdcard/reorganize', methods=['POST'])
def reorganize():
    """Move samples between pad slots on the SD card.

    Accepts a JSON body::

        {"moves": [{"from": {"bank": "D", "pad": 1}, "to": {"bank": "F", "pad": 3}}, ...]}

    Every move is validated before anything on the card changes. Moving onto
    an occupied pad swaps the two samples (nothing is deleted). Renames run
    through temp names and roll back on failure, and PAD_INFO.BIN is rebuilt
    from its original bytes so each sample's settings (BPM, loop/gate,
    reverse, lofi, trim) follow it.
    """
    sd_smpl = _sd_smpl_dir()
    if not os.path.isdir(sd_smpl):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400

    data = request.get_json(silent=True) or {}
    try:
        placement, vacated = _plan_reorganize(data.get('moves'), sd_smpl)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc), 'errors': [str(exc)]}), 400

    done = []  # (from_path, to_path) renames already applied, for rollback
    try:
        temps = {}
        for origin in placement.values():
            path = os.path.join(sd_smpl, _slot_fname(origin))
            tmp = path + '.REORG_TMP'
            os.rename(path, tmp)
            done.append((path, tmp))
            temps[origin] = tmp
        for target, origin in placement.items():
            dest = os.path.join(sd_smpl, _slot_fname(target))
            os.rename(temps[origin], dest)  # never overwrites: every occupied target was moved away
            done.append((temps[origin], dest))
    except OSError as exc:
        for src, dest in reversed(done):
            try:
                os.rename(dest, src)
            except OSError:
                pass
        message = f'Reorganize failed, card left unchanged: {exc}'
        return jsonify({'ok': False, 'error': message, 'errors': [message]}), 500

    errors = []
    padinfo_path = os.path.join(sd_smpl, 'PAD_INFO.BIN')
    if os.path.exists(padinfo_path):
        try:
            _rebuild_padinfo(padinfo_path, placement, vacated)
        except (OSError, ValueError) as exc:
            errors.append(f'PAD_INFO rebuild failed: {exc}')

    return jsonify({
        'ok': not errors,
        'moved': len(placement),
        'placement': {_slot_fname(t): _slot_fname(o) for t, o in placement.items()},
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


@sdcard_bp.route('/sdcard/eject', methods=['POST'])
def eject_card():
    """Eject the SD card volume (macOS only)."""
    sd_card = _sd_card()
    if not os.path.isdir(sd_card):
        return jsonify({'ok': False, 'error': 'SD card is not mounted'}), 400

    try:
        result = subprocess.run(
            ['diskutil', 'eject', sd_card],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return jsonify({'ok': True, 'message': f'Ejected {sd_card}'})
        return jsonify({
            'ok': False,
            'error': result.stderr.strip() or result.stdout.strip() or 'Eject failed',
        }), 500
    except FileNotFoundError:
        return jsonify({'ok': False, 'error': 'diskutil not found (macOS only)'}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'Eject timed out'}), 500
    except OSError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
