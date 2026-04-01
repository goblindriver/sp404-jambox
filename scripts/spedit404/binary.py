# Vendored from spEdit404 (binary_utilities.py), adapted for direct path output
import binascii
from itertools import islice
from . import constants
from .utils import add_padding


def write_binary(pattern, bank_letter, pad_number, output_path):
    """Write a Pattern to a .BIN file at the given path."""
    with open(output_path, 'wb') as f:
        notes = get_sorted_notes(pattern)
        for i, note in enumerate(notes):
            write_note_hex_data(i, note, notes, f)
        write_pattern_length_hex_data(f, pattern)


def get_sorted_notes(pattern):
    notes = [note for track in pattern.tracks for note in track.notes]
    return sorted(notes, key=lambda n: n.start_tick)


def write_note_hex_data(i, note, notes, f):
    is_last = i + 1 == len(notes)
    next_start = note.start_tick if is_last else notes[i + 1].start_tick
    write_hex(f, write_note(note, next_start))


def write_pattern_length_hex_data(f, pattern):
    encoding = constants.length_encoding.format(get_bar_code(pattern))
    write_hex(f, encoding)


def write_hex(f, hex_string):
    f.write(binascii.unhexlify(''.join(hex_string.split()).strip()))


def write_note(note, next_note_start_tick):
    velocity = add_padding(str(hex(note.velocity))[2:], 2)
    next_note = next_note_start_tick - note.start_tick
    next_note_hex = add_padding(str(hex(next_note))[2:], 2)
    pad_code, bank_switch = gen_pad_code_bank_switch(note.bank, note.pad)
    length_hex = get_hex_length(note.length)
    return f'{next_note_hex}{pad_code}0{bank_switch}00{velocity}40{length_hex}\n'


def gen_pad_code_bank_switch(bank_letter, pad_number):
    bank_number = ord(bank_letter.lower()) - constants.ascii_character_offset
    bank_switch = 1 if bank_number >= constants.number_of_bank_pads else 0
    bank_number -= constants.secondary_bank_offset if bank_switch else 0
    bank_offset = bank_number * constants.pads_per_bank
    pad_offset = bank_offset + int(pad_number) + constants.pad_offset_magic_number
    return add_padding(str(hex(pad_offset))[2:], 2), str(bank_switch)


def get_hex_length(length):
    return add_padding(str(hex(length))[2:], 4)


def get_bar_code(pattern):
    return add_padding(str(hex(pattern.length))[2:], 2)


def get_pad_code(bank_letter, pad_number):
    bank = ord(bank_letter.lower()) - constants.ascii_character_offset
    code = str(hex((bank * constants.pads_per_bank) + int(pad_number)))[2:]
    return add_padding(code, 3)


def get_ptn_filename(bank_letter, pad_number):
    """Get the SP-404 pattern filename for a given bank/pad."""
    return f"PTN00{get_pad_code(bank_letter, pad_number)}.BIN"
