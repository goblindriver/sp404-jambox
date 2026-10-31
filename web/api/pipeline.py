"""Pipeline control API — fetch, build, deploy, watcher."""
import os, sys, time as _time, threading, subprocess, json
from flask import Blueprint, jsonify, request, current_app
from jambox_config import build_subprocess_env, find_sd_card, load_tag_db

from api._helpers import JobTracker, normalize_bank, normalize_pad

pipeline_bp = Blueprint('pipeline', __name__)

_tracker = JobTracker(max_age=600)
# execute_fetch_scope is shared by /pipeline/fetch and the vibe populate jobs;
# two runs at once would race on _CARD_STAGING and the score cache.
_FETCH_LOCK = threading.Lock()


class FetchBusy(RuntimeError):
    pass


def fetch_running():
    return _FETCH_LOCK.locked()
PADINFO_TIMEOUT = 120
PATTERN_BUILD_TIMEOUT = 180


def _settings():
    return current_app.config


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
    return normalize_pad(value)


def _normalize_bank_value(value):
    if value in (None, ''):
        return None
    return normalize_bank(value)


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


def execute_fetch_scope(settings, bank=None, pad=None, progress_callback=None):
    """Execute fetch_samples for a bank/pad scope and return run summary.

    Raises FetchBusy if another fetch is running.
    """
    if not _FETCH_LOCK.acquire(blocking=False):
        raise FetchBusy("A fetch is already running")
    try:
        return _execute_fetch_scope(settings, bank, pad, progress_callback)
    finally:
        _FETCH_LOCK.release()


def _execute_fetch_scope(settings, bank, pad, progress_callback):
    repo_dir = settings['REPO_DIR']
    scripts_dir = os.path.join(repo_dir, 'scripts')
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    import fetch_samples as fs
    from jambox_cache import load_score_cache, save_score_cache

    config = fs.load_config()
    os.makedirs(fs.STAGING, exist_ok=True)
    fs.clear_staging_wavs(bank=bank, pad=pad)

    tag_db = fs.load_tag_db()
    used_files = set()
    score_cache = load_score_cache(fs.LIBRARY)
    generated_files = []
    total_fetched = 0
    total_pads = 0

    pad_count_total = 0
    pad_count_done = 0
    for key, bank_config in config.items():
        if not key.startswith('bank_') or not bank_config:
            continue
        letter = key.split('_')[1]
        if bank and letter.lower() != bank.lower():
            continue
        pads = bank_config.get('pads', {})
        if pad is not None:
            pad_count_total += 1 if (pads.get(pad) or pads.get(str(pad))) else 0
        else:
            pad_count_total += len(pads)

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
                pad_count_done += 1
                pct = int(pad_count_done * 100 / max(pad_count_total, 1))
                if progress_callback:
                    progress_callback(f"Bank {letter.upper()} Pad {pad}", pct)
                result = fs.fetch_pad(letter, pad, pad_query, bank_config, tag_db, used_files, cache_entries=score_cache)
                if result:
                    total_fetched += 1
                    generated_files.append(result)
                total_pads += 1
        else:
            for pad_num, pad_query in pads.items():
                pad_num = int(pad_num)
                pad_count_done += 1
                pct = int(pad_count_done * 100 / max(pad_count_total, 1))
                if progress_callback:
                    progress_callback(f"Bank {letter.upper()} Pad {pad_num}: {str(pad_query)[:40]}", pct)
                result = fs.fetch_pad(letter, pad_num, pad_query, bank_config, tag_db, used_files, cache_entries=score_cache)
                if result:
                    total_fetched += 1
                    generated_files.append(result)
                total_pads += 1

    save_score_cache(fs.LIBRARY, score_cache)

    fs.publish_staging(bank=bank, pad=pad)

    return {
        'total_fetched': total_fetched,
        'total_pads': total_pads,
        'generated_files': generated_files,
    }


def _run_fetch(job_id, repo_dir, settings, bank=None, pad=None):
    """Run fetch_samples in a background thread."""
    try:
        _tracker.update(job_id, status='running')
        summary = execute_fetch_scope(
            settings,
            bank=bank,
            pad=pad,
            progress_callback=lambda progress, percent: _tracker.update(job_id, progress=progress, percent=percent),
        )

        _tracker.update(
            job_id,
            status='done',
            result=f"{summary['total_fetched']}/{summary['total_pads']} pads filled",
            finished_at=_time.time(),
        )

    except Exception as e:
        _tracker.update(job_id, status='error', result=str(e), finished_at=_time.time())


@pipeline_bp.route('/pipeline/fetch', methods=['POST'])
def fetch():
    data = request.get_json(silent=True) or {}
    try:
        bank = _normalize_bank_value(data.get('bank'))
        pad = _normalize_pad_value(data.get('pad'))
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    job_id = None if fetch_running() else _tracker.start_exclusive(
        ('starting', 'running'), type='fetch', status='starting', progress='', result='')
    if not job_id:
        return jsonify({'ok': False, 'error': 'Fetch already running'}), 409

    repo_dir = current_app.config['REPO_DIR']
    settings = dict(current_app.config)
    _tracker.start_thread(job_id, _run_fetch, job_id, repo_dir, settings, bank, pad, error_field='result')

    return jsonify({'ok': True, 'job_id': job_id})


@pipeline_bp.route('/pipeline/status/<job_id>')
def job_status(job_id):
    job = _tracker.get(job_id)
    if not job:
        return jsonify({'ok': False, 'error': 'Job not found'}), 404
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
        import ingest

        if ingest.get_watcher_state()['running']:
            return jsonify({'ok': True, 'message': 'Watcher already running'})

        # Run initial ingest in background, then start watching.
        # State stays False until start_watcher() actually succeeds.
        with ingest._watcher_lock:
            ingest._watcher_state['stats']['since'] = __import__('datetime').datetime.now().isoformat()

        def _start_with_ingest():
            try:
                ingest.one_shot_ingest()
            except Exception as e:
                print("[WATCHER] Initial ingest error: %s" % e)
            try:
                ingest.start_watcher()
                with ingest._watcher_lock:
                    ingest._watcher_state['running'] = True
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
        import ingest

        if ingest.stop_watcher():
            return jsonify({'ok': True, 'message': 'Watcher stopped'})
        return jsonify({'ok': True, 'message': 'Watcher stopping after the current file'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/watcher/status')
def watcher_status():
    """Get watcher state and recent activity."""
    try:
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ingest

        state = ingest.get_watcher_state()

        # Also read from ingest log for historical data
        log_path = _settings()['INGEST_LOG']
        log = []
        if os.path.exists(log_path):
            try:
                with open(log_path, encoding='utf-8') as f:
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
        return jsonify({'running': False, 'recent': [], 'stats': {}, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/disk-report')
def disk_report():
    """Get disk usage report."""
    try:
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ingest
        return jsonify(ingest.disk_usage_report())
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@pipeline_bp.route('/pipeline/cleanup', methods=['POST'])
def cleanup():
    """Remove already-ingested items from Downloads."""
    try:
        scripts_dir = os.path.join(current_app.config['REPO_DIR'], 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ingest

        data = request.get_json(silent=True) or {}
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
    import ingest

    if request.method == 'GET':
        return jsonify({'ok': True, 'path': ingest.DOWNLOADS})

    data = request.get_json(silent=True) or {}
    new_path = data.get('path', '')
    if not new_path:
        return jsonify({'ok': False, 'error': 'path required'}), 400
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
            import ingest
            features['watcher'] = ingest.get_watcher_state()['running']
        except Exception:
            features['watcher'] = False

        llm_endpoint = current_app.config.get('LLM_ENDPOINT', '')
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

        try:
            tags_file = current_app.config.get('TAGS_FILE', '')
            tag_db = load_tag_db(tags_file) if tags_file else {}
        except Exception:
            tag_db = {}

        clap_info = {'available': False, 'embedded': 0, 'coverage': 0}
        try:
            from clap_engine import EmbeddingStore
            library = current_app.config.get('SAMPLE_LIBRARY', '')
            store = EmbeddingStore(library)
            if tag_db:
                cov = round(store.count / max(1, len(tag_db)) * 100, 1)
            else:
                cov = 100.0 if store.count else 0.0
            clap_info = {
                'available': True,
                'embedded': store.count,
                'coverage': cov,
            }
            features['clap'] = store.count > 0
        except ImportError:
            features['clap'] = False

        discogs_info = {'available': False, 'classified': 0, 'coverage': 0, 'danceable': 0}
        try:
            # Status only: never download or load the ONNX model inside a request.
            import importlib.util
            from discogs_engine import model_path as _discogs_model_path
            if importlib.util.find_spec('onnxruntime') is None or not os.path.isfile(_discogs_model_path()):
                raise FileNotFoundError(_discogs_model_path())
            discogs_info['available'] = True
            features['discogs'] = True
            if tag_db:
                classified = sum(1 for e in tag_db.values() if e.get('discogs_styles'))
                danceable = sum(1 for e in tag_db.values() if (e.get('danceability') or 0) > 0.6)
                total = len(tag_db)
                discogs_info['classified'] = classified
                discogs_info['coverage'] = round(classified / max(1, total) * 100, 1)
                discogs_info['danceable'] = danceable
        except Exception:
            features['discogs'] = False

        return jsonify({
            'ok': True,
            'pid': os.getpid(),
            'features': features,
            'clap': clap_info,
            'discogs': discogs_info,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# Waits for the old server to exit (so the port is free), then starts web/app.py.
_RESTART_HELPER = (
    "import subprocess, sys\n"
    "import psutil\n"
    "try:\n"
    "    psutil.Process(int(sys.argv[1])).wait(timeout=30)\n"
    "except Exception:\n"
    "    pass\n"
    "subprocess.Popen([sys.executable, sys.argv[2]], cwd=sys.argv[3])\n"
)


def restart_helper_argv(python_bin, pid, app_py, web_dir):
    return [python_bin, "-c", _RESTART_HELPER, str(pid), app_py, web_dir]


@pipeline_bp.route('/pipeline/server/restart', methods=['POST'])
def server_restart():
    """Restart Flask: a detached helper relaunches app.py once this process exits."""
    import signal
    settings = dict(current_app.config)
    repo_dir = settings.get('REPO_DIR', current_app.config['REPO_DIR'])
    web_dir = os.path.join(repo_dir, 'web')
    app_py = os.path.join(web_dir, 'app.py')
    python_bin = os.path.abspath(sys.executable)
    env = build_subprocess_env(settings)

    def _restart():
        """Launch the relaunch helper, then terminate this process."""
        import time
        if os.name == 'nt':
            detach = {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            detach = {'start_new_session': True}
        try:
            subprocess.Popen(
                restart_helper_argv(python_bin, os.getpid(), app_py, web_dir),
                cwd=web_dir,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **detach,
            )
        except Exception:
            pass
        time.sleep(0.2)
        os.kill(os.getpid(), signal.SIGTERM)

    # Run in background so we can return the response first
    t = threading.Thread(target=_restart, daemon=True)
    t.start()
    return jsonify({'ok': True, 'message': 'Server restarting...'})


@pipeline_bp.route('/pipeline/deploy', methods=['POST'])
def deploy():
    card = find_sd_card(_settings())
    if not card or not os.path.isdir(card):
        return jsonify({'ok': False, 'error': 'SD card not mounted'}), 400
    try:
        import deploy_sd
        report = deploy_sd.deploy(card)
        return jsonify({'ok': True, 'output': deploy_sd.format_report(report), 'report': report})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
