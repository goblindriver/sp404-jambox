# Creative Karaoke Mode — Design (not built)

_Drafted 2026-10-30 for GOBLINDRIVER (the shed "toy" PC). Status: **design only** — nothing installed, no code written. Hardware facts come from COPS (`nodes/av-shed-rig`, `nodes/av-numark-m6`, `nodes/av-roland-sp404a`, `nodes/net-dev-crtchain`, `runbooks/shed-party-rig.md`) and the SP-404A Reference Manual p. 47–48 (`docs/hardware/`)._

## The idea

Regular karaoke is "play an instrumental, show lyrics". Creative karaoke adds the things only this rig can do:

- **Any song in the Plex library** becomes a karaoke track (Demucs pulls the vocal out), not just the songs a karaoke catalog happens to sell.
- **The SP-404A plays along**: MIDI clock locks its BPM-synced effects and loops to the song, and pad drops (air horns, choir stabs, crowd roars) land on cue, by hand or from a per-song "drop sheet".
- **Singer-friendly controls**: key shift (±semitones), an optional guide vocal at low level, and reverb on mic 2 through the sampler.
- **The party feeds the library** (later): recorded takes go back through jambox ingest as `personal` VOX samples.

## Who does what

| Concern | iMac (jambox server, Plex, Ollama, sample library) | GOBLINDRIVER (Windows toy PC) |
|---|---|---|
| Song selection | Plex playlist "Karaoke" (or the jambox My Music tab) | — |
| Stem separation | **Demucs** `--two-stems=vocals` (default; see Decision 1) | optional CUDA worker (RTX 4060 Ti) if Decision 1 goes that way |
| Analysis | `audio_analysis.py`: BPM, key, first-beat offset | — |
| Lyrics | `.lrc` beside the Plex file → LRCLIB lookup → none | displays them |
| Drop sheets | Ollama (Qwen3 8B) drafts them, the human edits them in the jambox UI | plays them |
| SD card | jambox builds the karaoke set (`fetch_samples` → `gen_padinfo` → `copy_to_sd`) | — |
| Playback | — | **deck**: mpv → M6 USB (CH3) |
| MIDI | — | deck → "USB Midi Cable" → SP-404A MIDI IN |
| Lyrics display | — | Moonlight→CRT today; projector/TV or direct HDMI later |
| Takes (later) | ingest into the library as `personal` VOX | records the M6 USB return |

At party time GOBLINDRIVER does **not** depend on the iMac or Wi-Fi: songs are mirrored locally ahead of time. The iMac is the kitchen, GOBLINDRIVER is the stage.

## 1. Backing tracks (iMac)

### What exists today and why it can't be reused as-is

jambox has three Demucs paths, all built to make **samples**:

- `scripts/stem_split.py:run_demucs()` makes 4 stems (`htdemucs`), pre-converted to stereo 44.1 kHz. It's used by the CLI and by `POST /api/music/split` (`web/api/music.py:_run_split`), which carries Plex metadata.
- `scripts/ingest/enrichment.py:_stem_split_task()` runs `--two-stems=drums` during ingest.
- All three write **into the sample library** and tag their output in `_tags.json`.

A 4-minute instrumental in `_tags.json` would pollute fetch scoring, so karaoke output lives **outside** `SP404-Sample-Library`.

### Proposed: `scripts/karaoke_prep.py`

```
python scripts/karaoke_prep.py --playlist Karaoke          # everything in the Plex playlist
python scripts/karaoke_prep.py --track 123456 [--model htdemucs_ft]
```

The steps, per track:

1. Resolve the file through `plex_client.py` (read-only, as today).
2. Run `run_demucs(path, tmp, model, two_stems="vocals")`, a new optional arg that adds `--two-stems=vocals` and returns `vocals` + `no_vocals`. `htdemucs` is the default; `htdemucs_ft` is cleaner but about 4× slower.
3. Write the backing as **stereo** FLAC. The SP-404 mono rule applies only to SD-card output.
4. Run `audio_analysis.py` for BPM, key, and the **first-beat offset** (librosa `beat_track`); the clock needs the offset to line up.
5. Find lyrics, in this order:
   - a `.lrc` sidecar next to the Plex file;
   - the LRCLIB API (`lrclib.net/api/get` by artist/title/album/duration; free, synced lyrics);
   - none: the song is marked `lyrics: none` and plays as instrumental, or with plain unsynced text if LRCLIB has it.
6. Convert the LRC to ASS, the display format, with the current line highlighted and the next line dimmed. Font height is at least 1/10 of the screen for 480i legibility on the CRT, and the layout is 4:3 safe.
7. Write `song.json`.

Output package (iMac `~/Music/Karaoke/`):

```
Karaoke/
  _index.json                      # all songs: artist, title, bpm, key, duration, has_lyrics
  Artist - Title/
    song.json                      # plex_id, bpm, key, beat_offset_s, demucs_model, lyrics_source, preset, drops[]
    backing.flac                   # no_vocals, stereo 44.1k
    guide.flac                     # vocals stem (guide-vocal mode)
    lyrics.lrc  lyrics.ass
    cover.jpg                      # Plex art, the background behind the lyrics
```

About 30–40 MB per song, so 500 songs come to roughly 20 GB.

Note: jambox defaults to `/opt/homebrew/bin/ffmpeg` and Mac paths. Anything that runs on Windows must take paths from `jambox_config.py` env overrides (`SP404_FFMPEG`, etc.).

### Sync to GOBLINDRIVER

The iMac shares `~/Music/Karaoke` over SMB. GOBLINDRIVER pulls it into **`D:\Karaoke`**: the Scratch SSD has 135 GB free, and `O:` is 88% full, so not there.

```
robocopy \\<imac>\Karaoke D:\Karaoke /MIR /COPY:DT /R:1 /W:1
```

That's the same `/COPY:DT` pattern COPS already uses for QNAP transfers. Run it before a party, or on a schedule.

### Later: jambox UI

A "Karaoke" tab next to My Music: pick tracks, queue prep jobs (same job/poll pattern as `/api/music/split`), preview, and edit drop sheets.

## 2. Lyrics display

The player is **mpv**, driven by the deck. It plays `backing.flac` with `cover.jpg` as the picture and `lyrics.ass` as subtitles. Lyrics are **not burned into video**, so `--sub-delay` can offset them for stream latency. (An MP4 export with burned-in lyrics can come later, for portable copies or a Plex "Karaoke" library.)

| Option | Path | Latency | Cost | Notes |
|---|---|---|---|---|
| **A. Moonlight → CRT (works today)** | Sunshine captures the host display (parked at 1440×1080) → Wi-Fi → Xbox Series S Moonlight → DAC → Extron P1 → Onkyo VIDEO 2 → CRT | ~60–120 ms (double Wi-Fi + encode); fixed with `--sub-delay` | $0 | mpv full-screen **on the display Sunshine captures**; the operator UI goes on another monitor. H.264-only invariant unchanged. |
| B. Direct HDMI → CRT | PC out 3 → 3-in HDMI switch (to buy) → DAC → Extron **P3** (1024×768 native 4:3) → CRT | ~1 frame | ~$30 | No Wi-Fi, no Sunshine. Already planned in the runbook. |
| C. Projector / big TV | PC out 2 → screen facing the room | ~1 frame | $150+ | The runbook's lyrics screen and "the single biggest karaoke upgrade". The CRT then shows VJ visuals or a "now singing" card. |

**Recommendation:** use A for the first nights. C is the long-term lyrics screen, with the CRT kept for retro visuals. B is the fallback if the projector slips.

### Audio gotchas with option A (important)

- In Moonlight on the Xbox, **"Play audio on host PC" must be ON.** Otherwise Sunshine silences the host and the M6 gets nothing.
- During a stream, Sunshine **switches the Windows default playback device** to its virtual sink. The deck therefore pins mpv to the M6 explicitly (`--audio-device=wasapi/<M6 "Speakers (USB Audio CODEC)" id>`) instead of trusting the default.
- Keep the Xbox's copy of the audio out of the PA. Today the Onkyo selects VIDEO 2 (Extron, no audio), so its TAPE OUT carries nothing. Once the HDMI audio extractor feeds VIDEO 3, **keep M6 CH1 down during karaoke**, or the track doubles ~100 ms late.

## 3. Mic path

This follows COPS `av-shed-rig` exactly; nothing new to wire.

- **Mic 1 → M6 MIC 1 (top XLR): dry.** Set DJ MIC ON and mic BASS ~-3. The M6 has no FX, sends or inserts, and its USB return is the *whole mix*, so the PC can't add reverb to mic 1 without feedback.
- **Mic 2 → SP-404A MIC IN → (REVERB/DELAY) → LINE OUT → M6 CH2: wet.** Set [MIC] lit, [EXT SOURCE] lit, and MIC LEVEL so PEAK flickers on a shout.
- **Lead singer on mic 2, duet/hype on mic 1** is the default. A singer who wants it dry swaps.

Consequences to design around:

1. **The SP-404A effect is global.** Drops fired while REVERB is on get reverb too. The SP-404A's MIDI implementation recognizes only notes, clock and start/stop (no CC or program change), so the deck **cannot automate FX on/off**. Accept it, or choose DELAY (it sits better on stabs).
2. **One fader for mic 2 and the drops.** M6 CH2 and the SP-404A VOLUME move both, so drop loudness has to be set **when the card is built**. The karaoke drop pads get normalized a few dB under the vocal (jambox already stores `loudness_db`).
3. **Mic 1 reverb later:** a TC Helicon Mic Mechanic 2 inline (already on the COPS to-buy list).
4. **The deck can toggle EXT SOURCE** (note 46, see below). That mutes mic 2 between songs so the sampler isn't a hot mic during the queue shuffle. Verify on the hardware.

## 4. Pad drops over USB MIDI

### What the SP-404A receives (Reference Manual p. 47–48)

- **Note On** 46–106, velocity recognized, on two channels: **Pad Base Ch** and **Pad Base Ch + 1**. Pad Base Ch is set on the hardware with [9] MIDI CH + CTRL 3; Jason should read the current value off the unit.
  - **Banks A–E** on Pad Base Ch: A = 47–58, B = 59–70, C = 71–82, D = 83–94, E = 95–106 (pads 1–12 in order).
  - **Banks F–J** on Pad Base Ch + 1, same note ranges: F = 47–58 … J = 95–106.
  - Note 46 = **EXT SOURCE**. The table lists it beside the channel column, so confirm which channel by test.
- **Clock + Start/Stop/Continue + Song Position.** Sync range is 40–200 BPM. MIDI SYNC mode is [10] + CTRL 3:
  - `AUt`: clock plus start/stop drives patterns.
  - `tnP`: tempo only.
  - `oFF`: no sync.
- **Nothing is transmitted** (the SP-404A has no MIDI OUT). One-way only.

**Recommendation: `tnP` (tempo sync) for karaoke.** BPM-synced effects (delay, DJFX looper, BPM-synced loops) follow the song, but deck Start/Stop never launches a pattern by surprise.

### The deck (`deck/karaoke_deck.py`, GOBLINDRIVER)

A small Python app in the jambox repo, run from a Windows venv (`mido` + `python-rtmidi`, `pynput` for hotkeys, `sounddevice` for takes).

1. Launches mpv with `--input-ipc-server=\\.\pipe\jambox-karaoke` and polls `time-pos` (about every 10 ms). Everything is slaved to the player.
2. **MIDI clock** at 24 PPQN from `song.json` bpm. Start is sent on the first beat (`beat_offset_s`). Seeks, pauses and tempo changes resync the clock.
3. **Drop sheet**: `drops: [{t: 61.2, bank: "J", pad: 1, vel: 110, label: "air horn into chorus"}]`, fired from `time-pos`. Bank/pad are mapped to channel and note with the table above.
4. **Manual drops**: numpad → pads 1–12 of the selected bank; PgUp/PgDn → bank. Velocity comes from a modifier, for example Shift = 127. The operator can be 25 ft from the sampler.
5. **Key shift / tempo**: mpv `af=rubberband` pitch-scale (±6 semitones) and speed with pitch preserved. The clock follows the speed change.
6. **Guide vocal**: `guide.flac` mixed in with mpv `--lavfi-complex` (amix). Hotkey cycles off → -18 dB → -9 dB.
7. **Queue**: a simple ordered list (CLI or a tiny local page) read from `D:\Karaoke\_index.json`.
8. Pins the **M6** as the audio device (see §2).

MIDI port note: classic WinMM MIDI ports are single-client. If REAPER (originals mode) and the deck both want "USB Midi Cable" at the same time, route both through **loopMIDI** plus a merger (or Windows MIDI Services if the OS build has it). Otherwise, close one before opening the other.

### The karaoke SD set (built on the iMac)

`karaoke-metal.yaml` is a **loop-heavy jam-along bank** (pads 5–12 are loops at 140 BPM in Em). It's great for originals or a metal night, but loops clash with an arbitrary song's key and tempo, and the SP-404A's BPM sync shifts their pitch. Drops over arbitrary songs want **one-shots** (tempo- and key-agnostic). Proposed set:

| Bank | Content | Why |
|---|---|---|
| A (internal) | `karaoke-drops`, **new preset**: crowd cheer, applause, air horn, choir stab, crash, rewind, riser, impact, "one more time" vocal, record scratch, laser, gong. All one-shots, all normalized | Survives card swaps; always available |
| B (internal) | Weapons Cache (`weapons-cache`) | Between-singer utility, already the runbook's plan |
| C | `karaoke-metal` | Metal nights and jam-alongs at 140 |
| D–J | Genre presets matched to the playlist (Ollama can suggest a mapping from Plex styles: disco → `disco-inferno`, punk → `riot-mode`…) | Loops only when the song's BPM is close |

## 5. Ollama's role (optional, iMac, prep time only)

- **Drop-sheet drafts.** Input: the LRC (choruses found as repeated line groups), BPM, Plex moods and styles, and the karaoke bank's pad descriptions. Output: `drops[]` JSON. The human reviews it in the UI, and it's never auto-applied blind.
- **Preset suggestion** per playlist through the existing vibe pipeline (`SP404_VIBE_PARSER_MODE=rag`).
- No LLM runs on GOBLINDRIVER or at party time.

## 6. Windows apps — proposed additions to COPS `deploy/host-windows.winget.json`

IDs verified with `winget search` on GOBLINDRIVER, 2026-10-29. **Not added yet**: per COPS decision E, a manifest change plus apply is Jason-confirmed actuation, with a `decisions/` entry.

| winget ID | Why | Need |
|---|---|---|
| `shinchiro.mpv` | The player: IPC control, ASS/LRC subtitles, rubberband key shift, WASAPI device pinning | **Required** |
| `Gyan.FFmpeg` | ffprobe/ffmpeg for the deck and any local renders | **Required** |
| `JamieOConnell.MIDI-OX` | First-light MIDI test: send note 47 on Pad Base Ch → pad A1 should fire; swap the 5-pin plugs if not | Recommended (diagnostic) |
| `TobiasErichsen.loopMIDI` | Virtual MIDI ports, only if two apps must share the cable | Optional |
| `Audacity.Audacity` | Trim and edit recorded takes | Optional (only with takes) |
| `Cockos.REAPER` | Originals mode (DAW + clock), not karaoke | Out of scope here |
| `UltraStarEspana.UltraStarWorldParty` | Pitch-scored "game mode" (UltraStar .txt) | Later, if wanted |

Not in winget:

- **Python** is already present via the Python Install Manager (MSIX, untracked by winget). The deck's venv uses `py`, and pip installs `mido`, `python-rtmidi`, `pynput` and `sounddevice`. The rebuild story for Python goes in the COPS deploy README rather than the manifest.
- **OpenKJ** (if Decision 4 picks it) is a manual install.
- **Demucs/torch** goes in the venv only if Decision 1 picks GPU splitting (~3 GB of CUDA wheels).

## 7. Phases

| Phase | What | Code? |
|---|---|---|
| 0 — first night | Split 5–10 songs on the iMac with the existing `stem_split.py` and sum drums+bass+other with ffmpeg (or `python -m demucs --two-stems=vocals` directly). Grab the LRCs from lrclib.net by hand. Copy them to `D:\Karaoke`. Play with `mpv backing.flac --sub-file=lyrics.lrc --force-window` (ffmpeg reads LRC; verify), pinned to the M6. Moonlight → CRT. Drops by hand on the pads. | none |
| 1 — the kitchen | `karaoke_prep.py`, the `two_stems` arg on `run_demucs`, LRC→ASS, `song.json`, SMB share + robocopy | jambox (iMac) |
| 2 — the deck | `deck/karaoke_deck.py`: MIDI clock, drop sheets, hotkeys, key shift, guide vocal, M6 pinning; the `karaoke-drops` preset and SD set | jambox (Windows) + card build |
| 3 — the toy box | Ollama drop sheets, a Karaoke tab in the web UI, takes → ingest as `personal` VOX, optional UltraStar export / game mode, projector as the lyrics screen | both |

## Decisions for Jason

1. **Where Demucs runs.** The iMac (M3, CPU, overnight batches, zero new installs; recommended) or GOBLINDRIVER's RTX 4060 Ti (seconds per song, enables mid-party requests; needs torch+CUDA and SMB access to the Plex music files). Also: `htdemucs` (fast) or `htdemucs_ft` (cleaner, ~4× slower).
2. **Song source.** A Plex playlist named "Karaoke" (recommended), picking in the jambox UI, or both.
3. **Lyrics screen.** Start on Moonlight → CRT? And which purchase comes first: the projector/TV (lyrics) or the HDMI switch (direct CRT)?
4. **Queue/player.** The jambox deck (mpv, MIDI-integrated; recommended) or OpenKJ for singer rotation (manual install, no MIDI/key-shift integration).
5. **SD card for karaoke night.** OK to build a new one-shot `karaoke-drops` preset for bank A, with Weapons Cache in B and `karaoke-metal` in C? Note that this displaces the Tiger Dust A–B internal banks for the night.
6. **Mic roles.** Lead on mic 2 (wet, through the sampler) and duet on mic 1 (dry)? Is the global-reverb-on-drops trade-off OK, or is the Mic Mechanic 2 moving up the list?
7. **Record takes?** Storage on `D:`, guest consent, and whether takes feed the sample library.
8. **Local mirror** on `D:\Karaoke` before parties (recommended) or play live over SMB from the iMac.
9. **Approve the winget additions** in §6 (mpv + FFmpeg required, MIDI-OX recommended).
10. **v1 scope.** Are key shift and guide vocal in phase 2, or later?

Also to read off the hardware: the SP-404A's current **Pad Base Ch** ([9] MIDI CH) and MIDI SYNC mode ([10]).
