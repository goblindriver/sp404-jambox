"""Unified scoring engine for SP-404 Jambox sample matching.

Both CLAP and legacy tag-based scoring flow through this module.
All weights are configurable via config/scoring.yaml. No hardcoded bonuses.

Design:
  - Each scoring dimension produces a sub-score in 0.0–1.0 range
  - Final score = weighted sum of normalized sub-scores
  - CLAP cosine similarity is one sub-score (the dominant one)
  - Legacy tag matching produces equivalent sub-scores per dimension
  - SD card performance bonuses apply to both paths
  - Config changes affect both paths identically
"""

from __future__ import annotations

import math
import os
from typing import Any

from jambox_config import load_scoring_config

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_CONFIG = None


def _get_config():
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_scoring_config()
    return _CONFIG


def reload_config():
    """Force config reload (e.g. after scoring.yaml changes)."""
    global _CONFIG
    _CONFIG = None


# ---------------------------------------------------------------------------
# Key normalization (shared between paths)
# ---------------------------------------------------------------------------

_ENHARMONIC = {
    "Gs": "Ab", "As": "Bb", "Cs": "Db", "Ds": "Eb", "Fs": "Gb",
    "Gsm": "Abm", "Asm": "Bbm", "Csm": "Dbm", "Dsm": "Ebm", "Fsm": "Gbm",
    "G#": "Ab", "A#": "Bb", "C#": "Db", "D#": "Eb", "F#": "Gb",
    "G#m": "Abm", "A#m": "Bbm", "C#m": "Dbm", "D#m": "Ebm", "F#m": "Gbm",
}

_KEY_RELATIVES = {
    "Am": "C", "C": "Am", "Dm": "F", "F": "Dm",
    "Em": "G", "G": "Em", "Bm": "D", "D": "Bm",
    "Abm": "B", "B": "Abm", "Bbm": "Db", "Db": "Bbm",
    "Dbm": "E", "E": "Dbm", "Ebm": "Gb", "Gb": "Ebm",
    "Gbm": "A", "A": "Gbm",
    "Fm": "Ab", "Ab": "Fm", "Gm": "Bb", "Bb": "Gm",
    "Cm": "Eb", "Eb": "Cm",
}


def normalize_key(key: str | None) -> str:
    if not key:
        return ""
    return _ENHARMONIC.get(key, key)


def keys_compatible(key_a: str, key_b: str) -> bool:
    a = normalize_key(key_a)
    b = normalize_key(key_b)
    return _KEY_RELATIVES.get(a) == b or _KEY_RELATIVES.get(b) == a


# ---------------------------------------------------------------------------
# BPM scoring — smooth Gaussian falloff
# ---------------------------------------------------------------------------

def bpm_score(target: float | None, actual: float | None, tolerance: float = 10.0) -> float:
    """Score BPM match on 0.0-1.0 scale with smooth Gaussian-ish falloff.

    tolerance: BPM range within which score stays above 0.8.
    Beyond tolerance, score decays to 0 over ~30 BPM.
    """
    if not target or not actual:
        return 0.0
    try:
        diff = abs(float(actual) - float(target))
    except (TypeError, ValueError):
        return 0.0
    if diff == 0:
        return 1.0
    if diff <= tolerance:
        return 0.8
    return max(0.0, 1.0 - (diff - tolerance) / 30.0)


# ---------------------------------------------------------------------------
# Key scoring
# ---------------------------------------------------------------------------

def key_score(target: str | None, actual: str | None) -> float:
    """Score key match on 0.0-1.0 scale."""
    if not target or not actual or str(target).upper() == "XX":
        return 0.0
    norm_t = normalize_key(target)
    norm_a = normalize_key(actual)
    if norm_t.lower() == norm_a.lower():
        return 1.0
    if keys_compatible(target, actual):
        cfg = (_get_config().get("clap") or {})
        return cfg.get("key_compatible_score", 0.33)
    return 0.0


# ---------------------------------------------------------------------------
# Unified sample scorer
# ---------------------------------------------------------------------------

_DANCE_KEYWORDS = frozenset({
    "dance", "groove", "party", "hype", "danceable", "funky",
    "disco", "house", "bounce", "club", "rave", "energy",
})


def score_sample(
    entry: dict[str, Any],
    parsed_query: dict[str, Any],
    bank_config: dict[str, Any],
    *,
    clap_similarity: float | None = None,
    performance_profile: dict | None = None,
    discogs_tokens_fn=None,
) -> tuple[float, dict[str, float]]:
    """Score a single library entry against a parsed pad query.

    Works for both CLAP and legacy paths:
    - If clap_similarity is provided, it's used as the primary signal
    - If not, tag-based matching generates the primary signal
    - All other sub-scores (BPM, key, energy, quality, performance) apply to both

    Returns: (final_score, breakdown_dict)
    """
    config = _get_config()
    clap_cfg = config.get("clap") or {}
    weights = config.get("weights") or {}
    perf_cfg = config.get("performance") or {}
    is_clap = clap_similarity is not None

    q = parsed_query
    breakdown = {}

    # ── Primary signal ──
    if is_clap:
        breakdown["clap_similarity"] = max(0.0, float(clap_similarity))
    else:
        breakdown["clap_similarity"] = 0.0
        # Tag-based primary: type_code + keyword matching
        breakdown["tag_match"] = _tag_match_score(entry, q, weights, discogs_tokens_fn)

    # ── Type code filter (both paths) ──
    breakdown["type_code"] = _type_code_score(entry, q)

    # ── Playability ──
    breakdown["playability"] = _playability_score(entry, q)

    # ── Duration sanity ──
    breakdown["duration"] = _duration_score(entry, q)

    # ── BPM ──
    target_bpm = q.get("bpm") or bank_config.get("bpm")
    breakdown["bpm"] = bpm_score(target_bpm, entry.get("bpm"))

    # ── Key ──
    target_key = q.get("key") or bank_config.get("key")
    breakdown["key"] = key_score(target_key, entry.get("key"))

    # ── Energy ──
    breakdown["energy"] = _energy_score(entry, q)

    # ── Danceability ──
    breakdown["danceability"] = _danceability_score(entry, q, clap_cfg)

    # ── Discogs keywords (additive, not primary) ──
    breakdown["discogs"] = _discogs_score(entry, q, clap_cfg, discogs_tokens_fn)

    # ── Quality score ──
    qs = entry.get("quality_score")
    breakdown["quality"] = (float(qs) / 5.0) if isinstance(qs, (int, float)) and 1 <= qs <= 5 else 0.0

    # ── Plex play count ──
    breakdown["plex"] = _plex_score(entry)

    # ── Instrument hint ──
    breakdown["instrument_hint"] = _instrument_hint_score(entry, q)

    # ── SD Card performance intelligence (both paths) ──
    breakdown["performance"] = _performance_score(entry, performance_profile, perf_cfg)

    # ── Weighted sum ──
    final = _weighted_sum(breakdown, is_clap, config)
    return final, breakdown


def _weighted_sum(breakdown: dict[str, float], is_clap: bool, config: dict) -> float:
    """Compute final score from sub-score breakdown.

    CLAP mode: clap_similarity is the dominant signal (~60% of score).
    Legacy mode: tag_match is the dominant signal, scaled to match.
    All other dimensions contribute equally in both modes.
    """
    clap_cfg = config.get("clap") or {}
    weights = config.get("weights") or {}
    perf_cfg = config.get("performance") or {}

    if is_clap:
        sim_weight = clap_cfg.get("similarity_weight", 0.6)
        score = breakdown["clap_similarity"] * sim_weight
    else:
        # Legacy tag matching: scale tag_match (0-1) to be the dominant signal
        score = breakdown.get("tag_match", 0.0) * clap_cfg.get("legacy_tag_match_weight", 0.6)

    # Type code: strongest structural signal — wrong type is a dealbreaker
    score += breakdown["type_code"] * clap_cfg.get("type_code_weight", 0.20)

    # Structural bonuses (shared, smaller contributions)
    score += breakdown["bpm"] * clap_cfg.get("bpm_weight", 0.05)
    score += breakdown["key"] * clap_cfg.get("key_weight", 0.03)
    score += breakdown["playability"] * clap_cfg.get("playability_weight", 0.15)
    score += breakdown["duration"] * clap_cfg.get("duration_weight", 0.10)
    score += breakdown["energy"] * clap_cfg.get("energy_weight", 0.03)
    score += breakdown["danceability"] * clap_cfg.get("danceability_weight", 0.03)
    score += breakdown["discogs"] * clap_cfg.get("discogs_weight", 0.03)
    score += breakdown["quality"] * clap_cfg.get("quality_weight", 0.02)
    score += breakdown["plex"] * clap_cfg.get("plex_weight", 0.02)
    score += breakdown["instrument_hint"] * clap_cfg.get("instrument_hint_weight", 0.02)

    # Performance bonuses
    perf_weight = clap_cfg.get("performance_weight", 0.04)
    score += breakdown["performance"] * perf_weight

    return round(score, 4)


# ---------------------------------------------------------------------------
# Sub-score functions
# ---------------------------------------------------------------------------

def _type_code_score(entry: dict, q: dict) -> float:
    """1.0 = exact match, 0.5 = related, 0.0 = unknown, -1.0 = mismatch."""
    from fetch_samples import _RELATED_TYPE_CODES
    if not q.get("type_code"):
        return 0.0
    entry_tc = entry.get("type_code", "")
    if entry_tc == q["type_code"]:
        return 1.0
    if not entry_tc:
        return 0.0
    if entry_tc in _RELATED_TYPE_CODES.get(q["type_code"], set()):
        return 0.5
    return -1.0


def _playability_score(entry: dict, q: dict) -> float:
    """1.0 = match, 0.0 = unknown, -1.0 = mismatch."""
    if not q.get("playability"):
        return 0.0
    entry_play = entry.get("playability", "")
    if entry_play == q["playability"]:
        return 1.0
    if not entry_play:
        return 0.0
    if q["playability"] in ("one-shot", "loop") and entry_play in ("one-shot", "loop"):
        if entry_play != q["playability"]:
            return -1.0
    return 0.0


def _duration_score(entry: dict, q: dict) -> float:
    """Penalize duration mismatches. 0.0 = fine, -1.0 = bad mismatch."""
    duration = entry.get("duration", 0) or 0
    play = q.get("playability")
    if play == "one-shot" and duration > 10:
        return -1.0
    if play == "loop" and 0 < duration < 1:
        return -1.0
    return 0.0


def _energy_score(entry: dict, q: dict) -> float:
    """1.0 = match, -0.66 = mismatch, 0.0 = no data."""
    entry_energy = (entry.get("energy") or "").lower()
    query_energy = q.get("energy")
    if not entry_energy or not query_energy:
        return 0.0
    if entry_energy == query_energy:
        return 1.0
    cfg = (_get_config().get("clap") or {})
    return cfg.get("energy_mismatch_score", -0.66)


def _danceability_score(entry: dict, q: dict, clap_cfg: dict) -> float:
    """Bonus for danceable samples when query implies dance context."""
    wants_dance = bool(q.get("keywords", set()) & _DANCE_KEYWORDS)
    if not wants_dance:
        return 0.0
    threshold = clap_cfg.get("danceability_threshold", 0.6)
    file_dance = entry.get("danceability") or 0.0
    return 1.0 if file_dance >= threshold else 0.0


def _discogs_score(entry: dict, q: dict, clap_cfg: dict, discogs_tokens_fn) -> float:
    """Score Discogs keyword overlap, capped. Returns 0.0-1.0."""
    keywords = q.get("keywords", set())
    if not keywords or not discogs_tokens_fn:
        return 0.0
    dtoks = discogs_tokens_fn(entry)
    entry_genres = {g.lower() for g in (entry.get("genre") or []) if isinstance(g, str)}
    bonus_each = clap_cfg.get("discogs_keyword_bonus", 0.018)
    bonus_cap = clap_cfg.get("discogs_keyword_bonus_cap", 0.045)
    bonus = 0.0
    for kw in keywords:
        if kw in dtoks and kw not in entry_genres:
            bonus += bonus_each
    # Normalize to 0-1 range (cap is the max)
    return min(bonus, bonus_cap) / max(bonus_cap, 0.001)


def _plex_score(entry: dict) -> float:
    """Score based on Plex metadata presence and play count."""
    score = 0.0
    if entry.get("plex_moods"):
        score += 0.3
    play_count = entry.get("plex_play_count", 0) or 0
    if play_count > 0:
        # Diminishing returns: log scale, normalize so 100 plays = 1.0
        score += min(1.0, math.log1p(play_count) / math.log1p(100)) * 0.7
    return min(score, 1.0)


def _instrument_hint_score(entry: dict, q: dict) -> float:
    """1.0 if instrument hint matches a query keyword, else 0.0."""
    hint = (entry.get("instrument_hint") or "").lower().strip()
    if not hint or not q.get("keywords"):
        return 0.0
    hint_tokens = set(hint.split())
    return 1.0 if hint_tokens & q["keywords"] else 0.0


def _performance_score(entry: dict, perf_profile: dict | None, perf_cfg: dict) -> float:
    """Score based on SD card performance intelligence. Returns 0.0-1.0."""
    if not perf_profile:
        return 0.0
    wid = entry.get("sp404_wav_identity") or entry.get("card_identity")
    if not wid or wid not in perf_profile:
        return 0.0

    p = perf_profile[wid]
    score = 0.0

    # Pattern hits = sample was used in patterns (musician liked it)
    pad_reuse_weight = perf_cfg.get("pad_reuse", 4)
    bpm_stable_weight = perf_cfg.get("bpm_stable", 3)
    velocity_weight = perf_cfg.get("high_velocity", 2)
    total_possible = pad_reuse_weight + bpm_stable_weight + velocity_weight

    if p.get("pattern_hits", 0) > 0:
        score += pad_reuse_weight
    if p.get("bpm_adjustments"):
        # User adjusted BPM = they cared enough to tweak it
        score += bpm_stable_weight
    if p.get("avg_velocity", 0) > 90:
        score += velocity_weight

    return score / max(total_possible, 1)


def _tag_match_score(entry: dict, q: dict, weights: dict, discogs_tokens_fn) -> float:
    """Legacy tag-based matching, normalized to 0.0-1.0.

    Computes keyword/dimension matches and normalizes against the theoretical
    max score for the query.
    """
    raw = 0.0
    max_possible = 0.0
    keywords = q.get("keywords", set())

    entry_tags = {t.lower() for t in entry.get("tags", [])}
    entry_vibes = {v.lower() for v in entry.get("vibe", [])}
    entry_textures = {t.lower() for t in entry.get("texture", [])}
    entry_genres = {g.lower() for g in entry.get("genre", [])}
    fname_lower = os.path.basename(entry.get("path", "")).lower()

    w_dim = weights.get("keyword_dimension", 3)
    w_tag = weights.get("keyword_tag", 2)
    w_fname = weights.get("keyword_filename", 1)
    w_discogs = weights.get("discogs_keyword_match", 2)

    for kw in keywords:
        max_possible += w_dim  # best case per keyword
        # Score best match per keyword (no double-dipping across dimensions)
        if kw in entry_vibes or kw in entry_textures or kw in entry_genres:
            raw += w_dim
        elif kw in entry_tags:
            raw += w_tag
        elif discogs_tokens_fn and kw in discogs_tokens_fn(entry):
            raw += w_discogs
        elif kw in fname_lower:
            raw += w_fname

    # Plex metadata bonuses (small)
    if entry.get("plex_moods"):
        raw += weights.get("plex_moods_bonus", 1)
        max_possible += weights.get("plex_moods_bonus", 1)
    if entry.get("plex_play_count", 0) > 0:
        raw += weights.get("plex_play_count_bonus", 2)
        max_possible += weights.get("plex_play_count_bonus", 2)

    if max_possible <= 0:
        return 0.5  # no keywords = neutral score
    return min(1.0, raw / max_possible)
