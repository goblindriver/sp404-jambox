# Sample Library Webapp — Requirements for Claude Code

## Overview
Build a local webapp that serves as a sample browser/player for the audio files in this watchfolder. The webapp should read `sample_index.json` for metadata and allow the user to browse, filter, play, and drag-and-drop samples into a DAW or file system.

## Data Source
- **sample_index.json** — master index with 102 samples, each with metadata: file path, genre tags, type, instrument, mood, energy, source, license, duration, notes
- Audio files are organized in subfolders: `witch-house-glitch/`, `dictator-speeches/`, `dirty-party-horns/`, `aggressive-basslines/`, `idm-trance-house/`, `punk-black-metal/`, `casino-heist-exotica/`, `disco-funk/`, `punk-rock-riot-grrrl/`, `thrash-guitars-bass/`, `blast-d-beat-crust/`, `full-mixes/`, `drums-bank/`

## Core Features

### 1. Sample Browser
- Display all samples in a grid or list view
- Show key metadata per sample: filename, genre tags, type, duration, energy level
- Thumbnail/waveform visualization would be nice but not required for v1

### 2. Filtering & Search
- Filter by genre, type, instrument, mood, energy
- Text search across filenames and notes
- Multiple filters should be combinable (AND logic)
- **Genre categories must be editable/changeable** — the user wants to be able to rename, add, remove, or reorganize genre tags on the fly without editing JSON manually

### 3. Banks / Views
- **Full Mixes Bank** — dedicated view showing only items with type "full-mix". These are complete songs/radio shows intended for sampling out of
- **Drums Bank** — dedicated view showing only items with type "drum-break" or "drum-loop"
- **All Samples** — default view showing everything
- User should be able to create custom banks/views

### 4. Audio Playback
- Click to play/preview any sample
- Waveform display during playback
- Play/pause, scrub/seek
- Volume control
- For long full mixes, the scrub bar is especially important

### 5. Drag and Drop
- **Each sample should have a drag-and-drop handle/button**
- Dragging a sample should allow dropping it into:
  - A DAW (Ableton, Logic, etc.) via file drag
  - The OS file system (Finder)
  - Other sections/banks within the webapp itself
- The drag-and-drop functionality on buttons is a key requirement from the user

### 6. Tag Editing
- Inline editing of genre, type, instrument, mood, energy tags per sample
- Ability to bulk-edit tags across multiple selected samples
- Changes should persist back to sample_index.json
- **Genre categories should be editable** — add new genres, rename existing ones, merge genres together

### 7. Metadata Display
- Source and license info visible per sample
- Notes field visible and editable
- Duration display

## Technical Recommendations
- **Stack**: React + Node.js backend (to serve files and handle JSON read/write)
- **Audio**: Web Audio API or Howler.js for playback, wavesurfer.js for waveform visualization
- **Drag & Drop**: HTML5 Drag and Drop API, with file:// protocol support for DAW integration
- **State**: The JSON file is the source of truth — read on startup, write back on edits

## File Structure
```
watchfolder/
├── sample_index.json          # Master index (source of truth)
├── WEBAPP_REQUIREMENTS.md     # This file
├── SAMPLE_SOURCES.md          # Catalog of source URLs
├── webapp/                    # Claude Code builds this
│   ├── server.js
│   ├── package.json
│   └── src/
│       ├── App.jsx
│       ├── components/
│       └── ...
├── witch-house-glitch/
├── dictator-speeches/
├── dirty-party-horns/
├── aggressive-basslines/
├── idm-trance-house/
├── punk-black-metal/
├── nu-rave-indie-sleaze/
├── casino-heist-exotica/
├── disco-funk/
├── punk-rock-riot-grrrl/
├── thrash-guitars-bass/
├── blast-d-beat-crust/
├── full-mixes/
└── drums-bank/
```

## Priority Order
1. Sample browser with playback (MVP)
2. Filtering by tags
3. Drag and drop on sample buttons
4. Editable genre categories
5. Banks (full mixes, drums, custom)
6. Tag editing and persistence
7. Waveform visualization
