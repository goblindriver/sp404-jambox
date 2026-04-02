#!/usr/bin/env python3
"""SP-404 Jambox Web UI — Flask application."""
import os, sys

# Add scripts/ to path so we can import existing modules
SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, os.path.abspath(SCRIPT_DIR))

from flask import Flask, render_template

app = Flask(__name__,
    template_folder='templates',
    static_folder='static',
)
app.config['REPO_DIR'] = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Register API blueprints
from api.banks import banks_bp
from api.audio import audio_bp
from api.pipeline import pipeline_bp
from api.library import library_bp
from api.sdcard import sdcard_bp
from api.music import music_bp

app.register_blueprint(banks_bp, url_prefix='/api')
app.register_blueprint(audio_bp, url_prefix='/api')
app.register_blueprint(pipeline_bp, url_prefix='/api')
app.register_blueprint(library_bp, url_prefix='/api')
app.register_blueprint(sdcard_bp, url_prefix='/api')
app.register_blueprint(music_bp, url_prefix='/api')


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    print("SP-404 Jambox UI: http://localhost:5404")
    app.run(host='127.0.0.1', port=5404, debug=True)
