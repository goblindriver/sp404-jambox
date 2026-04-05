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


def _normalize_banks_map(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('banks must be an object')
    normalized = {}
    for key, bank_value in value.items():
        if not isinstance(key, str):
            raise ValueError('banks keys must be strings')
        if key in pu.BANK_LETTERS:
            if bank_value is not None and not isinstance(bank_value, str):
                raise ValueError(f'banks.{key} must be a preset ref string or null')
            normalized[key] = bank_value
        elif key.endswith('_meta') and key[:-5] in pu.BANK_LETTERS:
            if not isinstance(bank_value, dict):
                raise ValueError(f'banks.{key} must be an object')
            normalized[key] = bank_value
        else:
            raise ValueError(f'Invalid bank slot: {key}')
    return normalized


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
    preset = pu.load_preset(ref)
    if not preset:
        return jsonify({'error': f'Preset not found: {ref}'}), 404
    # Remove internal fields
    result = {k: v for k, v in preset.items() if not k.startswith('_')}
    result['ref'] = ref
    return jsonify(result)


@presets_bp.route('/presets/from-bank/<letter>', methods=['POST'])
def save_bank_as_preset(letter):
    """Save a bank's current config as a new preset."""
    try:
        data = _json_object_body()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    try:
        letter = _normalize_bank_name(letter)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    if not letter:
        return jsonify({'error': 'bank letter required'}), 400

    preset = pu.bank_to_preset(letter)
    if not preset:
        return jsonify({'error': f'Bank {letter.upper()} has no pads'}), 400

    # Override with user-provided values
    try:
        name = _normalize_string_field(data, 'name')
        vibe = _normalize_string_field(data, 'vibe')
        tags = _normalize_tags(data.get('tags'))
        category = _normalize_string_field(data, 'category') or 'community'
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    if name:
        preset['name'] = name
        preset['slug'] = pu.slugify(name)
    if vibe:
        preset['vibe'] = vibe
    if tags is not None:
        preset['tags'] = tags

    ref = pu.save_preset(preset, category=category)

    return jsonify({'ok': True, 'ref': ref, 'slug': preset['slug']})


@presets_bp.route('/presets/load', methods=['POST'])
def load_preset_to_bank():
    """Load a preset into a bank slot."""
    try:
        data = _json_object_body()
        ref = _normalize_string_field(data, 'ref')
        bank = _normalize_bank_name(data.get('bank', ''))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    if not ref or not bank:
        return jsonify({'error': 'ref and bank required'}), 400

    try:
        result = pu.load_preset_to_bank(ref, bank)
        return jsonify({'ok': True, 'bank': bank, 'name': result.get('name')})
    except ValueError as e:
        return jsonify({'error': str(e)}), 404


@presets_bp.route('/presets/daily', methods=['POST'])
def generate_daily_preset():
    """Generate a daily preset and optionally load it to a bank."""
    try:
        data = _json_object_body()
        source = _normalize_string_field(data, 'source')
        bank = _normalize_bank_name(data.get('bank', ''))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    try:
        result = db.build_daily_preset(source=source)
        if bank:
            pu.load_preset_to_bank(result['ref'], bank)
            result['loaded_bank'] = bank
        return jsonify({'ok': True, **result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Sets ──

@presets_bp.route('/sets')
def list_sets():
    """List all sets."""
    results = pu.list_sets()
    # Mark which is active
    try:
        config = pu._load_config()
        active = config.get('active_set')
    except Exception:
        active = None
    for s in results:
        s['active'] = s['slug'] == active
    return jsonify({'sets': results, 'active': active})


@presets_bp.route('/sets/<slug>')
def get_set(slug):
    """Get full set detail with resolved preset names."""
    set_data = pu.load_set(slug)
    if not set_data:
        return jsonify({'error': f'Set not found: {slug}'}), 404

    # Resolve preset names for display
    banks_detail = {}
    for letter, ref in set_data.get('banks', {}).items():
        if ref:
            preset = pu.load_preset(ref)
            banks_detail[letter] = {
                'ref': ref,
                'name': preset.get('name', ref) if preset else f'(missing: {ref})',
                'bpm': preset.get('bpm') if preset else None,
                'key': preset.get('key') if preset else None,
                'vibe': preset.get('vibe', '') if preset else '',
            }
        else:
            banks_detail[letter] = None

    result = {k: v for k, v in set_data.items() if not k.startswith('_')}
    result['banks_detail'] = banks_detail
    return jsonify(result)


@presets_bp.route('/sets', methods=['POST'])
def create_set():
    """Create a new set."""
    try:
        data = _json_object_body()
        name = _normalize_string_field(data, 'name')
        notes = _normalize_string_field(data, 'notes') or ''
        banks = _normalize_banks_map(data.get('banks', {}))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    if not name:
        return jsonify({'error': 'name required'}), 400

    set_data = {
        'name': name,
        'slug': pu.slugify(name),
        'notes': notes,
        'banks': banks,
    }
    slug = pu.save_set(set_data)
    return jsonify({'ok': True, 'slug': slug})


@presets_bp.route('/sets/save-current', methods=['POST'])
def save_current_as_set():
    """Snapshot current bank config as a new set."""
    try:
        data = _json_object_body()
        name = _normalize_string_field(data, 'name') or 'Untitled Set'
        notes = _normalize_string_field(data, 'notes') or ''
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    try:
        slug = pu.save_current_as_set(name, notes)
        return jsonify({'ok': True, 'slug': slug})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@presets_bp.route('/sets/<slug>/apply', methods=['POST'])
def apply_set(slug):
    """Apply a set: regenerate bank_config.yaml from preset references."""
    try:
        config = pu.apply_set(slug)
        return jsonify({'ok': True, 'active_set': slug})
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
