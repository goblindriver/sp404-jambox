"""Shared runtime settings for the SP-404 Jambox app and scripts."""

import os


DEFAULT_SAMPLE_LIBRARY = "~/Music/SP404-Sample-Library"
DEFAULT_DOWNLOADS = "~/Downloads"
DEFAULT_SD_CARD = "/Volumes/SP-404SX"
DEFAULT_TOOL_PATH_PREFIX = "/opt/homebrew/bin"


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
        "FREESOUND_DIR": os.path.join(sample_library, "Freesound"),
        "STAGING_DIR": os.path.join(repo_dir, "_CARD_STAGING"),
        "SMPL_DIR": os.path.join(repo_dir, "sd-card-template", "ROLAND", "SP-404SX", "SMPL"),
        "CONFIG_PATH": os.path.join(repo_dir, "bank_config.yaml"),
        "FFMPEG_BIN": _read_command("SP404_FFMPEG", os.path.join(DEFAULT_TOOL_PATH_PREFIX, "ffmpeg")),
        "FFPROBE_BIN": _read_command("SP404_FFPROBE", os.path.join(DEFAULT_TOOL_PATH_PREFIX, "ffprobe")),
        "UNAR_BIN": _read_command("SP404_UNAR", os.path.join(DEFAULT_TOOL_PATH_PREFIX, "unar")),
        "TOOL_PATH_PREFIX": tool_path_prefix,
        "WEB_DEBUG": _read_bool("SP404_WEB_DEBUG", default=False),
    }


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
