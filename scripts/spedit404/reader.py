"""Read SP-404 pattern (.PTN) binary files.

Reverses the writer in ``binary.py``.  Each note is encoded as 9 raw
bytes (18 hex chars) produced by the writer's ``write_note`` function::

    {delta_4h}{pad_code_2h}0{bank_switch_1h}00{velocity_2h}40{length_4h}

The file footer is 16 bytes: ``008C 00000000 0000 00{bars} 00000000 0000``.

Hardware-written files may differ slightly in layout; the reader falls
back to 8-byte records when 9-byte parsing fails.
"""
from . import constants


FOOTER_MARKER = b'\x00\x8c'
FOOTER_SIZE = 16
NOTE_SIZE_PRIMARY = 9
NOTE_SIZE_FALLBACK = 8

BANKS_LOWER = 'abcdefghij'


def _decode_pad_bank(pad_code, bank_switch):
    """Reverse ``gen_pad_code_bank_switch`` from the writer."""
    base = pad_code - constants.pad_offset_magic_number
    if bank_switch:
        base += constants.secondary_bank_offset * constants.pads_per_bank
    bank_idx = base // constants.pads_per_bank
    pad_num = base % constants.pads_per_bank
    if 0 <= bank_idx < constants.number_of_banks and 1 <= pad_num <= constants.pads_per_bank:
        return BANKS_LOWER[bank_idx], pad_num
    return None, None


def _parse_notes_9byte(body):
    """Parse note records at 9 bytes each."""
    notes = []
    pos = 0
    abs_tick = 0
    while pos + NOTE_SIZE_PRIMARY <= len(body):
        b = body[pos:pos + NOTE_SIZE_PRIMARY]
        delta = (b[0] << 8) | b[1]
        pad_code = b[2]
        bank_switch = (b[3] & 0x0F)
        velocity = b[5]
        note_len = (b[7] << 8) | b[8]

        abs_tick += delta
        bank, pad = _decode_pad_bank(pad_code, bank_switch)
        if bank is not None:
            notes.append({
                'bank': bank,
                'pad': pad,
                'tick': abs_tick,
                'velocity': velocity,
                'length': note_len,
            })
        pos += NOTE_SIZE_PRIMARY
    return notes


def _parse_notes_8byte(body):
    """Fallback parser for hardware-written 8-byte records."""
    notes = []
    pos = 0
    abs_tick = 0
    while pos + NOTE_SIZE_FALLBACK <= len(body):
        b = body[pos:pos + NOTE_SIZE_FALLBACK]
        pad_code = b[0]
        velocity = b[1]
        delta = (b[2] << 8) | b[3]
        pad_code2 = b[4]
        velocity2 = b[5]
        note_len = (b[6] << 8) | b[7]

        # Heuristic: if the pad_code looks like a valid pad offset, use it
        bank, pad = _decode_pad_bank(pad_code, 0)
        if bank is None:
            bank, pad = _decode_pad_bank(pad_code, 1)
        if bank is not None and 1 <= velocity <= constants.max_velocity:
            abs_tick += delta
            notes.append({
                'bank': bank,
                'pad': pad,
                'tick': abs_tick,
                'velocity': velocity,
                'length': note_len,
            })
        pos += NOTE_SIZE_FALLBACK
    return notes


def _extract_bar_count(footer):
    """Read bar count from the 16-byte footer."""
    if len(footer) >= 10:
        return footer[9]
    return 2


def read_binary(path):
    """Read a .PTN file and return decoded notes + bar count.

    Returns ``(notes, bar_count)`` where each note is a dict with keys
    ``bank``, ``pad``, ``tick``, ``velocity``, ``length``.
    """
    with open(path, 'rb') as f:
        data = f.read()

    if len(data) < FOOTER_SIZE:
        return [], 2

    footer = data[-FOOTER_SIZE:]
    body = data[:-FOOTER_SIZE]
    bar_count = _extract_bar_count(footer)

    # Try 9-byte records first (the canonical spEdit404 format)
    if len(body) % NOTE_SIZE_PRIMARY == 0 and len(body) > 0:
        notes = _parse_notes_9byte(body)
        if notes:
            return notes, bar_count

    # Fallback: try 8-byte records (hardware-written or alternate format)
    if len(body) % NOTE_SIZE_FALLBACK == 0 and len(body) > 0:
        notes = _parse_notes_8byte(body)
        if notes:
            return notes, bar_count

    # Last resort: try 9-byte on non-aligned data (truncated footer?)
    notes = _parse_notes_9byte(body)
    if notes:
        return notes, bar_count

    return [], bar_count


def ptn_filename_to_bank_pad(filename):
    """Decode a PTN filename to ``(bank_letter, pad_number)``.

    ``PTN00{hex_code}.BIN`` where code = bank_index * 12 + pad_number.
    """
    import os, re
    base = os.path.basename(filename).upper()
    m = re.match(r'PTN0*([0-9A-Fa-f]+)\.BIN$', base)
    if not m:
        return None, None
    code = int(m.group(1), 16)
    if code < 1:
        return None, None
    bank_idx = (code - 1) // constants.pads_per_bank
    pad_num = ((code - 1) % constants.pads_per_bank) + 1
    if 0 <= bank_idx < constants.number_of_banks:
        return BANKS_LOWER[bank_idx], pad_num
    return None, None
