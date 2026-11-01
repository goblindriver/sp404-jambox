#!/usr/bin/env python3
"""Karaoke lyrics: find synced lyrics, spot the choruses, render CRT-legible ASS.

Pure-Python except for the optional LRCLIB lookup (``requests``). Used by
``karaoke_prep.py`` (iMac, prep time) and readable by the deck on Windows.

    lines = parse_lrc(open("song.lrc").read())          # [LyricLine(t, text), ...]
    sections = find_choruses(lines)                      # [(start_s, end_s), ...]
    ass = render_ass(lines, title="Artist - Title")      # str, 4:3 safe
"""
import json
import os
import re
from collections import Counter
from dataclasses import dataclass

LRCLIB_BASE = "https://lrclib.net/api"
USER_AGENT = "sp404-jambox karaoke_prep (https://github.com/goblindriver/sp404-jambox)"

_TS_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_OFFSET_RE = re.compile(r"^\[offset:\s*([+-]?\d+)\s*\]", re.IGNORECASE)
_META_RE = re.compile(r"^\[(ar|ti|al|by|length|re|ve|au|#):", re.IGNORECASE)


@dataclass(frozen=True)
class LyricLine:
    t: float      # seconds from song start
    text: str


# ── LRC ──────────────────────────────────────────────────────────────

def parse_lrc(text):
    """Parse LRC into time-sorted LyricLines.

    Handles multiple timestamps per line (``[00:12.00][01:30.00]chorus``),
    ``[offset:+/-ms]`` (positive offset = lyrics earlier, per LRC convention),
    metadata tags, and enhanced word timings (``<00:12.34>`` — stripped).
    Blank timed lines are kept as instrumental gaps (text ``""``).
    """
    if not text:
        return []
    offset_s = 0.0
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        m = _OFFSET_RE.match(raw)
        if m:
            offset_s = int(m.group(1)) / 1000.0
            continue
        if _META_RE.match(raw):
            continue
        stamps = []
        pos = 0
        while True:
            m = _TS_RE.match(raw, pos)
            if not m:
                break
            mins, secs, frac = m.group(1), m.group(2), m.group(3) or "0"
            frac_s = int(frac) / (10 ** len(frac))
            stamps.append(int(mins) * 60 + int(secs) + frac_s)
            pos = m.end()
        if not stamps:
            continue
        lyric = re.sub(r"<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>", "", raw[pos:]).strip()
        for t in stamps:
            lines.append(LyricLine(round(max(0.0, t - offset_s), 3), lyric))
    lines.sort(key=lambda ln: ln.t)
    return lines


def format_lrc(lines, *, artist=None, title=None):
    """Serialize LyricLines back to LRC text."""
    out = []
    if artist:
        out.append(f"[ar:{artist}]")
    if title:
        out.append(f"[ti:{title}]")
    for ln in lines:
        mins, secs = divmod(ln.t, 60)
        out.append(f"[{int(mins):02d}:{secs:05.2f}]{ln.text}")
    return "\n".join(out) + "\n"


# ── LRCLIB ───────────────────────────────────────────────────────────

def fetch_lrclib(artist, title, album=None, duration_s=None, *, session=None, timeout=10):
    """Look a song up on LRCLIB (free, no key).

    Returns ``{'synced': str|None, 'plain': str|None, 'source': 'lrclib',
    'id': int}`` or ``None``. Tries the exact ``/get`` endpoint first, then
    ``/search`` (picking the synced hit closest in duration).
    """
    if not artist or not title:
        return None
    try:
        import requests
    except ImportError:
        return None
    http = session or requests
    headers = {"User-Agent": USER_AGENT}

    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration_s:
        params["duration"] = int(round(duration_s))
    try:
        resp = http.get(f"{LRCLIB_BASE}/get", params=params, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            hit = resp.json()
            if hit.get("syncedLyrics") or hit.get("plainLyrics"):
                return _lrclib_result(hit)
    except Exception:
        pass

    try:
        resp = http.get(f"{LRCLIB_BASE}/search",
                        params={"artist_name": artist, "track_name": title},
                        headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None
        hits = [h for h in (resp.json() or []) if not h.get("instrumental")]
    except Exception:
        return None
    if not hits:
        return None

    def rank(h):
        has_sync = 0 if h.get("syncedLyrics") else 1
        dur_gap = abs((h.get("duration") or 0) - duration_s) if duration_s else 0
        return (has_sync, dur_gap)

    best = min(hits, key=rank)
    # A synced hit >8s off in length is probably a different edit; timings would drift.
    if duration_s and best.get("duration") and abs(best["duration"] - duration_s) > 8:
        return {"synced": None, "plain": best.get("plainLyrics"),
                "source": "lrclib", "id": best.get("id")}
    return _lrclib_result(best)


def _lrclib_result(hit):
    return {
        "synced": hit.get("syncedLyrics") or None,
        "plain": hit.get("plainLyrics") or None,
        "source": "lrclib",
        "id": hit.get("id"),
    }


def find_lyrics(audio_path, artist=None, title=None, album=None, duration_s=None, *,
                online=True, session=None):
    """Lyrics lookup chain: ``.lrc`` sidecar → LRCLIB → none.

    Returns ``(lines, source, plain_text)`` where ``source`` is one of
    ``'sidecar'``, ``'lrclib'``, ``'lrclib-plain'`` or ``'none'``.
    """
    if audio_path:
        sidecar = os.path.splitext(audio_path)[0] + ".lrc"
        if os.path.isfile(sidecar):
            with open(sidecar, encoding="utf-8", errors="replace") as fh:
                lines = parse_lrc(fh.read())
            if lines:
                return lines, "sidecar", None
    if online:
        hit = fetch_lrclib(artist, title, album, duration_s, session=session)
        if hit and hit.get("synced"):
            lines = parse_lrc(hit["synced"])
            if lines:
                return lines, "lrclib", hit.get("plain")
        if hit and hit.get("plain"):
            return [], "lrclib-plain", hit["plain"]
    return [], "none", None


# ── Song structure ───────────────────────────────────────────────────

def _norm(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def find_choruses(lines, *, min_repeats=2, min_block=2, max_gap_s=10.0):
    """Find repeated multi-line blocks (choruses / hooks) in synced lyrics.

    A line that shows up ``min_repeats``+ times is "hooky". Consecutive hooky
    lines form a block; blocks shorter than ``min_block`` lines are ignored
    unless the single line repeats 3+ times (one-line hooks are a thing).
    Returns ``[(start_s, end_s), ...]`` sorted by time. ``end_s`` is the
    start of the line after the block (or the last line + 4s).
    """
    seq = sorted(lines, key=lambda ln: ln.t)
    sung = [ln for ln in seq if _norm(ln.text)]
    if len(sung) < 3:
        return []
    counts = Counter(_norm(ln.text) for ln in sung)
    # Empty lines (instrumental gaps) and long silences break a block, so a
    # chorus after a solo isn't merged into the one before it.
    hooky = [bool(_norm(ln.text)) and counts[_norm(ln.text)] >= min_repeats for ln in seq]

    blocks = []
    i = 0
    while i < len(seq):
        if not hooky[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(seq) and hooky[j + 1] and seq[j + 1].t - seq[j].t <= max_gap_s:
            j += 1
        size = j - i + 1
        if size >= min_block or counts[_norm(seq[i].text)] >= 3:
            start = seq[i].t
            end = seq[j + 1].t if j + 1 < len(seq) else seq[j].t + 4.0
            blocks.append((round(start, 3), round(end, 3)))
        i = j + 1
    return blocks


def first_vocal_time(lines):
    for ln in lines:
        if _norm(ln.text):
            return ln.t
    return None


# ── ASS rendering ────────────────────────────────────────────────────

# 640x480 PlayRes = 4:3. Font 52px ≈ 1/9 of screen height: legible on a 480i CRT
# through Moonlight + Extron. Margins keep text inside the CRT's overscan-safe box.
_ASS_HEADER = """[Script Info]
Title: {title}
ScriptType: v4.00+
PlayResX: 640
PlayResY: 480
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Now,Arial,52,&H0000F0FF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,3,2,2,48,48,150,1
Style: Next,Arial,40,&H00B0B0B0,&H00B0B0B0,&H00000000,&HA0000000,0,0,0,0,100,100,0,0,1,2,1,2,48,48,80,1
Style: Cue,Arial,34,&H00FFC060,&H00FFC060,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,2,1,8,48,48,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text):
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def render_ass(lines, *, title="Karaoke", duration_s=None, lead_in_s=1.5, countdown=True):
    """Render synced lines as ASS: current line big + yellow, next line dim below.

    The current line sweeps in with a ``\\kf`` fill across its own duration so
    singers can see where they are inside a long line. Instrumental gaps >6s
    get a "♪" cue and, before the first vocal, a 3-2-1 countdown.
    """
    sung = list(lines)
    out = [_ASS_HEADER.format(title=_ass_escape(title))]
    if not sung:
        return "".join(out)
    end_of_song = duration_s or (sung[-1].t + 6.0)
    first = first_vocal_time(sung)
    countdown_active = countdown and first is not None and first >= 4.0

    for idx, ln in enumerate(sung):
        nxt = sung[idx + 1] if idx + 1 < len(sung) else None
        start = ln.t
        end = nxt.t if nxt else min(end_of_song, ln.t + 6.0)
        if end <= start:
            continue
        text = ln.text.strip()
        if text:
            # Show a long line no more than 8s; the remainder shows the next line early.
            sweep_cs = max(1, int(min(end - start, 8.0) * 100 * 0.9))
            out.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Now,,0,0,0,,"
                       f"{{\\kf{sweep_cs}}}{_ass_escape(text)}\n")
        elif end - start > 6.0:
            out.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end - lead_in_s)},Cue,,0,0,0,,♪ ♪ ♪\n")
        # Preview the next sung line underneath.
        nxt_sung = next((n for n in sung[idx + 1:] if n.text.strip()), None)
        if nxt_sung and (nxt_sung.t - end) < 0.01:
            out.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Next,,0,0,0,,"
                       f"{_ass_escape(nxt_sung.text.strip())}\n")
        elif nxt_sung and not text and not (countdown_active and nxt_sung.t == first):
            out.append(f"Dialogue: 0,{_ass_time(max(start, nxt_sung.t - 4.0))},{_ass_time(end)},Next,,0,0,0,,"
                       f"{_ass_escape(nxt_sung.text.strip())}\n")

    if countdown_active:
        out.append(f"Dialogue: 0,{_ass_time(0.0)},{_ass_time(first - 3.0)},Next,,0,0,0,,"
                   f"{_ass_escape(title)}\n")
        nxt_text = next(ln.text for ln in sung if ln.text.strip())
        out.append(f"Dialogue: 0,{_ass_time(first - 3.0)},{_ass_time(first)},Next,,0,0,0,,"
                   f"{_ass_escape(nxt_text.strip())}\n")
        for n in (3, 2, 1):
            t0 = first - n
            out.append(f"Dialogue: 2,{_ass_time(t0)},{_ass_time(t0 + 1.0)},Cue,,0,0,0,,{'● ' * n}\n")
    return "".join(out)


def plain_to_ass(plain, *, title="Karaoke", duration_s=None):
    """Unsynced fallback: page through plain lyrics evenly across the song."""
    rows = [r.strip() for r in (plain or "").splitlines() if r.strip()]
    if not rows or not duration_s:
        return render_ass([], title=title)
    step = max(2.0, (duration_s * 0.85) / len(rows))
    start = duration_s * 0.08
    return render_ass([LyricLine(round(start + i * step, 2), r) for i, r in enumerate(rows)],
                      title=title, duration_s=duration_s, countdown=False)


if __name__ == "__main__":  # quick manual check: python karaoke_lyrics.py song.lrc
    import sys
    with open(sys.argv[1], encoding="utf-8") as fh:
        parsed = parse_lrc(fh.read())
    print(json.dumps({"lines": len(parsed), "choruses": find_choruses(parsed)}, indent=2))
