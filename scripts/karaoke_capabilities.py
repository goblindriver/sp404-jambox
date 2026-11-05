#!/usr/bin/env python3
"""What this install can actually use for karaoke.

Two different floors, on purpose. Do not collapse them:

* ``SP404_KARAOKE_BACKEND`` (see ``jambox_config``) is the headless CLI floor.
  Unset, it is ``demucs``, because that is the separator this repo installs.
  A headless ``karaoke_prep.py`` run must not require karaoke-gen.
* This probe is the web UI floor. It picks the best separator that is really
  here: karaoke-gen if the binary is on PATH or ``SP404_KARAOKE_REMOTE`` names
  a lane, otherwise Demucs, otherwise nothing. The tab must not default to a
  tool that can only fail.

The probe does not ssh, and it does not import Demucs or karaoke-gen.
"""
import importlib.util

from jambox_config import load_settings_for_script, resolve_command

# Models the web API accepts. htdemucs_ft is Demucs, never the default.
DEMUCS_MODELS = ("htdemucs", "htdemucs_ft")
KARAOKE_GEN_MODEL = "karaoke-gen"
MODELS = (KARAOKE_GEN_MODEL, *DEMUCS_MODELS)

NO_SEPARATOR = (
    "No vocal separator installed. Install Demucs, or karaoke-gen, "
    "or set SP404_KARAOKE_REMOTE to a GPU lane."
)


def _settings():
    return load_settings_for_script(__file__)


def _installed(command):
    return resolve_command(command) is not None


def _detect():
    """Live look at this process. ``plex`` is filled in by the caller."""
    settings = _settings()
    remote = (settings.get("KARAOKE_REMOTE_HOST") or "").strip() or None
    return {
        "demucs": importlib.util.find_spec("demucs") is not None,
        "karaoke_gen": _installed(settings.get("KARAOKE_GEN_BIN") or "karaoke-gen"),
        "remote_lane": remote,
        "ytdlp": _installed(settings.get("YTDLP_BIN") or "yt-dlp"),
        "librosa": importlib.util.find_spec("librosa") is not None,
        "ffmpeg": _installed(settings.get("FFMPEG_BIN") or "ffmpeg"),
        "plex": False,
    }


def separate_default(demucs, karaoke_gen, remote_lane):
    """``karaoke-gen``, ``htdemucs``, or None. ``htdemucs_ft`` is never the default."""
    if karaoke_gen or remote_lane:
        return KARAOKE_GEN_MODEL
    if demucs:
        return "htdemucs"
    return None


def capabilities(*, found=None, plex=None):
    """The ladder the web UI and ``POST /api/karaoke/prep`` both trust.

    ``found`` overrides detection (tests, and any caller that already knows).
    ``plex`` is the live client or a bool; status passes ``_get_plex()``.
    Missing means "not a source", never a network probe from here.
    """
    detected = _detect()
    if found:
        detected.update(found)
    if plex is not None:
        detected["plex"] = bool(plex)
    default = separate_default(detected["demucs"], detected["karaoke_gen"], detected["remote_lane"])
    return {
        "separate": {
            "demucs": bool(detected["demucs"]),
            "karaoke_gen": bool(detected["karaoke_gen"]),
            "remote_lane": detected["remote_lane"] or None,
            "default": default,
            "reason": None if default else NO_SEPARATOR,
        },
        "sources": {"file": True, "plex": bool(detected["plex"])},
        "lyrics": {"sidecar": True, "lrclib": True},
        "extras": {
            "ytdlp": bool(detected["ytdlp"]),
            "librosa": bool(detected["librosa"]),
            "ffmpeg": bool(detected["ffmpeg"]),
        },
        "stage": {"browser": True},
    }


def model_available(cap, model):
    sep = cap["separate"]
    if model == KARAOKE_GEN_MODEL:
        return bool(sep["karaoke_gen"] or sep["remote_lane"])
    if model in DEMUCS_MODELS:
        return bool(sep["demucs"])
    return False


def reject_prep(cap, model, videos):
    """A sentence to 400 with, or None if this prep is allowed to start.

    ``model`` may be None when the caller asked for the probe default and
    there is no separator at all.
    """
    if not model:
        return cap["separate"]["reason"] or NO_SEPARATOR
    if model not in MODELS:
        return "model must be karaoke-gen, htdemucs or htdemucs_ft"
    if not model_available(cap, model):
        if model == KARAOKE_GEN_MODEL:
            return "karaoke-gen is not installed and no remote lane is set (SP404_KARAOKE_REMOTE)"
        return "Demucs is not installed"
    if videos and not cap["extras"]["ytdlp"]:
        return "yt-dlp is not installed; set SP404_YTDLP or leave videos off"
    return None
