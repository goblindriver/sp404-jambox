#!/usr/bin/env python3
"""
Preset & Set management utilities for the SP-404 Jam Box.

Presets are standalone bank YAML files in presets/<category>/<slug>.yaml.
Sets map 10 bank slots (A-J) to preset references.
bank_config.yaml is always fully expanded for backward compatibility.
"""
import os
import re
import yaml
from datetime import datetime

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESETS_DIR = os.path.join(REPO_DIR, 'presets')
SETS_DIR = os.path.join(REPO_DIR, 'sets')
CONFIG_PATH = os.path.join(REPO_DIR, 'bank_config.yaml')

BANK_LETTERS = list('abcdefghij')
CATEGORIES = ['genre', 'utility', 'song-kits', 'palette', 'community', 'auto']


def slugify(name):
    """Convert name to URL-safe slug."""
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


# ── Presets ──

def load_preset(ref):
    """Load a preset by reference (e.g. 'genre/funk-dance-punk').
    Returns dict or None if not found. Validates path stays within PRESETS_DIR."""
    path = os.path.realpath(os.path.join(PRESETS_DIR, f"{ref}.yaml"))
    if not path.startswith(os.path.realpath(PRESETS_DIR)):
        return None  # path traversal attempt
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    data['_ref'] = ref
    data['_path'] = path
    return data


def save_preset(preset, category=None):
    """Save a preset dict to disk. Returns the ref string."""
    slug = preset.get('slug') or slugify(preset.get('name', 'untitled'))
    if not slug:
        slug = 'untitled'
    preset['slug'] = slug
    cat = category or preset.get('category', 'community')
    if cat not in CATEGORIES:
        cat = 'community'

    cat_dir = os.path.join(PRESETS_DIR, cat)
    os.makedirs(cat_dir, exist_ok=True)

    # Remove internal fields before saving
    save_data = {k: v for k, v in preset.items() if not k.startswith('_')}
    save_data.pop('category', None)

    path = os.path.join(cat_dir, f"{slug}.yaml")
    with open(path, 'w') as f:
        yaml.safe_dump(save_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    ref = f"{cat}/{slug}"
    return ref


def list_presets(category=None, query=None, tag=None, bpm=None, key=None):
    """List all presets, optionally filtered. Returns list of summary dicts."""
    results = []
    categories = [category] if category else CATEGORIES

    for cat in categories:
        cat_dir = os.path.join(PRESETS_DIR, cat)
        if not os.path.isdir(cat_dir):
            continue
        for fname in sorted(os.listdir(cat_dir)):
            if not fname.endswith('.yaml'):
                continue
            slug = fname[:-5]
            ref = f"{cat}/{slug}"
            path = os.path.join(cat_dir, fname)

            try:
                with open(path) as f:
                    data = yaml.safe_load(f) or {}
            except (yaml.YAMLError, IOError):
                continue
            if not isinstance(data, dict):
                continue

            # Apply filters
            if query:
                q = query.lower()
                raw_tags = data.get('tags', [])
                if isinstance(raw_tags, list):
                    search_tags = ' '.join(str(tag) for tag in raw_tags)
                else:
                    search_tags = str(raw_tags or '')
                searchable = f"{data.get('name', '')} {data.get('vibe', '')} {data.get('notes', '')} {search_tags}".lower()
                if q not in searchable:
                    continue

            if tag:
                raw_tags = data.get('tags', [])
                if not isinstance(raw_tags, list):
                    raw_tags = [raw_tags] if raw_tags else []
                if tag.lower() not in [str(t).lower() for t in raw_tags]:
                    continue

            if bpm and data.get('bpm'):
                try:
                    if abs(int(bpm) - int(data['bpm'])) > 10:
                        continue
                except (ValueError, TypeError):
                    pass

            if key and data.get('key'):
                if data['key'].lower() != key.lower():
                    continue

            results.append({
                'ref': ref,
                'slug': slug,
                'category': cat,
                'name': data.get('name', slug),
                'bpm': data.get('bpm'),
                'key': data.get('key'),
                'vibe': data.get('vibe', ''),
                'author': data.get('author', ''),
                'tags': data.get('tags', []),
                'pad_count': len(data.get('pads', {})),
            })

    return results


def list_categories():
    """List categories with preset counts."""
    cats = []
    for cat in CATEGORIES:
        cat_dir = os.path.join(PRESETS_DIR, cat)
        count = 0
        if os.path.isdir(cat_dir):
            count = sum(1 for f in os.listdir(cat_dir) if f.endswith('.yaml'))
        cats.append({'name': cat, 'count': count})
    return cats


def bank_to_preset(letter, config=None):
    """Extract a bank from config as a preset dict."""
    if config is None:
        config = _load_config()
    if not isinstance(config, dict):
        return None

    bank_key = f'bank_{letter.lower()}'
    bank = config.get(bank_key)
    if not bank:
        return None

    pads = bank.get('pads', {})
    if not pads:
        return None

    # Extract tags from name, notes, and pad descriptions
    tags = set()
    name = bank.get('name', '')
    notes = bank.get('notes', '')
    for word in re.findall(r'\b[a-z]{3,}\b', f"{name} {notes}".lower()):
        if word in ('the', 'and', 'for', 'with', 'from', 'your', 'use',
                     'are', 'this', 'that', 'pad', 'bank', 'pads', 'loop',
                     'one', 'shot', 'chop', 'ready'):
            continue
        tags.add(word)

    return {
        'name': name,
        'slug': slugify(name),
        'author': 'jambox',
        'bpm': bank.get('bpm'),
        'key': bank.get('key'),
        'vibe': notes[:80] if notes else '',
        'notes': notes or '',
        'source': 'curated',
        'tags': sorted(tags)[:10],
        'pads': {int(k): v for k, v in pads.items()},
    }


# ── Sets ──

def load_set(slug):
    """Load a set by slug. Returns dict or None."""
    path = os.path.join(SETS_DIR, f"{slug}.yaml")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    data['_slug'] = slug
    return data


def save_set(set_data):
    """Save a set dict to disk. Returns slug."""
    slug = set_data.get('slug') or slugify(set_data.get('name', 'untitled'))
    set_data['slug'] = slug

    os.makedirs(SETS_DIR, exist_ok=True)

    save_data = {k: v for k, v in set_data.items() if not k.startswith('_')}
    path = os.path.join(SETS_DIR, f"{slug}.yaml")
    with open(path, 'w') as f:
        yaml.safe_dump(save_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return slug


def list_sets():
    """List all sets with summaries."""
    results = []
    if not os.path.isdir(SETS_DIR):
        return results
    for fname in sorted(os.listdir(SETS_DIR)):
        if not fname.endswith('.yaml'):
            continue
        slug = fname[:-5]
        path = os.path.join(SETS_DIR, fname)
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, IOError):
            continue
        if not isinstance(data, dict):
            continue
        banks = data.get('banks', {})
        if not isinstance(banks, dict):
            banks = {}
        filled = sum(1 for v in banks.values() if v)
        results.append({
            'slug': slug,
            'name': data.get('name', slug),
            'notes': data.get('notes', ''),
            'author': data.get('author', ''),
            'created': data.get('created', ''),
            'bank_count': filled,
        })
    return results


def apply_set(set_slug):
    """Apply a set: resolve presets, regenerate bank_config.yaml.
    Returns the updated config dict."""
    set_data = load_set(set_slug)
    if not set_data:
        raise ValueError(f"Set not found: {set_slug}")

    config = _load_config()
    banks_map = set_data.get('banks', {})

    for letter in BANK_LETTERS:
        bank_key = f'bank_{letter}'
        ref = banks_map.get(letter)

        if ref is None or ref == '_empty':
            # Empty bank — use inline data from set if available, otherwise minimal
            inline = banks_map.get(f'{letter}_meta', {})
            config[bank_key] = {
                'name': inline.get('name', 'Your Space') if letter == 'a' else inline.get('name', f'Bank {letter.upper()}'),
                'notes': inline.get('notes', 'Bank A is yours — resample and chop on-device') if letter == 'a' else inline.get('notes', ''),
            }
            continue

        # Load the preset
        preset = load_preset(ref)
        if not preset:
            # Missing preset — preserve what we have but flag it
            config.setdefault(bank_key, {})
            config[bank_key]['notes'] = f'(missing preset: {ref})'
            config[bank_key].pop('preset', None)
            continue

        # Expand preset into bank config
        config[bank_key] = {
            'preset': ref,
            'name': preset.get('name', ref),
            'bpm': preset.get('bpm'),
            'key': preset.get('key'),
            'notes': preset.get('notes', ''),
            'pads': preset.get('pads', {}),
        }

    config['active_set'] = set_slug
    _save_config(config)
    return config


def save_current_as_set(name, notes=''):
    """Snapshot current bank_config.yaml as a new set."""
    config = _load_config()
    banks = {}

    for letter in BANK_LETTERS:
        bank_key = f'bank_{letter}'
        bank = config.get(bank_key, {})
        ref = bank.get('preset')
        if ref:
            banks[letter] = ref
        elif bank.get('pads'):
            # Bank has pads but no preset ref — it's inline
            # Save it as a preset first
            preset = bank_to_preset(letter, config)
            if preset:
                ref = save_preset(preset, category='community')
                banks[letter] = ref
            else:
                banks[letter] = None
        else:
            banks[letter] = None

    set_data = {
        'name': name,
        'slug': slugify(name),
        'author': 'jasongronvold',
        'created': datetime.now().strftime('%Y-%m-%d'),
        'notes': notes,
        'banks': banks,
    }
    slug = save_set(set_data)
    return slug


def load_preset_to_bank(ref, bank_letter):
    """Load a preset into a specific bank slot in bank_config.yaml."""
    preset = load_preset(ref)
    if not preset:
        raise ValueError(f"Preset not found: {ref}")

    config = _load_config()
    bank_key = f'bank_{bank_letter.lower()}'

    config[bank_key] = {
        'preset': ref,
        'name': preset.get('name', ref),
        'bpm': preset.get('bpm'),
        'key': preset.get('key'),
        'notes': preset.get('notes', ''),
        'pads': preset.get('pads', {}),
    }

    _save_config(config)
    return config[bank_key]


# ── Config I/O ──

def _load_config():
    """Load bank_config.yaml."""
    try:
        with open(CONFIG_PATH) as f:
            payload = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_config(config):
    """Write bank_config.yaml preserving structure."""
    with open(CONFIG_PATH, 'w') as f:
        yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
