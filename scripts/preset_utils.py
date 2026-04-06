#!/usr/bin/env python3
"""Preset management utilities for the SP-404 Jam Box."""
import os
import re
import yaml
from jambox_config import atomic_write_yaml, load_bank_config, load_settings_for_script

SETTINGS = load_settings_for_script(__file__)
REPO_DIR = SETTINGS['REPO_DIR']
PRESETS_DIR = os.path.join(REPO_DIR, 'presets')
CONFIG_PATH = SETTINGS['CONFIG_PATH']

BANK_LETTERS = list('abcdefghij')
CATEGORIES = ['genre', 'utility', 'song-kits', 'palette', 'community', 'auto']
REQUIRED_PAD_NUMBERS = set(range(1, 13))


def slugify(name):
    """Convert name to URL-safe slug."""
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


def _normalize_tags(raw_tags):
    if raw_tags is None:
        return []
    if isinstance(raw_tags, list):
        out = []
        for item in raw_tags:
            if not isinstance(item, str):
                raise ValueError('tags must contain only strings')
            tag = item.strip()
            if tag:
                out.append(tag)
        return out
    if isinstance(raw_tags, str):
        return [tag.strip() for tag in raw_tags.split(',') if tag.strip()]
    raise ValueError('tags must be a list of strings')


def _normalize_optional_int(value, field_name):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} must be an integer') from exc


def _normalize_optional_str(value):
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        raise ValueError('key must be a string')
    text = value.strip()
    return text or None


def _normalize_pads(raw_pads, *, require_full=True):
    if not isinstance(raw_pads, dict):
        raise ValueError('pads must be an object keyed by pad number')
    normalized = {}
    for raw_key, raw_value in raw_pads.items():
        try:
            pad_num = int(raw_key)
        except (TypeError, ValueError) as exc:
            raise ValueError('pads keys must be numbers 1-12') from exc
        if pad_num < 1 or pad_num > 12:
            raise ValueError('pads keys must be between 1 and 12')
        if not isinstance(raw_value, str):
            raise ValueError(f'pads.{pad_num} must be a string')
        desc = raw_value.strip()
        if not desc:
            raise ValueError(f'pads.{pad_num} cannot be empty')
        normalized[pad_num] = desc

    if require_full and set(normalized.keys()) != REQUIRED_PAD_NUMBERS:
        missing = sorted(REQUIRED_PAD_NUMBERS.difference(normalized.keys()))
        raise ValueError(f'preset must define pads 1-12 (missing: {missing})')

    return normalized


def validate_preset_payload(preset, *, ref=None, require_full_pads=True):
    """Validate and normalize a preset payload."""
    if not isinstance(preset, dict):
        raise ValueError('preset must be a YAML object')

    normalized = dict(preset)
    name = normalized.get('name')
    if name is None:
        name = ref or normalized.get('slug') or 'Untitled'
    if not isinstance(name, str) or not name.strip():
        raise ValueError('name must be a non-empty string')
    normalized['name'] = name.strip()

    slug = normalized.get('slug')
    if slug in (None, ''):
        slug = slugify(normalized['name'])
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError('slug must be a non-empty string')
    normalized['slug'] = slugify(slug)

    normalized['bpm'] = _normalize_optional_int(normalized.get('bpm'), 'bpm')
    normalized['key'] = _normalize_optional_str(normalized.get('key'))
    normalized['tags'] = _normalize_tags(normalized.get('tags'))
    normalized['pads'] = _normalize_pads(normalized.get('pads', {}), require_full=require_full_pads)
    return normalized


# ── Presets ──

def load_preset(ref, *, require_full_pads=True):
    """Load a preset by reference (e.g. 'genre/funk-dance-punk').
    Returns dict or None if not found. Raises ValueError for invalid shape."""
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
    validated = validate_preset_payload(data, ref=ref, require_full_pads=require_full_pads)
    validated['_ref'] = ref
    validated['_path'] = path
    return validated


def save_preset(preset, category=None):
    """Save a preset dict to disk. Returns the ref string."""
    normalized = validate_preset_payload(preset, require_full_pads=True)
    slug = slugify(normalized.get('slug') or normalized.get('name', 'untitled'))
    if not slug:
        slug = 'untitled'
    normalized['slug'] = slug
    cat = category or normalized.get('category', 'community')
    if cat not in CATEGORIES:
        cat = 'community'

    cat_dir = os.path.join(PRESETS_DIR, cat)
    os.makedirs(cat_dir, exist_ok=True)

    save_data = {k: v for k, v in normalized.items() if not k.startswith('_')}
    save_data.pop('category', None)

    path = os.path.join(cat_dir, f"{slug}.yaml")
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(PRESETS_DIR)):
        raise ValueError(f"Invalid preset slug: {slug}")
    atomic_write_yaml(path, save_data)

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
            try:
                data = load_preset(ref, require_full_pads=True)
            except ValueError:
                continue
            if not data:
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
                if tag.lower() not in [str(t).lower() for t in data.get('tags', [])]:
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
                'pad_count': 12,
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

    return validate_preset_payload({
        'name': name,
        'slug': slugify(name),
        'author': 'jambox',
        'bpm': bank.get('bpm'),
        'key': bank.get('key'),
        'vibe': notes[:80] if notes else '',
        'notes': notes or '',
        'source': 'curated',
        'tags': sorted(tags)[:10],
        'pads': {int(k): v for k, v in pads.items() if str(k).isdigit()},
    }, require_full_pads=True)


def load_preset_to_bank(ref, bank_letter):
    """Load a preset into a specific bank slot in bank_config.yaml."""
    preset = load_preset(ref, require_full_pads=True)
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
        'pads': dict(preset.get('pads', {})),
    }

    _save_config(config)
    return config[bank_key]


# ── Config I/O ──

def _load_config():
    """Load bank_config.yaml."""
    return load_bank_config(CONFIG_PATH, strict=False)


def _save_config(config):
    """Write bank_config.yaml atomically (temp+rename)."""
    atomic_write_yaml(CONFIG_PATH, config)
