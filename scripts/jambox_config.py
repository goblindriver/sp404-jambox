"""Shared runtime settings for the SP-404 Jambox app and scripts."""

import json
import os
import shutil


def _load_dotenv():
    """Load .env file from repo root into os.environ (only if not already set)."""
    # Walk up from this file to find the repo root
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    env_file = os.path.join(repo_root, ".env")
    if not os.path.isfile(env_file):
        return
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Don't override existing env vars
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


_load_dotenv()


DEFAULT_SAMPLE_LIBRARY = "~/Music/SP404-Sample-Library"
DEFAULT_DOWNLOADS = "~/Downloads"
DEFAULT_SD_CARD = "/Volumes/SP-404SX"
DEFAULT_TOOL_PATH_PREFIX = "/opt/homebrew/bin"
DEFAULT_LLM_TIMEOUT = 30


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


def _normalize_path(path_value):
    return os.path.abspath(os.path.expanduser(path_value))


def _read_required_path(name, default):
    value = os.environ.get(name)
    if value is None:
        return _normalize_path(default)

    value = value.strip()
    if not value:
        raise ConfigError(f"{name} cannot be empty")
    return _normalize_path(value)


def _read_optional_path(name, default=""):
    value = os.environ.get(name)
    if value is None:
        return _normalize_path(default) if default else ""

    value = value.strip()
    if not value:
        return ""
    return _normalize_path(value)


def _read_command(name, default):
    value = os.environ.get(name)
    if value is None:
        return default

    value = value.strip()
    if not value:
        raise ConfigError(f"{name} cannot be empty")
    return value


def _read_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be one of: 1, 0, true, false, yes, no, on, off")


def _read_int(name, default, minimum=None):
    value = os.environ.get(name)
    if value is None:
        return default

    value = value.strip()
    if not value:
        raise ConfigError(f"{name} cannot be empty")

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc

    if minimum is not None and parsed < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return parsed


def _read_optional_int(name, default=None, minimum=None):
    """Like _read_int but returns default when the variable is unset or empty."""
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return parsed


def _read_choice(name, default, choices):
    value = os.environ.get(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if not normalized:
        raise ConfigError(f"{name} cannot be empty")
    if normalized not in choices:
        allowed = ", ".join(sorted(choices))
        raise ConfigError(f"{name} must be one of: {allowed}")
    return normalized


def load_settings(repo_dir):
    """Load environment-backed settings with development-friendly defaults."""
    repo_dir = _normalize_path(repo_dir)
    sample_library = _read_required_path("SP404_SAMPLE_LIBRARY", DEFAULT_SAMPLE_LIBRARY)
    downloads_path = _read_required_path("SP404_DOWNLOADS", DEFAULT_DOWNLOADS)
    sd_card = _read_required_path("SP404_SD_CARD", DEFAULT_SD_CARD)
    tool_path_prefix = _read_optional_path("SP404_TOOL_PATH_PREFIX", DEFAULT_TOOL_PATH_PREFIX)

    return {
        "REPO_DIR": repo_dir,
        "SAMPLE_LIBRARY": sample_library,
        "DOWNLOADS_PATH": downloads_path,
        "SD_CARD": sd_card,
        "SD_SMPL_DIR": os.path.join(sd_card, "ROLAND", "SP-404SX", "SMPL"),
        "GOLD_BANK_A_DIR": os.path.join(sample_library, "_GOLD", "Bank-A"),
        "INGEST_LOG": os.path.join(sample_library, "_ingest_log.json"),
        "RAW_ARCHIVE": os.path.join(sample_library, "_RAW-DOWNLOADS"),
        "TAGS_FILE": os.path.join(sample_library, "_tags.json"),
        "MUSIC_INDEX_FILE": os.path.join(sample_library, "_music_index.json"),
        "STEMS_DIR": os.path.join(sample_library, "Stems"),
        "STAGING_DIR": os.path.join(repo_dir, "_CARD_STAGING"),
        "SMPL_DIR": os.path.join(repo_dir, "sd-card-template", "ROLAND", "SP-404SX", "SMPL"),
        "CONFIG_PATH": os.path.join(repo_dir, "bank_config.yaml"),
        "VIBE_MAPPINGS_PATH": os.path.join(repo_dir, "config", "vibe_mappings.yaml"),
        "SCORING_CONFIG_PATH": os.path.join(repo_dir, "config", "scoring.yaml"),
        "FFMPEG_BIN": _read_command("SP404_FFMPEG", os.path.join(DEFAULT_TOOL_PATH_PREFIX, "ffmpeg")),
        "FFPROBE_BIN": _read_command("SP404_FFPROBE", os.path.join(DEFAULT_TOOL_PATH_PREFIX, "ffprobe")),
        "UNAR_BIN": _read_command("SP404_UNAR", os.path.join(DEFAULT_TOOL_PATH_PREFIX, "unar")),
        "TOOL_PATH_PREFIX": tool_path_prefix,
        "WEB_DEBUG": _read_bool("SP404_WEB_DEBUG", default=False),
        "LLM_ENDPOINT": _read_command("SP404_LLM_ENDPOINT", ""),
        "LLM_MODEL": _read_command("SP404_LLM_MODEL", "qwen3"),
        # smart_retag: model for LONG clips only (see SMART_RETAG_DURATION_SPLIT_SEC). Empty = qwen3:8b.
        "SMART_RETAG_LLM_MODEL": _read_command("SP404_SMART_RETAG_LLM_MODEL", ""),
        "SMART_RETAG_DURATION_SPLIT_SEC": _read_int(
            "SP404_SMART_RETAG_DURATION_SPLIT_SEC", 60, minimum=0
        ),
        "SMART_RETAG_SKIP_ABOVE_SECONDS": _read_optional_int(
            "SP404_SMART_RETAG_SKIP_ABOVE_SECONDS", default=None, minimum=1
        ),
        "LLM_TIMEOUT": _read_int("SP404_LLM_TIMEOUT", DEFAULT_LLM_TIMEOUT, minimum=1),
        # smart_retag only: longer HTTP read than vibe UI; unset = script default floor
        "SMART_RETAG_LLM_TIMEOUT": _read_optional_int(
            "SP404_SMART_RETAG_LLM_TIMEOUT", default=None, minimum=60
        ),
        "SMART_RETAG_LLM_RETRIES": _read_optional_int(
            "SP404_SMART_RETAG_LLM_RETRIES", default=None, minimum=0
        ),
        "MUSICVAE_CHECKPOINT_DIR": _read_optional_path(
            "SP404_MUSICVAE_CHECKPOINT_DIR", os.path.join(repo_dir, "models", "musicvae")
        ),
        "MAGENTA_COMMAND": _read_command("SP404_MAGENTA_COMMAND", "music_vae_generate"),
        "FINGERPRINT_TOOL": _read_command("SP404_FINGERPRINT_TOOL", os.path.join(DEFAULT_TOOL_PATH_PREFIX, "fpcalc")),
        "DAILY_BANK_SOURCE": _read_choice("SP404_DAILY_BANK_SOURCE", "recent", {"recent", "trending"}),
        "TRENDING_FILE": _read_optional_path("SP404_TRENDING_FILE", os.path.join(repo_dir, "trending.json")),
        "VIBE_DATA_DIR": os.path.join(repo_dir, "data"),
        "VIBE_SESSIONS_DB": os.path.join(repo_dir, "data", "vibe_sessions.sqlite"),
        "VIBE_EVAL_DIR": os.path.join(repo_dir, "data", "evals"),
        "VIBE_PARSER_MODE": _read_choice("SP404_VIBE_PARSER_MODE", "base", {"base", "rag", "fine_tuned"}),
        "FINE_TUNED_LLM_ENDPOINT": _read_command("SP404_FINE_TUNED_LLM_ENDPOINT", ""),
        "FINE_TUNED_LLM_MODEL": _read_command("SP404_FINE_TUNED_LLM_MODEL", ""),
        "VIBE_RETRIEVAL_LIMIT": _read_int("SP404_VIBE_RETRIEVAL_LIMIT", 4, minimum=0),
        # Optional second clone: blackout "Live crunch" reads retag checkpoint + crunch logs here
        "CRUNCH_REPO": _read_optional_path("SP404_CRUNCH_REPO", ""),
    }


def _tags_sqlite_path(tags_file):
    """Derive SQLite path from the JSON tags file path."""
    return os.path.splitext(tags_file)[0] + ".sqlite"


def _ensure_tags_sqlite(db_path):
    """Create the tags SQLite database if it doesn't exist."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            rel_path TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _migrate_json_to_sqlite(json_path, db_path):
    """One-time migration: import existing JSON tags into SQLite."""
    import sqlite3
    try:
        with open(json_path, "r") as fh:
            payload = json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict) or not payload:
        return

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            rel_path TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)
    # Batch insert
    conn.executemany(
        "INSERT OR REPLACE INTO tags (rel_path, data) VALUES (?, ?)",
        [(k, json.dumps(v)) for k, v in payload.items()]
    )
    conn.commit()
    conn.close()
    print(f"[TAG_DB] Migrated {len(payload)} entries from JSON to SQLite")


def load_tag_db(tags_file):
    """Load the tag database. Uses SQLite backend, falls back to JSON.

    Auto-migrates from JSON on first use. Returns a dict (rel_path -> tag entry).
    """
    import sqlite3
    db_path = _tags_sqlite_path(tags_file)

    # Auto-migrate from JSON if SQLite doesn't exist yet
    if not os.path.exists(db_path) and os.path.exists(tags_file):
        _migrate_json_to_sqlite(tags_file, db_path)

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute("SELECT rel_path, data FROM tags").fetchall()
            conn.close()
            result = {}
            for rel_path, data in rows:
                try:
                    result[rel_path] = json.loads(data)
                except (json.JSONDecodeError, ValueError):
                    pass
            return result
        except sqlite3.Error:
            pass

    # Fallback to JSON
    try:
        with open(tags_file, "r") as fh:
            payload = json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_tag_db(tags_file, db):
    """Save the tag database to SQLite. Also writes JSON for compatibility."""
    import sqlite3
    db_path = _tags_sqlite_path(tags_file)

    conn = _ensure_tags_sqlite(db_path)
    # Batch upsert
    conn.executemany(
        "INSERT OR REPLACE INTO tags (rel_path, data) VALUES (?, ?)",
        [(k, json.dumps(v)) for k, v in db.items()]
    )
    # Remove stale rows (files no longer in the db dict)
    existing = {r[0] for r in conn.execute("SELECT rel_path FROM tags").fetchall()}
    stale = existing - set(db.keys())
    if stale:
        conn.executemany("DELETE FROM tags WHERE rel_path=?", [(k,) for k in stale])
    conn.commit()
    conn.close()

    # Also write JSON for backward compatibility and human readability
    # (skip if file would be >50MB to avoid slowdowns)
    estimated_size = len(db) * 1100  # ~1.1KB avg per entry
    if estimated_size < 50 * 1024 * 1024:
        try:
            with open(tags_file, "w") as fh:
                json.dump(db, fh, indent=1, sort_keys=True)
        except OSError:
            pass


def load_settings_for_script(script_file):
    """Load settings for a script living in the repo's scripts directory."""
    script_dir = os.path.dirname(os.path.abspath(script_file))
    repo_dir = os.path.dirname(script_dir)
    return load_settings(repo_dir)


def build_subprocess_env(settings, base_env=None):
    """Build an environment with the configured tool path prefix on PATH."""
    env = dict(base_env or os.environ)
    path_prefix = settings.get("TOOL_PATH_PREFIX", "")
    if not path_prefix:
        return env

    current_path = env.get("PATH", "")
    env["PATH"] = f"{path_prefix}:{current_path}" if current_path else path_prefix
    return env


def resolve_command(command, env=None):
    """Resolve a configured command to an executable path if possible."""
    command = (command or "").strip()
    if not command:
        return None

    env = dict(env or os.environ)
    executable = command.split()[0]
    if os.path.isabs(executable):
        return executable if os.path.isfile(executable) and os.access(executable, os.X_OK) else None
    return shutil.which(executable, path=env.get("PATH"))
