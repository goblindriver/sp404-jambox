# Karaoke: the Jam Box first

_Plan, 2026-11-03. Branch `plan/karaoke-jambox-first`, off `main` at `1939437` (PR #25)._

_Status: phases 1–2 implemented on this branch. Phases 3–8 not started._

## The rule

Karaoke has to be singable on a machine that has this repo and nothing else from the shed. Plex, karaoke-gen, the remote GPU lane, yt-dlp, mpv, and the SP-404A over USB MIDI are upgrades. When a probe says one of them is there, use it. When it doesn't, don't offer a button that can only fail.

The browser is the stage. `deck/karaoke_deck.py` is the upgrade for a second screen and a MIDI clock. It is not the product.

This is the thing the Oct 30 design (`docs/KARAOKE_MODE_DESIGN.md`) and the Nov 1–2 implementation lost. That design is a two-computer party rig: the iMac as the kitchen, GOBLINDRIVER as the stage. The code followed it. The kitchen UI can already play a prepped song (backing, synced line, guide fader, fullscreen, drop sheet). It cannot *make* a song unless Plex answers, and it defaults the split to `karaoke-gen`, which is not a dependency of this repo.

## What already matches the rule

Leave these alone.

- Song packages live outside the sample library (`KARAOKE_DIR`). A four-minute instrumental never enters `_tags.json`.
- `prep_batch` isolates a bad file. A missing video does not fail the song (`scripts/karaoke_prep.py`).
- Lyrics already degrade: sidecar `.lrc` → LRCLIB → plain text → a title card (`scripts/karaoke_lyrics.py`).
- Analysis already degrades: librosa beat grid → ffprobe duration (`analyze()`).
- Drop sheets draft from the beat grid and choruses with no LLM (`scripts/karaoke_drops.py`). MIDI note math is pure.
- An empty `SP404_KARAOKE_REMOTE` means no ssh. The lane is opt-in.
- Refresh keeps going when the source drive is offline, as long as `backing.flac` exists.
- Song folder names are refused if they traverse (`web/api/karaoke.py` `_song_dir`).
- `tests/test_karaoke.py` covers the lane, the video ranker, and the lyric WER swap. Extend it. Don't replace it.

## What does not

| | Today | Target |
|---|---|---|
| Where a song comes from | Web prep accepts a Plex playlist, a Plex track id, or an already-prepped `dir`. A local file is CLI-only (`--file`). No Plex → the tab cannot make a song. | A file upload, or a path under a configured root, is always enough. Plex is a picker on top. |
| Which separator runs | `SP404_KARAOKE_BACKEND` defaults to `karaoke-gen`. The `<select id="karaoke-model">` defaults to the same option. Demucs is what `requirements.txt` actually installs. | The default is the best separator the probe can see. A missing tool is not a selectable default. |
| Status chips | `openKaraoke()` paints Plex / karaoke-gen / lane / yt-dlp / Demucs / librosa, then ignores them. | The chips decide which controls are enabled. |
| What you sing to | karaoke-gen writes `backing_bv.flac` (instrumental, backing vocals kept) and the index sets `has_backing_vocals`. `AUDIO_FILES` and `build_mpv_args` only play `backing.flac`. | Sing to `backing_bv` when the file is there. Dry instrumental is a toggle. |
| Hearing a drop | `karaFirePad` fetches `/api/audio/preview/{bank}/{pad}`, which is the card template or `_CARD_STAGING` only. `karaoke-drops.yaml` is twelve search strings, not samples. A 404 is cached as "never try again". | Card WAV if Fetch has placed one, otherwise the library's best match for that pad. Say so when there is no match. |
| A failed batch | Per-song exceptions are swallowed and the job still becomes `status: 'done'`. The toast says finished. | `done` / `partial` / `error`. |
| Replacing the banks | Load Karaoke Set overwrites `bank_config.yaml` after one confirm. Tiger Dust A–J is gone. | Write a timestamped copy first, and say the path in the toast. |
| The deck without the shed | Docstring says it needs mpv and a MIDI cable on GOBLINDRIVER. `find_mpv` can return `None` and `Deck.play` will `Popen` it anyway. | No mpv: exit and point at the web UI. No MIDI port: play the song anyway and skip the clock. |

## Capability ladder

One probe, used by the CLI default and by `GET /api/karaoke/status`. Put it in a new `scripts/karaoke_capabilities.py` so `karaoke_prep.py` (already ~1,070 lines) does not grow a second responsibility.

```
{
  "separate": {
    "demucs": true,             # importlib find_spec
    "karaoke_gen": false,       # shutil.which(KARAOKE_GEN)
    "remote_lane": null,        # SP404_KARAOKE_REMOTE or null. Do not ssh from a status poll.
    "default": "htdemucs"       # see the rule below
  },
  "sources": { "file": true, "plex": false },
  "lyrics":  { "sidecar": true, "lrclib": true },
  "extras":  { "ytdlp": false, "librosa": true, "ffmpeg": true },
  "stage":   { "browser": true }
}
```

`separate.default`, in order:

1. `karaoke-gen` if `karaoke_gen` is true **or** `remote_lane` is set. The lane is how this install reaches karaoke-gen. A configured lane with no local binary is still the better split, and `prep_batch` already falls back to local after `REMOTE_TRIES`.
2. Else `htdemucs` if `demucs` is true.
3. Else `null`. Prep is refused with a sentence that names the missing tool. Do not start a job that can only fail.

`htdemucs_ft` stays selectable whenever Demucs is installed. It is never the default (about 4× slower, same fallback lyrics).

Videos default off. The checkbox is disabled unless `extras.ytdlp`. Passing `videos: true` from the API when yt-dlp is missing is a 400, not a batch of soft failures.

Plex controls render only when `sources.plex`. The file control always renders.

Keep the existing `tools` object in the status payload so current tests and the chip markup keep working. `capabilities` is the new contract. The chips stay, and they start meaning something.

## Song package

No schema break. `SCHEMA_VERSION` stays `1`. New fields are optional. Old `song.json` files keep playing.

```
Karaoke/
  _index.json
  _sources/                        # uploads and pinned copies. Not a song.
    <sha16>.flac
  Artist - Title/
    song.json
    backing.flac                   # dry instrumental. Always, once prep succeeds.
    backing_bv.flac                # optional. karaoke-gen only, today.
    guide.flac                     # optional.
    lyrics.lrc / lyrics.txt / lyrics.ass
    cover.jpg
    video.mkv                      # optional. Unchanged.
```

`song.json` gains:

- `mix`: `"bv"` or `"dry"`. Missing means `"bv"` when `backing_bv.flac` exists, else `"dry"`.
- `source_kind`: `"file"`, `"upload"`, or `"plex"`. Missing means whatever `plex_id` implies (`"plex"` if set, else `"file"`).

`preferred_backing(song_dir, song) -> path` lives next to the probe (or as a function in `karaoke_prep.py` if the tests already import from there — prefer `karaoke_prep.py` only if moving it would churn imports; otherwise `karaoke_capabilities.py`). The web API and `build_mpv_args` both call it. One function, two callers.

## Phases

Each phase is a reviewable chunk. Don't land them as one commit the size of the review. Do land them on this branch.

### Phase 1 — Probe and honest defaults (implemented)

Files: `scripts/karaoke_capabilities.py` (new), `scripts/karaoke_prep.py` (`main()` default when `--backend` is omitted stays the config value, but the config default in `jambox_config.py` changes — see below), `web/api/karaoke.py` `status()` and `prep()`, `web/static/js/karaoke.js` `openKaraoke` / `startKaraokePrep`, `web/templates/index.html` model `<select>`.

- `jambox_config.KARAOKE_BACKEND` default becomes `demucs`. An install that has karaoke-gen opts in with `SP404_KARAOKE_BACKEND=karaoke-gen`, **and** the web UI still auto-selects karaoke-gen when the probe sees it or a lane. The config default is the floor for a headless CLI run with no env. The probe is the floor for the UI. Write this down in the module docstring so the next session doesn't "fix" it back.
- CLI: with no `--backend` and no env, use `demucs` (the new config default). With `--backend` unset and `SP404_KARAOKE_BACKEND` set, honor the env, same as today. Don't make the CLI secretly prefer the lane over an explicit `--backend demucs`.
- UI on open: set `#karaoke-model` to `capabilities.separate.default`. Disable options the probe can't run. If the default is `null`, disable Prep and show the one-line reason in `#karaoke-job`.
- Re-split confirm text names the model about to run, not "Demucs" unconditionally (`reprepKaraoke`).
- Videos checkbox: disabled and unchecked when `extras.ytdlp` is false.

Tests in `tests/test_karaoke.py`:

- Probe with neither binary → `default is None`.
- Probe with only Demucs → `htdemucs`.
- Probe with karaoke-gen on PATH, or with a fake remote host set → `karaoke-gen`.
- `POST /api/karaoke/prep` with `model=karaoke-gen` while the probe's default is `null` for that tool → 400.
- Same for `videos: true` without yt-dlp.

### Phase 2 — A song from a file (implemented)

Files: `web/api/karaoke.py` `prep()`, `web/templates/index.html`, `web/static/js/karaoke.js`. CLI `--file` already works. Don't reinvent it.

Two ways in, both ending at `prep_song`:

1. **Upload.** `POST /api/karaoke/upload` multipart: `file`, optional `artist`, `title`, `album`. Write to `KARAOKE_DIR/_sources/<sha256[:16]><ext>` (stream the hash, don't hold the whole file twice). Then start the same prep job as a one-track batch with `source_kind=upload`. Extension allow-list: `.flac .wav .aiff .aif .mp3 .m4a .ogg`. Reject the rest with 400. The existing 256 MB `MAX_CONTENT_LENGTH` is the size cap.
2. **Server path.** `POST /api/karaoke/prep` body `{ "file_path", "artist?", "title?", "album?" }`. `realpath` must sit under one of: `KARAOKE_DIR`, `SAMPLE_LIBRARY`, `DOWNLOADS_PATH`, or an entry in `SP404_KARAOKE_SOURCES` (os.pathsep-separated). Anywhere else is 403. This is the same rule as `preview_library`, applied to reads.

`_sources/` is not a song folder. `rebuild_index` already skips directories with no `song.json` and no `backing.flac`. Keep that. Don't special-case the name beyond a leading underscore if you want the belt: `_song_dir` already rejects names starting with `_`.

UI: a file input and an artist/title line under the Plex row. The Plex row hides when `sources.plex` is false. Empty copy in the detail pane stops saying "Prep a playlist".

Tests:

- Upload of a tiny valid file (a generated wav is enough) lands in `_sources/` and the prep job's track has that `file_path`. Mock the separator the way the existing tests do.
- `file_path` outside the roots → 403.
- `file_path` with `..` that realpaths back inside a root → allowed. Outside after realpath → 403.
- Index rebuild does not list `_sources`.

### Phase 3 — Job status

Files: `web/api/karaoke.py` `_run_prep`, `web/static/js/karaoke.js` `pollKaraokeJob`.

After `prep_batch` returns:

| done | failed | status |
|---|---|---|
| >0 | 0 | `done` |
| >0 | >0 | `partial` |
| 0 | >0 | `error` |
| 0 | 0 | `done` (empty input is already a 400 before the thread) |

The toast for `partial` names the failed count. `error` does not say finished. An exception that escapes `prep_batch` stays `error`, as today.

Test: a two-track batch whose separator raises on the second track finishes `partial` with `failed == 1`.

### Phase 4 — The mix you actually sing to

Files: `web/api/karaoke.py` `AUDIO_FILES` and a new route, `scripts/karaoke_prep.py` or `karaoke_capabilities.py` for `preferred_backing`, `deck/karaoke_deck.py` `build_mpv_args`, `web/static/js/karaoke.js` transport.

- `GET /api/karaoke/audio/<name>/backing_bv` serves the file. 404 when it was never made (Demucs). The dry `backing` route stays.
- Playback default is `preferred_backing`. The stage has a toggle, "backing vocals", shown only when the file exists. It writes `mix` through `PUT /api/karaoke/song/<name>/mix` with `{ "mix": "bv"|"dry" }`. Unknown value → 400. This does not touch the drop sheet or `drops_locked`.
- `build_mpv_args` plays that same path. Guide behavior is unchanged.
- The deck has no toggle in this phase. It follows `song.json`. The browser is where you pick.

Tests: preferred path is `backing_bv.flac` when present and `mix` is missing; `backing.flac` when `mix == "dry"`; `backing.flac` when the bv file is absent. `build_mpv_args` argv contains that path and not the other.

### Phase 5 — Drops you can hear without a fetched card

Files: `web/api/audio.py` or a small helper used by `preview_pad`, `web/static/js/karaoke.js` `karaFirePad`. Do not copy samples into the repo.

Resolve in order:

1. The card WAV, exactly as `preview_pad` does now (`sd-card-template/.../SMPL`, then `_CARD_STAGING`). That is what the SP-404A will fire after Fetch + Export, so rehearsal matches the rig once the card is built.
2. Else the top library hit for that pad's description. Read the description from the loaded bank in `bank_config.yaml` (after Load Karaoke Set, bank A is `karaoke-drops`). Score with the existing read-only path in `scoring_engine` / `fetch_samples` — call whatever `fetch` already uses to rank one pad, and do not write a WAV. Serve the library file through the same send path as `preview_library`.
3. Else 404 with `{ "ok": false, "error": "no sample", "bank", "pad" }`.

Cache key is `(bank, pad, mtime of the tag store, mtime of bank_config.yaml)`. A negative result is cached only until those mtimes change. Delete the `kara.padAudio[url] = false` forever-cache. On failure, flash the pad name and "no sample" once per miss. Don't mute the pad for the rest of the session: Fetch may have just filled it.

If the scorer isn't importable without a library (tests, fresh clone), step 2 is a miss, not a 500.

Tests: with a fake library hit and no card WAV, preview returns that file. With a card WAV, the card wins even if the library has a hit. With neither, 404 and the JSON error. A second call after the tag-store mtime changes is allowed to find a file.

### Phase 6 — The deck is an upgrade

Files: `deck/karaoke_deck.py` only, plus its tests if the pure helpers live in `tests/test_karaoke.py` (they do — add cases there or next to the deck tests that already import it).

- `find_mpv` returning `None`: `main` exits 2 before `Popen`. The message names the web UI (`scripts/karaoke_prep` output is already what the browser plays) and the `--mpv` flag. `--list-ports` may still run; it already catches an unrunnable mpv.
- Opening MIDI: if the chosen port isn't there and `--dry-run` was not passed, warn once and continue with no clock and no pad notes. The song still plays. Don't make `--dry-run` a requirement for singing on the machine that has mpv and no interface.
- `--video-screen` behavior stays opt-in. No video file still means the spectrum visual, as today. Don't probe displays.
- Non-Windows default root stays `~/Music/Karaoke`. Don't hardcode `D:\Karaoke\Songs` anywhere new.

### Phase 7 — Don't destroy the current banks quietly

Files: `web/api/karaoke.py` `load_set`, `web/static/js/karaoke.js` `loadKaraokeSet`, the confirm copy in `index.html`.

Before the first `load_preset_to_bank`, copy `bank_config.yaml` to `bank_config.yaml.bak-karaoke-YYYYMMDD-HHMMSS` beside it. If the copy fails, do not write the banks. The response includes `backup`. The toast prints it. The modal line that already says the load replaces banks stays, and it names the backup.

One copy per click, not per bank.

Test: load-set against a tmp config writes the bak, then the banks, and the bak still parses as the old YAML.

### Phase 8 — Docs the next session will actually read

Two edits. Not a rewrite of the architecture doc.

- `docs/KARAOKE_MODE_DESIGN.md` header. Replace "design only — nothing installed, no code written" with: built through PR #25; the party-rig sections are the upgrade path; the contract is this plan. Leave the hardware notes (M6, MIDI chart, Moonlight) where they are. They are still true for the deck.
- `docs/ARCHITECTURE.md`. Add a short Karaoke subsection: packages outside the library, browser is the stage, the probe decides which extras run. Fix the one pipeline line that still says `_tags.json` is the store and `copy_to_sd.sh` is the only deploy, in a sentence, not a chapter. SQLite is the tag source of truth. `deploy_sd.py` exists.

Do not restamp `docs/API_REFERENCE.md` in this branch. It is still the April skeleton. A lie of omission there is older than this work.

## Explicitly not in this branch

- Splitting `smart_retag.py`, `plex_client.py`, or `jambox_config.py`.
- Persisting `JobTracker` across a restart.
- Shipping one-shot WAVs inside the repo. The library is the source. If it has no air horn, the UI says so.
- Ollama-drafted drop sheets (design doc §5). The deterministic draft stays the only draft.
- Burned-in lyric videos, UltraStar, take ingest.
- Changing Tiger Dust as the default `bank_config.yaml`. Load-set is opt-in and now reversible from the bak.
- Reworking `RemoteLane`'s ssh quoting. Noted in review. Not this bug.

## Done when

On a machine with ffmpeg, Demucs, and librosa, and without Plex, karaoke-gen, yt-dlp, mpv, or a MIDI port:

1. The karaoke tab opens with Demucs selected, videos off, and a file control. Prep is not a Plex-shaped button.
2. Uploading one audio file produces a song folder with `backing.flac`, a lyric file or a title card, and a drop sheet.
3. Play in the browser runs the backing and the lyric line. Guide fader appears only if `guide.flac` exists.
4. Tapping a drop pad either plays a library match or says "no sample". It does not fail silently, and it does not stay silent after a later Fetch.
5. Installing karaoke-gen (or setting `SP404_KARAOKE_REMOTE`) flips the default to karaoke-gen without a code change. `backing_bv.flac` becomes what you sing to, with a dry toggle.
6. A batch that fails every track reports `error`. A batch that fails one reports `partial`.
7. Load Karaoke Set leaves a `bank_config.yaml.bak-karaoke-*` that still parses as the previous banks.
8. `python deck/karaoke_deck.py` with no mpv exits 2 and names the web UI. It does not throw from `Popen`.

## Suggested commit cuts

1. `Karaoke: capability probe and honest defaults` (phase 1)
2. `Karaoke: prep from a local file` (phase 2)
3. `Karaoke: failed prep is not done` (phase 3)
4. `Karaoke: sing to the backing-vocal mix when it exists` (phase 4)
5. `Karaoke: drop preview falls back to the library` (phase 5)
6. `Karaoke deck: sing without mpv-or-MIDI being fatal` (phase 6)
7. `Karaoke: snapshot bank_config before loading the set` (phase 7)
8. `Docs: karaoke is a jambox feature, the shed is optional` (phase 8)
