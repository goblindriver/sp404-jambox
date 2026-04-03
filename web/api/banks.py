"""Bank and pad configuration API."""
import os, yaml
from flask import Blueprint, jsonify, request, current_app

banks_bp = Blueprint('banks', __name__)


def _config_path():
    return os.path.join(current_app.config['REPO_DIR'], 'bank_config.yaml')


def _smpl_dir():
    return os.path.join(current_app.config['REPO_DIR'], 'sd-card-template', 'ROLAND', 'SP-404SX', 'SMPL')


def _load_config():
    try:
        with open(_config_path()) as f:
            payload = yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_object_body():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        raise ValueError('Request body must be a JSON object')
    return data


def _normalize_letter(letter):
    letter = str(letter or '').strip().lower()
    if len(letter) != 1 or letter < 'a' or letter > 'j':
        raise ValueError('Bank not found')
    return letter


def _normalize_pad_num(num):
    try:
        value = int(num)
    except (TypeError, ValueError) as exc:
        raise ValueError('Pad must be between 1 and 12') from exc
    if value < 1 or value > 12:
        raise ValueError('Pad must be between 1 and 12')
    return value


def _get_pad_status(bank_letter, pad_num):
    """Check if a WAV exists for this pad."""
    fname = f"{bank_letter.upper()}{pad_num:07d}.WAV"
    smpl = os.path.join(_smpl_dir(), fname)
    if os.path.exists(smpl):
        return 'filled', os.path.getsize(smpl)
    staging = os.path.join(current_app.config['REPO_DIR'], '_CARD_STAGING', fname)
    if os.path.exists(staging):
        return 'staged', os.path.getsize(staging)
    return 'empty', 0


BANK_COLORS = {
    'a': '#FFD700', 'b': '#9B59B6', 'c': '#D4A0A0', 'd': '#8B0000',
    'e': '#39FF14', 'f': '#FF1493', 'g': '#FF8C00', 'h': '#00BCD4',
    'i': '#87CEEB', 'j': '#CCCCCC',
}


@banks_bp.route('/banks')
def get_banks():
    config = _load_config()
    banks = []
    for key, bank_config in config.items():
        if not key.startswith('bank_') or not bank_config:
            continue
        letter = key.split('_')[1]
        pads = bank_config.get('pads', {})
        pad_list = []
        for i in range(1, 13):
            desc = pads.get(i, pads.get(str(i), ''))
            status, size = _get_pad_status(letter, i)
            pad_list.append({
                'num': i,
                'description': desc or '',
                'status': status,
                'size': size,
            })
        banks.append({
            'letter': letter,
            'name': bank_config.get('name', ''),
            'bpm': bank_config.get('bpm'),
            'key': bank_config.get('key'),
            'notes': bank_config.get('notes', ''),
            'color': BANK_COLORS.get(letter, '#666'),
            'pads': pad_list,
        })
    return jsonify(banks)


@banks_bp.route('/banks/<letter>')
def get_bank(letter):
    try:
        letter = _normalize_letter(letter)
    except ValueError:
        return jsonify({'error': 'Bank not found'}), 404
    config = _load_config()
    bank_config = config.get(f'bank_{letter}')
    if not bank_config:
        return jsonify({'error': 'Bank not found'}), 404

    pads = bank_config.get('pads', {})
    pad_list = []
    for i in range(1, 13):
        desc = pads.get(i, pads.get(str(i), ''))
        status, size = _get_pad_status(letter, i)
        pad_list.append({
            'num': i,
            'description': desc or '',
            'status': status,
            'size': size,
        })
    return jsonify({
        'letter': letter,
        'name': bank_config.get('name', ''),
        'bpm': bank_config.get('bpm'),
        'key': bank_config.get('key'),
        'notes': bank_config.get('notes', ''),
        'color': BANK_COLORS.get(letter, '#666'),
        'pads': pad_list,
    })


@banks_bp.route('/banks/<letter>', methods=['PUT'])
def update_bank(letter):
    try:
        letter = _normalize_letter(letter)
        data = _json_object_body()
    except ValueError as e:
        status = 404 if str(e) == 'Bank not found' else 400
        return jsonify({'error': str(e)}), status
    config = _load_config()
    bank_key = f'bank_{letter}'
    if bank_key not in config or not config[bank_key]:
        config[bank_key] = {'name': letter.upper(), 'pads': {}}

    if 'name' in data:
        if data['name'] is not None and not isinstance(data['name'], str):
            return jsonify({'error': 'name must be a string'}), 400
        config[bank_key]['name'] = (data['name'] or '').strip() if data['name'] is not None else ''
    if 'bpm' in data:
        if data['bpm'] in (None, ''):
            config[bank_key]['bpm'] = None
        else:
            try:
                config[bank_key]['bpm'] = int(data['bpm'])
            except (TypeError, ValueError):
                return jsonify({'error': 'bpm must be an integer'}), 400
    if 'key' in data:
        if data['key'] is not None and not isinstance(data['key'], str):
            return jsonify({'error': 'key must be a string'}), 400
        config[bank_key]['key'] = data['key'].strip() if data['key'] else None
    if 'notes' in data:
        if data['notes'] is not None and not isinstance(data['notes'], str):
            return jsonify({'error': 'notes must be a string'}), 400
        config[bank_key]['notes'] = data['notes'] or ''

    with open(_config_path(), 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return jsonify({'ok': True})


@banks_bp.route('/banks/<letter>/pads/<int:num>', methods=['PUT'])
def update_pad(letter, num):
    try:
        letter = _normalize_letter(letter)
        num = _normalize_pad_num(num)
        data = _json_object_body()
    except ValueError as e:
        status = 404 if str(e) == 'Bank not found' else 400
        return jsonify({'error': str(e)}), status
    desc = data.get('description', '')
    if desc is not None and not isinstance(desc, str):
        return jsonify({'error': 'description must be a string'}), 400

    config = _load_config()
    bank_key = f'bank_{letter}'
    if bank_key not in config or not config[bank_key]:
        config[bank_key] = {'name': letter.upper(), 'pads': {}}
    if 'pads' not in config[bank_key]:
        config[bank_key]['pads'] = {}
    config[bank_key]['pads'][num] = desc or ''

    with open(_config_path(), 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return jsonify({'ok': True})
