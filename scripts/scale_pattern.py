#!/usr/bin/env python3
"""
Scale-mapped pattern generator for SP-404SX.

Reads `scale_mapping` and `patterns` fields from preset YAML files and generates
.PTN binary files using the spedit404 library. No external AI/Magenta required —
pure algorithmic patterns: arpeggios, sequences, bass pulses, chord progressions.

Usage:
    # Generate all patterns from a preset
    python scripts/scale_pattern.py --preset presets/genre/fm-songwriter.yaml --bank c

    # Generate a specific pattern
    python scripts/scale_pattern.py --preset presets/genre/am-songwriter.yaml --bank c --pattern "Rising Arp"

    # From JSON on stdin (API mode)
    echo '{"preset_ref":"genre/fm-songwriter","bank":"c"}' | python scripts/scale_pattern.py --stdin
"""
import json
import os
import sys
import yaml
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spedit404.pattern import Pattern
from spedit404.note import Note
from spedit404.binary import write_binary, get_ptn_filename

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
PRESETS_DIR = os.path.join(REPO_DIR, 'presets')
DEFAULT_PTN_DIR = os.path.join(REPO_DIR, 'sd-card-template', 'ROLAND', 'SP-404SX', 'PTN')

# Timing constants (384 ticks per bar)
BAR = 384
QUARTER = 96
EIGHTH = 48
SIXTEENTH = 24

# Rate string → tick duration
RATE_MAP = {
    '1/4': QUARTER,
    '1/8': EIGHTH,
    '1/16': SIXTEENTH,
    '1bar': BAR,
    '2bar': BAR * 2,
    '1/2': QUARTER * 2,
}


def _parse_rate(rate_str):
    """Convert rate string to tick duration."""
    return RATE_MAP.get(str(rate_str), EIGHTH)


def _apply_swing(tick, swing, rate_ticks):
    """Apply swing to a tick position. swing=0.5 is straight, 0.6+ is swung."""
    if swing <= 0.5:
        return tick
    # Only swing offbeat notes (odd positions)
    beat_pos = tick % (rate_ticks * 2)
    if beat_pos >= rate_ticks:
        # This is an offbeat — push it forward
        swing_amount = int((swing - 0.5) * rate_ticks)
        return tick + swing_amount
    return tick


def _humanize_velocity(base_vel, amount=15):
    """Add slight velocity variation for human feel."""
    offset = random.randint(-amount, amount)
    return max(1, min(127, base_vel + offset))


def _generate_arpeggio(pattern_def, bank, bars=2):
    """Generate an arpeggio pattern from pad list + direction."""
    pads = pattern_def.get('pads', [])
    if not pads:
        return []

    direction = pattern_def.get('direction', 'up')
    rate = _parse_rate(pattern_def.get('rate', '1/8'))
    swing = float(pattern_def.get('swing', 0.5))
    base_velocity = int(pattern_def.get('velocity', 100))

    # Build the note sequence based on direction
    if direction == 'down':
        sequence = list(reversed(pads))
    elif direction == 'updown':
        sequence = list(pads) + list(reversed(pads[1:-1])) if len(pads) > 2 else list(pads)
    elif direction == 'random':
        sequence = list(pads)
        random.shuffle(sequence)
    else:  # 'up'
        sequence = list(pads)

    total_ticks = bars * BAR
    notes = []
    seq_len = len(sequence)
    if seq_len == 0:
        return notes

    tick = 0
    idx = 0
    while tick < total_ticks:
        pad = sequence[idx % seq_len]
        actual_tick = _apply_swing(tick, swing, rate)
        if actual_tick < total_ticks:
            # Accent pattern: first note of each cycle louder
            accent = 10 if (idx % seq_len == 0) else 0
            vel = _humanize_velocity(base_velocity + accent, 8)
            note_len = max(SIXTEENTH, rate - 4)  # slightly shorter than rate for separation
            notes.append((pad, bank, actual_tick, note_len, vel))
        tick += rate
        idx += 1

    return notes


def _generate_sequence(pattern_def, bank, bars=2):
    """Generate a repeating pad sequence (bass pulse, etc).
    For rates longer than a quarter note, retrigger at quarter intervals.
    """
    pads = pattern_def.get('pads', [])
    if not pads:
        return []

    rate = _parse_rate(pattern_def.get('rate', '1/4'))
    swing = float(pattern_def.get('swing', 0.5))
    base_velocity = int(pattern_def.get('velocity', 110))

    total_ticks = bars * BAR
    notes = []
    seq_len = len(pads)
    tick = 0
    idx = 0
    while tick < total_ticks:
        pad = pads[idx % seq_len]
        if rate > QUARTER:
            retriggers = rate // QUARTER
            for rt in range(retriggers):
                rt_tick = tick + rt * QUARTER
                actual_tick = _apply_swing(rt_tick, swing, QUARTER)
                if actual_tick < total_ticks:
                    vel_offset = 0 if rt == 0 else -12
                    vel = _humanize_velocity(base_velocity + vel_offset, 8)
                    notes.append((pad, bank, actual_tick, QUARTER - 4, vel))
        else:
            actual_tick = _apply_swing(tick, swing, rate)
            if actual_tick < total_ticks:
                vel = _humanize_velocity(base_velocity, 10)
                note_len = max(SIXTEENTH, rate - 4)
                notes.append((pad, bank, actual_tick, note_len, vel))
        tick += rate
        idx += 1

    return notes


def _generate_progression(pattern_def, bank, bars=2):
    """Generate a chord progression (long sustained hits).
    For rates longer than a quarter note, retrigger the pad at quarter-note
    intervals to maintain the chord feel (SP-404 is a sampler, no sustain).
    """
    pads = pattern_def.get('pads', [])
    if not pads:
        return []

    rate = _parse_rate(pattern_def.get('rate', '1bar'))
    swing = float(pattern_def.get('swing', 0.5))
    base_velocity = int(pattern_def.get('velocity', 100))

    total_ticks = bars * BAR
    notes = []
    seq_len = len(pads)
    tick = 0
    idx = 0
    while tick < total_ticks:
        pad = pads[idx % seq_len]
        # For long rates (> quarter note), retrigger at quarter intervals
        if rate > QUARTER:
            retriggers = rate // QUARTER
            for rt in range(retriggers):
                rt_tick = tick + rt * QUARTER
                actual_tick = _apply_swing(rt_tick, swing, QUARTER)
                if actual_tick < total_ticks:
                    # First hit is accent, retriggers are softer
                    vel_offset = 0 if rt == 0 else -15
                    vel = _humanize_velocity(base_velocity + vel_offset, 5)
                    notes.append((pad, bank, actual_tick, QUARTER - 4, vel))
        else:
            actual_tick = _apply_swing(tick, swing, rate)
            if actual_tick < total_ticks:
                vel = _humanize_velocity(base_velocity, 5)
                notes.append((pad, bank, actual_tick, max(SIXTEENTH, rate - 4), vel))
        tick += rate
        idx += 1

    return notes


def _generate_euclidean(pattern_def, bank, bars=2):
    """Generate a euclidean rhythm pattern.
    hits: number of hits to distribute
    steps: total steps in the cycle
    """
    pads = pattern_def.get('pads', [1])
    hits = int(pattern_def.get('hits', 5))
    steps = int(pattern_def.get('steps', 8))
    rate = _parse_rate(pattern_def.get('rate', '1/8'))
    swing = float(pattern_def.get('swing', 0.5))
    base_velocity = int(pattern_def.get('velocity', 100))

    # Bjorklund's algorithm
    def bjorklund(hits, steps):
        if hits >= steps:
            return [1] * steps
        pattern = [[1] if i < hits else [0] for i in range(steps)]
        while True:
            remainder = [p for p in pattern if p != pattern[0]]
            if len(remainder) <= 1:
                break
            count = min(len([p for p in pattern if p == pattern[0]]),
                        len(remainder))
            new_pattern = []
            for i in range(count):
                new_pattern.append(pattern[i] + remainder[i])
            leftover_start = count
            leftover_rem = len(remainder)
            for i in range(count, len(pattern) - leftover_rem):
                new_pattern.append(pattern[i])
            for i in range(count, leftover_rem):
                new_pattern.append(remainder[i])
            pattern = new_pattern
        return [bit for group in pattern for bit in group]

    rhythm = bjorklund(hits, steps)
    total_ticks = bars * BAR
    notes = []
    pad_idx = 0

    for cycle_start in range(0, total_ticks, steps * rate):
        for step, active in enumerate(rhythm):
            tick = cycle_start + step * rate
            if tick >= total_ticks:
                break
            if active:
                pad = pads[pad_idx % len(pads)]
                actual_tick = _apply_swing(tick, swing, rate)
                if actual_tick < total_ticks:
                    vel = _humanize_velocity(base_velocity, 12)
                    notes.append((pad, bank, actual_tick, max(SIXTEENTH, rate - 4), vel))
                pad_idx += 1

    return notes


# Pattern type → generator function
GENERATORS = {
    'arpeggio': _generate_arpeggio,
    'sequence': _generate_sequence,
    'progression': _generate_progression,
    'euclidean': _generate_euclidean,
}


def generate_scale_patterns(preset_data, bank, bars=2, pattern_name=None, ptn_dir=None):
    """Generate SP-404 .PTN files from a preset's scale_mapping + patterns.

    Args:
        preset_data: dict with 'patterns' list and optional 'scale_mapping'
        bank: bank letter (a-j)
        bars: bars per pattern (default 2)
        pattern_name: if set, only generate this named pattern
        ptn_dir: output directory for .PTN files

    Returns:
        list of {name, type, path, bank, pad_slot, bars, note_count}
    """
    if ptn_dir is None:
        ptn_dir = DEFAULT_PTN_DIR
    os.makedirs(ptn_dir, exist_ok=True)

    bank = bank.lower()
    patterns_list = preset_data.get('patterns', [])
    if not patterns_list:
        return []

    results = []
    # Each pattern gets its own .PTN file, assigned to sequential pad slots
    # starting from pad 1 (the bank's "pattern" slot)
    for slot_idx, pdef in enumerate(patterns_list):
        name = pdef.get('name', f'Pattern {slot_idx + 1}')
        ptype = pdef.get('type', 'sequence')

        # Filter by name if requested
        if pattern_name and name.lower() != pattern_name.lower():
            continue

        gen_func = GENERATORS.get(ptype)
        if not gen_func:
            continue

        # Generate the note list
        note_tuples = gen_func(pdef, bank, bars)
        if not note_tuples:
            continue

        # Build the Pattern object
        pattern = Pattern(bars)
        for pad, bnk, tick, length, vel in note_tuples:
            try:
                pattern.add_note(Note(
                    pad=int(pad),
                    bank=bnk,
                    start_tick=int(tick),
                    length=int(length),
                    velocity=int(vel),
                ))
            except ValueError:
                continue

        # Write to .PTN file — assign to pad slot (1-indexed)
        pad_slot = slot_idx + 1
        if pad_slot > 12:
            break  # max 12 patterns per bank

        filename = get_ptn_filename(bank, pad_slot)
        out_path = os.path.join(ptn_dir, filename)
        write_binary(pattern, bank, pad_slot, out_path)

        note_count = sum(len(t.notes) for t in pattern.tracks)
        results.append({
            'name': name,
            'type': ptype,
            'path': out_path,
            'bank': bank.upper(),
            'pad_slot': pad_slot,
            'bars': bars,
            'note_count': note_count,
        })

    return results


def generate_from_preset_file(preset_path, bank, bars=2, pattern_name=None, ptn_dir=None):
    """Load a preset YAML and generate its patterns."""
    with open(preset_path) as f:
        preset_data = yaml.safe_load(f)
    if not isinstance(preset_data, dict):
        raise ValueError(f"Invalid preset file: {preset_path}")
    return generate_scale_patterns(preset_data, bank, bars, pattern_name, ptn_dir)


def generate_from_preset_ref(ref, bank, bars=2, pattern_name=None, ptn_dir=None):
    """Load a preset by reference (e.g. 'genre/fm-songwriter') and generate patterns."""
    path = os.path.join(PRESETS_DIR, f"{ref}.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Preset not found: {ref}")
    return generate_from_preset_file(path, bank, bars, pattern_name, ptn_dir)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate scale-mapped patterns for SP-404SX')
    parser.add_argument('--preset', help='Path to preset YAML file')
    parser.add_argument('--ref', help='Preset reference (e.g. genre/fm-songwriter)')
    parser.add_argument('--bank', default='c', help='Target bank letter (a-j)')
    parser.add_argument('--bars', type=int, default=2, help='Bars per pattern')
    parser.add_argument('--pattern', help='Generate only this named pattern')
    parser.add_argument('--output', help='Output directory for .PTN files')
    parser.add_argument('--stdin', action='store_true', help='Read JSON from stdin (API mode)')
    args = parser.parse_args()

    if args.stdin:
        payload = json.loads(sys.stdin.read().strip())
        ref = payload.get('preset_ref')
        preset_path = payload.get('preset_path')
        bank = payload.get('bank', 'c')
        bars = int(payload.get('bars', 2))
        pattern_name = payload.get('pattern_name')
        ptn_dir = payload.get('output_dir') or args.output or DEFAULT_PTN_DIR

        if ref:
            results = generate_from_preset_ref(ref, bank, bars, pattern_name, ptn_dir)
        elif preset_path:
            results = generate_from_preset_file(preset_path, bank, bars, pattern_name, ptn_dir)
        else:
            # Inline preset data in the payload
            results = generate_scale_patterns(payload, bank, bars, pattern_name, ptn_dir)

        print(json.dumps({'ok': True, 'patterns': results}, indent=2))
        return

    if args.preset:
        results = generate_from_preset_file(args.preset, args.bank, args.bars, args.pattern, args.output)
    elif args.ref:
        results = generate_from_preset_ref(args.ref, args.bank, args.bars, args.pattern, args.output)
    else:
        parser.error('--preset or --ref required (or --stdin for API mode)')
        return

    print(f"=== Scale Pattern Generator ===")
    for r in results:
        print(f"  {r['name']} ({r['type']}): Bank {r['bank']} Pad {r['pad_slot']} — {r['note_count']} notes, {r['bars']} bars")
    print(f"\n{len(results)} patterns generated")


if __name__ == '__main__':
    main()
