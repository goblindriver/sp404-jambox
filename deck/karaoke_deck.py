#!/usr/bin/env python3
"""Karaoke deck ("the stage"): mpv + SP-404A over USB MIDI, on GOBLINDRIVER.

Plays a prepped song (``scripts/karaoke_prep.py`` output, mirrored to
``D:\\Karaoke``) in mpv with lyrics on screen, and keeps the SP-404A locked to
it: MIDI clock at the song's BPM (Start lands on the first downbeat), the
song's drop sheet fired on time, and manual pad drops from the keyboard.

    py deck\\karaoke_deck.py                       # pick songs from D:\\Karaoke\\_index.json
    py deck\\karaoke_deck.py --root D:\\Karaoke --midi "USB Midi" --base-ch 1
    py deck\\karaoke_deck.py --list-ports           # MIDI + audio device names
    py deck\\karaoke_deck.py --dry-run              # no MIDI; prints what it would send

Set the SP-404A to MIDI SYNC ``tnP`` ([10] + CTRL 3) so tempo follows the song
but patterns never auto-start.

Keys (global via pynput when installed; otherwise type in this console + Enter):
  numpad 1-9, 0      pads 1-10 of the selected bank      (/ = pad 11, * = pad 12)
  numpad + / -       next / previous bank
  ]  [               key shift up / down a semitone (clock unaffected)
  g                  guide vocal: off → -18 dB → -9 dB
  d                  drop sheet on/off for this song
  m                  mute mic 2 (toggle SP-404A EXT SOURCE, note 46)
  n                  next song      q  quit
Space / arrows / seeking work in the mpv window as usual; clock + drops follow.

Needs: mpv (winget shinchiro.mpv; found in its install folder if not on PATH);
pip install -r deck/requirements.txt (mido + pygame for MIDI; pynput optional).
"""
import argparse
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import karaoke_drops  # noqa: E402  (pure python, no jambox config needed)

PPQN = 24
DEFAULT_ROOT = r"D:\Karaoke" if os.name == "nt" else os.path.expanduser("~/Music/Karaoke")
PIPE_NAME = r"\\.\pipe\jambox-karaoke" if os.name == "nt" else "/tmp/jambox-karaoke.sock"
GUIDE_LEVELS_DB = (None, -18, -9)           # None = off
SEEK_JUMP_S = 0.75                           # a time-pos jump bigger than this = seek
MAX_SEMITONES = 6

NUMPAD_PADS = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
               "0": 10, "/": 11, "*": 12}


# ── Pure timing logic (unit tested) ──────────────────────────────────

def ticks_due(song_pos, bpm, beat_offset_s=0.0):
    """How many 24-PPQN clock ticks should have been sent by ``song_pos``.

    Tick 0 (with MIDI Start) is the first downbeat; nothing before it.
    """
    if not bpm or song_pos is None:
        return 0
    elapsed = song_pos - (beat_offset_s or 0.0)
    if elapsed < 0:
        return 0
    return int(elapsed * bpm / 60.0 * PPQN) + 1


def song_position_pointer(song_pos, bpm, beat_offset_s=0.0):
    """MIDI Song Position (16th notes since the first downbeat) for resync after a seek."""
    if not bpm or song_pos is None:
        return 0
    return max(0, int((song_pos - (beat_offset_s or 0.0)) * bpm / 60.0 * 4))


def drops_between(drops, prev_pos, pos):
    """Drops whose time falls in (prev_pos, pos]. Assumes drops sorted by t."""
    if prev_pos is None or pos is None or pos <= prev_pos:
        return []
    return [d for d in drops if prev_pos < d["t"] <= pos]


def pitch_scale(semitones):
    return round(2 ** (semitones / 12.0), 6)


def build_mpv_args(song_dir, song, *, ipc=PIPE_NAME, audio_device=None, fullscreen=True,
                   screen=None, sub_delay=0.0, mpv="mpv"):
    args = [mpv, os.path.join(song_dir, "backing.flac"),
            f"--input-ipc-server={ipc}",
            "--force-window=yes", "--keep-open=no", "--idle=no",
            "--af=@rb:rubberband=pitch-scale=1.0",
            "--sub-font-provider=auto", "--sub-ass-override=no",
            f"--title={song.get('artist') or ''} - {song.get('title') or ''}"]
    for name, flag in (("lyrics.ass", "--sub-files"), ("cover.jpg", "--cover-art-files"),
                       ("guide.flac", "--audio-files")):
        path = os.path.join(song_dir, name)
        if os.path.isfile(path):
            args.append(f"{flag}={path}")
    if os.path.isfile(os.path.join(song_dir, "guide.flac")):
        args.append("--aid=1")          # backing; guide is aid 2 until mixed in
    if audio_device:
        args.append(f"--audio-device={audio_device}")
    if fullscreen:
        args.append("--fullscreen")
    if screen is not None:
        args.append(f"--fs-screen={screen}")
    if sub_delay:
        args.append(f"--sub-delay={sub_delay}")
    return args


def guide_graph(level_db, has_cover):
    """lavfi-complex for backing + guide vocal at ``level_db``; '' restores plain playback."""
    if level_db is None:
        return ""
    graph = (f"[aid2]volume={level_db}dB[g];"
             f"[aid1][g]amix=inputs=2:duration=first:normalize=0[ao]")
    if has_cover:
        graph += ";[vid1]null[vo]"
    return graph


# ── mpv IPC ──────────────────────────────────────────────────────────

class Mpv:
    """Minimal JSON-IPC client. Observes time-pos/pause/speed in a reader thread."""

    def __init__(self, path, timeout=10.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                if os.name == "nt":
                    self._fh = open(path, "r+b", buffering=0)
                    self._send_raw = self._fh.write
                    self._recv_raw = self._pipe_read
                else:
                    sock = socket.socket(socket.AF_UNIX)
                    sock.connect(path)
                    self._fh = sock.makefile("rwb", buffering=0)
                    self._send_raw = self._fh.write
                    self._recv_raw = self._fh.readline
                break
            except OSError as exc:
                last = exc
                time.sleep(0.1)
        else:
            raise RuntimeError(f"mpv IPC not reachable at {path}: {last}")
        self.lock = threading.Lock()
        self.state = {"time-pos": None, "pause": False, "speed": 1.0}
        self.state_at = time.monotonic()
        self.closed = threading.Event()
        threading.Thread(target=self._reader, daemon=True).start()
        for i, prop in enumerate(("time-pos", "pause", "speed"), start=1):
            self.command("observe_property", i, prop)

    def command(self, *cmd):
        msg = json.dumps({"command": list(cmd)}).encode() + b"\n"
        try:
            with self.lock:
                self._send_raw(msg)
        except OSError:
            self.closed.set()

    def _pipe_read(self):
        """Whatever bytes mpv has sent, without blocking in ReadFile.

        The pipe handle is synchronous, and Windows runs I/O on such a handle one
        request at a time: a pending read holds up every write until mpv next
        sends something, which while paused is never (resume, key shift and quit
        all hung). So wait for data with PeekNamedPipe and read only what's there.
        """
        import _winapi
        import msvcrt
        handle = msvcrt.get_osfhandle(self._fh.fileno())
        while not self.closed.is_set():
            available = _winapi.PeekNamedPipe(handle, 0)[0]   # OSError once mpv exits
            if available:
                return self._fh.read(available)
            time.sleep(0.005)
        return b""

    def _reader(self):
        buf = b""
        while not self.closed.is_set():
            try:
                chunk = self._recv_raw()
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            *lines, buf = buf.split(b"\n")
            if any(self._handle_event(line) for line in lines):
                break
        self.closed.set()

    def _handle_event(self, line):
        """Apply one IPC line; True once mpv says the file ended."""
        try:
            ev = json.loads(line)
        except ValueError:
            return False
        if ev.get("event") == "property-change" and ev.get("name") in self.state:
            self.state[ev["name"]] = ev.get("data")
            if ev["name"] == "time-pos":
                self.state_at = time.monotonic()
        return ev.get("event") in ("end-file", "shutdown")

    def position(self):
        """time-pos extrapolated between IPC updates (smooth enough for 24 PPQN)."""
        pos = self.state["time-pos"]
        if pos is None:
            return None
        if self.state["pause"]:
            return pos
        return pos + (time.monotonic() - self.state_at) * float(self.state["speed"] or 1.0)


# ── MIDI ─────────────────────────────────────────────────────────────

def load_mido():
    """mido on a backend that installs everywhere.

    mido defaults to python-rtmidi, which has no Windows wheel for Python 3.13
    (it needs the MSVC build tools), so without it use pygame's PortMidi.
    MIDO_BACKEND, if set, wins.
    """
    import mido
    if not os.environ.get("MIDO_BACKEND"):
        try:
            import rtmidi  # noqa: F401
        except ImportError:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            mido.set_backend("mido.backends.pygame")
    return mido


def find_mpv(name="mpv"):
    """mpv on PATH, else winget's install folder (shinchiro.mpv doesn't add itself to PATH)."""
    found = shutil.which(name)
    if found or os.name != "nt" or name != "mpv":
        return found or name
    for base in (os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        for sub in (r"MPV Player\mpv.exe", r"Programs\mpv\mpv.exe", r"mpv\mpv.exe"):
            path = os.path.join(base or "", sub)
            if base and os.path.isfile(path):
                return path
    return name


class MidiOut:
    def __init__(self, port_hint=None, dry_run=False):
        self.dry = dry_run
        self.port = None
        if dry_run:
            return
        mido = load_mido()
        self.mido = mido
        names = mido.get_output_names()
        match = [n for n in names if port_hint and port_hint.lower() in n.lower()] or names
        if not match:
            raise RuntimeError("No MIDI outputs. Is the USB MIDI cable plugged in?")
        self.port = mido.open_output(match[0])
        print(f"MIDI → {match[0]}")

    def _send(self, kind, **kw):
        if self.dry:
            if kind not in ("clock",):
                print(f"  [midi] {kind} {kw}")
            return
        self.port.send(self.mido.Message(kind, **kw))

    def clock(self):
        self._send("clock")

    def start(self):
        self._send("start")

    def stop(self):
        self._send("stop")

    def cont(self):
        self._send("continue")

    def spp(self, pos16):
        self._send("songpos", pos=min(pos16, 16383))

    def pad(self, bank, pad, vel, base_ch):
        ch, note = karaoke_drops.pad_to_midi(bank, pad, base_ch)
        self._send("note_on", channel=ch - 1, note=note, velocity=vel)
        threading.Timer(0.08, lambda: self._send("note_off", channel=ch - 1, note=note, velocity=0)).start()

    def ext_source(self, base_ch):
        self._send("note_on", channel=base_ch - 1, note=karaoke_drops.EXT_SOURCE_NOTE, velocity=100)
        threading.Timer(0.08, lambda: self._send(
            "note_off", channel=base_ch - 1, note=karaoke_drops.EXT_SOURCE_NOTE, velocity=0)).start()

    def close(self):
        if self.port:
            self.port.close()


# ── Keys ─────────────────────────────────────────────────────────────

def start_key_listener(keyq):
    """pynput global hotkeys if available, else console line input."""
    try:
        from pynput import keyboard

        def on_press(key):
            ch = getattr(key, "char", None)
            vk = getattr(key, "vk", None)
            if vk is not None and 96 <= vk <= 105:       # Windows numpad 0-9
                ch = str(vk - 96)
            elif vk == 111:
                ch = "/"
            elif vk == 106:
                ch = "*"
            elif vk == 107:
                ch = "+"
            elif vk == 109:
                ch = "-"
            if ch:
                keyq.put(ch)
        keyboard.Listener(on_press=on_press, daemon=True).start()
        return "global hotkeys (pynput)"
    except Exception:
        def reader():
            for line in sys.stdin:
                for ch in line.strip() or " ":
                    keyq.put(ch)
        threading.Thread(target=reader, daemon=True).start()
        return "console keys (type + Enter)"


# ── Song runner ──────────────────────────────────────────────────────

class Deck:
    def __init__(self, args):
        self.args = args
        self.midi = MidiOut(args.midi, dry_run=args.dry_run)
        self.keys = queue.Queue()
        self.bank = "A"
        print(f"Keys: {start_key_listener(self.keys)}")

    def play(self, song_dir):
        with open(os.path.join(song_dir, "song.json"), encoding="utf-8") as fh:
            song = json.load(fh)
        drops = karaoke_drops.validate_drops(song.get("drops"))
        bpm, offset = song.get("bpm"), song.get("beat_offset_s") or 0.0
        if bpm and not 40 <= bpm <= 200:   # SP-404A sync range
            bpm = bpm / 2 if bpm > 200 else bpm * 2
        has_cover = os.path.isfile(os.path.join(song_dir, "cover.jpg"))
        has_guide = os.path.isfile(os.path.join(song_dir, "guide.flac"))
        print(f"\n▶ {song.get('artist')} - {song.get('title')}  "
              f"[{bpm} bpm, key {song.get('key')}, {len(drops)} drops, bank {self.bank}]")

        proc = subprocess.Popen(build_mpv_args(
            song_dir, song, audio_device=self.args.audio_device, fullscreen=not self.args.windowed,
            screen=self.args.screen, sub_delay=self.args.sub_delay, mpv=self.args.mpv))
        try:
            mpv = Mpv(PIPE_NAME)
        except RuntimeError as exc:
            print(exc)
            proc.wait()
            return "next"

        sent, started, prev_pos, result = 0, False, None, "next"
        self._semis, self._guide, self._drops_on = 0, 0, True   # mpv relaunches clean per song
        try:
            while not mpv.closed.is_set() and proc.poll() is None:
                pos = mpv.position()
                if pos is not None and prev_pos is not None and abs(pos - prev_pos) > SEEK_JUMP_S:
                    # Seek: re-point the sampler instead of bursting ticks.
                    self.midi.stop()
                    self.midi.spp(song_position_pointer(pos, bpm, offset))
                    # Speed changes need no special case: pos runs faster, ticks follow.
                    sent = ticks_due(pos, bpm, offset)
                    if sent:
                        self.midi.cont()
                    started = sent > 0
                    prev_pos = pos
                elif pos is not None and not mpv.state["pause"]:
                    due = ticks_due(pos, bpm, offset)
                    if due and not started:
                        self.midi.start()
                        started = True
                    for _ in range(min(due - sent, 4)):   # never burst more than 4
                        self.midi.clock()
                    sent = max(sent, due)
                    if self._drops_on:
                        for d in drops_between(drops, prev_pos, pos):
                            print(f"  ✦ {d['t']:6.1f}s  {d['bank']}{d['pad']:<2} {d['label']}")
                            self.midi.pad(d["bank"], d["pad"], d["vel"], self.args.base_ch)
                    prev_pos = pos

                result = self._handle_keys(mpv, has_cover, has_guide) or result
                if result in ("quit", "skip"):
                    break
                time.sleep(0.002)
        finally:
            if started:
                self.midi.stop()
            if proc.poll() is None:
                mpv.command("quit")
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        return "quit" if result == "quit" else "next"

    def _handle_keys(self, mpv, has_cover, has_guide):
        try:
            k = self.keys.get_nowait()
        except queue.Empty:
            return None
        a = self.args
        if k in NUMPAD_PADS:
            self.midi.pad(self.bank, NUMPAD_PADS[k], 127 if a.hot else 105, a.base_ch)
        elif k in "+-":
            i = karaoke_drops.BANKS.index(self.bank) + (1 if k == "+" else -1)
            self.bank = karaoke_drops.BANKS[i % 10]
            print(f"  bank → {self.bank}")
        elif k in "[]":
            step = 1 if k == "]" else -1
            self._semis = max(-MAX_SEMITONES, min(MAX_SEMITONES, self._semis + step))
            mpv.command("af-command", "rb", "set-pitch", str(pitch_scale(self._semis)))
            print(f"  key {self._semis:+d}")
        elif k == "g" and has_guide:
            self._guide = (self._guide + 1) % len(GUIDE_LEVELS_DB)
            level = GUIDE_LEVELS_DB[self._guide]
            mpv.command("set_property", "lavfi-complex", guide_graph(level, has_cover))
            print(f"  guide vocal {'off' if level is None else f'{level} dB'}")
        elif k == "d":
            self._drops_on = not self._drops_on
            print(f"  drop sheet {'on' if self._drops_on else 'off'}")
        elif k == "m":
            self.midi.ext_source(a.base_ch)
            print("  mic 2 (EXT SOURCE) toggled")
        elif k == "n":
            return "skip"
        elif k == "q":
            return "quit"
        return None


def load_index(root):
    path = os.path.join(root, "_index.json")
    if not os.path.isfile(path):
        raise SystemExit(f"No {path}. Run scripts/karaoke_prep.py on the iMac and mirror it here.")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("songs", [])


def pick_queue(songs):
    for i, s in enumerate(songs, 1):
        tag = "" if s.get("has_lyrics") else "  (no lyrics)"
        print(f"{i:3d}. {s['artist']} - {s['title']}  [{s.get('bpm')} bpm]{tag}")
    raw = input("\nQueue (e.g. 3 7 12, Enter = all, r = shuffle all): ").strip().lower()
    if not raw:
        return list(songs)
    if raw == "r":
        import random
        q = list(songs)
        random.shuffle(q)
        return q
    picks = []
    for tok in raw.replace(",", " ").split():
        if tok.isdigit() and 1 <= int(tok) <= len(songs):
            picks.append(songs[int(tok) - 1])
    return picks


def list_ports(mpv="mpv"):
    try:
        mido = load_mido()
        print("MIDI outputs (%s):" % mido.backend.name, *mido.get_output_names(), sep="\n  ")
    except ImportError:
        print("MIDI libraries missing: py -m pip install -r deck/requirements.txt")
    print("\nAudio devices (use the M6 'USB Audio CODEC' id with --audio-device):")
    # Captured and reprinted: the Windows mpv.exe prints nothing into an
    # inherited stdout, only into a pipe.
    try:
        found = subprocess.run([mpv, "--audio-device=help"], capture_output=True, text=True, timeout=30)
        print((found.stdout or found.stderr).rstrip())
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  mpv not runnable ({exc}); install it or pass --mpv")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--midi", default="USB Midi", help="substring of the MIDI output name")
    ap.add_argument("--base-ch", type=int, default=1, help="SP-404A Pad Base Ch (1-16)")
    ap.add_argument("--audio-device", default=None, help="mpv device id, e.g. wasapi/{...} (the M6)")
    ap.add_argument("--screen", type=int, default=None, help="fullscreen on this display index")
    ap.add_argument("--sub-delay", type=float, default=0.0, help="lyrics offset, e.g. 0.1 for Moonlight lag")
    ap.add_argument("--windowed", action="store_true")
    ap.add_argument("--hot", action="store_true", help="manual drops at velocity 127")
    ap.add_argument("--mpv", default="mpv")
    ap.add_argument("--dry-run", action="store_true", help="no MIDI port; print messages")
    ap.add_argument("--list-ports", action="store_true")
    ap.add_argument("songs", nargs="*", help="song folder names (skip the picker)")
    args = ap.parse_args(argv)
    args.mpv = find_mpv(args.mpv)

    if args.list_ports:
        list_ports(args.mpv)
        return 0
    songs = load_index(args.root)
    if args.songs:
        wanted = {s.lower() for s in args.songs}
        q = [s for s in songs if s["dir"].lower() in wanted]
    else:
        q = pick_queue(songs)
    if not q:
        print("Nothing queued.")
        return 0
    deck = Deck(args)
    try:
        for s in q:
            if deck.play(os.path.join(args.root, s["dir"])) == "quit":
                break
    except KeyboardInterrupt:
        pass
    finally:
        deck.midi.close()
    print("Goodnight.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
