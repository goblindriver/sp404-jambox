# Vendored from spEdit404
from . import constants
from .track import Track

NUMBER_OF_TRACKS = 12


class Pattern:
    def __init__(self, length):
        self.length = int(length)
        self.tracks = [Track(length) for _ in range(NUMBER_OF_TRACKS)]

    def __len__(self):
        return self.length

    def add_note(self, new_note):
        if new_note.start_tick < self.length * constants.TICKS_PER_BAR:
            for track in self.tracks:
                try:
                    track.add_note(new_note)
                    return
                except ValueError:
                    pass
            raise ValueError('note cannot be added: overlaps on all tracks')
        else:
            raise ValueError('note must start before the pattern ends')
