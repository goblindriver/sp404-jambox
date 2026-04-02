# Architecture & Design Decisions

## Overview

Three components work together:

1. **SD Card Builder** — Python scripts that match, convert, and deploy samples to an SP-404A/SX SD card
2. **Sample Library** — A permanent, tagged collection of 9,600+ royalty-free WAVs on disk
3. **Web UI** — Flask app for visual bank editing, library browsing, and pipeline control

## Pipeline

```
MusicRadar / Freesound / Cowork downloads
        │
        ▼
  ~/Downloads/*.zip
        │
        ▼
  ingest_downloads.py ──► ~/Music/SP404-Sample-Library/
        │                    ├── Drums/{Kicks, Snares-Claps, Hi-Hats, Percussion, Drum-Loops}
        │                    ├── Melodic/{Bass, Guitar, Keys-Piano, Synths-Pads}
        │                    ├── Loops/Instrument-Loops
        │                    ├── Ambient-Textural/Atmospheres
        │                    ├── SFX/Stabs-Hits
        │                    ├── Vocals/Chops
        │                    ├── Freesound/{bank-name}/
        │                    ├── _RAW-DOWNLOADS/
        │                    └── _tags.json
        │
        ▼
  tag_library.py ──► Auto-tags every WAV across 7 dimensions
        │              (type_code, vibe, texture, genre, energy, source, playability)
        │
        ▼
  bank_config.yaml ──► Defines all 10 banks with pad descriptions
        │
        ▼
  fetch_samples.py ──► Scores entire _tags.json against each pad description
        │                 Type match = +10, playability = +5, BPM/key = +3-4, keywords = +3 each
        │                 Global dedup (no file reused across pads)
        │                 Falls back to Freesound API if no local match
        │                 Converts to 16-bit/44.1kHz/mono + RLND chunk
        │
        ▼
  gen_padinfo.py ──► PAD_INFO.BIN (pads 1-4 = gate, 5-12 = loop)
  gen_patterns.py ──► Starter .PTN pattern files via vendored spEdit404
        │
        ▼
  copy_to_sd.sh ──► /Volumes/SP-404SX/ROLAND/SP-404SX/SMPL/
```

## Web UI Architecture

Flask app at `web/`, runs on http://localhost:5404.

- **Pad grid**: Visual representation of SP-404 layout, click to edit/preview/fetch
- **Library sidebar**: Folder browser + tag cloud with dimension-aware filtering
- **Bank edit modal**: Name, BPM, key, notes per bank
- **Pipeline controls**: Fetch All, Ingest Downloads, Build, Deploy buttons
- **SD card status**: Auto-polling indicator
- **Drag-and-drop**: From library sidebar or OS file explorer onto pads
- **Tag Cloud API**: `GET /api/library/tags`, `GET /api/library/by-tag?type_code=KIK&vibe=dark`

## Design Decisions

### Why 16-bit/44.1kHz Mono?
The SP-404A (original) requires this exact format. The SX and MK2 accept higher rates but mono 44.1 is the universal common denominator. Keeps file sizes small on the SD card too.

### Why Pads 1–4 = Hits, 5–12 = Loops?
Natural performance layout. Left hand on drum hits, right hand layers loops and melodic content. Consistent across all banks so muscle memory transfers between genres.

### Why YAML Bank Config?
Decouples bank design from code. Chat can suggest new banks, the user pastes them into `bank_config.yaml`, and Code's fetch pipeline picks them up without any script changes. The pad description format (`TYPE keywords playability`) is deliberately simple — 3–4 tokens get better matches than overspecified queries.

### Harmonic Design
All bank keys (Am, Dm, Em, F) are diatonic to C major. This means any sample from any bank will harmonize with any other — you can freely layer across banks during a performance without clashing.

### Tempo Design
BPMs cluster at 112/120/128/130. This range is tight enough that the SP-404's time-stretch can handle cross-bank mixing cleanly, but wide enough to give each genre its own feel.

### Bank Genre Selection (v3)
Chosen for a cohesive DJ/performance set that flows from warm to hard:

| Bank | Genre | Why |
|------|-------|-----|
| B | Sessions | Raw material — long-form breaks and tracks for live chopping |
| C | Drum Loops | Pure rhythm palette — genre-agnostic backbone |
| D | Funk | Organic warmth, guitar-driven, dance-punk energy |
| E | Disco | Classic four-on-the-floor, bridges funk → electronic |
| F | Electroclash | Dirty analog, bridges disco → aggressive electronic |
| G | Nu-Rave | High-energy blog-house, neon maximalism |
| H | Aggressive | Peak-time industrial — maximum intensity |
| I | Textures | Connective tissue — pads, risers, ambient glue |
| J | Utility | Performance triggers — speeches, SFX, crowd control |

### Why Real Samples Over Synthesis?
Version 1 synthesized everything using numpy. Results were functional but lacked character. MusicRadar SampleRadar packs are royalty-free and provide much better source material, especially for organic sounds.

### Tag-Based Fetching Over Keyword Matching
The tag system (`_tags.json`) pre-computes 7 dimensions per sample, so `fetch_samples.py` can score candidates quickly without re-analyzing audio each time. The scoring weights favor type code accuracy (you asked for a kick, you get a kick) while allowing vibe/texture/genre keywords to break ties between candidates.

### Freesound Fallback
If the local library has no good match for a pad description, the fetcher hits the Freesound API. Downloaded files go into `Freesound/{bank-name}/` with proper attribution. This keeps the library growing organically as bank designs evolve.

## File Format Details

### SP-404 WAV Naming
```
{Bank}0000{Pad}.WAV
  │         │
  │         └── 1-12 (pad number within bank)
  └── A-J (bank letter)
```
Full path on SD: `ROLAND/SP-404SX/SMPL/{Bank}000000{Pad}.WAV`

### RLND WAV Chunk
SP-404SX WAVs include a proprietary "RLND" chunk (466 bytes) encoding device ID and pad index. Injected by `scripts/wav_utils.py:inject_rlnd()` during sample conversion.

### PAD_INFO.BIN
Per-pad metadata at `ROLAND/SP-404SX/SMPL/PAD_INFO.BIN`. Generated by `gen_padinfo.py` — auto-sets loop mode for pads 5–12, gate for 1–4.

### Pattern Files (.PTN)
Proprietary binary format in `ROLAND/SP-404SX/PTN/`. Generated via `scripts/gen_patterns.py` using vendored spEdit404 (`scripts/spedit404/`).

## Multi-Agent Coordination

| Agent | Role | Touches |
|-------|------|---------|
| **Chat** | Creative direction, docs, orchestration | `docs/`, tag vocabulary, bank concepts |
| **Code** | Implementation | `scripts/`, `web/`, `bank_config.yaml` |
| **Cowork** | Sample sourcing | `~/Downloads/` watchfolders |

Chat owns all documentation. Code doesn't create or update docs unless asked. See `CLAUDE.md` for full coordination protocol.

## Plex Integration

The system reads metadata from the local Plex Media Server SQLite database in **read-only** mode. No API calls, no network dependency — just direct DB reads.

**Database location:**
```
~/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db
```

**Music library root:** `/Volumes/Jansen's FL Drobo/Multimedia/Music`

**What we pull from Plex:**
- Artist name, album, track title, genre, duration
- 298 mood tags mapped to our 15 vibes via `MOOD_TO_VIBE` in `plex_client.py`
- 412 style tags mapped to our genre categories via `STYLE_TO_GENRE` in `plex_client.py`
- Play count (used as relevance signal in fetch scoring)
- Album art paths, artist bios, country

**Data flow:**
```
Plex SQLite DB (read-only)
  → plex_client.py (query + map tags)
    → Web UI "My Music" sidebar (Moods tab, Styles tab, Artist detail)
    → stem_split.py (metadata carried through to _tags.json on child stems)
    → fetch_samples.py (Plex-tagged stems get scoring boost)
```

**Key constraint:** Read-only access only. Never writes to the Plex database.

## Bank Preset Library

The bank configuration system has two layers: **presets** (individual bank definitions) and **sets** (curated groups of 10 presets mapped to slots A–J).

**Presets** (`presets/<category>/<name>.yaml`):
- Each preset is a standalone YAML file defining a single bank configuration
- Contains: name, BPM, key, vibe, notes, tags, and 12 pad descriptions
- Categories: `genre/`, `utility/`, `song-kits/`, `palette/`, `community/`, `auto/`

**Sets** (`sets/<name>.yaml`):
- Maps 10 slots (A–J) to preset references (relative paths without `.yaml`)
- Switching sets swaps all 10 banks at once

**Backward compatibility:**
- `bank_config.yaml` remains the fully expanded runtime config
- `preset_utils.py` resolves set → presets → expanded bank_config.yaml
- Existing scripts that read `bank_config.yaml` work unchanged

## Background File Watcher

The ingest pipeline (`scripts/ingest_downloads.py`) can run as a persistent daemon using `watchdog`.

1. Monitors `~/Downloads` for new files via filesystem events
2. Waits for file size to stabilize (handles in-progress downloads)
3. Ingests: normalize, categorize, move to library
4. Reads `_SOURCE.txt` sidecar files (from Cowork) and stores context in `_tags.json`
5. Auto-runs `tag_library.py --update` to refresh the tag index
6. Logs every action to `_ingest_log.json`
7. Web UI has a Watch toggle button and activity feed

## Future Ideas

- **MK2 support**: Add 48kHz/stereo variant for SP-404 MK2 users
- **Harmonic engine**: Map keys to diatonic families, chemistry view for cross-bank compatibility
- **"Build a Set" workflow**: Guided modal for assembling 10 presets into a new set
- **Community preset import**: Import preset files from external sources
- **Playlist-to-bank**: Generate bank presets from Plex playlist metadata
