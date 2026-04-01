"""Library browser API."""
import json
import os
import re

from flask import Blueprint, jsonify, request, abort

library_bp = Blueprint('library', __name__)

LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
TAGS_FILE = os.path.join(LIBRARY, "_tags.json")
AUDIO_EXTS = {'.wav', '.aif', '.aiff', '.mp3'}

# Cache the tag database in memory (loaded on first request)
_tag_db_cache = None
_tag_db_mtime = 0


def _load_tag_db():
    """Load and cache the tag database from _tags.json."""
    global _tag_db_cache, _tag_db_mtime
    try:
        mtime = os.path.getmtime(TAGS_FILE)
    except OSError:
        return {}
    if _tag_db_cache is not None and mtime <= _tag_db_mtime:
        return _tag_db_cache
    try:
        with open(TAGS_FILE, 'r') as f:
            _tag_db_cache = json.load(f)
            _tag_db_mtime = mtime
            return _tag_db_cache
    except (json.JSONDecodeError, IOError):
        return {}


@library_bp.route('/library/browse')
def browse_root():
    return _browse('')


@library_bp.route('/library/browse/<path:subdir>')
def browse_subdir(subdir):
    return _browse(subdir)


def _browse(subdir):
    full = os.path.join(LIBRARY, subdir)
    full = os.path.realpath(full)
    if not full.startswith(os.path.realpath(LIBRARY)):
        abort(403)
    if not os.path.isdir(full):
        abort(404)

    dirs = []
    files = []
    try:
        entries = sorted(os.listdir(full))
    except PermissionError:
        return jsonify({'dirs': [], 'files': [], 'path': subdir})

    for name in entries:
        if name.startswith('.') or name.startswith('_'):
            continue
        path = os.path.join(full, name)
        rel = os.path.relpath(path, LIBRARY)
        if os.path.isdir(path):
            # Count audio files inside
            count = sum(1 for _, _, fs in os.walk(path) for f in fs if os.path.splitext(f)[1].lower() in AUDIO_EXTS)
            dirs.append({'name': name, 'path': rel, 'count': count})
        elif os.path.splitext(name)[1].lower() in AUDIO_EXTS:
            files.append({
                'name': name,
                'path': rel,
                'size': os.path.getsize(path),
            })

    # Limit files to 200 to avoid huge responses
    return jsonify({'dirs': dirs, 'files': files[:200], 'path': subdir, 'total_files': len(files)})


@library_bp.route('/library/search')
def search():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'results': []})

    words = set(re.findall(r'[a-z]+', q.lower()))
    results = []

    for root, dirs, files in os.walk(LIBRARY):
        if '_RAW-DOWNLOADS' in root or '_GOLD' in root:
            continue
        for f in files:
            if os.path.splitext(f)[1].lower() not in AUDIO_EXTS:
                continue
            fname_lower = f.lower()
            score = sum(2 for w in words if w in fname_lower)
            dir_lower = root.lower()
            score += sum(1 for w in words if w in dir_lower)
            if score >= 2:
                rel = os.path.relpath(os.path.join(root, f), LIBRARY)
                results.append({'name': f, 'path': rel, 'score': score})

        if len(results) > 500:
            break

    results.sort(key=lambda x: -x['score'])
    return jsonify({'results': results[:30], 'query': q})


@library_bp.route('/library/stats')
def stats():
    """Return library statistics for the dashboard."""
    categories = {}
    total = 0
    for root, dirs, files in os.walk(LIBRARY):
        if '_RAW-DOWNLOADS' in root or '_GOLD' in root:
            continue
        for f in files:
            if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
                # Get top-level category
                rel = os.path.relpath(root, LIBRARY)
                cat = rel.split(os.sep)[0] if rel != '.' else 'Other'
                categories[cat] = categories.get(cat, 0) + 1
                total += 1

    # Check Downloads for pending packs
    import glob
    downloads = os.path.expanduser("~/Downloads")
    pending_packs = 0
    for item in os.listdir(downloads):
        if any(s in item for s in ['WAV-MASCHiNE', 'WAV-EXPANSION', 'WAV-SONiTUS', 'MULTiFORMAT', 'Prime Loops']):
            marker = os.path.join(downloads, item, '.sp404-ingested')
            if not os.path.exists(marker):
                pending_packs += 1

    return jsonify({
        'total': total,
        'categories': categories,
        'pending_packs': pending_packs,
    })


@library_bp.route('/library/tags')
def tag_cloud():
    """Return tag frequency data for a tag cloud visualization."""
    db = _load_tag_db()
    if not db:
        return jsonify({'error': 'No tag database found. Run: python scripts/tag_library.py', 'tags': {}, 'total': 0})

    from collections import Counter
    tag_counts = Counter()
    instrument_counts = Counter()
    genre_counts = Counter()
    type_counts = Counter()
    bpm_counts = Counter()

    for entry in db.values():
        for t in entry.get('tags', []):
            tag_counts[t] += 1
        inst = entry.get('instrument')
        if inst:
            instrument_counts[inst] += 1
        genre = entry.get('genre')
        if genre:
            genre_counts[genre] += 1
        dur_type = entry.get('type')
        if dur_type:
            type_counts[dur_type] += 1
        bpm = entry.get('bpm')
        if bpm:
            bpm_counts[bpm] += 1

    return jsonify({
        'total': len(db),
        'tags': dict(tag_counts.most_common(100)),
        'instruments': dict(instrument_counts.most_common()),
        'genres': dict(genre_counts.most_common()),
        'types': dict(type_counts.most_common()),
        'bpms': dict(bpm_counts.most_common(30)),
    })


@library_bp.route('/library/by-tag')
def by_tag():
    """Return files matching ALL given tags.

    Usage: GET /api/library/by-tag?tag=kick&tag=funk
    Optional: &limit=50 (default 100)
    """
    tags = request.args.getlist('tag')
    if not tags:
        return jsonify({'error': 'Provide at least one tag parameter', 'results': []})

    tags_set = set(t.lower() for t in tags)
    limit = min(int(request.args.get('limit', 100)), 500)

    db = _load_tag_db()
    if not db:
        return jsonify({'error': 'No tag database found. Run: python scripts/tag_library.py', 'results': []})

    results = []
    for rel_path, entry in db.items():
        entry_tags = set(t.lower() for t in entry.get('tags', []))
        if tags_set.issubset(entry_tags):
            results.append({
                'name': os.path.basename(rel_path),
                'path': rel_path,
                'tags': entry.get('tags', []),
                'bpm': entry.get('bpm'),
                'key': entry.get('key'),
                'duration': entry.get('duration'),
                'type': entry.get('type'),
                'instrument': entry.get('instrument'),
                'genre': entry.get('genre'),
            })
            if len(results) >= limit:
                break

    return jsonify({
        'query_tags': tags,
        'total': len(results),
        'results': results,
    })
