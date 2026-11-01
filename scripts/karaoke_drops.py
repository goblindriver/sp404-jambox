#!/usr/bin/env python3
"""Karaoke drop sheets: when to fire which SP-404A pad during a song.

Two jobs, both pure Python (no MIDI library needed here):

1. **MIDI mapping** (SP-404A Reference Manual p. 47-48). Banks A-E receive on
   Pad Base Ch, banks F-J on Pad Base Ch + 1; within each group the five banks
   take notes 47-58, 59-70, 71-82, 83-94, 95-106 (pads 1-12). Note 46 is EXT
   SOURCE (toggle the mic input).

2. **Drafting a drop sheet** from the song's beat grid and lyric structure, no
   LLM required: crowd pop when the band kicks in, riser into the first chorus,
   air horn / choir stab on every chorus downbeat (alternating), impact on the
   last chorus, cheer after the last line, applause on the way out. Everything
   snaps to the bar grid so it lands musically. The drafts are a starting
   point; the human edits ``song.json`` (or the web UI later).

Drop dict shape (stored in ``song.json['drops']``)::

    {"t": 61.2, "bank": "A", "pad": 3, "vel": 110, "label": "air horn: chorus 1"}
"""

EXT_SOURCE_NOTE = 46
BANKS = "ABCDEFGHIJ"

# Bank A on karaoke night = presets/utility/karaoke-drops.yaml. Keep in sync.
DROP_BANK = "A"
DROP_PADS = {
    "cheer": 1,
    "applause": 2,
    "airhorn": 3,
    "choir": 4,
    "crash": 5,
    "rewind": 6,
    "riser": 7,
    "impact": 8,
    "hype_vox": 9,
    "scratch": 10,
    "laser": 11,
    "gong": 12,
}

MIN_GAP_S = 3.0        # never stack two drafted drops closer than this
RISER_BARS = 2         # riser starts this many bars before the first chorus


def pad_to_midi(bank, pad, base_channel=1):
    """Map (bank letter, pad 1-12) → (channel 1-16, note).

    ``base_channel`` is the SP-404A's Pad Base Ch ([9] MIDI CH + CTRL 3), 1-16.
    Banks F-J use base_channel + 1 (wrapping 16 → 1 is not supported by the
    hardware, so base 16 is rejected for F-J).
    """
    bank = str(bank).upper()
    if bank not in BANKS or len(bank) != 1:
        raise ValueError(f"bank must be A-J, got {bank!r}")
    pad = int(pad)
    if not 1 <= pad <= 12:
        raise ValueError(f"pad must be 1-12, got {pad}")
    if not 1 <= int(base_channel) <= 16:
        raise ValueError("base_channel must be 1-16")
    idx = BANKS.index(bank)
    channel = int(base_channel) + (1 if idx >= 5 else 0)
    if channel > 16:
        raise ValueError("Pad Base Ch 16 leaves no channel for banks F-J")
    note = 47 + (idx % 5) * 12 + (pad - 1)
    return channel, note


def midi_to_pad(channel, note, base_channel=1):
    """Inverse of ``pad_to_midi``. Returns (bank, pad) or None."""
    if not 47 <= note <= 106:
        return None
    group = channel - int(base_channel)
    if group not in (0, 1):
        return None
    idx = (note - 47) // 12 + group * 5
    return BANKS[idx], (note - 47) % 12 + 1


# ── Beat grid helpers ────────────────────────────────────────────────

def bar_seconds(bpm, beats_per_bar=4):
    return 60.0 / float(bpm) * beats_per_bar


def snap_to_bar(t, bpm, first_beat_s=0.0, beats_per_bar=4):
    """Snap ``t`` to the nearest downbeat on the song's grid."""
    if not bpm:
        return round(t, 3)
    bar = bar_seconds(bpm, beats_per_bar)
    n = round((t - (first_beat_s or 0.0)) / bar)
    return round((first_beat_s or 0.0) + n * bar, 3)


# ── Drafting ─────────────────────────────────────────────────────────

def _drop(t, role, label, vel=100):
    return {"t": round(max(0.0, t), 3), "bank": DROP_BANK, "pad": DROP_PADS[role],
            "vel": int(vel), "label": label}


def draft_drop_sheet(*, duration_s, bpm=None, first_beat_s=0.0, choruses=(),
                     first_vocal_s=None, last_vocal_s=None, energy=None):
    """Draft a drop sheet for one song.

    ``choruses``: ``[(start_s, end_s), ...]`` from ``karaoke_lyrics.find_choruses``.
    ``energy``: optional 'low'/'mid'/'high' (e.g. from Plex moods). Low-energy
    songs get a gentler sheet (no air horns, softer velocities).
    """
    if not duration_s or duration_s <= 0:
        return []
    first_beat_s = first_beat_s or 0.0
    snap = (lambda t: snap_to_bar(t, bpm, first_beat_s)) if bpm else (lambda t: round(t, 3))
    bar = bar_seconds(bpm) if bpm else 2.0
    gentle = energy == "low"
    hit_vel = 90 if gentle else 115

    drops = []
    # 1. Crowd pop when the band kicks in (skip if vocals start almost immediately).
    kick_in = first_beat_s if first_beat_s and first_beat_s < 20 else 0.0
    if first_vocal_s is None or first_vocal_s - kick_in > 6.0:
        drops.append(_drop(max(kick_in, 0.25), "cheer", "crowd pop: band kicks in", 80 if gentle else 100))

    choruses = sorted(c for c in choruses if 0 < c[0] < duration_s)
    for i, (start, _end) in enumerate(choruses):
        down = snap(start)
        last = i == len(choruses) - 1 and len(choruses) > 1
        if i == 0:
            drops.append(_drop(down - RISER_BARS * bar, "riser", "riser into first chorus", 95))
        if last:
            drops.append(_drop(down, "impact", "impact: final chorus", hit_vel + 5))
            if not gentle:
                drops.append(_drop(down + bar * 4, "hype_vox", "hype vox: final chorus", 110))
        elif gentle:
            drops.append(_drop(down, "crash", f"crash: chorus {i + 1}", hit_vel))
        else:
            role = "airhorn" if i % 2 == 0 else "choir"
            name = "air horn" if role == "airhorn" else "choir stab"
            drops.append(_drop(down, role, f"{name}: chorus {i + 1}", hit_vel))

    if not choruses and bpm and not gentle:
        # No lyric structure: a horn every 32 bars after the first vocal (or kick-in).
        t = snap((first_vocal_s or kick_in) + 32 * bar)
        n = 1
        while t < duration_s - 20:
            drops.append(_drop(t, "airhorn" if n % 2 else "choir", f"hype {n} (no lyric map)", hit_vel))
            t += 32 * bar
            n += 1

    if last_vocal_s and last_vocal_s < duration_s - 4:
        drops.append(_drop(snap(last_vocal_s + bar), "cheer", "cheer: last line sung", 110 if not gentle else 85))
    drops.append(_drop(max(0.0, duration_s - 6.0), "applause", "applause: outro", 100))

    return _thin(drops)


def _thin(drops):
    """Sort and drop anything closer than MIN_GAP_S to the previous kept drop."""
    kept = []
    for d in sorted(drops, key=lambda d: d["t"]):
        if kept and d["t"] - kept[-1]["t"] < MIN_GAP_S:
            continue
        kept.append(d)
    return kept


def validate_drops(drops):
    """Normalize a hand-edited drop list; raises ValueError on bad entries."""
    clean = []
    for i, d in enumerate(drops or []):
        try:
            t = float(d["t"])
            bank = str(d.get("bank", DROP_BANK)).upper()
            pad = int(d["pad"])
            vel = int(d.get("vel", 100))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"drop #{i}: {exc}") from exc
        pad_to_midi(bank, pad)  # validates bank/pad
        if t < 0:
            raise ValueError(f"drop #{i}: negative time")
        clean.append({"t": round(t, 3), "bank": bank, "pad": pad,
                      "vel": max(1, min(127, vel)), "label": str(d.get("label", ""))})
    return sorted(clean, key=lambda d: d["t"])
