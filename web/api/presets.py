"""Preset & Set management API."""
import os
import sys
from flask import Blueprint, jsonify, request

presets_bp = Blueprint('presets', __name__)

# Add scripts dir for preset_utils
_scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            '..', 'scripts')
sys.path.insert(0, os.path.abspath(_scripts_dir))

import preset_utils as pu
import daily_bank as db


def _json_object_body():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ValueError('Request body must be a JSON object')
    return data


def _normalize_string_field(data, field_name):
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'{field_name} must be a string')
    value = value.strip()
    return value or None


def _normalize_tags(value):
    if value is None:
        return None
    if isinstance(value, str):
        return [tag.strip() for tag in value.split(',') if tag.strip()]
    if isinstance(value, list):
        tags = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError('tags must contain only strings')
            item = item.strip()
            if item:
                tags.append(item)
        return tags
    raise ValueError('tags must be a comma-separated string or list of strings')


def _normalize_bank_name(value):
    if not isinstance(value, str):
        raise ValueError('bank must be a string')
    bank = value.lower().strip()
    if not bank:
        return ''
    if bank not in pu.BANK_LETTERS:
        raise ValueError(f'Invalid bank: {bank}')
    return bank


# ── Presets ──

@presets_bp.route('/presets')
def list_presets():
    """List/search presets. Query params: category, q, tag, bpm, key."""
    category = request.args.get('category')
    q = request.args.get('q')
    tag = request.args.get('tag')
    bpm = request.args.get('bpm')
    key = request.args.get('key')

    results = pu.list_presets(category=category, query=q, tag=tag, bpm=bpm, key=key)
    return jsonify({'presets': results, 'total': len(results)})


@presets_bp.route('/presets/categories')
def list_categories():
    """List preset categories with counts."""
    return jsonify({'categories': pu.list_categories()})


@presets_bp.route('/presets/<path:ref>')
def get_preset(ref):
    """Get full preset detail by reference."""
    try:
        preset = pu.load_preset(ref, require_full_pads=True)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 422
    if not preset:
        return jsonify({'ok': False, 'error': f'Preset not found: {ref}'}), 404
    # Remove internal fields
    result = {k: v for k, v in preset.items() if not k.startswith('_')}
    result['ref'] = ref
    result['ok'] = True
    return jsonify(result)


@presets_bp.route('/presets/from-bank/<letter>', methods=['POST'])
def save_bank_as_preset(letter):
    """Save a bank's current config as a new preset."""
    try:
        data = _json_object_body()
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    try:
        letter = _normalize_bank_name(letter)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if not letter:
        return jsonify({'ok': False, 'error': 'bank letter required'}), 400

    preset = pu.bank_to_preset(letter)
    if not preset:
        return jsonify({'ok': False, 'error': f'Bank {letter.upper()} has no pads'}), 400

    # Override with user-provided values
    try:
        name = _normalize_string_field(data, 'name')
        vibe = _normalize_string_field(data, 'vibe')
        tags = _normalize_tags(data.get('tags'))
        category = _normalize_string_field(data, 'category') or 'community'
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    updated_preset = dict(preset)
    if name:
        updated_preset['name'] = name
        updated_preset['slug'] = pu.slugify(name)
    if vibe:
        updated_preset['vibe'] = vibe
    if tags is not None:
        updated_preset['tags'] = tags

    try:
        ref = pu.save_preset(updated_preset, category=category)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 422

    return jsonify({'ok': True, 'ref': ref, 'slug': updated_preset['slug']})


@presets_bp.route('/presets/load', methods=['POST'])
def load_preset_to_bank():
    """Load a preset into a bank slot."""
    try:
        data = _json_object_body()
        ref = _normalize_string_field(data, 'ref')
        bank = _normalize_bank_name(data.get('bank', ''))
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    if not ref or not bank:
        return jsonify({'ok': False, 'error': 'ref and bank required'}), 400

    try:
        result = pu.load_preset_to_bank(ref, bank)
        return jsonify({'ok': True, 'bank': bank, 'name': result.get('name')})
    except ValueError as e:
        message = str(e)
        code = 404 if message.startswith('Preset not found') else 422
        return jsonify({'ok': False, 'error': message}), code


@presets_bp.route('/presets/daily', methods=['POST'])
def generate_daily_preset():
    """Generate a daily preset and optionally load it to a bank."""
    try:
        data = _json_object_body()
        source = _normalize_string_field(data, 'source')
        bank = _normalize_bank_name(data.get('bank', ''))
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    try:
        result = db.build_daily_preset(source=source)
        if bank:
            pu.load_preset_to_bank(result['ref'], bank)
            result['loaded_bank'] = bank
        return jsonify({'ok': True, **result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
