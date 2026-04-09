# API Reference

**Version:** 1.0 (skeleton)
**Date:** 2026-04-08
**Generated from:** Flask route definitions
**Status:** Skeleton — Chat will add context, examples, and usage notes in review pass

---

## Audio

### GET /api/audio/preview/{bank}/{pad}
**Blueprint:** audio
**Auth:** None
**Params:** `bank` (A-J), `pad` (1-12)
**Response:** WAV file stream
**Notes:** Serves the converted WAV for a populated pad

### GET /api/audio/library/{filepath}
**Blueprint:** audio
**Auth:** None
**Params:** `filepath` (relative to sample library root)
**Response:** Audio file stream
**Notes:** Serves library audio for preview playback

### GET /api/audio/waveform/{bank}/{pad}
**Blueprint:** audio
**Auth:** None
**Params:** `bank` (A-J), `pad` (1-12)
**Response:** `{ peaks: number[] }` (80-point array)
**Notes:** Returns peak waveform data for rendering

### POST /api/audio/assign
**Blueprint:** audio
**Auth:** None
**Params:** `{ bank: string, pad: int, library_path: string }`
**Response:** `{ success: bool }`
**Notes:** Assign library file to pad with auto-conversion (16-bit/44.1kHz/mono + RLND)

### POST /api/audio/upload
**Blueprint:** audio
**Auth:** None
**Params:** Multipart form: `bank`, `pad`, `file`
**Response:** `{ success: bool }`
**Notes:** Upload and convert audio file directly to pad

---

## Banks

### GET /api/banks
**Blueprint:** banks
**Auth:** None
**Params:** None
**Response:** `{ banks: [...] }` — all banks with pad status
**Notes:** Returns full bank config with per-pad population state

### GET /api/banks/{letter}
**Blueprint:** banks
**Auth:** None
**Params:** `letter` (A-J)
**Response:** Bank config + pad list
**Notes:** Single bank detail

### PUT /api/banks/{letter}
**Blueprint:** banks
**Auth:** None
**Params:** `{ name?: string, bpm?: int, key?: string, notes?: string }`
**Response:** `{ success: bool }`
**Notes:** Update bank metadata

### PUT /api/banks/{letter}/pads/{num}
**Blueprint:** banks
**Auth:** None
**Params:** `{ description: string }`
**Response:** `{ success: bool }`
**Notes:** Update pad description (drives fetch scoring)

---

## Presets

### GET /api/presets
**Blueprint:** presets
**Auth:** None
**Params:** `category?`, `q?`, `tag?`, `bpm?`, `key?`
**Response:** `{ presets: [...] }`
**Notes:** List/search presets with optional filters

### GET /api/presets/categories
**Blueprint:** presets
**Auth:** None
**Params:** None
**Response:** `{ categories: [...] }` with counts
**Notes:** List preset categories

### GET /api/presets/{ref}
**Blueprint:** presets
**Auth:** None
**Params:** `ref` (preset reference path)
**Response:** Full preset detail with pads
**Notes:** —

### POST /api/presets/from-bank/{letter}
**Blueprint:** presets
**Auth:** None
**Params:** `{ name: string, vibe?: string, tags?: string[], category?: string }`
**Response:** `{ ref: string }`
**Notes:** Save current bank config as a new preset YAML

### POST /api/presets/load
**Blueprint:** presets
**Auth:** None
**Params:** `{ ref: string, bank: string }`
**Response:** `{ success: bool }`
**Notes:** Load preset into a bank slot

### POST /api/presets/daily
**Blueprint:** presets
**Auth:** None
**Params:** `{ source?: string, bank?: string }`
**Response:** Preset object
**Notes:** Generate daily auto preset from recent/trending activity

---

## Vibe

### POST /api/vibe/generate
**Blueprint:** vibe
**Auth:** None
**Params:** `{ prompt: string }`
**Response:** `{ session_id: string, parsed: {...}, suggestions: [...] }`
**Notes:** Parse natural language prompt into structured tags via LLM

### POST /api/vibe/inspire-bank
**Blueprint:** vibe
**Auth:** None
**Params:** `{ genre?: string }`
**Response:** `{ name: string, notes: string, bpm: int, key: string }`
**Notes:** Generate bank metadata (name, notes, BPM, key) via LLM

### POST /api/vibe/populate-bank
**Blueprint:** vibe
**Auth:** None
**Params:** `{ prompt: string, bpm?: int, key?: string, bank: string, fetch?: bool }`
**Response:** `{ job_id: string }`
**Notes:** End-to-end: LLM parse -> preset -> load -> fetch. Async — poll populate-status

### POST /api/vibe/generate-fetch-bank
**Blueprint:** vibe
**Auth:** None
**Params:** `{ prompt: string, bpm?: int, key?: string, bank: string, fetch?: bool }`
**Response:** `{ job_id: string }`
**Notes:** Metadata-first generation + fetch for one bank

### POST /api/vibe/apply-bank
**Blueprint:** vibe
**Auth:** None
**Params:** `{ preset: object, bank: string, reviewed_parsed?: object, fetch?: bool, session_id?: string }`
**Response:** `{ success: bool }`
**Notes:** Apply reviewed vibe draft to a bank (with optional auto-fetch)

### GET /api/vibe/populate-status/{job_id}
**Blueprint:** vibe
**Auth:** None
**Params:** `job_id`
**Response:** `{ status: string, progress?: object }`
**Notes:** Poll background populate-bank job

---

## Pattern

### POST /api/pattern/generate
**Blueprint:** pattern
**Auth:** None
**Params:** Pattern generation payload
**Response:** Pattern file metadata
**Notes:** Generate Magenta-based drum patterns

### POST /api/pattern/scale-generate
**Blueprint:** pattern
**Auth:** None
**Params:** Scale pattern payload
**Response:** Pattern file metadata
**Notes:** Generate scale-mapped patterns from preset

---

## Music (Plex)

### GET /api/music/status
**Blueprint:** music
**Auth:** None
**Params:** None
**Response:** `{ available: bool, source: string, stats: {...} }`
**Notes:** Library availability and stats (Plex vs ID3 fallback)

### GET /api/music/browse
**Blueprint:** music
**Auth:** None
**Params:** None
**Response:** `{ artists: [...], genres: [...], moods: [...], styles: [...], decades: [...] }`
**Notes:** Browse all dimensions of the personal music library

### GET /api/music/artist/{name}
**Blueprint:** music
**Auth:** None
**Params:** `name` (artist name, URL-encoded)
**Response:** Artist detail with albums and tracks
**Notes:** —

### GET /api/music/artist_by_id/{artist_id}
**Blueprint:** music
**Auth:** None
**Params:** `artist_id` (Plex int ID)
**Response:** Artist detail
**Notes:** Lookup by Plex internal ID

### GET /api/music/track/{track_id}
**Blueprint:** music
**Auth:** None
**Params:** `track_id` (Plex int ID)
**Response:** Full track metadata including moods, loudness
**Notes:** —

### GET /api/music/search
**Blueprint:** music
**Auth:** None
**Params:** `q` (min 2 chars)
**Response:** `{ results: [...] }`
**Notes:** Text search across artists, albums, tracks

### GET /api/music/mood/{mood}
**Blueprint:** music
**Auth:** None
**Params:** `mood` (Plex mood string)
**Response:** `{ tracks: [...] }`
**Notes:** Filter by Plex mood tag

### GET /api/music/style/{style}
**Blueprint:** music
**Auth:** None
**Params:** `style` (Plex style string)
**Response:** `{ tracks: [...] }`
**Notes:** Filter by Plex style tag

### GET /api/music/playlists
**Blueprint:** music
**Auth:** None
**Params:** None
**Response:** `{ playlists: [...] }`
**Notes:** List Plex playlists

### GET /api/music/most-played
**Blueprint:** music
**Auth:** None
**Params:** None
**Response:** `{ tracks: [...] }`
**Notes:** Most-played tracks by play count

### GET /api/music/art
**Blueprint:** music
**Auth:** None
**Params:** `thumb` (Plex metadata URL)
**Response:** Image stream
**Notes:** Proxy album art from Plex metadata store

### GET /api/music/preview/{track_id}
**Blueprint:** music
**Auth:** None
**Params:** `track_id`
**Response:** Audio stream
**Notes:** Stream track for preview playback

### POST /api/music/split
**Blueprint:** music
**Auth:** None
**Params:** `{ track_id: int }` or `{ id: int }`
**Response:** `{ job_id: string }`
**Notes:** Split track into stems via Demucs. Carries Plex metadata to stems

### GET /api/music/split/status/{job_id}
**Blueprint:** music
**Auth:** None
**Params:** `job_id`
**Response:** `{ status: string, stems?: [...] }`
**Notes:** Poll stem split job status

---

## Library

### GET /api/library/browse
**Blueprint:** library
**Auth:** None
**Params:** None
**Response:** Root directory listing
**Notes:** Browse sample library root

### GET /api/library/browse/{subdir}
**Blueprint:** library
**Auth:** None
**Params:** `subdir` (relative path)
**Response:** Directory listing
**Notes:** Browse subdirectory

### GET /api/library/search
**Blueprint:** library
**Auth:** None
**Params:** `q?`, `type_code?`, `genre?`, `danceable?`, `limit?`
**Response:** `{ results: [...] }`
**Notes:** Semantic search (CLAP) or filename matching

### GET /api/library/stats
**Blueprint:** library
**Auth:** None
**Params:** None
**Response:** `{ categories: {...}, pending_packs: int, clap_coverage: float }`
**Notes:** Library statistics

### GET /api/library/tags
**Blueprint:** library
**Auth:** None
**Params:** None
**Response:** `{ dimensions: {...} }` — tag frequencies grouped by dimension
**Notes:** Powers the tag cloud UI

### GET /api/library/by-tag
**Blueprint:** library
**Auth:** None
**Params:** `tag?`, `type_code?`, `vibe?`, `texture?`, `genre?`, `source?`, `energy?`, `playability?`, `bpm?`, `limit?`
**Response:** `{ files: [...] }`
**Notes:** Dimension-aware filtering (OR within dimension, AND across)

### POST /api/library/smart-retag
**Blueprint:** library
**Auth:** None
**Params:** `{ type_code?: string, path?: string, file?: string, limit?: int, force?: bool, dry_run?: bool, workers?: int }`
**Response:** `{ job_id: string }`
**Notes:** Trigger LLM-powered smart retagging batch

### GET /api/library/smart-retag/{job_id}
**Blueprint:** library
**Auth:** None
**Params:** `job_id`
**Response:** `{ status: string, progress: {...} }`
**Notes:** Poll smart retag job progress

### POST /api/library/smart-retag/{job_id}/stop
**Blueprint:** library
**Auth:** None
**Params:** `job_id`
**Response:** `{ success: bool }`
**Notes:** Stop a running smart-retag job

---

## Media (Plex Movies/TV)

### GET /api/media/status
**Blueprint:** media
**Auth:** None
**Params:** None
**Response:** `{ available: bool, counts: {...} }`
**Notes:** Media library availability and counts

### GET /api/media/movies
**Blueprint:** media
**Auth:** None
**Params:** `genre?`, `sort?`, `search?`, `limit?`
**Response:** `{ movies: [...] }`
**Notes:** Browse movies with optional filters

### GET /api/media/movie/{movie_id}
**Blueprint:** media
**Auth:** None
**Params:** `movie_id`
**Response:** Movie detail (cast, path, extras)
**Notes:** —

### GET /api/media/shows
**Blueprint:** media
**Auth:** None
**Params:** `search?`, `section?`, `limit?`
**Response:** `{ shows: [...] }`
**Notes:** Browse TV shows and anime

### GET /api/media/show/{show_id}/episodes
**Blueprint:** media
**Auth:** None
**Params:** `show_id`, `season?`, `limit?`
**Response:** `{ episodes: [...] }`
**Notes:** List episodes for a show

### GET /api/media/taste
**Blueprint:** media
**Auth:** None
**Params:** None
**Response:** Taste profile object
**Notes:** Build taste profile from full library

### GET /api/media/genres
**Blueprint:** media
**Auth:** None
**Params:** None
**Response:** `{ genres: [...] }` with counts
**Notes:** All genres across media library

### POST /api/media/extract
**Blueprint:** media
**Auth:** None
**Params:** `{ movie_id?: int, show_id?: int, season?: int, scan_minutes?: int, max_clips?: int }`
**Response:** `{ job_id: string }`
**Notes:** Extract audio clips from movie/episode for sampling

### GET /api/media/extract-status/{job_id}
**Blueprint:** media
**Auth:** None
**Params:** `job_id`
**Response:** `{ status: string, clips?: [...] }`
**Notes:** Poll extraction job status

---

## Pipeline

### POST /api/pipeline/fetch
**Blueprint:** pipeline
**Auth:** None
**Params:** `{ bank?: string, pad?: int }`
**Response:** `{ job_id: string }`
**Notes:** Start async fetch job. Omit params for all banks

### GET /api/pipeline/status/{job_id}
**Blueprint:** pipeline
**Auth:** None
**Params:** `job_id`
**Response:** `{ status: string, progress?: {...} }`
**Notes:** Poll any pipeline job status

### POST /api/pipeline/padinfo
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ success: bool }`
**Notes:** Generate PAD_INFO.BIN from playability tags

### POST /api/pipeline/patterns
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ success: bool }`
**Notes:** Build .PTN pattern files

### POST /api/pipeline/ingest
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ job_id: string }`
**Notes:** Run ingest_downloads.py (process pending packs from ~/Downloads)

### POST /api/pipeline/watcher/start
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ success: bool }`
**Notes:** Start background file watcher daemon

### POST /api/pipeline/watcher/stop
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ success: bool }`
**Notes:** Stop file watcher

### GET /api/pipeline/watcher/status
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ running: bool, recent_activity: [...] }`
**Notes:** Watcher state and recent activity log

### GET /api/pipeline/disk-report
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** Disk usage breakdown
**Notes:** Library size, staging size, reclaimable space

### POST /api/pipeline/cleanup
**Blueprint:** pipeline
**Auth:** None
**Params:** `{ purge_archive?: bool }`
**Response:** `{ freed_bytes: int }`
**Notes:** Remove processed items from ~/Downloads

### GET /api/pipeline/downloads-path
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ path: string }`
**Notes:** Current downloads watch path

### POST /api/pipeline/downloads-path
**Blueprint:** pipeline
**Auth:** None
**Params:** `{ path: string }`
**Response:** `{ success: bool }`
**Notes:** Set downloads watch path

### GET /api/pipeline/server/status
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ features: {...}, uptime: int, clap_coverage: float }`
**Notes:** Server health check — feature availability (LLM, librosa, fpcalc, demucs, watcher)

### POST /api/pipeline/server/restart
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ success: bool }`
**Notes:** Graceful Flask restart

### POST /api/pipeline/deploy
**Blueprint:** pipeline
**Auth:** None
**Params:** None
**Response:** `{ success: bool }`
**Notes:** Deploy staging directory to SD card via copy_to_sd.sh

---

## SD Card

### GET /api/sdcard/status
**Blueprint:** sdcard
**Auth:** None
**Params:** None
**Response:** `{ mounted: bool, free_space: int }`
**Notes:** SD card mount status and free space

### GET /api/sdcard/scan
**Blueprint:** sdcard
**Auth:** None
**Params:** None
**Response:** Per-pad identity, settings, provenance, pattern stats
**Notes:** Full card scan

### POST /api/sdcard/pull-bank-a
**Blueprint:** sdcard
**Auth:** None
**Params:** None
**Response:** `{ archived: [...] }`
**Notes:** Archive Bank A WAVs from card to _GOLD

### POST /api/sdcard/pull-intelligence
**Blueprint:** sdcard
**Auth:** None
**Params:** None
**Response:** Card intelligence diff
**Notes:** Full card intelligence pull + diff for performance scoring

### POST /api/sdcard/reorganize
**Blueprint:** sdcard
**Auth:** None
**Params:** `{ moves: [{ from: string, to: string }] }`
**Response:** `{ success: bool }`
**Notes:** Move samples between pads on card

### POST /api/sdcard/eject
**Blueprint:** sdcard
**Auth:** None
**Params:** None
**Response:** `{ success: bool }`
**Notes:** Eject SD card (macOS diskutil)

### GET /api/gold/sessions
**Blueprint:** sdcard
**Auth:** None
**Params:** None
**Response:** `{ sessions: [...] }`
**Notes:** List archived Bank A sessions from _GOLD

---

## Blackout

### GET /api/blackout/status
**Blueprint:** blackout
**Auth:** None
**Params:** None
**Response:** Dashboard snapshot (eval suite, session stats, training export, pattern readiness, LoRA artifacts, host metrics)
**Notes:** Offline training dashboard status

---

## Sets (Not Yet Implemented)

The following endpoints are planned but not yet wired up in the Flask routes. Set management currently happens through the preset system and `bank_config.yaml`.

- `GET /api/sets` — List saved set configurations
- `POST /api/sets/{slug}/apply` — Apply a set (loads 10 presets across Banks A-J)
- `POST /api/sets/save-current` — Save current bank config as a named set
