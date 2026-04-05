#!/usr/bin/env python3
"""SP-404 Jambox Web UI — Flask application."""
import os, sys

# Add scripts/ to path so we can import existing modules
SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, os.path.abspath(SCRIPT_DIR))

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from jambox_config import ConfigError, load_settings

app = Flask(__name__,
    template_folder='templates',
    static_folder='static',
)
repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
try:
    app.config.update(load_settings(repo_dir))
except ConfigError as exc:
    raise RuntimeError(f"Configuration error: {exc}") from exc

# Register API blueprints
from api.banks import banks_bp
from api.audio import audio_bp
from api.pipeline import pipeline_bp
from api.library import library_bp
from api.sdcard import sdcard_bp
from api.music import music_bp
from api.presets import presets_bp
from api.vibe import vibe_bp
from api.pattern import pattern_bp
from api.media import media_bp
from api.blackout import blackout_bp

app.register_blueprint(banks_bp, url_prefix='/api')
app.register_blueprint(audio_bp, url_prefix='/api')
app.register_blueprint(pipeline_bp, url_prefix='/api')
app.register_blueprint(library_bp, url_prefix='/api')
app.register_blueprint(sdcard_bp, url_prefix='/api')
app.register_blueprint(music_bp, url_prefix='/api')
app.register_blueprint(presets_bp, url_prefix='/api')
app.register_blueprint(vibe_bp, url_prefix='/api')
app.register_blueprint(pattern_bp, url_prefix='/api')
app.register_blueprint(media_bp, url_prefix='/api')
app.register_blueprint(blackout_bp, url_prefix='/api')


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    if request.path.startswith('/api/'):
        return jsonify({'error': exc.description, 'ok': False}), exc.code
    return exc.get_response()


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    if request.path.startswith('/api/'):
        app.logger.exception("Unhandled error on %s", request.path)
        return jsonify({'error': 'Internal server error', 'ok': False}), 500
    raise exc


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    print("SP-404 Jambox UI: http://localhost:5404")
    app.run(host='127.0.0.1', port=5404, debug=app.config['WEB_DEBUG'])
