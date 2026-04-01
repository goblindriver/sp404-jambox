#!/usr/bin/env python3
"""
Generate starter beat patterns for each SP-404SX genre bank.
Creates .PTN files that go in ROLAND/SP-404SX/PTN/ on the SD card.

Uses vendored spEdit404 library (patched for banks A-J).
Pattern format: 384 ticks per bar, 96 = quarter note, 48 = eighth, 24 = 16th.

Each bank gets a 2-bar pattern using its own drum hits (pads 1-4):
  Pad 1 = Kick, Pad 2 = Snare, Pad 3 = Hi-Hat, Pad 4 = Clap/Perc
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spedit404.pattern import Pattern
from spedit404.note import Note
from spedit404.binary import write_binary, get_ptn_filename

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
PTN_DIR = os.path.join(REPO_DIR, "sd-card-template", "ROLAND", "SP-404SX", "PTN")

# Timing constants
BAR = 384
Q = 96    # quarter note
E = 48    # eighth note
S = 24    # sixteenth note
HIT = 24  # default note length (16th)
LONG = 48 # longer hit


def add_notes(pattern, notes):
    """Add a list of (pad, bank, start_tick, length, velocity) tuples."""
    for pad, bank, tick, length, vel in notes:
        pattern.add_note(Note(pad=pad, bank=bank, start_tick=tick, length=length, velocity=vel))


def gen_lofi_hiphop(bank='c'):
    """Bank C: Lo-fi hip-hop — lazy, swung boom-bap (2 bars)"""
    p = Pattern(2)
    notes = []
    for bar in range(2):
        b = bar * BAR
        # Kick: beat 1 and the "and" of 2
        notes += [(1, bank, b + 0, HIT, 110), (1, bank, b + Q*2 + E, HIT, 90)]
        # Snare: beats 2 and 4
        notes += [(2, bank, b + Q, HIT, 100), (2, bank, b + Q*3, HIT, 105)]
        # Hi-hat: eighth notes, lighter on offbeats
        for i in range(8):
            vel = 80 if i % 2 == 0 else 55
            notes.append((3, bank, b + i * E, HIT, vel))
    add_notes(p, notes)
    return p


def gen_witch_house(bank='d'):
    """Bank D: Witch house — slow, sparse, heavy (2 bars)"""
    p = Pattern(2)
    notes = []
    for bar in range(2):
        b = bar * BAR
        # Kick: beat 1 only, heavy
        notes.append((1, bank, b + 0, LONG, 127))
        # Snare/clap: beat 3 (half-time feel)
        notes.append((4, bank, b + Q*2, LONG, 110))
        # Hat: sparse, every other beat
        notes += [(3, bank, b + Q, HIT, 60), (3, bank, b + Q*3, HIT, 50)]
    add_notes(p, notes)
    return p


def gen_nu_rave(bank='e'):
    """Bank E: Nu-rave — four-on-the-floor, high energy (2 bars)"""
    p = Pattern(2)
    notes = []
    for bar in range(2):
        b = bar * BAR
        # Kick: four on the floor
        for beat in range(4):
            notes.append((1, bank, b + beat * Q, HIT, 120))
        # Clap: beats 2 and 4
        notes += [(3, bank, b + Q, HIT, 100), (3, bank, b + Q*3, HIT, 100)]
        # Hat: 16th notes, accented on offbeats
        for i in range(16):
            vel = 70 if i % 2 == 0 else 90
            notes.append((2, bank, b + i * S, S - 2, vel))
        # Extra FX hit on beat 4 "and" in bar 2
        if bar == 1:
            notes.append((4, bank, b + Q*3 + E, HIT, 80))
    add_notes(p, notes)
    return p


def gen_electroclash(bank='f'):
    """Bank F: Electroclash — punchy, driving (2 bars)"""
    p = Pattern(2)
    notes = []
    for bar in range(2):
        b = bar * BAR
        # Kick: four on the floor
        for beat in range(4):
            notes.append((1, bank, b + beat * Q, HIT, 115))
        # Snare: 2 and 4
        notes += [(2, bank, b + Q, HIT, 105), (2, bank, b + Q*3, HIT, 105)]
        # Hat: offbeat eighths
        for i in range(4):
            notes.append((3, bank, b + i * Q + E, HIT, 75))
        # Perc accent
        notes.append((4, bank, b + Q*3 + E, HIT, 70))
    add_notes(p, notes)
    return p


def gen_funk(bank='g'):
    """Bank G: Funk — syncopated, groovy (2 bars)"""
    p = Pattern(2)
    notes = []
    for bar in range(2):
        b = bar * BAR
        # Kick: beat 1, "and" of 2, beat 4
        notes += [
            (1, bank, b + 0, HIT, 115),
            (1, bank, b + Q*2 + E, HIT, 95),
            (1, bank, b + Q*3, HIT, 100),
        ]
        # Snare: ghost on "e" of 2, solid on 3
        notes += [
            (2, bank, b + Q + S, HIT, 50),   # ghost note
            (2, bank, b + Q*2, HIT, 110),     # backbeat
        ]
        if bar == 1:
            notes.append((2, bank, b + Q*3 + S*3, HIT, 60))  # fill ghost
        # Hat: 16th note groove
        for i in range(16):
            vel = 90 if i % 4 == 0 else (65 if i % 2 == 0 else 45)
            notes.append((3, bank, b + i * S, S - 2, vel))
    add_notes(p, notes)
    return p


def gen_idm(bank='h'):
    """Bank H: IDM — irregular, glitchy (2 bars)"""
    p = Pattern(2)
    notes = []
    # IDM is intentionally irregular — different patterns each bar
    # Bar 1: syncopated kick cluster
    notes += [
        (1, bank, 0, HIT, 120),
        (1, bank, S*3, HIT, 80),
        (1, bank, Q*2, HIT, 110),
        (1, bank, Q*3 + S, HIT, 90),
    ]
    # Bar 1: scattered hats
    for tick in [E, Q + S*3, Q*2 + E, Q*3]:
        notes.append((2, bank, tick, S - 2, 70))
    # Bar 1: accent hits
    notes += [(3, bank, Q + E, HIT, 100), (4, bank, Q*3 + E, HIT, 85)]

    # Bar 2: different rhythm
    b = BAR
    notes += [
        (1, bank, b + S, HIT, 100),
        (1, bank, b + Q + S*3, HIT, 115),
        (1, bank, b + Q*2 + S*2, HIT, 90),
        (1, bank, b + Q*3 + E, HIT, 105),
    ]
    for tick in [0, S*2, Q*2, Q*2 + S*3, Q*3 + S]:
        notes.append((2, bank, b + tick, S - 2, 65))
    notes.append((3, bank, b + Q*2 + E, LONG, 90))

    add_notes(p, notes)
    return p


def gen_ambient(bank='i'):
    """Bank I: Ambient — minimal, breathing (2 bars)"""
    p = Pattern(2)
    notes = []
    for bar in range(2):
        b = bar * BAR
        # Very sparse — just a gentle hat and perc
        notes.append((1, bank, b + 0, LONG, 50))
        notes.append((2, bank, b + Q*2, LONG, 40))
    # One soft hit in bar 2
    notes.append((1, bank, BAR + Q*3, LONG, 35))
    add_notes(p, notes)
    return p


def gen_utility(bank='j'):
    """Bank J: Utility — straight metronome-style (2 bars)"""
    p = Pattern(2)
    notes = []
    for bar in range(2):
        b = bar * BAR
        # Simple 4/4 click track
        for beat in range(4):
            vel = 120 if beat == 0 else 80
            notes.append((1, bank, b + beat * Q, HIT, vel))
        # Offbeat percussion
        for beat in range(4):
            notes.append((3, bank, b + beat * Q + E, HIT, 60))
    add_notes(p, notes)
    return p


GENERATORS = {
    'C': ('Lo-Fi Hip-Hop', gen_lofi_hiphop),
    'D': ('Witch House', gen_witch_house),
    'E': ('Nu-Rave', gen_nu_rave),
    'F': ('Electroclash', gen_electroclash),
    'G': ('Funk & Horns', gen_funk),
    'H': ('IDM', gen_idm),
    'I': ('Ambient', gen_ambient),
    'J': ('Utility', gen_utility),
}


def generate_patterns(ptn_dir=None):
    """Generate starter patterns for all genre banks."""
    if ptn_dir is None:
        ptn_dir = PTN_DIR
    os.makedirs(ptn_dir, exist_ok=True)

    print("=== Generating Starter Patterns ===")
    for bank, (name, gen_func) in GENERATORS.items():
        pattern = gen_func(bank.lower())
        # Write pattern to pad 1 of that bank (the "bank pattern")
        filename = get_ptn_filename(bank.lower(), 1)
        out_path = os.path.join(ptn_dir, filename)
        write_binary(pattern, bank.lower(), 1, out_path)
        print(f"  Bank {bank} ({name}): {filename} — 2-bar pattern")

    print(f"\nDone! {len(GENERATORS)} patterns written to {ptn_dir}")


if __name__ == '__main__':
    ptn = sys.argv[1] if len(sys.argv) > 1 else None
    generate_patterns(ptn)
