"""Shared runtime settings for the SP-404 Jambox app and scripts."""

import contextlib
import json
import os
import shutil
import subprocess
import sys
import time

import yaml


def _load_dotenv():
    """Load .env file from repo root into os.environ (only if not already set)."""
    # Walk up from this file to find the repo root
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    env_file = os.path.join(repo_root, ".env")
    if not os.path.isfile(env_file):
        return
    try:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


_load_dotenv()


DEFAULT_SAMPLE_LIBRARY = "~/Music/SP404-Sample-Library"
DEFAULT_DOWNLOADS = "~/Downloads"
IS_MACOS = sys.platform == "darwin"
# macOS mounts the card at a fixed path; elsewhere it is auto-detected
# (find_sd_card) unless SP404_SD_CARD is set.
DEFAULT_SD_CARD = "/Volumes/SP-404SX" if IS_MACOS else ""
DEFAULT_QNAP_ROOT = "/Volumes/Temp QNAP"
DEFAULT_DROBO_ROOT = "/Volumes/Jansen's FL Drobo"
# Homebrew's bin isn't always on PATH for GUI-launched apps on macOS; other
# platforms find tools on PATH.
DEFAULT_TOOL_PATH_PREFIX = "/opt/homebrew/bin" if IS_MACOS else ""
SD_SMPL_PARTS = ("ROLAND", "SP-404SX", "SMPL")


def default_plex_data_dir():
    """Plex Media Server's data folder for this OS (holds the library DB and art)."""
    if IS_MACOS:
        return "~/Library/Application Support/Plex Media Server"
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return os.path.join(local, "Plex Media Server")
    return "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server"


def plex_data_dir():
    """SP404_PLEX_DATA_DIR, or the OS default Plex data folder."""
    return os.path.abspath(os.path.expanduser(
        os.environ.get("SP404_PLEX_DATA_DIR") or default_plex_data_dir()
    ))


def find_sd_card(settings):
    """Root of the mounted SP-404 card, or None.

    An explicit SP404_SD_CARD (or the macOS default) wins. Otherwise look for
    a mounted volume holding ROLAND/SP-404SX (drive letters on Windows,
    /media and /run/media mounts on Linux).
    """
    configured = (settings or {}).get("SD_CARD")
    if configured:
        return configured
    try:
        import psutil
        mounts = [p.mountpoint for p in psutil.disk_partitions(all=False)]
    except Exception:
        mounts = []
    for mount in mounts:
        if os.path.isdir(os.path.join(mount, "ROLAND", "SP-404SX")):
            return mount
    return None


def sd_smpl_dir(card_root):
    """SMPL folder on a card root ('' when no card)."""
    return os.path.join(card_root, *SD_SMPL_PARTS) if card_root else ""


def _tool_default(name, prefix):
    """Tool path under the configured prefix when it exists there, else the bare name (PATH lookup)."""
    if prefix:
        for candidate in (os.path.join(prefix, name), os.path.join(prefix, name + ".exe")):
            if os.path.isfile(candidate):
                return candidate
    return name
DEFAULT_LLM_TIMEOUT = 30

# Raw/long material lives here until chopped; excluded from pad fetch and bulk library walks.
LONG_HOLD_DIRNAME = "_LONG-HOLD"
# library_trim moves cut files here (one folder per run) instead of deleting them.
TRASH_DIRNAME = "_TRASH"

# Canonical set of directories to skip in library walks.
# Every script that walks the sample library should import this instead of
# defining its own copy.  ".git" is omitted because library roots should not
# be repos; add it locally only if you scan a repo tree.
LIBRARY_SKIP_DIRS = frozenset({
    "_RAW-DOWNLOADS",
    "_GOLD",
    "_DUPES",
    "_QUARANTINE",
    "Stems",
    LONG_HOLD_DIRNAME,
    TRASH_DIRNAME,
})

_EXCLUDED_PREFIXES = LIBRARY_SKIP_DIRS


def is_excluded_rel_path(rel_path):
    """True if *rel_path* is under any internal/triage folder."""
    if not rel_path or not isinstance(rel_path, str):
        return False
    norm = rel_path.replace("\\", "/").lstrip("/")
    if not norm:
        return False
    top = norm.split("/", 1)[0]
    return top in _EXCLUDED_PREFIXES


def is_long_hold_rel_path(rel_path):
    """True if *rel_path* is under the long-sample holding folder."""
    if not rel_path or not isinstance(rel_path, str):
        return False
    norm = rel_path.replace("\\", "/").lstrip("/")
    if not norm:
        return False
    return norm.split("/", 1)[0] == LONG_HOLD_DIRNAME


def atomic_write_json(path, data, indent=2, sort_keys=True):
    """Write a JSON file atomically via temp-file-then-rename."""
    import tempfile
    target_dir = os.path.dirname(path) or "."
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent, sort_keys=sort_keys)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_yaml(path, data, **kwargs):
    """Write a YAML file atomically via temp-file-then-rename."""
    import tempfile
    import yaml
    target_dir = os.path.dirname(path) or "."
    os.makedirs(target_dir, exist_ok=True)
    kwargs.setdefault("default_flow_style", False)
    kwargs.setdefault("allow_unicode", True)
    kwargs.setdefault("sort_keys", False)
    fd, tmp = tempfile.mkstemp(suffix=".yaml", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, **kwargs)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextlib.contextmanager
def file_lock(path, timeout=60):
    """Hold an exclusive inter-process lock on ``path + ".lock"``.

    Uses fcntl on POSIX and msvcrt on Windows so read-modify-write cycles on
    shared JSON files (ingest log, caches) don't interleave across processes.
    """
    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    with open(lock_path, "a+b") as fh:
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + timeout
            fh.seek(0)
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Timed out waiting for lock: {lock_path}")
                    time.sleep(0.05)
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)


def ffmpeg_atomic(ffmpeg, src, dest, out_args, *, fmt, timeout):
    """Run ffmpeg into ``dest + ".part"`` and rename it into place on success.

    A failed, killed or timed-out run never leaves a file at *dest*, so
    "the output exists" stays a reliable "already done" check for ingest and
    conversion. Returns True on success.
    """
    part = dest + ".part"
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", src, *out_args, "-f", fmt, part],
            capture_output=True, timeout=timeout,
        )
        if result.returncode == 0 and os.path.getsize(part) > 0:
            os.replace(part, dest)
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        if os.path.exists(part):
            os.remove(part)
    return False


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
    sd_card = _read_optional_path("SP404_SD_CARD", DEFAULT_SD_CARD)
    qnap_root = _read_required_path("SP404_QNAP_ROOT", DEFAULT_QNAP_ROOT)
    drobo_root = _read_required_path("SP404_DROBO_ROOT", DEFAULT_DROBO_ROOT)
    tool_path_prefix = _read_optional_path("SP404_TOOL_PATH_PREFIX", DEFAULT_TOOL_PATH_PREFIX)

    smart_retag_workers_max = _read_int("SP404_SMART_RETAG_WORKERS_MAX", 16, minimum=1)
    smart_retag_workers = max(
        1,
        min(_read_int("SP404_SMART_RETAG_WORKERS", 3, minimum=1), smart_retag_workers_max),
    )

    return {
        "REPO_DIR": repo_dir,
        "SAMPLE_LIBRARY": sample_library,
        "DOWNLOADS_PATH": downloads_path,
        "SD_CARD": sd_card,
        "QNAP_ROOT": qnap_root,
        "DROBO_ROOT": drobo_root,
        "SD_SMPL_DIR": sd_smpl_dir(sd_card),
        "PLEX_DATA_DIR": plex_data_dir(),
        "WEB_PORT": _read_int("SP404_WEB_PORT", 5404, minimum=1),
        # Extra Host values the web UI accepts besides localhost (comma-separated)
        "WEB_ALLOWED_HOSTS": os.environ.get("SP404_WEB_ALLOWED_HOSTS", ""),
        "GOLD_BANK_A_DIR": os.path.join(sample_library, "_GOLD", "Bank-A"),
        "INGEST_LOG": os.path.join(sample_library, "_ingest_log.json"),
        "RAW_ARCHIVE": os.path.join(sample_library, "_RAW-DOWNLOADS"),
        "LONG_HOLD_DIR": os.path.join(sample_library, LONG_HOLD_DIRNAME),
        "LONG_HOLD_MIN_SECONDS": _read_int("SP404_LONG_HOLD_MIN_SECONDS", 120, minimum=1),
        "TAGS_FILE": os.path.join(sample_library, "_tags.json"),
        "MUSIC_INDEX_FILE": os.path.join(sample_library, "_music_index.json"),
        "STEMS_DIR": os.path.join(sample_library, "Stems"),
        "STAGING_DIR": os.path.join(repo_dir, "_CARD_STAGING"),
        "SMPL_DIR": os.path.join(repo_dir, "sd-card-template", "ROLAND", "SP-404SX", "SMPL"),
        "CONFIG_PATH": os.path.join(repo_dir, "bank_config.yaml"),
        "VIBE_MAPPINGS_PATH": os.path.join(repo_dir, "config", "vibe_mappings.yaml"),
        "SCORING_CONFIG_PATH": os.path.join(repo_dir, "config", "scoring.yaml"),
        "FFMPEG_BIN": _read_command("SP404_FFMPEG", _tool_default("ffmpeg", tool_path_prefix)),
        "FFPROBE_BIN": _read_command("SP404_FFPROBE", _tool_default("ffprobe", tool_path_prefix)),
        "UNAR_BIN": _read_command("SP404_UNAR", _tool_default("unar", tool_path_prefix)),
        "TOOL_PATH_PREFIX": tool_path_prefix,
        "WEB_DEBUG": _read_bool("SP404_WEB_DEBUG", default=False),
        "LLM_ENDPOINT": _read_command("SP404_LLM_ENDPOINT", ""),
        "LLM_MODEL": _read_command("SP404_LLM_MODEL", "qwen3.5:9b"),
        "SMART_RETAG_SKIP_ABOVE_SECONDS": _read_optional_int(
            "SP404_SMART_RETAG_SKIP_ABOVE_SECONDS", default=None, minimum=1
        ),
        "LLM_TIMEOUT": _read_int("SP404_LLM_TIMEOUT", DEFAULT_LLM_TIMEOUT, minimum=1),
        # Per-call max_tokens caps. Smaller caps = lower latency; LLM outputs for
        # these tasks are bounded (vibe tags ~200-300 tok, bank metadata <100 tok).
        "VIBE_PARSE_MAX_TOKENS": _read_int("SP404_VIBE_PARSE_MAX_TOKENS", 400, minimum=50),
        "VIBE_INSPIRE_MAX_TOKENS": _read_int("SP404_VIBE_INSPIRE_MAX_TOKENS", 200, minimum=50),
        "DEDUP_TAG_MAX_TOKENS": _read_int("SP404_DEDUP_TAG_MAX_TOKENS", 200, minimum=50),
        "SMART_RETAG_MAX_TOKENS": _read_int("SP404_SMART_RETAG_MAX_TOKENS", 2048, minimum=256),
        # smart_retag only: longer HTTP read than vibe UI; unset = script default floor
        "SMART_RETAG_LLM_TIMEOUT": _read_optional_int(
            "SP404_SMART_RETAG_LLM_TIMEOUT", default=None, minimum=60
        ),
        "SMART_RETAG_LLM_RETRIES": _read_optional_int(
            "SP404_SMART_RETAG_LLM_RETRIES", default=None, minimum=0
        ),
        "SMART_RETAG_WORKERS_MAX": smart_retag_workers_max,
        "SMART_RETAG_WORKERS": smart_retag_workers,
        "MUSICVAE_CHECKPOINT_DIR": _read_optional_path(
            "SP404_MUSICVAE_CHECKPOINT_DIR", os.path.join(repo_dir, "models", "musicvae")
        ),
        "MAGENTA_COMMAND": _read_command("SP404_MAGENTA_COMMAND", "music_vae_generate"),
        "FINGERPRINT_TOOL": _read_command("SP404_FINGERPRINT_TOOL", _tool_default("fpcalc", tool_path_prefix)),
        "DAILY_BANK_SOURCE": _read_choice("SP404_DAILY_BANK_SOURCE", "recent", {"recent", "trending"}),
        "TRENDING_FILE": _read_optional_path("SP404_TRENDING_FILE", os.path.join(repo_dir, "trending.json")),
        "VIBE_DATA_DIR": os.path.join(repo_dir, "data"),
        "VIBE_SESSIONS_DB": os.path.join(repo_dir, "data", "vibe_sessions.sqlite"),
        "VIBE_EVAL_DIR": os.path.join(repo_dir, "data", "evals"),
        "VIBE_PARSER_MODE": _read_choice("SP404_VIBE_PARSER_MODE", "base", {"base", "rag", "fine_tuned"}),
        "FINE_TUNED_LLM_ENDPOINT": _read_command("SP404_FINE_TUNED_LLM_ENDPOINT", ""),
        "FINE_TUNED_LLM_MODEL": _read_command("SP404_FINE_TUNED_LLM_MODEL", ""),
        "VIBE_RETRIEVAL_LIMIT": _read_int("SP404_VIBE_RETRIEVAL_LIMIT", 4, minimum=0),
        "FETCH_HISTORY_FILE": _read_optional_path(
            "SP404_FETCH_HISTORY_FILE", os.path.join(repo_dir, "data", "fetch_history.json")
        ),
        "FETCH_DIVERSITY_TOP_N": _read_int("SP404_FETCH_DIVERSITY_TOP_N", 8, minimum=1),
        "FETCH_DETERMINISTIC": _read_bool("SP404_FETCH_DETERMINISTIC", default=False),
        "FETCH_DIVERSITY_COOLDOWN_SECONDS": _read_int(
            "SP404_FETCH_DIVERSITY_COOLDOWN_SECONDS", 6 * 3600, minimum=0
        ),
        # Optional second clone: blackout "Live crunch" reads retag checkpoint + crunch logs here
        "CRUNCH_REPO": _read_optional_path("SP404_CRUNCH_REPO", ""),
        "MULTITRACK_SESSIONS_ROOT": _read_required_path(
            "SP404_MULTITRACK_SESSIONS_ROOT",
            os.path.join(qnap_root, "Video Production", "Multitrack Sessions", "FUN SESSIONS"),
        ),
        "MULTITRACK_H4N_ROOT": _read_required_path(
            "SP404_MULTITRACK_H4N_ROOT",
            os.path.join(qnap_root, "Video Production", "H4N"),
        ),
        "MULTITRACK_FILM_ROOT": _read_required_path(
            "SP404_MULTITRACK_FILM_ROOT",
            os.path.join(qnap_root, "Video Production", "Finished Movies"),
        ),
    }


def load_bank_config(config_path, *, strict=False):
    """Load a bank config YAML mapping.

    strict=False:
      - missing/invalid files return {}
    strict=True:
      - raises ValueError for missing/invalid/non-mapping payloads
    """
    import yaml

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            payload = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        if strict:
            raise ValueError(f"Config file not found: {config_path}") from exc
        return {}
    except (OSError, yaml.YAMLError) as exc:
        if strict:
            raise ValueError(f"Config file is invalid YAML: {config_path}") from exc
        return {}

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        if strict:
            raise ValueError(f"Config file must contain a mapping: {config_path}")
        return {}
    return payload


def _tags_sqlite_path(tags_file):
    """Derive SQLite path from the JSON tags file path."""
    return os.path.splitext(tags_file)[0] + ".sqlite"


# The tag DB is row-oriented: every writer changes only the rows it names.
# There is deliberately no "save the whole dict" call -- loading a snapshot,
# mutating it and writing it back deletes or reverts rows that other
# processes (ingest, smart retag, the web UI) wrote in the meantime.
_TAGS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS tags (rel_path TEXT PRIMARY KEY, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
"""
_TAGS_BUSY_TIMEOUT_S = 30


def _connect_tags(db_path):
    """Open the tag DB for writing (autocommit; callers BEGIN explicitly)."""
    import sqlite3
    conn = sqlite3.connect(db_path, timeout=_TAGS_BUSY_TIMEOUT_S, isolation_level=None)
    conn.execute(f"PRAGMA busy_timeout = {_TAGS_BUSY_TIMEOUT_S * 1000}")
    conn.executescript(_TAGS_SCHEMA)
    return conn


def _migrate_json_to_sqlite(json_path, db_path):
    """One-time migration: import existing JSON tags into SQLite."""
    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict) or not payload:
        return

    conn = _connect_tags(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "INSERT OR REPLACE INTO tags (rel_path, data) VALUES (?, ?)",
            [(k, json.dumps(v)) for k, v in payload.items()]
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    print(f"[TAG_DB] Migrated {len(payload)} entries from JSON to SQLite")


def _ensure_migrated(tags_file):
    """Import a legacy _tags.json before anything creates the SQLite file."""
    db_path = _tags_sqlite_path(tags_file)
    if not os.path.exists(db_path) and os.path.exists(tags_file):
        _migrate_json_to_sqlite(tags_file, db_path)
    return db_path


def load_tag_db(tags_file):
    """Load the tag database. Uses SQLite backend, falls back to JSON.

    Auto-migrates from JSON on first use. Returns a dict (rel_path -> tag entry).
    The dict is a read-only snapshot: write changes back with
    write_tag_changes / upsert_tag_entries / merge_tag_fields / delete_tag_paths.
    """
    import sqlite3
    db_path = _ensure_migrated(tags_file)

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path, timeout=_TAGS_BUSY_TIMEOUT_S)
            try:
                rows = conn.execute("SELECT rel_path, data FROM tags").fetchall()
            finally:
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
        with open(tags_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_tag_changes(tags_file, *, upserts=None, merges=None, deletes=None):
    """Apply row-level changes to the tag DB in one transaction.

    upserts: {rel_path: entry}  -- replace whole rows (new rows, re-keys).
    merges:  {rel_path: fields} -- update only these fields of existing rows;
             rows that no longer exist are skipped, never resurrected.
    deletes: iterable of rel_paths -- the only way rows are ever removed.

    Rows not named here are never touched. Deletes apply first, so a re-key is
    ``deletes=[old], upserts={new: entry}``. Returns counts per operation.
    """
    upserts = upserts or {}
    merges = merges or {}
    deletes = [p for p in (deletes or ()) if p]
    stats = {"deleted": len(deletes), "upserted": len(upserts), "merged": 0, "missing": 0}
    if not (upserts or merges or deletes):
        return stats

    conn = _connect_tags(_ensure_migrated(tags_file))
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if deletes:
                conn.executemany("DELETE FROM tags WHERE rel_path=?", [(p,) for p in deletes])
            if upserts:
                conn.executemany(
                    "INSERT OR REPLACE INTO tags (rel_path, data) VALUES (?, ?)",
                    [(k, json.dumps(v)) for k, v in upserts.items()],
                )
            for rel_path, fields in merges.items():
                row = conn.execute("SELECT data FROM tags WHERE rel_path=?", (rel_path,)).fetchone()
                if row is None:
                    stats["missing"] += 1
                    continue
                try:
                    entry = json.loads(row[0])
                except (json.JSONDecodeError, ValueError):
                    entry = {}
                if not isinstance(entry, dict):
                    entry = {}
                entry.update(fields)
                conn.execute(
                    "UPDATE tags SET data=? WHERE rel_path=?", (json.dumps(entry), rel_path)
                )
                stats["merged"] += 1
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('version', 1) "
                "ON CONFLICT(key) DO UPDATE SET value = value + 1"
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return stats


def upsert_tag_entries(tags_file, entries):
    """Insert or replace whole rows for the given paths only."""
    return write_tag_changes(tags_file, upserts=entries)


def merge_tag_fields(tags_file, changes):
    """Update only the given fields on existing rows: {rel_path: {field: value}}."""
    return write_tag_changes(tags_file, merges=changes)


def delete_tag_paths(tags_file, rel_paths):
    """Remove rows from the tag DB (explicit deletes are the only deletes)."""
    paths = [p for p in rel_paths if p]
    if not paths or not os.path.exists(_ensure_migrated(tags_file)):
        return {"deleted": 0, "upserted": 0, "merged": 0, "missing": 0}
    return write_tag_changes(tags_file, deletes=paths)


def diff_tag_db(before, after):
    """Row-level changes between two snapshots, for write_tag_changes.

    Returns (upserts, merges): rows new in *after* become upserts; rows whose
    fields changed become merges of just those fields. Rows missing from
    *after* and removed fields are ignored -- deletes must stay explicit.
    """
    upserts, merges = {}, {}
    for rel_path, entry in after.items():
        old = before.get(rel_path)
        if old is None:
            upserts[rel_path] = entry
            continue
        if not isinstance(entry, dict) or not isinstance(old, dict):
            continue
        fields = {k: v for k, v in entry.items() if old.get(k, _MISSING) != v}
        if fields:
            merges[rel_path] = fields
    return upserts, merges


_MISSING = object()


def tags_version(tags_file):
    """Write counter bumped by every write_tag_changes call (0 if unknown)."""
    import sqlite3
    db_path = _tags_sqlite_path(tags_file)
    if not os.path.exists(db_path):
        return 0
    try:
        conn = sqlite3.connect(db_path, timeout=_TAGS_BUSY_TIMEOUT_S)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return 0
    return int(row[0]) if row else 0


_TAG_JSON_EXPORT_LIMIT = 50 * 1024 * 1024


def export_tags_json(tags_file):
    """Write _tags.json from the current SQLite state (compatibility copy).

    Call at the end of a batch run, never from an old in-memory snapshot.
    Returns True if the file was written.
    """
    db = load_tag_db(tags_file)
    if len(db) * 1100 >= _TAG_JSON_EXPORT_LIMIT:
        return False
    try:
        atomic_write_json(tags_file, db, indent=1)
    except OSError:
        return False
    return True


def library_rel_path(full_path, library_root):
    """Tag DB key for *full_path*: relative to the library, always with '/'.

    Returns None when the path is outside the library.
    """
    full_path = os.path.normpath(os.path.abspath(full_path))
    root = os.path.normpath(os.path.abspath(library_root))
    prefix = root + os.sep
    if not full_path.startswith(prefix):
        return None
    return full_path[len(prefix):].replace("\\", "/")


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
    env["PATH"] = f"{path_prefix}{os.pathsep}{current_path}" if current_path else path_prefix
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


# ---------------------------------------------------------------------------
# Tuning config loaders (merged from jambox_tuning.py)
# ---------------------------------------------------------------------------

DEFAULT_VIBE_MAPPINGS = {
    "genre_instruments": {
        "funk": [("GTR", "guitar"), ("KEY", "clavinet")],
        "disco": [("KEY", "piano"), ("STR", "strings")],
        "soul": [("KEY", "organ"), ("BRS", "brass")],
        "rock": [("GTR", "guitar"), ("GTR", "guitar")],
        "electronic": [("SYN", "synth"), ("SYN", "synth")],
        "ambient": [("PAD", "pad"), ("SYN", "synth")],
        "house": [("SYN", "synth"), ("KEY", "piano")],
        "techno": [("SYN", "synth"), ("SYN", "lead")],
        "trance": [("SYN", "synth"), ("SYN", "lead")],
        "dubstep": [("SYN", "synth"), ("BAS", "bass")],
        "drum-and-bass": [("SYN", "synth"), ("BAS", "bass")],
        "breakbeat": [("SYN", "synth"), ("BRK", "break")],
        "jungle": [("BRK", "break"), ("BAS", "bass")],
        "experimental": [("SYN", "synth"), ("PAD", "pad")],
        "hiphop": [("KEY", "piano"), ("SYN", "synth")],
        "lo-fi": [("KEY", "piano"), ("GTR", "guitar")],
        "industrial": [("SYN", "synth"), ("SYN", "lead")],
        "pop": [("SYN", "synth"), ("KEY", "piano")],
        "afrobeat": [("PRC", "percussion"), ("BAS", "bass")],
        "city-pop": [("KEY", "piano"), ("SYN", "synth")],
        "shoegaze": [("GTR", "guitar"), ("PAD", "pad")],
        "punk": [("GTR", "guitar"), ("BAS", "bass")],
        "jazz": [("KEY", "piano"), ("BRS", "brass")],
        "rnb": [("KEY", "piano"), ("SYN", "synth")],
        "boom-bap": [("KEY", "piano"), ("BAS", "bass")],
        "dancehall": [("BAS", "bass"), ("SYN", "synth")],
        "dub": [("BAS", "bass"), ("FX", "effects")],
        "latin": [("PRC", "percussion"), ("GTR", "guitar")],
        "tropical": [("PRC", "percussion"), ("SYN", "synth")],
        "trap": [("BAS", "bass"), ("SYN", "synth")],
        "drill": [("BAS", "bass"), ("SYN", "synth")],
        "footwork": [("BRK", "break"), ("VOX", "vocals")],
        "grime": [("BAS", "bass"), ("SYN", "synth")],
        "uk-garage": [("BRK", "break"), ("BAS", "bass")],
        "baile-funk": [("BRK", "break"), ("VOX", "vocals")],
        "breakcore": [("BRK", "break"), ("SYN", "synth")],
        "gqom": [("BRK", "break"), ("BAS", "bass")],
        "reggae": [("GTR", "guitar"), ("BAS", "bass")],
        "industrial-techno": [("SYN", "synth"), ("BRK", "break")],
    },
    "default_instruments": [("SYN", "synth"), ("BAS", "bass")],
    "fallback_dimensions": {
        "genre": {
            "afrobeat", "ambient", "boom-bap", "breakbeat", "dancehall", "disco", "drum-and-bass",
            "dub", "dubstep", "electronic", "experimental", "funk", "hiphop", "house", "industrial",
            "jungle", "latin", "lo-fi", "pop", "rnb", "rock", "soul", "techno", "trance",
            "tropical",
        },
        "vibe": {"dark", "mellow", "hype", "dreamy", "nostalgic", "aggressive", "soulful", "tense", "chill", "playful", "eerie", "gritty", "ethereal", "triumphant", "melancholic", "uplifting", "unfiltered", "comforting"},
        "texture": {"dusty", "lo-fi", "raw", "clean", "warm", "bitcrushed", "airy", "crunchy", "crispy", "glassy", "saturated", "vinyl", "tape", "digital", "organic", "bright", "thick", "thin", "filtered", "muddy", "warbly"},
        "energy": {"low", "mid", "high"},
    },
    "type_keyword_aliases": {
        "kick": "KIK", "snare": "SNR", "hat": "HAT", "hihat": "HAT", "clap": "CLP",
        "break": "BRK", "bass": "BAS", "synth": "SYN", "guitar": "GTR", "keys": "KEY",
        "piano": "KEY", "pad": "PAD", "vocal": "VOX", "vox": "VOX", "fx": "FX", "effect": "FX",
    },
}

DEFAULT_CLAP_SCORING = {
    "similarity_weight": 0.6,
    "legacy_tag_match_weight": 0.6,
    "type_code_weight": 0.20,
    "bpm_weight": 0.05,
    "key_weight": 0.03,
    "playability_weight": 0.15,
    "duration_weight": 0.10,
    "energy_weight": 0.03,
    "danceability_weight": 0.03,
    "discogs_weight": 0.03,
    "quality_weight": 0.02,
    "plex_weight": 0.02,
    "instrument_hint_weight": 0.02,
    "performance_weight": 0.04,
    "key_compatible_score": 0.33,
    "energy_mismatch_score": -0.66,
    "danceability_bonus": 0.03,
    "danceability_threshold": 0.5,
    "discogs_keyword_bonus": 0.018,
    "discogs_keyword_bonus_cap": 0.045,
}

DEFAULT_PERFORMANCE_SCORING = {
    "pad_reuse": 4,
    "bpm_stable": 3,
    "high_velocity": 2,
}

DEFAULT_SCORING = {
    "score_version": 8,
    "weights": {
        "keyword_dimension": 3,
        "keyword_tag": 2,
        "keyword_filename": 1,
        "discogs_keyword_match": 2,
        "plex_moods_bonus": 1,
        "plex_play_count_bonus": 2,
    },
}


def _safe_load_yaml(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except (FileNotFoundError, OSError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_instrument_pairs(value, fallback):
    if not isinstance(value, list):
        return fallback
    pairs = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            return fallback
        code, label = item
        pairs.append((str(code).strip().upper(), str(label).strip().lower()))
    return pairs or fallback


def load_vibe_mappings(path=None):
    if path is None:
        path = load_settings_for_script(__file__)["VIBE_MAPPINGS_PATH"]
    payload = _safe_load_yaml(path)
    result = {
        "genre_instruments": dict(DEFAULT_VIBE_MAPPINGS["genre_instruments"]),
        "default_instruments": list(DEFAULT_VIBE_MAPPINGS["default_instruments"]),
        "fallback_dimensions": {key: set(value) for key, value in DEFAULT_VIBE_MAPPINGS["fallback_dimensions"].items()},
        "type_keyword_aliases": dict(DEFAULT_VIBE_MAPPINGS["type_keyword_aliases"]),
    }

    genre_instruments = payload.get("genre_instruments")
    if isinstance(genre_instruments, dict):
        for genre, pairs in genre_instruments.items():
            result["genre_instruments"][str(genre).strip().lower()] = _coerce_instrument_pairs(
                pairs,
                result["genre_instruments"].get(str(genre).strip().lower(), result["default_instruments"]),
            )

    result["default_instruments"] = _coerce_instrument_pairs(
        payload.get("default_instruments"),
        result["default_instruments"],
    )

    fallback_dimensions = payload.get("fallback_dimensions")
    if isinstance(fallback_dimensions, dict):
        for key, values in fallback_dimensions.items():
            if isinstance(values, list):
                normalized = {str(item).strip().lower() for item in values if str(item).strip()}
                if normalized:
                    result["fallback_dimensions"][str(key).strip().lower()] = normalized

    type_keyword_aliases = payload.get("type_keyword_aliases")
    if isinstance(type_keyword_aliases, dict):
        normalized_aliases = {}
        for key, value in type_keyword_aliases.items():
            alias = str(key).strip().lower()
            type_code = str(value).strip().upper()
            if alias and type_code:
                normalized_aliases[alias] = type_code
        if normalized_aliases:
            result["type_keyword_aliases"] = normalized_aliases

    return result


def load_scoring_config(path=None):
    if path is None:
        path = load_settings_for_script(__file__)["SCORING_CONFIG_PATH"]
    payload = _safe_load_yaml(path)
    result = {
        "score_version": DEFAULT_SCORING["score_version"],
        "weights": dict(DEFAULT_SCORING["weights"]),
        "clap": dict(DEFAULT_CLAP_SCORING),
        "performance": dict(DEFAULT_PERFORMANCE_SCORING),
    }

    try:
        score_version = int(payload.get("score_version", result["score_version"]))
        if score_version >= 1:
            result["score_version"] = score_version
    except (TypeError, ValueError):
        pass

    weights = payload.get("weights")
    if isinstance(weights, dict):
        for key, default_value in result["weights"].items():
            try:
                result["weights"][key] = float(weights.get(key, default_value))
            except (TypeError, ValueError):
                result["weights"][key] = default_value

    clap = payload.get("clap")
    if isinstance(clap, dict):
        for key, default_value in result["clap"].items():
            try:
                result["clap"][key] = float(clap.get(key, default_value))
            except (TypeError, ValueError):
                result["clap"][key] = default_value

    performance = payload.get("performance")
    if isinstance(performance, dict):
        for key, default_value in result["performance"].items():
            try:
                result["performance"][key] = float(performance.get(key, default_value))
            except (TypeError, ValueError):
                result["performance"][key] = default_value

    return result


# Lazy score version — avoids disk I/O at import time
_SCORE_VERSION_CACHE = None

def get_score_version():
    global _SCORE_VERSION_CACHE
    if _SCORE_VERSION_CACHE is None:
        _SCORE_VERSION_CACHE = load_scoring_config()["score_version"]
    return _SCORE_VERSION_CACHE

