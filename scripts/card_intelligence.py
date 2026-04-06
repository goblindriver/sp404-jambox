#!/usr/bin/env python3
"""SP-404 SD Card Intelligence Pipeline.

Reads all performance metadata from the card respecting the three-tier
storage model:

* **Tier 1 — Bank A (beds):** Internal memory.  WAV-direct inspection
  (no reliable PAD_INFO).  Detects provenance via RLND chunk and Roland
  default timestamp.

* **Tier 2 — Bank B (toolkit):** Internal memory with reliable PAD_INFO.
  Tracks adjustments across sessions.

* **Tier 3 — Banks C-J (session):** SD-card content.  Full PAD_INFO +
  pattern analytics + WAV provenance.

Outputs session snapshots to ``data/card_sessions/<timestamp>.json``.

Usage::

    python scripts/card_intelligence.py              # full pull
    python scripts/card_intelligence.py --summary    # print summary only
"""
import argparse
import datetime
import json
import os
import struct
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from jambox_config import load_settings_for_script

SETTINGS = load_settings_for_script(__file__)
SD_CARD = SETTINGS["SD_CARD"]
SD_SMPL_DIR = SETTINGS["SD_SMPL_DIR"]
SESSIONS_DIR = os.path.join(REPO_DIR, "data", "card_sessions")

BANKS = "ABCDEFGHIJ"
INTERNAL_BANKS = frozenset("AB")
ROLAND_DEFAULT_YEAR = 2009

# ═══════════════════════════════════════════════════════════
# WAV inspection utilities
# ═══════════════════════════════════════════════════════════

def wav_identity(wav_path, chunk_size=65536):
    """SHA-256 of the first chunk_size bytes of WAV audio data."""
    try:
        with open(wav_path, "rb") as f:
            header = f.read(12)
            if len(header) < 12 or header[:4] != b"RIFF":
                return None
            import hashlib
            h = hashlib.sha256()
            while True:
                chunk_hdr = f.read(8)
                if len(chunk_hdr) < 8:
                    break
                cid = chunk_hdr[:4]
                csz = struct.unpack("<I", chunk_hdr[4:])[0]
                if cid == b"data":
                    to_read = min(csz, chunk_size)
                    h.update(f.read(to_read))
                    return h.hexdigest()
                f.read(csz + (csz % 2))
    except (OSError, struct.error):
        pass
    return None


def wav_provenance(wav_path):
    """Classify provenance: device-created, jambox, or user-loaded."""
    has_rlnd = False
    try:
        with open(wav_path, "rb") as f:
            header = f.read(12)
            if len(header) < 12:
                return "user-loaded"
            while True:
                chunk_hdr = f.read(8)
                if len(chunk_hdr) < 8:
                    break
                cid = chunk_hdr[:4]
                csz = struct.unpack("<I", chunk_hdr[4:])[0]
                if cid == b"RLND":
                    has_rlnd = True
                    break
                f.read(csz + (csz % 2))
    except (OSError, struct.error):
        pass

    if has_rlnd:
        return "jambox"

    try:
        mtime = os.path.getmtime(wav_path)
        dt = datetime.datetime.fromtimestamp(mtime)
        if dt.year <= ROLAND_DEFAULT_YEAR:
            return "device-created"
    except OSError:
        pass

    return "user-loaded"


# ═══════════════════════════════════════════════════════════
# PAD_INFO.BIN decoder (standalone, no Flask dependency)
# ═══════════════════════════════════════════════════════════

def decode_padinfo(path):
    """Full PAD_INFO.BIN decode returning all fields per pad."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except (OSError, IOError):
        return {}

    if len(data) < 3840:
        return {}

    result = {}
    for bank_idx, bank_letter in enumerate(BANKS):
        for pad_num in range(1, 13):
            offset = (bank_idx * 12 + (pad_num - 1)) * 32
            record = data[offset : offset + 32]
            if len(record) < 32:
                continue
            fields = struct.unpack(">IIII BBBBBBBB II", record)
            orig_start, orig_end = fields[0], fields[1]
            user_start, user_end = fields[2], fields[3]
            volume = fields[4]
            lofi = bool(fields[5])
            loop = bool(fields[6])
            gate = bool(fields[7])
            reverse = bool(fields[8])
            channels = fields[10]
            tempo_mode = fields[11]
            orig_tempo_raw, user_tempo_raw = fields[12], fields[13]
            bpm_original = round(orig_tempo_raw / 10, 1) if orig_tempo_raw else 0
            bpm_user = round(user_tempo_raw / 10, 1) if user_tempo_raw else 0

            has_sample = orig_end > orig_start
            bpm_adjusted = tempo_mode == 2 and bpm_original != bpm_user
            trimmed = (user_start != orig_start or user_end != orig_end) and has_sample

            result[(bank_letter, pad_num)] = {
                "volume": volume,
                "lofi": lofi,
                "loop": loop,
                "gate": gate,
                "reverse": reverse,
                "channels": channels,
                "tempo_mode": tempo_mode,
                "bpm_original": bpm_original,
                "bpm_user": bpm_user,
                "bpm": bpm_user if bpm_adjusted else bpm_original,
                "bpm_adjusted": bpm_adjusted,
                "has_sample": has_sample,
                "trimmed": trimmed,
                "trim_start": user_start if trimmed else None,
                "trim_end": user_end if trimmed else None,
                "internal_memory": bank_letter in INTERNAL_BANKS,
                "padinfo_reliable": bank_letter not in INTERNAL_BANKS or bank_letter == "B",
            }
    return result


def padinfo_diffs(path):
    """Return only pads modified by the user (skip Bank A)."""
    all_pads = decode_padinfo(path)
    diffs = {}
    for (bank, pad), info in all_pads.items():
        if bank == "A":
            continue
        mods = []
        if info["bpm_adjusted"]:
            mods.append({"field": "bpm", "original": info["bpm_original"], "user": info["bpm_user"]})
        if info["trimmed"]:
            mods.append({"field": "trim", "trim_start": info["trim_start"], "trim_end": info["trim_end"]})
        if info["reverse"]:
            mods.append({"field": "reverse"})
        if info["lofi"]:
            mods.append({"field": "lofi"})
        if info["volume"] != 127:
            mods.append({"field": "volume", "value": info["volume"]})
        if mods:
            diffs[(bank, pad)] = {"settings": info, "modifications": mods}
    return diffs


# ═══════════════════════════════════════════════════════════
# Pattern analytics
# ═══════════════════════════════════════════════════════════

def read_all_patterns(ptn_dir):
    """Read all .PTN files and return per-pad usage stats.

    Returns dict keyed by ``"B2"`` style strings with ``hit_count``,
    ``avg_velocity``, ``patterns_appeared_in``, and ``total_ticks``.
    This function is imported by the scan API.
    """
    from spedit404.reader import read_binary, ptn_filename_to_bank_pad

    pad_stats = {}

    for fname in os.listdir(ptn_dir):
        if not fname.upper().endswith(".BIN"):
            continue
        fpath = os.path.join(ptn_dir, fname)
        try:
            notes, bars = read_binary(fpath)
        except Exception:
            continue

        seen_in_pattern = set()
        for note in notes:
            key = f"{note['bank'].upper()}{note['pad']}"
            if key not in pad_stats:
                pad_stats[key] = {
                    "hit_count": 0,
                    "velocities": [],
                    "patterns_appeared_in": 0,
                    "total_ticks": 0,
                }
            pad_stats[key]["hit_count"] += 1
            pad_stats[key]["velocities"].append(note["velocity"])
            pad_stats[key]["total_ticks"] += note["length"]
            seen_in_pattern.add(key)

        for key in seen_in_pattern:
            pad_stats[key]["patterns_appeared_in"] += 1

    # Finalize: compute averages and drop raw velocity lists
    for key, stats in pad_stats.items():
        vels = stats.pop("velocities")
        stats["avg_velocity"] = round(sum(vels) / len(vels), 1) if vels else 0

    return pad_stats


def pad_frequency(ptn_dir):
    """Return ``{(bank, pad): hit_count}`` across all patterns."""
    stats = read_all_patterns(ptn_dir)
    return {k: v["hit_count"] for k, v in stats.items()}


def velocity_profile(ptn_dir):
    """Return average velocity per pad across all patterns."""
    stats = read_all_patterns(ptn_dir)
    return {k: v["avg_velocity"] for k, v in stats.items()}


def timing_density(ptn_dir):
    """Return total tick length per pad (busier = more rhythmic importance)."""
    stats = read_all_patterns(ptn_dir)
    return {k: v["total_ticks"] for k, v in stats.items()}


def tier_grouped_stats(ptn_dir):
    """Group pattern stats by storage tier."""
    stats = read_all_patterns(ptn_dir)
    tiers = {"bed": {}, "toolkit": {}, "session": {}}
    for key, data in stats.items():
        bank_letter = key[0]
        if bank_letter == "A":
            tiers["bed"][key] = data
        elif bank_letter == "B":
            tiers["toolkit"][key] = data
        else:
            tiers["session"][key] = data
    return tiers


def co_occurring_pads(ptn_dir, min_shared=2):
    """Find pads that appear together in multiple patterns."""
    from spedit404.reader import read_binary

    pattern_pads = []
    for fname in os.listdir(ptn_dir):
        if not fname.upper().endswith(".BIN"):
            continue
        fpath = os.path.join(ptn_dir, fname)
        try:
            notes, _ = read_binary(fpath)
        except Exception:
            continue
        pads = set()
        for note in notes:
            pads.add(f"{note['bank'].upper()}{note['pad']}")
        if len(pads) >= 2:
            pattern_pads.append(pads)

    from collections import Counter
    pairs = Counter()
    for pads in pattern_pads:
        pad_list = sorted(pads)
        for i in range(len(pad_list)):
            for j in range(i + 1, len(pad_list)):
                pairs[(pad_list[i], pad_list[j])] += 1

    return {pair: count for pair, count in pairs.items() if count >= min_shared}


# ═══════════════════════════════════════════════════════════
# Three-tier card reader
# ═══════════════════════════════════════════════════════════

def _inspect_bank_a(sd_smpl):
    """Bank A: WAV-direct inspection (no PAD_INFO)."""
    files = []
    for fname in sorted(os.listdir(sd_smpl)):
        if not fname.upper().startswith("A") or not fname.upper().endswith(".WAV"):
            continue
        fpath = os.path.join(sd_smpl, fname)
        try:
            stat = os.stat(fpath)
        except OSError:
            continue
        dt = datetime.datetime.fromtimestamp(stat.st_mtime)
        prov = wav_provenance(fpath)
        files.append({
            "name": fname,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 1),
            "date": dt.isoformat()[:10],
            "source": prov,
            "performance_capture": prov == "device-created",
            "identity": wav_identity(fpath),
        })

    primary_bed = None
    for f in files:
        if f["performance_capture"] and (primary_bed is None or f["size_bytes"] > primary_bed["size_bytes"]):
            primary_bed = f

    return {
        "files": files,
        "primary_bed": primary_bed["name"] if primary_bed else None,
        "pad_count": len(files),
    }


def _inspect_bank_b(sd_smpl, pad_settings):
    """Bank B: PAD_INFO + WAV inspection."""
    files = []
    adjustments = []
    for pad_num in range(1, 13):
        fname = f"B{pad_num:07d}.WAV"
        fpath = os.path.join(sd_smpl, fname)
        if not os.path.isfile(fpath):
            continue
        prov = wav_provenance(fpath)
        settings = pad_settings.get(("B", pad_num), {})
        entry = {
            "name": fname,
            "pad": pad_num,
            "source": prov,
            "identity": wav_identity(fpath),
            "settings": {
                "bpm": settings.get("bpm", 0),
                "loop": settings.get("loop", False),
                "gate": settings.get("gate", False),
                "reverse": settings.get("reverse", False),
                "lofi": settings.get("lofi", False),
                "volume": settings.get("volume", 127),
            },
        }
        files.append(entry)

        if settings.get("bpm_adjusted"):
            adjustments.append({
                "bank": "B", "pad": pad_num, "field": "bpm",
                "original": settings["bpm_original"], "user": settings["bpm_user"],
            })
        if settings.get("reverse"):
            adjustments.append({"bank": "B", "pad": pad_num, "field": "reverse"})

    provenance_summary = "all_jambox"
    sources = {f["source"] for f in files}
    if len(sources) > 1:
        provenance_summary = "mixed"
    elif sources and "jambox" not in sources:
        provenance_summary = list(sources)[0]

    return {
        "files": files,
        "adjustments": adjustments,
        "provenance": provenance_summary,
        "pad_count": len(files),
    }


def _inspect_session_banks(sd_smpl, pad_settings, ptn_dir):
    """Banks C-J: full PAD_INFO + PTN + WAV."""
    adjustments = []
    per_bank = {}

    for bank_letter in "CDEFGHIJ":
        bank_pads = []
        for pad_num in range(1, 13):
            fname = f"{bank_letter}{pad_num:07d}.WAV"
            fpath = os.path.join(sd_smpl, fname)
            on_card = os.path.isfile(fpath)
            settings = pad_settings.get((bank_letter, pad_num), {})

            pad_entry = {
                "pad": pad_num,
                "on_card": on_card,
                "identity": wav_identity(fpath) if on_card else None,
                "provenance": wav_provenance(fpath) if on_card else None,
                "settings": {
                    "bpm": settings.get("bpm", 0),
                    "bpm_adjusted": settings.get("bpm_adjusted", False),
                    "bpm_original": settings.get("bpm_original", 0),
                    "bpm_user": settings.get("bpm_user", 0),
                    "loop": settings.get("loop", False),
                    "gate": settings.get("gate", False),
                    "reverse": settings.get("reverse", False),
                    "lofi": settings.get("lofi", False),
                    "trimmed": settings.get("trimmed", False),
                    "volume": settings.get("volume", 127),
                },
            }
            bank_pads.append(pad_entry)

            if settings.get("bpm_adjusted"):
                adjustments.append({
                    "bank": bank_letter, "pad": pad_num, "field": "bpm",
                    "original": settings["bpm_original"], "user": settings["bpm_user"],
                })

        per_bank[bank_letter] = {
            "pads": bank_pads,
            "filled": sum(1 for p in bank_pads if p["on_card"]),
        }

    # Pattern analytics
    pattern_usage = {}
    co_occur = {}
    if os.path.isdir(ptn_dir):
        pattern_usage = read_all_patterns(ptn_dir)
        co_occur = co_occurring_pads(ptn_dir)

    most_used = sorted(pattern_usage.items(), key=lambda x: x[1]["hit_count"], reverse=True)[:10]

    return {
        "adjustments": adjustments,
        "banks": per_bank,
        "pattern_usage": {
            "most_used": [{"pad": k, **v} for k, v in most_used],
            "co_occurring": [
                {"pads": list(pair), "count": count}
                for pair, count in sorted(co_occur.items(), key=lambda x: -x[1])[:10]
            ],
        },
    }


def pull_intelligence(sd_card=None, sd_smpl=None):
    """Full card intelligence pull.  Returns the session dict."""
    sd_card = sd_card or SD_CARD
    sd_smpl = sd_smpl or SD_SMPL_DIR

    if not os.path.isdir(sd_smpl):
        return {"error": "SD card not mounted"}

    padinfo_path = os.path.join(sd_smpl, "PAD_INFO.BIN")
    pad_settings = decode_padinfo(padinfo_path)
    ptn_dir = os.path.join(sd_card, "ROLAND", "SP-404SX", "PTN")

    session = {
        "session_date": datetime.datetime.now().isoformat(),
        "bed_context": _inspect_bank_a(sd_smpl),
        "toolkit": _inspect_bank_b(sd_smpl, pad_settings),
        "session_banks": _inspect_session_banks(sd_smpl, pad_settings, ptn_dir),
    }

    return session


def save_session(session, sessions_dir=None):
    """Archive a session snapshot to disk.  Returns the file path."""
    sessions_dir = sessions_dir or SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(sessions_dir, f"{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, default=str)
    return path


def load_latest_session(sessions_dir=None):
    """Load the most recent session snapshot, or None."""
    sessions_dir = sessions_dir or SESSIONS_DIR
    if not os.path.isdir(sessions_dir):
        return None
    files = sorted(f for f in os.listdir(sessions_dir) if f.endswith(".json"))
    if not files:
        return None
    path = os.path.join(sessions_dir, files[-1])
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def diff_sessions(current, previous):
    """Compare two sessions and return a summary of changes."""
    changes = []

    if not previous:
        return [{"type": "first_session", "message": "First card intelligence pull — no previous session to diff."}]

    # Bank A changes
    prev_a_files = {f["name"] for f in previous.get("bed_context", {}).get("files", [])}
    curr_a_files = {f["name"] for f in current.get("bed_context", {}).get("files", [])}
    new_beds = curr_a_files - prev_a_files
    removed_beds = prev_a_files - curr_a_files
    if new_beds:
        changes.append({"type": "new_beds", "files": sorted(new_beds)})
    if removed_beds:
        changes.append({"type": "removed_beds", "files": sorted(removed_beds)})

    # Bank B provenance changes
    prev_b_prov = previous.get("toolkit", {}).get("provenance", "")
    curr_b_prov = current.get("toolkit", {}).get("provenance", "")
    if prev_b_prov != curr_b_prov:
        changes.append({"type": "toolkit_provenance_change", "from": prev_b_prov, "to": curr_b_prov})

    # C-J adjustment changes
    prev_adj = {(a["bank"], a["pad"]): a for a in previous.get("session_banks", {}).get("adjustments", [])}
    curr_adj = {(a["bank"], a["pad"]): a for a in current.get("session_banks", {}).get("adjustments", [])}
    new_adjustments = set(curr_adj.keys()) - set(prev_adj.keys())
    if new_adjustments:
        changes.append({
            "type": "new_adjustments",
            "pads": [curr_adj[k] for k in sorted(new_adjustments)],
        })

    return changes


def print_summary(session):
    """Print a human-readable intelligence summary."""
    bed = session.get("bed_context", {})
    toolkit = session.get("toolkit", {})
    sess = session.get("session_banks", {})

    print("═══ SP-404 Card Intelligence ═══")
    print(f"  Date: {session.get('session_date', 'unknown')}")
    print()

    # Bank A
    print("── Bank A (Beds) ──")
    for f in bed.get("files", []):
        flag = " ★ PERFORMANCE CAPTURE" if f.get("performance_capture") else ""
        print(f"  {f['name']}  {f['size_mb']}MB  [{f['source']}]{flag}")
    if bed.get("primary_bed"):
        print(f"  Primary bed: {bed['primary_bed']}")
    print()

    # Bank B
    print("── Bank B (Toolkit) ──")
    print(f"  {toolkit.get('pad_count', 0)} pads loaded  [{toolkit.get('provenance', 'unknown')}]")
    for adj in toolkit.get("adjustments", []):
        print(f"  ⚡ B{adj['pad']}: {adj['field']} adjusted" +
              (f" {adj.get('original')} → {adj.get('user')}" if "original" in adj else ""))
    print()

    # Banks C-J
    print("── Banks C-J (Session) ──")
    for adj in sess.get("adjustments", []):
        print(f"  ⚡ {adj['bank']}{adj['pad']}: {adj['field']} {adj.get('original', '')} → {adj.get('user', '')}")
    ptn = sess.get("pattern_usage", {})
    most_used = ptn.get("most_used", [])
    if most_used:
        print("  Pattern favorites:")
        for item in most_used[:5]:
            print(f"    {item['pad']}: {item['hit_count']} hits, avg vel {item['avg_velocity']}, in {item['patterns_appeared_in']} patterns")
    co = ptn.get("co_occurring", [])
    if co:
        print("  Co-occurring pads:")
        for item in co[:5]:
            print(f"    {item['pads'][0]} + {item['pads'][1]} ({item['count']}x)")
    print()


def main():
    parser = argparse.ArgumentParser(description="SP-404 Card Intelligence Pull")
    parser.add_argument("--summary", action="store_true", help="Print summary only, don't save session")
    parser.add_argument("--sd-card", default=None, help="Override SD card mount path")
    args = parser.parse_args()

    sd_card = args.sd_card or SD_CARD
    sd_smpl = os.path.join(sd_card, "ROLAND", "SP-404SX", "SMPL")

    session = pull_intelligence(sd_card=sd_card, sd_smpl=sd_smpl)
    if "error" in session:
        print(f"Error: {session['error']}")
        sys.exit(1)

    print_summary(session)

    if not args.summary:
        previous = load_latest_session()
        path = save_session(session)
        print(f"Session saved: {path}")

        changes = diff_sessions(session, previous)
        if changes:
            print("\n── Changes since last session ──")
            for c in changes:
                if c["type"] == "first_session":
                    print(f"  {c['message']}")
                elif c["type"] == "new_beds":
                    print(f"  New beds in Bank A: {', '.join(c['files'])}")
                elif c["type"] == "removed_beds":
                    print(f"  Removed from Bank A: {', '.join(c['files'])}")
                elif c["type"] == "new_adjustments":
                    for adj in c["pads"]:
                        print(f"  New adjustment: {adj['bank']}{adj['pad']} {adj['field']}")
                else:
                    print(f"  {c}")


if __name__ == "__main__":
    main()
