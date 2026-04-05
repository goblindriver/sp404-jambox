"""Library browser API."""
import json
import os
import re
import subprocess
import sys
import threading

from flask import Blueprint, jsonify, request, abort, current_app

from jambox_config import build_subprocess_env

library_bp = Blueprint('library', __name__)
AUDIO_EXTS = {'.wav', '.aif', '.aiff', '.mp3', '.flac'}

# Cache the tag database in memory (loaded on first request)
_tag_db_cache = None
_tag_db_mtime = 0


def _library_root():
    return current_app.config['SAMPLE_LIBRARY']


def _tags_file():
    return current_app.config['TAGS_FILE']


def _parse_limit_arg(name, default, maximum):
    raw_value = request.args.get(name, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be an integer') from exc
    if value < 1:
        raise ValueError(f'{name} must be >= 1')
    return min(value, maximum)


def _load_tag_db():
    """Load and cache the tag database from _tags.json."""
    global _tag_db_cache, _tag_db_mtime
    tags_file = _tags_file()
    try:
        mtime = os.path.getmtime(tags_file)
    except OSError:
        return {}
    if _tag_db_cache is not None and mtime <= _tag_db_mtime:
        return _tag_db_cache
    try:
        with open(tags_file, 'r') as f:
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
    library_root = _library_root()
    full = os.path.join(library_root, subdir)
    full = os.path.realpath(full)
    if not full.startswith(os.path.realpath(library_root)):
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
        rel = os.path.relpath(path, library_root)
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

    library_root = _library_root()
    for root, dirs, files in os.walk(library_root):
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
                rel = os.path.relpath(os.path.join(root, f), library_root)
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
    library_root = _library_root()
    downloads = current_app.config['DOWNLOADS_PATH']
    for root, dirs, files in os.walk(library_root):
        if '_RAW-DOWNLOADS' in root or '_GOLD' in root:
            continue
        for f in files:
            if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
                # Get top-level category
                rel = os.path.relpath(root, library_root)
                cat = rel.split(os.sep)[0] if rel != '.' else 'Other'
                categories[cat] = categories.get(cat, 0) + 1
                total += 1

    # Check Downloads for pending packs
    import glob
    pending_packs = 0
    try:
        for item in os.listdir(downloads):
            if any(s in item for s in ['WAV-MASCHiNE', 'WAV-EXPANSION', 'WAV-SONiTUS', 'MULTiFORMAT', 'Prime Loops']):
                marker = os.path.join(downloads, item, '.sp404-ingested')
                if not os.path.exists(marker):
                    pending_packs += 1
    except OSError:
        pending_packs = 0

    return jsonify({
        'total': total,
        'categories': categories,
        'pending_packs': pending_packs,
    })


@library_bp.route('/library/tags')
def tag_cloud():
    """Return tag frequency data by spec dimensions."""
    db = _load_tag_db()
    if not db:
        return jsonify({'error': 'No tag database found. Run: python scripts/tag_library.py', 'tags': {}, 'total': 0})

    from collections import Counter
    tag_counts = Counter()
    type_code_counts = Counter()
    vibe_counts = Counter()
    texture_counts = Counter()
    genre_counts = Counter()
    source_counts = Counter()
    energy_counts = Counter()
    playability_counts = Counter()
    bpm_counts = Counter()

    for entry in db.values():
        for t in entry.get('tags', []):
            tag_counts[t] += 1
        tc = entry.get('type_code')
        if tc:
            type_code_counts[tc] += 1
        for v in entry.get('vibe', []):
            vibe_counts[v] += 1
        for t in entry.get('texture', []):
            texture_counts[t] += 1
        for g in entry.get('genre', []):
            genre_counts[g] += 1
        s = entry.get('source')
        if s:
            source_counts[s] += 1
        e = entry.get('energy')
        if e:
            energy_counts[e] += 1
        p = entry.get('playability')
        if p:
            playability_counts[p] += 1
        bpm = entry.get('bpm')
        if bpm:
            bpm_counts[bpm] += 1

    return jsonify({
        'total': len(db),
        'tags': dict(tag_counts.most_common(100)),
        'type_codes': dict(type_code_counts.most_common()),
        'vibes': dict(vibe_counts.most_common()),
        'textures': dict(texture_counts.most_common()),
        'genres': dict(genre_counts.most_common()),
        'sources': dict(source_counts.most_common()),
        'energies': dict(energy_counts.most_common()),
        'playabilities': dict(playability_counts.most_common()),
        'bpms': dict(bpm_counts.most_common(30)),
    })


@library_bp.route('/library/by-tag')
def by_tag():
    """Return files matching filters.

    Supports both flat tags and dimension-specific filters:
      GET /api/library/by-tag?tag=KIK&tag=funk           (flat AND)
      GET /api/library/by-tag?type_code=KIK&vibe=dark    (dimension filters)
    """
    tags = request.args.getlist('tag')
    # Dimension-specific filters
    dim_filters = {}
    for dim in ('type_code', 'vibe', 'texture', 'genre', 'source', 'energy', 'playability'):
        vals = request.args.getlist(dim)
        if vals:
            dim_filters[dim] = set(v.lower() for v in vals)

    # BPM filter (numeric, parsed from "120bpm" or raw "120")
    bpm_filter = None
    bpm_vals = request.args.getlist('bpm')
    if bpm_vals:
        import re
        bpm_nums = []
        for v in bpm_vals:
            m = re.match(r'(\d+)', v)
            if m:
                bpm_nums.append(int(m.group(1)))
        if bpm_nums:
            bpm_filter = bpm_nums

    if not tags and not dim_filters and not bpm_filter:
        return jsonify({'error': 'Provide at least one filter', 'results': []})

    tags_set = set(t.lower() for t in tags) if tags else set()
    try:
        limit = _parse_limit_arg('limit', 100, 500)
    except ValueError as e:
        return jsonify({'error': str(e), 'results': []}), 400

    db = _load_tag_db()
    if not db:
        return jsonify({'error': 'No tag database found', 'results': []})

    results = []
    for rel_path, entry in db.items():
        # Check flat tags (AND)
        if tags_set:
            entry_tags = set(t.lower() for t in entry.get('tags', []))
            if not tags_set.issubset(entry_tags):
                continue

        # Check BPM filter (within ±5 BPM of any selected value)
        if bpm_filter:
            entry_bpm = entry.get('bpm')
            if not entry_bpm or not any(abs(entry_bpm - b) <= 5 for b in bpm_filter):
                continue

        # Check dimension filters (AND across dimensions, OR within)
        match = True
        for dim, vals in dim_filters.items():
            entry_val = entry.get(dim)
            if isinstance(entry_val, list):
                if not vals.intersection(v.lower() for v in entry_val):
                    match = False
                    break
            elif entry_val:
                if entry_val.lower() not in vals:
                    match = False
                    break
            else:
                match = False
                break
        if not match:
            continue

        results.append({
            'name': os.path.basename(rel_path),
            'path': rel_path,
            'tags': entry.get('tags', []),
            'type_code': entry.get('type_code'),
            'vibe': entry.get('vibe', []),
            'texture': entry.get('texture', []),
            'genre': entry.get('genre', []),
            'source': entry.get('source'),
            'energy': entry.get('energy'),
            'playability': entry.get('playability'),
            'bpm': entry.get('bpm'),
            'key': entry.get('key'),
            'duration': entry.get('duration'),
        })
        if len(results) >= limit:
            break

    return jsonify({
        'query_tags': tags,
        'filters': {k: list(v) for k, v in dim_filters.items()},
        'total': len(results),
        'results': results,
    })


# ═══════════════════════════════════════════════════════════
# Smart Retag (LLM-powered tag enrichment)
# ═══════════════════════════════════════════════════════════

_retag_jobs = {}
_retag_lock = threading.Lock()


def _run_smart_retag(job_id, repo_dir, settings, args_list):
    """Background worker for smart retagging."""
    try:
        _retag_jobs[job_id]["status"] = "running"
        script = os.path.join(repo_dir, "scripts", "smart_retag.py")
        cmd = [sys.executable, script] + args_list

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_dir,
            env=build_subprocess_env(settings),
            timeout=600,
        )
        _retag_jobs[job_id]["stdout"] = result.stdout
        _retag_jobs[job_id]["stderr"] = result.stderr
        _retag_jobs[job_id]["status"] = "done" if result.returncode == 0 else "error"

        # Invalidate tag cache
        global _tag_db_cache, _tag_db_mtime
        _tag_db_cache = None
        _tag_db_mtime = 0

    except subprocess.TimeoutExpired:
        _retag_jobs[job_id]["status"] = "error"
        _retag_jobs[job_id]["stderr"] = "Smart retag timed out after 10 minutes"
    except Exception as e:
        _retag_jobs[job_id]["status"] = "error"
        _retag_jobs[job_id]["stderr"] = str(e)


@library_bp.route('/library/smart-retag', methods=['POST'])
def smart_retag():
    """Trigger LLM-powered smart retagging.

    POST body:
        type_code: filter by type code (e.g., "FX")
        path: filter by path prefix (e.g., "SFX/")
        file: retag a single file
        limit: max samples (default 50)
        force: re-process already enriched (default false)
        dry_run: preview only (default false)
    """
    # Only one retag at a time
    with _retag_lock:
        for j in _retag_jobs.values():
            if j.get("status") == "running":
                return jsonify({"ok": False, "error": "A smart retag is already running"}), 409

    payload = request.get_json() or {}

    # Build CLI args
    args_list = []
    if payload.get("type_code"):
        args_list += ["--type", payload["type_code"]]
    if payload.get("path"):
        args_list += ["--path", payload["path"]]
    if payload.get("file"):
        args_list += ["--file", payload["file"]]
    if payload.get("force"):
        args_list.append("--force")
    if payload.get("dry_run"):
        args_list.append("--dry-run")
    limit = payload.get("limit", 50)
    args_list += ["--limit", str(limit)]

    import uuid
    job_id = str(uuid.uuid4())[:8]
    _retag_jobs[job_id] = {
        "id": job_id,
        "status": "starting",
        "stdout": "",
        "stderr": "",
    }

    repo_dir = current_app.config["REPO_DIR"]
    settings = dict(current_app.config)
    t = threading.Thread(target=_run_smart_retag, args=(job_id, repo_dir, settings, args_list))
    t.daemon = True
    t.start()

    return jsonify({"ok": True, "job_id": job_id})


@library_bp.route('/library/smart-retag/<job_id>')
def smart_retag_status(job_id):
    """Poll smart retag job progress."""
    job = _retag_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)
