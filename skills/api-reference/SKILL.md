---
name: api-reference
description: Jambox web API reference — all Flask routes grouped by blueprint. Use when the user asks about "API endpoints", "web API", "Flask routes", "how do I call", "what endpoints exist", or needs to know what HTTP endpoints are available on localhost:5404.
version: 0.2.0
---

# Jambox Web API (localhost:5404)

89 routes across 10 blueprints. All API routes are prefixed with `/api`.

## Bank Management (`web/api/banks.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/banks` | List all banks with pad info |
| GET | `/api/banks/<letter>` | Get single bank detail |
| PUT | `/api/banks/<letter>` | Update bank metadata (name, bpm, key, notes) |
| PUT | `/api/banks/<letter>/pads/<int:num>` | Update pad description |

## Audio (`web/api/audio.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/audio/preview/<bank>/<int:pad>` | Serve WAV file for pad preview |
| GET | `/api/audio/library/<path:filepath>` | Serve audio file from library |
| GET | `/api/audio/waveform/<bank>/<int:pad>` | Get waveform peak data for rendering |
| POST | `/api/audio/assign` | Convert and assign library file to pad |
| POST | `/api/audio/upload` | Upload audio file and assign to pad |

## Pipeline Controls (`web/api/pipeline.py`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/pipeline/fetch` | Start background sample fetch job |
| GET | `/api/pipeline/status/<job_id>` | Check fetch job status |
| POST | `/api/pipeline/padinfo` | Generate PAD_INFO.BIN |
| POST | `/api/pipeline/patterns` | Generate pattern files |
| POST | `/api/pipeline/ingest` | Extract and organize downloaded sample packs |
| POST | `/api/pipeline/watcher/start` | Start file watcher for downloads |
| POST | `/api/pipeline/watcher/stop` | Stop file watcher |
| GET | `/api/pipeline/watcher/status` | Get watcher state and activity log |
| GET | `/api/pipeline/disk-report` | Get disk usage report |
| POST | `/api/pipeline/cleanup` | Remove ingested items and archive |
| GET | `/api/pipeline/downloads-path` | Get downloads watch path |
| POST | `/api/pipeline/downloads-path` | Set downloads watch path |
| GET | `/api/pipeline/server/status` | Server health check with feature availability |
| POST | `/api/pipeline/server/restart` | Gracefully restart Flask server |
| POST | `/api/pipeline/deploy` | Copy files to SD card |

## Library (`web/api/library.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/library/browse` | Browse library root |
| GET | `/api/library/browse/<path:subdir>` | Browse library subdirectory |
| GET | `/api/library/search` | Search library files |
| GET | `/api/library/stats` | Library statistics and category counts |
| GET | `/api/library/tags` | Tag frequency cloud by dimensions |
| GET | `/api/library/by-tag` | Find files by tag/dimension filters |
| POST | `/api/library/smart-retag` | Start LLM-powered smart retagging |
| GET | `/api/library/smart-retag/<job_id>` | Poll smart retag job status |

## SD Card (`web/api/sdcard.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sdcard/status` | Check SD card mount status and space |
| GET | `/api/sdcard/scan` | Full scan of SD card samples, PAD_INFO, patterns |
| POST | `/api/sdcard/pull-bank-a` | Sync Bank A from card to repository |
| GET | `/api/gold/sessions` | List "gold" session backups from Bank A |

## Music — Plex Integration (`web/api/music.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/music/status` | Check music library availability and source |
| GET | `/api/music/browse` | Browse artists, genres, moods, styles, decades |
| GET | `/api/music/artist/<path:name>` | Get artist detail and discography |
| GET | `/api/music/artist_by_id/<int:id>` | Get artist by Plex ID |
| GET | `/api/music/track/<int:id>` | Get track metadata |
| GET | `/api/music/search` | Text search music library |
| GET | `/api/music/mood/<mood>` | Find tracks by Plex mood tag |
| GET | `/api/music/style/<path:style>` | Find tracks by Plex style tag |
| GET | `/api/music/playlists` | List Plex playlists |
| GET | `/api/music/most-played` | Get most-played tracks |
| GET | `/api/music/art` | Proxy album art from Plex metadata |
| GET | `/api/music/preview/<int:id>` | Stream track for preview |
| POST | `/api/music/split` | Split track into stems via Demucs |
| GET | `/api/music/split/status/<job_id>` | Check stem split job status |

## Presets (`web/api/presets.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/presets` | List/search presets (category, q, tag, bpm, key) |
| GET | `/api/presets/categories` | List preset categories with counts |
| GET | `/api/presets/<path:ref>` | Get full preset detail |
| POST | `/api/presets/from-bank/<letter>` | Save bank as new preset |
| POST | `/api/presets/load` | Load preset into bank slot |
| POST | `/api/presets/daily` | Generate daily preset, optionally load to bank |
| GET | `/api/sets` | List all sets |
| GET | `/api/sets/<slug>` | Get full set detail with resolved presets |
| POST | `/api/sets` | Create new set |
| POST | `/api/sets/save-current` | Snapshot current bank config as set |
| POST | `/api/sets/<slug>/apply` | Apply set to banks |

## Vibe Intelligence (`web/api/vibe.py`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/vibe/generate` | Parse prompt, return suggestions + session_id |
| POST | `/api/vibe/populate-bank` | End-to-end: LLM parse → preset → load → fetch |
| POST | `/api/vibe/apply-bank` | Apply reviewed draft to bank |
| GET | `/api/vibe/populate-status/<job_id>` | Poll background populate job |

## Pattern Generation (`web/api/pattern.py`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/pattern/generate` | Generate Magenta-based algorithmic pattern |
| POST | `/api/pattern/scale-generate` | Generate scale-mapped pattern from preset |

## Media — Movies/TV (`web/api/media.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/media/status` | Check media library availability and counts |
| GET | `/api/media/movies` | Browse movies (genre, sort, search, limit) |
| GET | `/api/media/movie/<int:id>` | Get full movie detail |
| GET | `/api/media/shows` | Browse TV shows/anime (search, section, limit) |
| GET | `/api/media/show/<int:id>/episodes` | List show episodes (season, limit) |
| GET | `/api/media/taste` | Build taste profile from library |
| GET | `/api/media/genres` | List all movie/TV/anime genres with counts |
| POST | `/api/media/extract` | Extract audio clips from movie/episode |
| GET | `/api/media/extract-status/<job_id>` | Poll extraction job status |

## App Root (`web/app.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve index.html |
