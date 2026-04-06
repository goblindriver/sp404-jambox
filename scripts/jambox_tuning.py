"""Validated loading for configurable vibe/scoring tuning."""

from __future__ import annotations

import os

import yaml

from jambox_config import load_settings_for_script


SETTINGS = load_settings_for_script(__file__)

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
        "hip-hop": [("KEY", "piano"), ("SYN", "synth")],
        "lo-fi": [("KEY", "piano"), ("GTR", "guitar")],
        "industrial": [("SYN", "synth"), ("SYN", "lead")],
        "pop": [("SYN", "synth"), ("KEY", "piano")],
    },
    "default_instruments": [("SYN", "synth"), ("KEY", "keys")],
    "fallback_dimensions": {
        "genre": {"funk", "disco", "soul", "rock", "electronic", "ambient", "house", "techno", "hiphop", "lo-fi", "industrial", "pop", "rnb", "dub", "dancehall", "latin", "boom-bap", "tropical", "afrobeat"},
        "vibe": {"dark", "mellow", "hype", "dreamy", "nostalgic", "aggressive", "soulful", "warm", "tense", "chill", "playful", "eerie", "gritty", "ethereal", "triumphant", "melancholic", "uplifting"},
        "texture": {"dusty", "lo-fi", "raw", "clean", "warm", "bitcrushed", "airy", "crunchy", "crispy", "glassy", "saturated", "vinyl", "tape", "digital", "organic", "bright", "thick", "thin", "filtered", "muddy", "warbly"},
        "energy": {"low", "mid", "high"},
    },
    "type_keyword_aliases": {
        "kick": "KIK",
        "snare": "SNR",
        "hat": "HAT",
        "hihat": "HAT",
        "clap": "CLP",
        "break": "BRK",
        "bass": "BAS",
        "synth": "SYN",
        "guitar": "GTR",
        "keys": "KEY",
        "piano": "KEY",
        "pad": "PAD",
        "vocal": "VOX",
        "vox": "VOX",
        "fx": "FX",
        "effect": "FX",
    },
}

DEFAULT_SCORING = {
    "score_version": 4,
    "weights": {
        "type_exact": 10,
        "type_related": 3,
        "type_mismatch": -8,
        "playability_exact": 5,
        "playability_mismatch": -4,
        "bpm_close": 4,
        "bpm_near": 2,
        "bpm_distant": -1,
        "bpm_far": -2,
        "key_exact": 3,
        "key_compatible": 1,
        "keyword_dimension": 3,
        "keyword_tag": 2,
        "keyword_filename": 1,
        "oneshot_long_penalty": -3,
        "loop_short_penalty": -3,
        "plex_moods_bonus": 1,
        "plex_play_count_bonus": 2,
        "quality_tiebreaker": 0.5,
        "instrument_hint_match": 5,
        "energy_match": 3,
        "energy_mismatch": -2,
        "performance_pattern_used": 4,
        "performance_bpm_adjust": 3,
        "performance_velocity_high": 2,
        "bed_complement": 3,
        "toolkit_survival": 5,
        "session_survival": 2,
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
    path = path or SETTINGS["VIBE_MAPPINGS_PATH"]
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
    path = path or SETTINGS["SCORING_CONFIG_PATH"]
    payload = _safe_load_yaml(path)
    result = {
        "score_version": DEFAULT_SCORING["score_version"],
        "weights": dict(DEFAULT_SCORING["weights"]),
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

    return result


SCORE_VERSION = load_scoring_config()["score_version"]
