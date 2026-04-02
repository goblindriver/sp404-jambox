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
    data = request.get_json() or {}
    letter = letter.lower()

    preset = pu.bank_to_preset(letter)
    if not preset:
        return jsonify({'error': f'Bank {letter.upper()} has no pads'}), 400

    # Override with user-provided values
    if data.get('name'):
        preset['name'] = data['name']
        preset['slug'] = pu.slugify(data['name'])
    if data.get('vibe'):
        preset['vibe'] = data['vibe']
    if data.get('tags'):
        preset['tags'] = data['tags'] if isinstance(data['tags'], list) else [t.strip() for t in data['tags'].split(',')]

    category = data.get('category', 'community')
    ref = pu.save_preset(preset, category=category)

    return jsonify({'ok': True, 'ref': ref, 'slug': preset['slug']})


@presets_bp.route('/presets/load', methods=['POST'])
def load_preset_to_bank():
    """Load a preset into a bank slot."""
    data = request.get_json() or {}
    ref = data.get('ref')
    bank = data.get('bank', '').lower()

    if not ref or not bank:
        return jsonify({'error': 'ref and bank required'}), 400
    if bank not in pu.BANK_LETTERS:
        return jsonify({'error': f'Invalid bank: {bank}'}), 400

    try:
        result = pu.load_preset_to_bank(ref, bank)
        return jsonify({'ok': True, 'bank': bank, 'name': result.get('name')})
    except ValueError as e:
        return jsonify({'error': str(e)}), 404


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
    data = request.get_json() or {}
    name = data.get('name')
    if not name:
        return jsonify({'error': 'name required'}), 400

    banks = data.get('banks', {})
    set_data = {
        'name': name,
        'slug': pu.slugify(name),
        'notes': data.get('notes', ''),
        'banks': banks,
    }
    slug = pu.save_set(set_data)
    return jsonify({'ok': True, 'slug': slug})


@presets_bp.route('/sets/save-current', methods=['POST'])
def save_current_as_set():
    """Snapshot current bank config as a new set."""
    data = request.get_json() or {}
    name = data.get('name', 'Untitled Set')
    notes = data.get('notes', '')

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
