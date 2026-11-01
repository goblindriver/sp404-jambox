import os
import sys

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


@pytest.fixture(autouse=True)
def _isolate_runtime_state(tmp_path, monkeypatch):
    """Keep tests out of real runtime state: data/vibe_sessions.sqlite feeds RAG,
    and data/fetch_history.json drives fetch diversity cooldowns."""
    import fetch_samples
    import vibe_training_store

    monkeypatch.setattr(vibe_training_store, "DB_PATH", str(tmp_path / "vibe_sessions.sqlite"))
    monkeypatch.setattr(fetch_samples, "FETCH_HISTORY_FILE", str(tmp_path / "fetch_history.json"))
