# Using Claude Code with This Project

## Overview

This project uses a multi-agent workflow. Claude Code handles all implementation — scripts, web UI, pipeline, and code changes. Chat handles creative direction and documentation. Cowork handles sample sourcing.

Claude Code reads `CLAUDE.md` in the project root automatically for full context on paths, commands, bank layout, tag system, and coordination rules.

## Getting Started

```bash
npm install -g @anthropic-ai/claude-code
claude login
cd ~/Desktop/SP-404SX/sp404-jambox
claude
```

## Example Workflows

### Curate a Bank
```
> Refetch Bank D with different samples — the current kick is too soft
> and I want a rawer guitar loop on pad 11.
```

### Expand the Library
```
> Ingest whatever's in ~/Downloads right now. Tag the new files
> and tell me what we got.
```

### Edit Bank Layout
```
> Change Bank G to 130 BPM and swap pad 6 from acid bass to
> a distorted bass loop.
```
(This updates `bank_config.yaml`, then re-fetches the affected pads.)

### Full Rebuild
```
> Rebuild the SD card from scratch. Re-fetch all banks,
> regenerate PAD_INFO.BIN and patterns, and deploy.
```

### Library Analysis
```
> How many kicks do we have in the library? Show me the
> distribution of energy tags across all drum samples.
```

### Web UI Development
```
> Add a waveform preview to the pad detail view in the web UI.
> It should show when you click a pad that has a sample loaded.
```

## Key Commands

| Task | Command |
|------|---------|
| Fetch all banks | `python scripts/fetch_samples.py` |
| Fetch one bank | `python scripts/fetch_samples.py --bank d` |
| Fetch one pad | `python scripts/fetch_samples.py --bank d --pad 1` |
| Ingest downloads | `python scripts/ingest_downloads.py` |
| Start file watcher | `python scripts/ingest_downloads.py --watch` |
| Tag library | `python scripts/tag_library.py` |
| Tag new only | `python scripts/tag_library.py --update` |
| Generate PAD_INFO | `python scripts/gen_padinfo.py` |
| Generate patterns | `python scripts/gen_patterns.py` |
| Deploy to SD | `bash scripts/copy_to_sd.sh` |
| Launch web UI | `cd web && python app.py` |

## Key Paths (New)

| Path | Purpose |
|------|---------|
| `presets/` | Bank preset YAML files (by category) |
| `sets/` | Set configs (10 presets per set, mapped to slots A–J) |
| `scripts/plex_client.py` | Plex DB client (read-only SQLite) |
| `scripts/preset_utils.py` | Preset/set resolution and management |
| `scripts/migrate_presets.py` | One-time preset migration (already run) |
| `~/Library/.../com.plexapp.plugins.library.db` | Plex database (read-only) |
| `/Volumes/Jansen's FL Drobo/Multimedia/Music` | Personal music library root |

## Coordination Rules

- **Chat owns docs** — don't create or update documentation files unless the user asks
- **bank_config.yaml is the source of truth** for bank layouts
- **_tags.json is the source of truth** for sample metadata
- After ingesting new samples, always re-tag: `python scripts/tag_library.py --update`
- Cowork drops samples into `~/Downloads/` — ingest them with `ingest_downloads.py`

## Working with Presets & Sets

Presets are standalone YAML files defining a single bank. Sets map 10 presets to slots A–J.

**Key files:**
- `scripts/preset_utils.py` — Core logic (load/save/list/apply)
- `presets/<category>/<slug>.yaml` — Individual bank presets
- `sets/<slug>.yaml` — Set configurations
- `bank_config.yaml` — Expanded runtime config (auto-generated when applying a set)

**Preset categories:** `genre/`, `utility/`, `song-kits/`, `palette/`, `community/`, `auto/`

**Web UI is the primary interface** — the preset browser sidebar has browse, search, preview, and drag-to-bank-tab. The set selector dropdown switches entire configurations.

**API-driven operations:**
```
# List presets
GET /api/presets
GET /api/presets?category=genre&q=funk

# Preview a preset
GET /api/presets/genre/funk

# Load preset into a bank
POST /api/presets/load  {"ref": "genre/funk", "bank": "d"}

# Save current bank as preset
POST /api/presets/from-bank/d  {"name": "My Funk", "category": "community"}

# Switch sets
POST /api/sets/default/apply

# Save current config as a new set
POST /api/sets/save-current  {"name": "Live Set"}
```

**Backward compatibility:** Any script that reads `bank_config.yaml` works unchanged. The preset system sits above it.

## Plex Integration

**Key file:** `scripts/plex_client.py` — read-only SQLite client for the local Plex database.

**CLI testing:**
```bash
python scripts/plex_client.py --stats            # Library counts
python scripts/plex_client.py --browse           # Top genres, moods, styles, decades
python scripts/plex_client.py --artist "Converge" # Artist detail with albums
python scripts/plex_client.py --mood "Aggressive" # Find tracks by mood
python scripts/plex_client.py --style "Hardcore Punk"  # Find tracks by style
python scripts/plex_client.py --search "dark electronic" # Text search
python scripts/plex_client.py --playlists        # List Plex playlists
```

**Tag mapping:**
- `MOOD_TO_VIBE` dict maps 298 Plex moods → 15 internal vibes
- `STYLE_TO_GENRE` dict maps 412 Plex styles → internal genre categories
- Edit these in `plex_client.py` to adjust how Plex metadata translates to the tag system

## File Watcher

```bash
python scripts/ingest_downloads.py --watch
```

Monitors `~/Downloads` for new audio files, waits for stable file size, ingests, auto-tags, logs to `_ingest_log.json`. Reads `_SOURCE.txt` sidecar files from Cowork. Toggle on/off from the web UI Watch button.

## Tips

1. Always verify audio format after conversion: `ffprobe -v quiet -print_format json -show_streams file.wav`
2. Test with `--bank` and `--pad` flags before fetching everything
3. The library is the source of truth, not the SD card — the card is just a deployment target
4. Version bank layouts in git so you can roll back
5. The web UI at localhost:5404 is often faster than terminal for browsing and previewing
6. Presets are the new atomic unit — save banks as presets to make them reusable
