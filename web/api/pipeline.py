"""Pipeline control API — fetch, build, deploy, watcher."""
import os, sys, threading, subprocess, uuid, json
from flask import Blueprint, jsonify, request, current_app
from jambox_config import build_subprocess_env

pipeline_bp = Blueprint('pipeline', __name__)

# In-memory job tracking
_jobs = {}
_job_lock = threading.Lock()
PADINFO_TIMEOUT = 120
PATTERN_BUILD_TIMEOUT = 180
DEPLOY_TIMEOUT = 180


def _settings():
    return current_app.config


def _clear_staging_wavs(staging_dir):
    """Remove only generated pad WAVs so a run starts cleanly."""
    if not os.path.isdir(staging_dir):
        return

    for name in os.listdir(staging_dir):
        if name.upper().endswith('.WAV'):
            os.remove(os.path.join(staging_dir, name))


def _command_error_payload(result):
    stderr = (result.stderr or '').strip()
    stdout = (result.stdout or '').strip()
    message = stderr or stdout or 'Command failed'
    payload = {'ok': False, 'error': message}
    if stdout:
        payload['output'] = stdout
    if stderr:
        payload['stderr'] = stderr
    return payload


def _normalize_pad_value(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('pad must be an integer') from exc


def _run_script(script_name, timeout=None):
    repo_dir = _settings()['REPO_DIR']
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(repo_dir, 'scripts', script_name)],
            capture_output=True,
            text=True,
            cwd=repo_dir,
            env=build_subprocess_env(_settings()),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        script_label = script_name.removesuffix('.py')
        return jsonify({'ok': False, 'error': f'{script_label} timed out'}), 500
    if result.returncode != 0:
        return jsonify(_command_error_payload(result)), 500

    payload = {'ok': True, 'output': result.stdout}
    return jsonify(payload)


def _run_fetch(job_id, repo_dir, settings, bank=None, pad=None):
    """Run fetch_samples in a background thread."""
    try:
        sys.path.insert(0, os.path.join(repo_dir, 'scripts'))
        import fetch_samples as fs

        _jobs[job_id]['status'] = 'running'
        config = fs.load_config()
        os.makedirs(fs.STAGING, exist_ok=True)
        _clear_staging_wavs(fs.STAGING)

        # Load tag database and init deduplication set
        tag_db = fs.load_tag_db()
        used_files = set()
        generated_files = []

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

            if pad is not None:
                pad_query = pads.get(pad)
                if pad_query is None:
                    pad_query = pads.get(str(pad))
                if pad_query:
                    _jobs[job_id]['progress'] = f"Bank {letter.upper()} Pad {pad}"
                    result = fs.fetch_pad(letter, pad, pad_query, bank_config, tag_db, used_files)
                    if result:
                        total_fetched += 1
                        generated_files.append(result)
                    total_pads += 1
            else:
                for pad_num, pad_query in pads.items():
                    pad_num = int(pad_num)
                    _jobs[job_id]['progress'] = f"Bank {letter.upper()} Pad {pad_num}: {pad_query[:40]}"
                    result = fs.fetch_pad(letter, pad_num, pad_query, bank_config, tag_db, used_files)
                    if result:
                        total_fetched += 1
                        generated_files.append(result)
                    total_pads += 1

        # Copy to SMPL
        smpl_dir = settings['SMPL_DIR']
        if total_fetched > 0:
            os.makedirs(smpl_dir, exist_ok=True)
            import shutil
            for f in generated_files:
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
    try:
        pad = _normalize_pad_value(data.get('pad'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    # Only one fetch at a time
    with _job_lock:
        for j in _jobs.values():
            if j['type'] == 'fetch' and j['status'] in {'starting', 'running'}:
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
    settings = dict(current_app.config)
    t = threading.Thread(target=_run_fetch, args=(job_id, repo_dir, settings, bank, pad))
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
    try:
        return _run_script('gen_padinfo.py', timeout=PADINFO_TIMEOUT)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/patterns', methods=['POST'])
def build_patterns():
    try:
        return _run_script('gen_patterns.py', timeout=PATTERN_BUILD_TIMEOUT)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/ingest', methods=['POST'])
def ingest_downloads():
    """Run ingest_downloads.py to extract and organize new sample packs."""
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(_settings()['REPO_DIR'], 'scripts', 'ingest_downloads.py')],
            capture_output=True, text=True, cwd=_settings()['REPO_DIR'],
            env=build_subprocess_env(_settings()),
            timeout=300,
        )
        if result.returncode != 0:
            return jsonify(_command_error_payload(result)), 500
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
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ingest_downloads as ingest

        if ingest.get_watcher_state()['running']:
            return jsonify({'ok': True, 'message': 'Watcher already running'})

        # Run initial ingest in background, then start watching.
        # Set watcher state active immediately so the UI stays lit.
        with ingest._watcher_lock:
            ingest._watcher_state['running'] = True
            ingest._watcher_state['stats']['since'] = __import__('datetime').datetime.now().isoformat()

        def _start_with_ingest():
            try:
                ingest.one_shot_ingest()
            except Exception as e:
                print("[WATCHER] Initial ingest error: %s" % e)
            try:
                ingest.start_watcher()
            except Exception as e:
                print("[WATCHER] Start error: %s" % e)
                with ingest._watcher_lock:
                    ingest._watcher_state['running'] = False

        t = threading.Thread(target=_start_with_ingest, daemon=True)
        t.start()
        return jsonify({'ok': True, 'message': 'Running initial ingest, then watching'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/watcher/stop', methods=['POST'])
def watcher_stop():
    """Stop the background file watcher."""
    try:
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ingest_downloads as ingest

        ingest.stop_watcher()
        return jsonify({'ok': True, 'message': 'Watcher stopped'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/watcher/status')
def watcher_status():
    """Get watcher state and recent activity."""
    try:
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ingest_downloads as ingest

        state = ingest.get_watcher_state()

        # Also read from ingest log for historical data
        log_path = _settings()['INGEST_LOG']
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


@pipeline_bp.route('/pipeline/disk-report')
def disk_report():
    """Get disk usage report."""
    try:
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ingest_downloads as ingest
        return jsonify(ingest.disk_usage_report())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pipeline_bp.route('/pipeline/cleanup', methods=['POST'])
def cleanup():
    """Remove already-ingested items from Downloads."""
    try:
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ingest_downloads as ingest

        data = request.get_json() or {}
        purge_archive = data.get('purge_archive', False)

        freed1, count1 = ingest.cleanup_downloads()
        freed2, count2 = 0, 0
        if purge_archive:
            freed2, count2 = ingest.purge_raw_archive()

        total_freed = freed1 + freed2
        total_count = count1 + count2
        return jsonify({
            'ok': True,
            'freed': total_freed,
            'freed_str': ingest._human_size(total_freed),
            'count': total_count,
            'downloads_cleaned': count1,
            'archive_purged': count2,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/downloads-path', methods=['GET', 'POST'])
def downloads_path():
    """Get or set the downloads watch path."""
    scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import ingest_downloads as ingest

    if request.method == 'GET':
        return jsonify({'path': ingest.DOWNLOADS})

    data = request.get_json() or {}
    new_path = data.get('path', '')
    if not new_path:
        return jsonify({'error': 'path required'}), 400
    try:
        result = ingest.set_downloads_path(new_path)
        return jsonify({'ok': True, 'path': result})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@pipeline_bp.route('/pipeline/server/status')
def server_status():
    """Server health check with uptime and feature availability."""
    import time
    try:
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        # Check feature availability
        features = {}
        try:
            from audio_analysis import is_available
            features['librosa'] = is_available()
        except ImportError:
            features['librosa'] = False

        try:
            import ingest_downloads as ingest
            features['watcher'] = ingest.get_watcher_state()['running']
        except Exception:
            features['watcher'] = False

        llm_endpoint = os.environ.get('SP404_LLM_ENDPOINT', '')
        features['llm'] = bool(llm_endpoint)

        try:
            import demucs
            features['demucs'] = True
        except ImportError:
            features['demucs'] = False

        try:
            tool = current_app.config.get('FINGERPRINT_TOOL', 'fpcalc')
            subprocess.run([tool, '-version'], capture_output=True, timeout=5)
            features['fpcalc'] = True
        except Exception:
            features['fpcalc'] = False

        return jsonify({
            'ok': True,
            'pid': os.getpid(),
            'features': features,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/server/restart', methods=['POST'])
def server_restart():
    """Gracefully restart the Flask server by re-exec'ing the process."""
    import signal

    def _restart():
        """Send SIGTERM to self — the launch wrapper or preview_start will respawn."""
        import time
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    # Run in background so we can return the response first
    t = threading.Thread(target=_restart, daemon=True)
    t.start()
    return jsonify({'ok': True, 'message': 'Server restarting...'})


@pipeline_bp.route('/pipeline/deploy', methods=['POST'])
def deploy():
    repo_dir = _settings()['REPO_DIR']
    script = os.path.join(repo_dir, 'scripts', 'copy_to_sd.sh')
    if not os.path.isdir(_settings()['SD_CARD']):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400
    try:
        result = subprocess.run(
            ['bash', script], capture_output=True, text=True, cwd=repo_dir,
            env=build_subprocess_env(_settings()),
            timeout=DEPLOY_TIMEOUT,
        )
        if result.returncode != 0:
            return jsonify(_command_error_payload(result)), 500
        return jsonify({'ok': True, 'output': result.stdout})
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'Deploy timed out'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
