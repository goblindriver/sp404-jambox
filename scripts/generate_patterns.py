#!/usr/bin/env python3
"""Generate an SP-404 pattern from a Magenta-compatible external generator.

Usage:
    echo '{"variant":"drum","bpm":124,"bars":2,"bank":"c","pad":1}' | python scripts/generate_patterns.py
"""

import json
import os
import struct
import sys
import tempfile

from jambox_config import ConfigError, load_settings_for_script
from integration_runtime import IntegrationFailure, run_command
from spedit404.binary import get_ptn_filename, write_binary
from spedit404.note import Note
from spedit404.pattern import Pattern
import gen_patterns


SETTINGS = load_settings_for_script(__file__)
REPO_DIR = SETTINGS["REPO_DIR"]
DEFAULT_PTN_DIR = os.path.join(REPO_DIR, "sd-card-template", "ROLAND", "SP-404SX", "PTN")
TICKS_PER_QUARTER = 96
SUPPORTED_VARIANTS = {"drum", "melody", "trio"}
MAGENTA_TIMEOUT = 60


def _read_input():
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("Expected JSON on stdin")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object")
    return payload


def _read_vlq(data, offset):
    value = 0
    while True:
        if offset >= len(data):
            raise ValueError("Truncated MIDI data")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            break
    return value, offset


def _parse_midi_file(path):
    with open(path, "rb") as handle:
        data = handle.read()

    if data[:4] != b"MThd":
        raise ValueError("Generated file is not a MIDI file")
    if len(data) < 14:
        raise ValueError("Truncated MIDI header")

    header_length = struct.unpack(">I", data[4:8])[0]
    if header_length < 6 or 8 + header_length > len(data):
        raise ValueError("Invalid MIDI header")
    header = data[8:8 + header_length]
    _, ntracks, division = struct.unpack(">HHH", header[:6])
    if division == 0:
        raise ValueError("MIDI ticks per quarter must be positive")
    if division & 0x8000:
        raise ValueError("SMPTE MIDI time division is not supported")
    offset = 8 + header_length
    note_events = []

    for _ in range(ntracks):
        if offset + 8 > len(data):
            raise ValueError("Truncated MIDI track chunk")
        if data[offset:offset + 4] != b"MTrk":
            raise ValueError("Invalid MIDI track chunk")
        track_length = struct.unpack(">I", data[offset + 4:offset + 8])[0]
        if offset + 8 + track_length > len(data):
            raise ValueError("Truncated MIDI track data")
        track = data[offset + 8:offset + 8 + track_length]
        offset += 8 + track_length

        cursor = 0
        abs_tick = 0
        running_status = None
        active_notes = {}

        while cursor < len(track):
            delta, cursor = _read_vlq(track, cursor)
            abs_tick += delta

            if cursor >= len(track):
                raise ValueError("Truncated MIDI event")
            status = track[cursor]
            if status < 0x80:
                if running_status is None:
                    raise ValueError("MIDI running status without prior status byte")
                status = running_status
            else:
                cursor += 1
                running_status = status

            if status == 0xFF:
                if cursor >= len(track):
                    raise ValueError("Truncated MIDI meta event")
                meta_type = track[cursor]
                cursor += 1
                meta_length, cursor = _read_vlq(track, cursor)
                if cursor + meta_length > len(track):
                    raise ValueError("Truncated MIDI meta event data")
                cursor += meta_length
                continue
            if status in (0xF0, 0xF7):
                sysex_length, cursor = _read_vlq(track, cursor)
                if cursor + sysex_length > len(track):
                    raise ValueError("Truncated MIDI sysex event")
                cursor += sysex_length
                continue

            event_type = status & 0xF0
            channel = status & 0x0F
            if event_type in (0x80, 0x90):
                if cursor + 2 > len(track):
                    raise ValueError("Truncated MIDI note event")
                pitch = track[cursor]
                velocity = track[cursor + 1]
                cursor += 2
                key = (channel, pitch)
                if event_type == 0x90 and velocity > 0:
                    active_notes.setdefault(key, []).append((abs_tick, velocity))
                else:
                    starts = active_notes.get(key)
                    if starts:
                        start_tick, start_velocity = starts.pop(0)
                        note_events.append({
                            "pitch": pitch,
                            "channel": channel,
                            "start_tick": start_tick,
                            "duration_tick": max(1, abs_tick - start_tick),
                            "velocity": start_velocity,
                        })
            elif event_type in (0xA0, 0xB0, 0xE0):
                if cursor + 2 > len(track):
                    raise ValueError("Truncated MIDI channel event")
                cursor += 2
            elif event_type in (0xC0, 0xD0):
                if cursor + 1 > len(track):
                    raise ValueError("Truncated MIDI channel event")
                cursor += 1
            else:
                raise ValueError(f"Unsupported MIDI event: 0x{status:02x}")

    return note_events, division


def _quantize(value, step=6):
    return max(step, int(round(value / step) * step))


def _pad_map(note_events, variant):
    pitches = sorted({event["pitch"] for event in note_events})
    if not pitches:
        return {}

    if variant == "drum":
        base_pads = list(range(1, 5))
    else:
        base_pads = list(range(5, 13))

    mapping = {}
    for index, pitch in enumerate(pitches):
        mapping[pitch] = base_pads[index % len(base_pads)]
    return mapping


def _pattern_from_midi(note_events, midi_ticks_per_quarter, bars, bank, variant):
    pattern = Pattern(int(bars))
    mapping = _pad_map(note_events, variant)
    max_tick = bars * 384

    for event in note_events:
        start_tick = event["start_tick"] * TICKS_PER_QUARTER / midi_ticks_per_quarter
        duration_tick = event["duration_tick"] * TICKS_PER_QUARTER / midi_ticks_per_quarter
        sp_start = max(0, int(round(start_tick)))
        sp_length = _quantize(duration_tick)
        if sp_start >= max_tick:
            continue
        if sp_start + sp_length > max_tick:
            sp_length = max(6, max_tick - sp_start)

        try:
            pattern.add_note(
                Note(
                    pad=mapping[event["pitch"]],
                    bank=bank.lower(),
                    start_tick=sp_start,
                    length=sp_length,
                    velocity=max(1, min(127, int(event["velocity"]))),
                )
            )
        except ValueError:
            continue

    return pattern


def _resolve_checkpoint(payload):
    variant = payload.get("variant", "drum").lower()
    if variant not in SUPPORTED_VARIANTS:
        raise ValueError(f"variant must be one of: {', '.join(sorted(SUPPORTED_VARIANTS))}")

    requested = payload.get("checkpoint")
    checkpoint_dir = SETTINGS.get("MUSICVAE_CHECKPOINT_DIR", "")
    if not checkpoint_dir:
        raise ConfigError("SP404_MUSICVAE_CHECKPOINT_DIR is required for pattern generation")

    checkpoint = requested or f"{variant}.mag"
    path = checkpoint if os.path.isabs(checkpoint) else os.path.join(checkpoint_dir, checkpoint)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Checkpoint not found: {path}")
    return variant, path


def _coerce_int(value, default, *, minimum=None, maximum=None, field_name="value"):
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{field_name} must be <= {maximum}")
    return parsed


def _coerce_float(value, default, *, minimum=None, maximum=None, field_name="value"):
    try:
        parsed = float(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{field_name} must be <= {maximum}")
    return parsed


def _normalize_bank(value):
    bank = str(value or "c").strip().lower()
    if len(bank) != 1 or bank < "a" or bank > "j":
        raise ValueError("bank must be a single letter from A to J")
    return bank


def _build_magenta_command(payload, checkpoint_path, output_dir):
    command = SETTINGS.get("MAGENTA_COMMAND", "").strip()
    if not command:
        raise ConfigError("SP404_MAGENTA_COMMAND is required for pattern generation")

    variant = payload.get("variant", "drum").lower()
    bars = _coerce_int(payload.get("bars"), 2, minimum=1, maximum=16, field_name="bars")
    bpm = _coerce_int(payload.get("bpm"), 120, minimum=20, maximum=300, field_name="bpm")
    temperature = _coerce_float(payload.get("temperature"), 0.8, minimum=0.0, maximum=2.0, field_name="temperature")
    output_file = os.path.join(output_dir, "generated.mid")

    executable = os.path.basename(command)
    if executable == "music_vae_generate":
        config_name = {
            "drum": "groovae_2bar_tap_fixed_velocity",
            "melody": "cat-mel_2bar_big",
            "trio": "hierdec-trio_16bar",
        }[variant]
        if variant == "trio" and bars != 16:
            raise ValueError("trio variant requires 16 bars when using music_vae_generate")
        return [
            command,
            f"--config={config_name}",
            f"--checkpoint_file={checkpoint_path}",
            "--mode=sample",
            "--num_outputs=1",
            f"--num_steps={bars * 16}",
            f"--temperature={temperature}",
            f"--output_dir={output_dir}",
            f"--qpm={bpm}",
        ], output_file

    return [
        command,
        "--checkpoint", checkpoint_path,
        "--output", output_file,
        "--variant", variant,
        "--bpm", str(bpm),
        "--bars", str(bars),
        "--temperature", str(temperature),
        "--key", str(payload.get("key", "")),
    ], output_file


def _find_generated_midi(output_dir, preferred_output):
    if os.path.exists(preferred_output):
        return preferred_output
    for name in os.listdir(output_dir):
        if name.lower().endswith(".mid") or name.lower().endswith(".midi"):
            return os.path.join(output_dir, name)
    raise FileNotFoundError("Pattern generator did not produce a MIDI file")


def _write_starter_fallback(bank, pad, bars, output_dir):
    generator = gen_patterns.GENERATORS.get(bank.upper(), ("Utility", gen_patterns.gen_utility))[1]
    pattern = generator(bank)
    filename = get_ptn_filename(bank, pad)
    output_path = os.path.join(output_dir, filename)
    write_binary(pattern, bank, pad, output_path)
    return output_path


def generate_pattern(payload):
    bank = _normalize_bank(payload.get("bank", "c"))
    pad = _coerce_int(payload.get("pad"), 1, minimum=1, maximum=12, field_name="pad")
    bars = _coerce_int(payload.get("bars"), 2, minimum=1, maximum=16, field_name="bars")
    output_dir = payload.get("output_dir") or DEFAULT_PTN_DIR
    output_dir = os.path.abspath(output_dir)

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="jambox_magenta_") as tmpdir:
        try:
            variant, checkpoint_path = _resolve_checkpoint(payload)
            command, preferred_output = _build_magenta_command(payload, checkpoint_path, tmpdir)
            result = run_command(command, cwd=REPO_DIR, timeout=MAGENTA_TIMEOUT)
            midi_path = _find_generated_midi(tmpdir, preferred_output)
            note_events, midi_ticks_per_quarter = _parse_midi_file(midi_path)
            pattern = _pattern_from_midi(note_events, midi_ticks_per_quarter, bars, bank, variant)

            filename = get_ptn_filename(bank, pad)
            output_path = os.path.join(output_dir, filename)
            write_binary(pattern, bank, pad, output_path)
            fallback_used = False
            fallback_reason = ""
            fallback_code = ""
        except (IntegrationFailure, ConfigError, FileNotFoundError) as exc:
            output_path = _write_starter_fallback(bank, pad, bars, output_dir)
            variant = payload.get("variant", "drum").lower()
            checkpoint_path = ""
            fallback_used = True
            if isinstance(exc, IntegrationFailure):
                fallback_reason = exc.message if not exc.detail else f"{exc.message}: {exc.detail}"
                fallback_code = f"magenta_{exc.code}"
            else:
                fallback_reason = str(exc)
                fallback_code = "magenta_unavailable"
        except ValueError:
            raise

    return {
        "ok": True,
        "variant": variant,
        "checkpoint": checkpoint_path,
        "path": output_path,
        "bank": bank,
        "pad": pad,
        "bars": bars,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "fallback_code": fallback_code,
    }


def main():
    try:
        payload = _read_input()
        result = generate_pattern(payload)
        print(json.dumps(result, indent=2))
    except (ConfigError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_code": "invalid_input"}))
        raise SystemExit(1)
    except IntegrationFailure as exc:
        print(json.dumps({"ok": False, "error": exc.message, "error_code": exc.code, "detail": exc.detail}))
        raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_code": "unexpected_error"}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
