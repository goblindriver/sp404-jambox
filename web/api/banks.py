"""Bank and pad configuration API."""
import os, yaml
from flask import Blueprint, jsonify, request, current_app

banks_bp = Blueprint('banks', __name__)


def _config_path():
    return os.path.join(current_app.config['REPO_DIR'], 'bank_config.yaml')


def _smpl_dir():
    return os.path.join(current_app.config['REPO_DIR'], 'sd-card-template', 'ROLAND', 'SP-404SX', 'SMPL')


def _load_config():
    with open(_config_path()) as f:
        return yaml.safe_load(f)


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
    data = request.get_json()
    config = _load_config()
    bank_key = f'bank_{letter}'
    if bank_key not in config or not config[bank_key]:
        config[bank_key] = {'name': letter.upper(), 'pads': {}}

    if 'name' in data:
        config[bank_key]['name'] = data['name']
    if 'bpm' in data:
        config[bank_key]['bpm'] = int(data['bpm']) if data['bpm'] else None
    if 'key' in data:
        config[bank_key]['key'] = data['key'] if data['key'] else None
    if 'notes' in data:
        config[bank_key]['notes'] = data['notes']

    with open(_config_path(), 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return jsonify({'ok': True})


@banks_bp.route('/banks/<letter>/pads/<int:num>', methods=['PUT'])
def update_pad(letter, num):
    data = request.get_json()
    desc = data.get('description', '')

    config = _load_config()
    bank_key = f'bank_{letter}'
    if bank_key not in config or not config[bank_key]:
        config[bank_key] = {'name': letter.upper(), 'pads': {}}
    if 'pads' not in config[bank_key]:
        config[bank_key]['pads'] = {}
    config[bank_key]['pads'][num] = desc

    with open(_config_path(), 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return jsonify({'ok': True})
