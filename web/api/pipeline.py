"""Pipeline control API — fetch, build, deploy, watcher."""
import os, sys, threading, time, subprocess, uuid, json
from flask import Blueprint, jsonify, request, current_app, Response

pipeline_bp = Blueprint('pipeline', __name__)

# In-memory job tracking
_jobs = {}
_job_lock = threading.Lock()


def _run_fetch(job_id, repo_dir, bank=None, pad=None):
    """Run fetch_samples in a background thread."""
    try:
        sys.path.insert(0, os.path.join(repo_dir, 'scripts'))
        import fetch_samples as fs

        _jobs[job_id]['status'] = 'running'
        config = fs.load_config()
        os.makedirs(fs.STAGING, exist_ok=True)
        os.makedirs(fs.FREESOUND_DIR, exist_ok=True)

        # Load tag database and init deduplication set
        tag_db = fs.load_tag_db()
        used_files = set()

        total_fetched = 0
        total_pads = 0

        for key, bank_config in config.items():
            if not key.startswith('bank_') or not bank_config:
                continue
            letter = key.split('_')[1]
            if bank and letter.lower() != bank.lower():
                continue

            pads = bank_config.get('pads', {})
            if not pads:
                continue

            if pad:
                pad_query = pads.get(pad) or pads.get(str(pad))
                if pad_query:
                    _jobs[job_id]['progress'] = f"Bank {letter.upper()} Pad {pad}"
                    result = fs.fetch_pad(letter, pad, pad_query, bank_config, tag_db, used_files)
                    if result:
                        total_fetched += 1
                    total_pads += 1
            else:
                for pad_num, pad_query in pads.items():
                    pad_num = int(pad_num)
                    _jobs[job_id]['progress'] = f"Bank {letter.upper()} Pad {pad_num}: {pad_query[:40]}"
                    result = fs.fetch_pad(letter, pad_num, pad_query, bank_config, tag_db, used_files)
                    if result:
                        total_fetched += 1
                    total_pads += 1

        # Copy to SMPL
        smpl_dir = os.path.join(repo_dir, 'sd-card-template', 'ROLAND', 'SP-404SX', 'SMPL')
        if total_fetched > 0:
            os.makedirs(smpl_dir, exist_ok=True)
            import shutil, glob
            for f in glob.glob(os.path.join(fs.STAGING, "*.WAV")):
                shutil.copy2(f, smpl_dir)

        _jobs[job_id]['status'] = 'done'
        _jobs[job_id]['result'] = f"{total_fetched}/{total_pads} pads filled"

    except Exception as e:
        _jobs[job_id]['status'] = 'error'
        _jobs[job_id]['result'] = str(e)


@pipeline_bp.route('/pipeline/fetch', methods=['POST'])
def fetch():
    data = request.get_json() or {}
    bank = data.get('bank')
    pad = data.get('pad')

    # Only one fetch at a time
    with _job_lock:
        for j in _jobs.values():
            if j['type'] == 'fetch' and j['status'] == 'running':
                return jsonify({'error': 'Fetch already running'}), 409

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        'id': job_id,
        'type': 'fetch',
        'status': 'starting',
        'progress': '',
        'result': '',
    }
    repo_dir = current_app.config['REPO_DIR']
    t = threading.Thread(target=_run_fetch, args=(job_id, repo_dir, bank, pad))
    t.daemon = True
    t.start()

    return jsonify({'job_id': job_id})


@pipeline_bp.route('/pipeline/status/<job_id>')
def job_status(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@pipeline_bp.route('/pipeline/padinfo', methods=['POST'])
def build_padinfo():
    repo_dir = current_app.config['REPO_DIR']
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(repo_dir, 'scripts', 'gen_padinfo.py')],
            capture_output=True, text=True, cwd=repo_dir,
            env={**os.environ, 'PATH': f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"},
        )
        return jsonify({'ok': True, 'output': result.stdout})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/patterns', methods=['POST'])
def build_patterns():
    repo_dir = current_app.config['REPO_DIR']
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(repo_dir, 'scripts', 'gen_patterns.py')],
            capture_output=True, text=True, cwd=repo_dir,
            env={**os.environ, 'PATH': f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"},
        )
        return jsonify({'ok': True, 'output': result.stdout})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/ingest', methods=['POST'])
def ingest_downloads():
    """Run ingest_downloads.py to extract and organize new sample packs."""
    repo_dir = current_app.config['REPO_DIR']
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(repo_dir, 'scripts', 'ingest_downloads.py')],
            capture_output=True, text=True, cwd=repo_dir,
            env={**os.environ, 'PATH': f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"},
            timeout=300,
        )
        # Parse the output for summary
        lines = result.stdout.strip().split('\n')
        summary = lines[-1] if lines else 'Done'
        return jsonify({'ok': True, 'output': result.stdout, 'summary': summary})
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'Ingest timed out (5min limit)'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/watcher/start', methods=['POST'])
def watcher_start():
    """Start the background file watcher."""
    try:
        sys.path.insert(0, os.path.join(current_app.config['REPO_DIR'], 'scripts'))
        import ingest_downloads as ingest
        # Reload to get fresh module state if restarting
        import importlib
        importlib.reload(ingest)

        if ingest.get_watcher_state()['running']:
            return jsonify({'ok': True, 'message': 'Watcher already running'})

        success = ingest.start_watcher()
        if success:
            return jsonify({'ok': True, 'message': 'Watcher started'})
        else:
            return jsonify({'ok': False, 'error': 'Failed to start watcher'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/watcher/stop', methods=['POST'])
def watcher_stop():
    """Stop the background file watcher."""
    try:
        sys.path.insert(0, os.path.join(current_app.config['REPO_DIR'], 'scripts'))
        import ingest_downloads as ingest

        ingest.stop_watcher()
        return jsonify({'ok': True, 'message': 'Watcher stopped'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/watcher/status')
def watcher_status():
    """Get watcher state and recent activity."""
    try:
        sys.path.insert(0, os.path.join(current_app.config['REPO_DIR'], 'scripts'))
        import ingest_downloads as ingest

        state = ingest.get_watcher_state()

        # Also read from ingest log for historical data
        log_path = os.path.join(os.path.expanduser("~/Music/SP404-Sample-Library"), "_ingest_log.json")
        log = []
        if os.path.exists(log_path):
            try:
                with open(log_path) as f:
                    log = json.load(f)
                # Return last 20 entries
                log = log[-20:]
            except (json.JSONDecodeError, IOError):
                pass

        return jsonify({
            'running': state['running'],
            'recent': state['recent'][-20:] if state['recent'] else log,
            'stats': state['stats'],
        })
    except Exception as e:
        return jsonify({'running': False, 'recent': [], 'stats': {}, 'error': str(e)})


@pipeline_bp.route('/pipeline/deploy', methods=['POST'])
def deploy():
    repo_dir = current_app.config['REPO_DIR']
    script = os.path.join(repo_dir, 'scripts', 'copy_to_sd.sh')
    if not os.path.isdir('/Volumes/SP-404SX'):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400
    try:
        result = subprocess.run(
            ['bash', script], capture_output=True, text=True, cwd=repo_dir,
            env={**os.environ, 'PATH': f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"},
        )
        return jsonify({'ok': True, 'output': result.stdout})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
