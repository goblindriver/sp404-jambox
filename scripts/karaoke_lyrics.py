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
import time
from collections import Counter
from dataclasses import dataclass

LRCLIB_BASE = "https://lrclib.net/api"
USER_AGENT = "sp404-jambox karaoke_prep (https://github.com/goblindriver/sp404-jambox)"

_TS_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_WORD_TS_RE = re.compile(r"<(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?>")
_MIDICO_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]\d+:(/?)(.*)$")
_OFFSET_RE = re.compile(r"^\[offset:\s*([+-]?\d+)\s*\]", re.IGNORECASE)
_META_RE = re.compile(r"^\[(ar|ti|al|by|length|re|ve|au|#):", re.IGNORECASE)


@dataclass(frozen=True)
class LyricLine:
    t: float      # seconds from song start
    text: str
    words: tuple = ()  # ((t, word), ...) when the source times each word


def _stamp_seconds(mins, secs, frac):
    frac = frac or "0"
    return int(mins) * 60 + int(secs) + int(frac) / (10 ** len(frac))


def _lrc_stamp(t):
    mins, secs = divmod(t, 60)
    return f"{int(mins):02d}:{secs:05.2f}"


# ── LRC ──────────────────────────────────────────────────────────────

def _parse_words(rest, line_t, offset_s):
    """Enhanced-LRC word stamps (``<mm:ss.xx>word``) as ((t, word), ...); () without any."""
    parts = _WORD_TS_RE.split(rest)  # [lead, mm, ss, frac, text, mm, ss, frac, text, ...]
    if len(parts) == 1:
        return ()
    words = [(line_t, w) for w in parts[0].split()]
    for i in range(1, len(parts), 4):
        t = round(max(0.0, _stamp_seconds(*parts[i:i + 3]) - offset_s), 3)
        words += [(t, w) for w in parts[i + 3].split()]
    return tuple(words)


def parse_lrc(text):
    """Parse LRC into time-sorted LyricLines.

    Handles multiple timestamps per line (``[00:12.00][01:30.00]chorus``),
    ``[offset:+/-ms]`` (positive offset = lyrics earlier, per LRC convention),
    metadata tags, and enhanced word timings (``<00:12.34>word``, kept in
    ``LyricLine.words`` for single-stamp lines). Blank timed lines are kept as
    instrumental gaps (text ``""``).
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
            stamps.append(_stamp_seconds(m.group(1), m.group(2), m.group(3)))
            pos = m.end()
        if not stamps:
            continue
        lyric = " ".join(_WORD_TS_RE.sub(" ", raw[pos:]).split())
        for t in stamps:
            line_t = round(max(0.0, t - offset_s), 3)
            # Word stamps are absolute, so they only belong to a line sung once.
            words = _parse_words(raw[pos:], line_t, offset_s) if len(stamps) == 1 else ()
            lines.append(LyricLine(line_t, lyric, words))
    lines.sort(key=lambda ln: ln.t)
    return lines


def parse_midico(text):
    """karaoke-gen's MidiCo LRC: ``[mm:ss.xxx]1:word`` per word, ``/`` starts a line."""
    lines = []
    for raw in (text or "").splitlines():
        m = _MIDICO_RE.match(raw.strip())
        if not m:
            continue
        t = round(_stamp_seconds(m.group(1), m.group(2), m.group(3)), 3)
        if m.group(4) or not lines:
            lines.append((t, []))
        if m.group(5).strip():
            lines[-1][1].append((t, m.group(5).strip()))
    return [LyricLine(t, " ".join(w for _, w in words), tuple(words)) for t, words in lines if words]


# With the separated vocal to listen to, a gap over this is checked, and the word
# moves when the vocal is audible for less than this share of it. Words Whisper
# parked in an intro or break measure 0.06-0.17; a held note around 0.5.
SUNG_CHECK_GAP_S = 2.5
HELD_NOTE_SUNG = 0.35


def tighten_word_gaps(lines, *, sung=None, first_line_gap_s=3.0, max_gap_s=8.0, step_s=0.3):
    """Pull stray early words up to the word after them, within each line.

    Whisper parks the first words of a line that follows an instrumental intro
    or break at 0:00 or seconds early ("Get" at 0.0, "a" at 13.2, "little" at
    17.5). A stray word is moved to ``step_s`` before the next word in its line.

    ``sung(t0, t1)`` is the share of that span where the separated vocal is
    audible: with it, any gap over ``SUNG_CHECK_GAP_S`` is checked and a word
    moves only when the vocal is mostly silent, so a held note keeps its start.
    Without it, the first sung line allows ``first_line_gap_s`` and later lines
    ``max_gap_s``.
    """
    out = []
    first = True
    for ln in lines:
        words = list(ln.words)
        gap = first_line_gap_s if first and words else max_gap_s
        first = first and not words
        for i in range(len(words) - 2, -1, -1):
            t, nxt = words[i][0], words[i + 1][0]
            if sung is not None:
                stray = nxt - t > SUNG_CHECK_GAP_S and sung(t, nxt) < HELD_NOTE_SUNG
            else:
                stray = nxt - t > gap
            if stray:
                words[i] = (round(max(0.0, nxt - step_s), 3), words[i][1])
        out.append(LyricLine(words[0][0], ln.text, tuple(words)) if words else ln)
    return out


def drop_word_loops(lines, *, min_run=6, max_avg_gap_s=0.12):
    """Remove Whisper hallucination loops: one word repeated faster than anyone sings.

    Over an instrumental intro Whisper can emit "la la la ..." dozens of times
    a few hundredths of a second apart. A run of ``min_run``+ identical words
    averaging under ``max_avg_gap_s`` apart is dropped; lines left empty go too.
    """
    out = []
    for ln in lines:
        words, keep, i = list(ln.words), [], 0
        while i < len(words):
            j = i
            key = words[i][1].lower().strip(",.!?")
            while j + 1 < len(words) and words[j + 1][1].lower().strip(",.!?") == key:
                j += 1
            run = j - i + 1
            if run < min_run or (words[j][0] - words[i][0]) / (run - 1) >= max_avg_gap_s:
                keep += words[i:j + 1]
            i = j + 1
        if not ln.words:
            out.append(ln)
        elif keep:
            out.append(LyricLine(keep[0][0], " ".join(w for _, w in keep), tuple(keep)))
    return out


def format_lrc(lines, *, artist=None, title=None):
    """Serialize LyricLines back to LRC text (enhanced, ``<mm:ss.xx>word``, where words are timed)."""
    out = []
    if artist:
        out.append(f"[ar:{artist}]")
    if title:
        out.append(f"[ti:{title}]")
    for ln in lines:
        body = " ".join(f"<{_lrc_stamp(t)}>{w}" for t, w in ln.words) if ln.words else ln.text
        out.append(f"[{_lrc_stamp(ln.t)}]{body}")
    return "\n".join(out) + "\n"


# ── LRCLIB ───────────────────────────────────────────────────────────

_RETRY_STATUS = {429, 500, 502, 503, 504}


def _get(http, url, params, headers, timeout, retries, backoff_s):
    """GET that retries server-side failures (5xx, 429, network) ``retries`` times."""
    for attempt in range(retries + 1):
        try:
            resp = http.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code not in _RETRY_STATUS:
                return resp
        except Exception:
            resp = None
        if attempt < retries:
            time.sleep(backoff_s * 2 ** attempt)
    return resp


def fetch_lrclib(artist, title, album=None, duration_s=None, *, session=None, timeout=10,
                 retries=0, backoff_s=2.0):
    """Look a song up on LRCLIB (free, no key).

    Returns ``{'synced': str|None, 'plain': str|None, 'source': 'lrclib',
    'id': int}`` or ``None``. Tries the exact ``/get`` endpoint first, then
    ``/search`` (picking the synced hit closest in duration). ``retries``
    re-asks after a 5xx/429 or network error, backing off from ``backoff_s``.
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
        resp = _get(http, f"{LRCLIB_BASE}/get", params, headers, timeout, retries, backoff_s)
        if resp is not None and resp.status_code == 200:
            hit = resp.json()
            if hit.get("syncedLyrics") or hit.get("plainLyrics"):
                return _lrclib_result(hit)
    except Exception:
        pass

    try:
        resp = _get(http, f"{LRCLIB_BASE}/search", {"artist_name": artist, "track_name": title},
                    headers, timeout, retries, backoff_s)
        if resp is None or resp.status_code != 200:
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
                online=True, session=None, retries=0):
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
        hit = fetch_lrclib(artist, title, album, duration_s, session=session, retries=retries)
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


def lyric_words(text):
    """Lower-case words without punctuation, for comparing lyrics."""
    return re.findall(r"[a-z0-9']+", (text or "").lower().replace("’", "'"))


def word_error_rate(reference, hypothesis):
    """Word-level edit distance over the reference length (word lists in, 0.0 = identical)."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    prev = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, 1):
        cur = [i] + [0] * len(hypothesis)
        for j, hyp in enumerate(hypothesis, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ref != hyp))
        prev = cur
    return prev[-1] / len(reference)


def longest_missed_run(reference, hypothesis):
    """Most reference words in a row that the hypothesis never matched (a skipped line or verse)."""
    import difflib
    matcher = difflib.SequenceMatcher(None, reference, hypothesis, autojunk=False)
    longest, done = 0, 0
    for a, _b, n in matcher.get_matching_blocks():
        longest = max(longest, a - done)
        done = a + n
    return longest


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


def _ass_word_sweep(start, words, end):
    """``{\\kf}`` per word, each filling until the next word starts (the last for up to 1.5s).

    Durations come from rounded cumulative offsets, so rounding never drifts
    the highlight away from the words over a long line.
    """
    def cs(t):
        return int(round((max(t, start) - start) * 100))

    parts = []
    if cs(words[0][0]) > 0:
        parts.append(f"{{\\k{cs(words[0][0])}}}")
    for i, (t, word) in enumerate(words):
        nxt = words[i + 1][0] if i + 1 < len(words) else min(end, t + 1.5)
        sep = " " if i + 1 < len(words) else ""
        parts.append(f"{{\\kf{max(1, cs(nxt) - cs(t))}}}{_ass_escape(word)}{sep}")
    return "".join(parts)


def render_ass(lines, *, title="Karaoke", duration_s=None, lead_in_s=1.5, countdown=True):
    """Render synced lines as ASS: current line big + yellow, next line dim below.

    The current line sweeps in with a ``\\kf`` fill so singers can see where
    they are inside a long line: word by word when the line has word timings,
    otherwise evenly across the line. Instrumental gaps >6s get a "♪" cue and,
    before the first vocal, a 3-2-1 countdown.
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
            if ln.words:
                body = _ass_word_sweep(start, ln.words, end)
            else:
                # Sweep a long line over no more than 8s; the remainder shows the next line early.
                sweep_cs = max(1, int(min(end - start, 8.0) * 100 * 0.9))
                body = f"{{\\kf{sweep_cs}}}{_ass_escape(text)}"
            out.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Now,,0,0,0,,{body}\n")
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
