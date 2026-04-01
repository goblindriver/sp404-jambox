# Vendored from spEdit404
from . import constants
import copy
import math

FRAMES_PER_BAR = 16
RESOLUTION = int(constants.TICKS_PER_BAR / FRAMES_PER_BAR)


class Track:
    def __init__(self, length):
        self.length = int(length)
        self.notes = []

    def __len__(self):
        return self.length

    def add_note(self, new_note):
        if new_note.start_tick < self.length * constants.TICKS_PER_BAR:
            for note in self.notes:
                if self.notes_collide(new_note, note):
                    raise ValueError('notes must not overlap with any notes on track')
            self.notes.append(new_note)
            self.notes = sorted(self.notes, key=lambda note: note.start_tick)
        else:
            raise ValueError('note must start before the pattern ends')

    def notes_collide(self, new_note, note):
        return ((note.start_tick <= new_note.start_tick <= note.end_tick)
                or (note.start_tick <= new_note.end_tick <= note.end_tick)
                or (new_note.start_tick <= note.end_tick <= new_note.end_tick)
                or (new_note.start_tick <= note.end_tick <= new_note.end_tick))
