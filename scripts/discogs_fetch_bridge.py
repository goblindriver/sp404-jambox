"""Map Discogs classifier output to fetch-scoring keyword tokens (lightweight).

Used by fetch_samples (legacy + CLAP bonuses) and optional genre[] backfill.
Does not call ONNX — only reads tag DB fields ``parent_genre`` and ``discogs_styles``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from tag_vocab import GENRES, normalize_genre

# Top-level Discogs categories from the EffNet label space → our genre slugs.
_PARENT_TO_GENRES: Dict[str, tuple[str, ...]] = {
    "electronic": ("electronic",),
    "hip hop": ("hiphop",),
    "rock": ("rock",),
    "jazz": ("jazz",),
    "reggae": ("reggae",),
    "latin": ("latin",),
    "funk / soul": ("funk", "soul"),
    "blues": ("rock",),
    "classical": ("classical",),
    "pop": ("pop",),
    "stage & screen": (),
    "non-music": (),
    "brass & military": (),
    "children's": (),
    "folk, world, & country": ("world",),
}

# Phrases / tokens that are not valid genre slugs but map to one (Discogs label tails).
_STYLE_TAIL_ALIASES: Dict[str, str] = {
    "metal": "rock",
    "boom bap": "boom-bap",
    "grime": "hiphop",
    "breaks": "breakbeat",
}


def _norm_parent_key(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def parent_genre_tokens(entry: Dict[str, Any]) -> Set[str]:
    """Tokens inferred only from ``parent_genre`` (backfill pass 1)."""
    out: Set[str] = set()
    pg = entry.get("parent_genre")
    if not isinstance(pg, str) or not pg.strip() or pg.strip() == "Unknown":
        return out
    key = _norm_parent_key(pg)
    mapped = _PARENT_TO_GENRES.get(key)
    if mapped:
        out.update(g for g in mapped if g)
    else:
        raw = normalize_genre(pg.replace("/", " ").replace("&", " "))
        if raw:
            out.add(raw)
        for chunk in re.split(r"[/,|]", pg.lower()):
            chunk = chunk.strip()
            if len(chunk) < 2:
                continue
            n = normalize_genre(chunk)
            if n:
                out.add(n)
    return out


def _style_rows_tokens(rows: List[Any], *, style_prob_floor: float, max_rows: int) -> Set[str]:
    out: Set[str] = set()
    if not isinstance(rows, list):
        return out
    for row in rows[:max_rows]:
        if not isinstance(row, dict):
            continue
        try:
            p = float(row.get("probability", 0) or 0)
        except (TypeError, ValueError):
            p = 0.0
        if p < style_prob_floor:
            continue
        label = row.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        parts = [x.strip().lower() for x in label.split("---") if x.strip()]
        for part in parts:
            n = normalize_genre(part)
            if n:
                out.add(n)
            alias = _STYLE_TAIL_ALIASES.get(part)
            if alias and alias in GENRES:
                out.add(alias)
            for phrase, ag in _STYLE_TAIL_ALIASES.items():
                if " " in phrase and phrase in part and ag in GENRES:
                    out.add(ag)
            for w in re.findall(r"[a-z][a-z0-9]+(?:[\s-][a-z0-9]+)?", part):
                n2 = normalize_genre(w)
                if n2:
                    out.add(n2)
                ag = _STYLE_TAIL_ALIASES.get(w)
                if ag and ag in GENRES:
                    out.add(ag)
            if "drum" in part and "bass" in part:
                out.add("drum-and-bass")
    return out


def discogs_style_tokens(
    entry: Dict[str, Any],
    *,
    style_prob_floor: float = 0.10,
    max_rows: int = 4,
) -> Set[str]:
    """Tokens from ``discogs_styles`` only (backfill pass 2 — subgenres)."""
    return _style_rows_tokens(entry.get("discogs_styles") or [], style_prob_floor=style_prob_floor, max_rows=max_rows)


def discogs_keyword_tokens(entry: Dict[str, Any], *, style_prob_floor: float = 0.07) -> Set[str]:
    """Union of parent + style tokens for pad-query keyword matching."""
    out = parent_genre_tokens(entry)
    out |= _style_rows_tokens(
        entry.get("discogs_styles") or [],
        style_prob_floor=style_prob_floor,
        max_rows=6,
    )
    return out


def suggested_genre_list(entry: Dict[str, Any]) -> List[str]:
    """Existing ``genre`` entries first, then Discogs-derived (deduped)."""
    existing = [str(g).lower() for g in (entry.get("genre") or []) if isinstance(g, str) and g.strip()]
    seen = set(existing)
    merged = list(existing)
    for t in sorted(discogs_keyword_tokens(entry, style_prob_floor=0.06)):
        if t not in seen:
            merged.append(t)
            seen.add(t)
    return merged
