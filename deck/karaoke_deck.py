#!/usr/bin/env python3
"""Karaoke deck ("the stage"): mpv + SP-404A over USB MIDI, on GOBLINDRIVER.

Plays a prepped song (``scripts/karaoke_prep.py`` output, mirrored to
``D:\\Karaoke\\Songs``) in mpv with lyrics on screen, and keeps the SP-404A locked to
it: MIDI clock at the song's BPM (Start lands on the first downbeat), the
song's drop sheet fired on time, and manual pad drops from the keyboard.

    py deck\\karaoke_deck.py                       # pick songs from D:\\Karaoke\\Songs\\_index.json
    py deck\\karaoke_deck.py --root D:\\Karaoke\\Songs --midi "USB Midi" --base-ch 1
    py deck\\karaoke_deck.py --list-ports           # MIDI + audio device names
    py deck\\karaoke_deck.py --dry-run              # no MIDI; prints what it would send
    py deck\\karaoke_deck.py --screen 1 --video-screen 2   # lyrics on display 1, video on display 2

Two screens: ``--video-screen`` opens a second, muted window for the room (the
CRT via Moonlight, or the computer screen). It plays the song's music video
(``song.json`` ``video``: kept on the song in ``sync`` mode, looping in
``loose`` mode) or, without one, a visual of the backing track, with a "now
singing / up next" card. The lyrics window stays the audio and MIDI clock.
``--video-lead`` runs the video that much ahead to cover a stream's lag.

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
# Songs live in their own folder: D:\Karaoke also holds the GPU karaoke lane (venv, models,
# work), which a /MIR mirror straight into D:\Karaoke would delete.
DEFAULT_ROOT = r"D:\Karaoke\Songs" if os.name == "nt" else os.path.expanduser("~/Music/Karaoke")
MIRROR_HINT = r'robocopy "\\<citadel>\jasongronvold\Music\Karaoke" D:\Karaoke\Songs /MIR /COPY:DT /R:1 /W:1'
PIPE_NAME = r"\\.\pipe\jambox-karaoke" if os.name == "nt" else "/tmp/jambox-karaoke.sock"
VIDEO_PIPE = PIPE_NAME + "-video"
GUIDE_LEVELS_DB = (None, -18, -9)           # None = off
VIDEO_TOLERANCE_S = 0.3                      # re-seek the video window when it drifts further
VIDEO_FOLLOW_EVERY_S = 0.25
VIDEO_SEEK_SETTLE_S = 1.0                    # after a seek, before checking drift again
CARD_FIRST_S = 15.0                          # "now singing" for a song's first seconds
CARD_NEXT_S = 30.0                           # "up next" for its last
# The second screen without a music video: a spectrum of the backing track (audio output off).
VISUAL_GRAPH = "[aid1]asplit[ao][a];[a]showcqt=s=1280x720:fps=30:count=4:bar_g=2:sono_g=4:axis=0[vo]"
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


def preferred_backing(song_dir, song=None):
    """Same rule as ``karaoke_prep.preferred_backing``.

    Inlined so the deck does not import the kitchen (that loads jambox config).
    ``backing_bv.flac`` when it exists and ``mix`` is not ``"dry"``; otherwise
    the dry instrumental.
    """
    dry = os.path.join(song_dir, "backing.flac")
    bv = os.path.join(song_dir, "backing_bv.flac")
    if (song or {}).get("mix") == "dry" or not os.path.isfile(bv):
        return dry
    return bv


def build_mpv_args(song_dir, song, *, ipc=PIPE_NAME, audio_device=None, fullscreen=True,
                   screen=None, sub_delay=0.0, mpv="mpv"):
    args = [mpv, preferred_backing(song_dir, song),
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
        args += [f"--screen={screen}", f"--fs-screen={screen}"]
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


def song_video(song_dir, song):
    """``(path, mode, offset_s)`` of the song's music video, or ``(None, None, None)``.

    ``song.json`` ``video``: ``{"file", "mode": "sync"|"loose", "offset_s"}`` where
    video_pos = song_pos + offset_s. A sync entry without an offset plays loose.
    """
    video = song.get("video") or {}
    path = os.path.join(song_dir, video["file"]) if video.get("file") else None
    if not path or not os.path.isfile(path):
        return None, None, None
    offset = video.get("offset_s")
    if video.get("mode") == "sync" and isinstance(offset, (int, float)):
        return path, "sync", float(offset)
    return path, "loose", None


def build_video_args(song_dir, song, *, ipc=VIDEO_PIPE, fullscreen=True, screen=None, mpv="mpv"):
    """The second screen's mpv: the music video muted, or a visual of the backing track.

    It starts paused unless the video loops on its own; ``VideoScreen`` keeps it
    on the song.
    """
    path, mode, _offset = song_video(song_dir, song)
    # No default key bindings: a stray q or space in the room window would quit or pause it alone.
    args = [mpv, f"--input-ipc-server={ipc}", "--force-window=yes", "--keep-open=yes", "--idle=no",
            "--osc=no", "--sid=no", "--input-default-bindings=no", "--cursor-autohide=always",
            f"--title=Jambox: {song.get('artist') or ''} - {song.get('title') or ''}"]
    if path:
        args += [path, "--aid=no"]
        args.append("--loop-file=inf" if mode == "loose" else "--pause")
    else:
        args += [os.path.join(song_dir, "backing.flac"), "--ao=null", "--pause",
                 f"--lavfi-complex={VISUAL_GRAPH}"]
    if fullscreen:
        args.append("--fullscreen")
    if screen is not None:
        args += [f"--screen={screen}", f"--fs-screen={screen}"]
    return args


def video_seek_target(song_pos, offset_s, lead_s, video_pos, *, tolerance=VIDEO_TOLERANCE_S):
    """Where the video window should seek to stay on the song, or None while it's close enough.

    It belongs at song_pos + offset_s + lead_s (the lead covers a streamed
    screen's lag); before the video starts it waits at 0.
    """
    target = max(0.0, song_pos + offset_s + lead_s)
    if video_pos is None or abs(video_pos - target) > tolerance:
        return round(target, 3)
    return None


def _ass_text(text):
    return str(text or "").replace("\\", "/").replace("{", "(").replace("}", ")")


def card_text(song, next_song, song_pos):
    """The second screen's overlay at ``song_pos``: "now singing", then "up next" near the end, or ''."""
    def name(s):
        return " - ".join(_ass_text(v) for v in (s.get("artist"), s.get("title")) if v)

    if song_pos < CARD_FIRST_S and name(song):
        return "{\\an1\\fs34\\bord3}Now singing\\N{\\b1\\fs52}" + name(song)
    duration = song.get("duration_s")
    if next_song and duration and song_pos > duration - CARD_NEXT_S and name(next_song):
        return "{\\an3\\fs34\\bord3}Up next\\N{\\b1\\fs44}" + name(next_song)
    return ""


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
        self._send({"command": list(cmd)})

    def command_named(self, **cmd):
        """mpv's named-argument form, e.g. ``osd-overlay``."""
        self._send({"command": cmd})

    def _send(self, payload):
        msg = json.dumps(payload).encode() + b"\n"
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
    """mpv on PATH, else winget's install folder (shinchiro.mpv doesn't add itself to PATH).

    None when it isn't there. ``main`` exits before opening a window; the web
    UI already plays these songs.
    """
    found = shutil.which(name)
    if found:
        return found
    # An explicit --mpv path is used as given when that file exists. It is not
    # swapped for the winget install.
    if name != "mpv":
        return name if os.path.isfile(name) else None
    if os.name != "nt":
        return None
    for base in (os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        for sub in (("MPV Player", "mpv.exe"), ("Programs", "mpv", "mpv.exe"), ("mpv", "mpv.exe")):
            path = os.path.join(base or "", *sub)
            if base and os.path.isfile(path):
                return path
    return None


class MidiOut:
    def __init__(self, port_hint=None, dry_run=False):
        self.dry = dry_run
        self.port = None
        self.mido = None
        if dry_run:
            return
        try:
            mido = load_mido()
        except ImportError:
            self._unavailable("mido is not installed")
            return
        self.mido = mido
        try:
            names = mido.get_output_names()
        except Exception as exc:
            self._unavailable(str(exc))
            return
        if port_hint:
            match = [n for n in names if port_hint.lower() in n.lower()]
        else:
            match = list(names)
        if not match:
            self._unavailable(f"port {port_hint!r} not found" if port_hint else "no MIDI ports")
            return
        try:
            self.port = mido.open_output(match[0])
        except Exception as exc:
            self._unavailable(f"{match[0]} could not be opened ({exc})")
            return
        print(f"MIDI → {match[0]}")

    def _unavailable(self, why):
        """One warning. Later notes are dropped so the song still plays."""
        self.port = None
        print(f"  MIDI unavailable ({why}); the song will play with no clock and no pad notes.")

    def _send(self, kind, **kw):
        if self.dry:
            if kind not in ("clock",):
                print(f"  [midi] {kind} {kw}")
            return
        if self.port is None:
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
        if not self.dry and self.port is None:
            return
        ch, note = karaoke_drops.pad_to_midi(bank, pad, base_ch)
        self._send("note_on", channel=ch - 1, note=note, velocity=vel)
        threading.Timer(0.08, lambda: self._send("note_off", channel=ch - 1, note=note, velocity=0)).start()

    def ext_source(self, base_ch):
        if not self.dry and self.port is None:
            return
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

class VideoScreen:
    """The second screen: follows the lyrics window's position, pause and song; shows the card."""

    def __init__(self, song_dir, song, next_song, args):
        path, mode, offset = song_video(song_dir, song)
        # The visual plays the backing track itself, so it follows the song like a synced video.
        self.mode, self.offset = (mode, offset) if path else ("visual", 0.0)
        self.end = (song.get("video") or {}).get("duration_s") if path else None
        self.song, self.next_song, self.lead = song, next_song, args.video_lead
        self.proc = subprocess.Popen(build_video_args(
            song_dir, song, fullscreen=not args.windowed, screen=args.video_screen, mpv=args.mpv))
        try:
            self.mpv = Mpv(VIDEO_PIPE)
        except RuntimeError:
            self.proc.kill()
            raise
        self._due, self._card = 0.0, None
        print(f"  video screen: {'music video, ' + mode if path else 'visual (no music video)'}")

    def update(self, song_pos, paused, speed=1.0):
        now = time.monotonic()
        if now < self._due or self.mpv.closed.is_set():
            return
        self._due = now + VIDEO_FOLLOW_EVERY_S
        if self.mode == "loose":
            hold = paused
        else:
            hold = paused or song_pos + self.offset + self.lead < 0
            if self.mpv.state["speed"] != speed:
                self.mpv.command("set_property", "speed", speed)
            target = video_seek_target(song_pos, self.offset, self.lead, self.mpv.position())
            if target is not None and not (self.end and target >= self.end - 0.5):
                self.mpv.command("seek", target, "absolute+exact")
                self._due = now + VIDEO_SEEK_SETTLE_S   # time-pos lags a seek; don't chase it
        if bool(self.mpv.state["pause"]) != hold:
            self.mpv.command("set_property", "pause", hold)
        text = card_text(self.song, self.next_song, song_pos)
        if text != self._card:
            self._card = text
            self.mpv.command_named(name="osd-overlay", id=1, format="ass-events" if text else "none",
                                   data=text, res_x=1280, res_y=720)

    def close(self):
        if self.proc.poll() is None:
            self.mpv.command("quit")
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class Deck:
    def __init__(self, args):
        self.args = args
        self.midi = MidiOut(args.midi, dry_run=args.dry_run)
        self.keys = queue.Queue()
        self.bank = "A"
        print(f"Keys: {start_key_listener(self.keys)}")

    def play(self, song_dir, next_song=None):
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

        # The room screen opens first so the lyrics window, opened last, keeps the focus.
        video = None
        if self.args.video_screen is not None:
            try:
                video = VideoScreen(song_dir, song, next_song, self.args)
            except (OSError, RuntimeError) as exc:  # the song still plays on the lyrics screen
                print(f"  video screen unavailable: {exc}")
        proc = subprocess.Popen(build_mpv_args(
            song_dir, song, audio_device=self.args.audio_device, fullscreen=not self.args.windowed,
            screen=self.args.screen, sub_delay=self.args.sub_delay, mpv=self.args.mpv))
        try:
            mpv = Mpv(PIPE_NAME)
        except RuntimeError as exc:
            print(exc)
            if video is not None:
                video.close()
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

                if video is not None and pos is not None:
                    video.update(pos, bool(mpv.state["pause"]), float(mpv.state["speed"] or 1.0))
                result = self._handle_keys(mpv, has_cover, has_guide) or result
                if result in ("quit", "skip"):
                    break
                time.sleep(0.002)
        finally:
            if started:
                self.midi.stop()
            if video is not None:
                video.close()
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
        raise SystemExit(f"No {path}. Prep songs on citadel (scripts/karaoke_prep.py or the web UI's "
                         f"Karaoke tab), then mirror them here: {MIRROR_HINT}")
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
    ap.add_argument("--screen", "--lyrics-screen", type=int, default=None,
                    help="lyrics window: fullscreen on this display index")
    ap.add_argument("--sub-delay", type=float, default=0.0, help="lyrics offset, e.g. 0.1 for Moonlight lag")
    ap.add_argument("--video-screen", type=int, default=None,
                    help="also open the room screen (music video or visual + now-singing card) on this display")
    ap.add_argument("--video-lead", type=float, default=0.0,
                    help="run the video this many seconds ahead, e.g. 0.1 when it goes out over Moonlight")
    ap.add_argument("--windowed", action="store_true")
    ap.add_argument("--hot", action="store_true", help="manual drops at velocity 127")
    ap.add_argument("--mpv", default="mpv")
    ap.add_argument("--dry-run", action="store_true", help="no MIDI port; print messages")
    ap.add_argument("--list-ports", action="store_true")
    ap.add_argument("songs", nargs="*", help="song folder names (skip the picker)")
    args = ap.parse_args(argv)
    requested = args.mpv
    args.mpv = find_mpv(requested)

    if args.list_ports:
        list_ports(args.mpv or requested)
        return 0
    if not args.mpv:
        print("mpv was not found, so the deck can't open a window.\n"
              "The songs are already playable in the jambox web UI: "
              "scripts/karaoke_prep output is already what the browser plays.\n"
              "Install mpv, or pass --mpv with its path.")
        return 2
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
        for i, s in enumerate(q):
            next_song = q[i + 1] if i + 1 < len(q) else None
            if deck.play(os.path.join(args.root, s["dir"]), next_song) == "quit":
                break
    except KeyboardInterrupt:
        pass
    finally:
        deck.midi.close()
    print("Goodnight.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
