# Sample Library Project — Handoff Package for Claude Code

## What This Is
Jason is building a sample library for music production. Cowork (desktop Claude) has been finding, downloading, and organizing audio samples from Archive.org and Mixkit. Claude Code's job is to build the webapp and handle tagging/categorization refinements.

## What's Been Done

### Sample Collection (141 audio files, 14 folders)
All files live in this watchfolder directory. Sources are primarily Archive.org (Creative Commons, public domain, community uploads) and Mixkit (royalty-free).

| Folder | Files | Content |
|--------|-------|---------|
| `witch-house-glitch/` | 16 | Glitch FX, dark atmospheres, broken signal textures (Mixkit WAVs) |
| `dictator-speeches/` | 7 | Historical speech recordings for industrial/noise sampling — Mussolini, Chaplin Great Dictator (Archive.org, public domain) |
| `dirty-party-horns/` | 10 | Horn stabs, brass hits, party horn blasts (Mixkit WAVs) |
| `aggressive-basslines/` | 6 | Heavy bass loops and one-shots (Mixkit WAVs) |
| `idm-trance-house/` | 5 | Electronic loops and textures (Mixkit WAVs) |
| `punk-black-metal/` | 5 | Punk and black metal tracks from Archive.org |
| `nu-rave-indie-sleaze/` | 0 | Empty — placeholder for future content |
| `casino-heist-exotica/` | 15 | Exotica, lounge, spy-movie vibes (Mixkit WAVs) |
| `disco-funk/` | 6 | Disco and funk loops (Mixkit MP3s) |
| `punk-rock-riot-grrrl/` | 8 | Punk rock loops and one-shots (Mixkit MP3s) |
| `thrash-guitars-bass/` | 4 | Thrash metal guitar and bass (Mixkit WAVs) |
| `blast-d-beat-crust/` | 2 | Blast beat and d-beat drum patterns (Mixkit WAVs) |
| `drums-bank/` | 21 | **Key collection** — Apache breaks (multiple versions), Simon Harris "Broken Beaten & Scratched" breaks (Levy Break, Cold Sweat, Memphis Groove, Voodoo, Bongola, Skaville, Rumble Riddim, Drum Culture, Rolling Thunder, Apache), Casio VL-1, Hardnoise, Young MC hi-hats |
| `full-mixes/` | 36 | **Largest collection** — Complete songs and DJ mixes for sampling out of: grindcore (More Drums Less Love EP), exotica (Vegas Vic's Tiki Lounge), punk radio (Rock a Todo Trapo), industrial/noise (Necktar 2017 vol.5 — 9 tracks), disco (Discoholic Dopamine, Instant Funk), acid house (Tom Middleton, Acid Kings), italo disco (4 tracks), EBM (Exferno — 4 tracks), dub/reggae (Parte 1 Dub Reggae, Robodub Dub Tech), rare groove (DJ Rahaan Birthday Mix, Markie Mark Disco Funk Soul), gabber (Dr. Herom Mental Beats — 4 tracks) |

### Master Index: `sample_index.json`
- **141 entries** with full metadata per sample
- Schema version 1.0 with tag taxonomy covering:
  - **38 genres**: witch-house, glitch, punk, black-metal, nu-rave, indie-sleaze, idm, trance, house, tech-house, industrial, neorave, hard-dance, dubstep, trap, grindcore, riot-grrrl, exotica, disco, breakbeat, jungle, dnb, hip-hop, funk, post-punk, acid-house, italo-disco, ebm, noise, drone, ambient, experimental, plunderphonic, concrete, dub, reggae, gabber, hardcore-techno, soul, soul-jazz, rare-groove, ska
  - **16 types**: loop, one-shot, speech, fx, stab, pad, lead, bassline, drum-loop, vocal, atmosphere, noise, texture, construction-kit, full-mix, drum-break
  - **14 instruments**: synth, drums, bass, guitar, horn, brass, vocal, piano, 303, 808, noise-generator, drum-machine, turntable
  - **12 moods**: dark, aggressive, euphoric, dirty, chaotic, hypnotic, melancholic, intense, fun, eerie, groovy, raw
  - **4 energy levels**: low, mid, high, extreme
- Each entry includes contextual notes explaining what the sample is, its historical significance, and why it's useful for production
- The notes field is designed to be interoperable with chat and code — rich enough that any AI session can understand the musical context

### Documentation Created
- `WEBAPP_REQUIREMENTS.md` — Full spec for the webapp (see below)
- `SAMPLE_SOURCES.md` — Catalog of 50+ direct source URLs organized by genre
- `CLAUDE_CODE_HANDOFF.md` — This file

## The Webapp (Claude Code's Primary Task)

Full requirements are in `WEBAPP_REQUIREMENTS.md`. Summary of what needs to be built:

### Priority Order
1. **Sample browser with audio playback** (MVP) — grid/list view, click to play, waveform display, scrub bar (critical for long full mixes), volume control
2. **Filtering by tags** — filter by genre, type, instrument, mood, energy; text search across filenames and notes; combinable AND-logic filters
3. **Drag and drop on sample buttons** — each sample gets a drag handle that works for dropping into DAWs (Ableton, Logic), Finder, and within the webapp
4. **Editable genre categories** — rename, add, remove, reorganize genre tags on the fly without editing JSON manually
5. **Banks** — Full Mixes bank (type=full-mix), Drums bank (type=drum-break or drum-loop), All Samples default view, custom user-created banks
6. **Tag editing with persistence** — inline editing of all tags, bulk editing across selected samples, changes write back to sample_index.json
7. **Waveform visualization** — wavesurfer.js or similar

### Recommended Stack
- React + Node.js backend (serve files + handle JSON read/write)
- Web Audio API or Howler.js for playback, wavesurfer.js for waveforms
- HTML5 Drag and Drop API with file:// protocol support
- sample_index.json is the source of truth — read on startup, write back on edits

### Key User Requirements
- Genre categories MUST be editable/changeable — not rigid
- Drag and drop on buttons is a KEY requirement
- Full mixes need good scrub bars (some are 60-120 minutes long)
- The JSON is the single source of truth

## What's NOT Done Yet (Future Cowork Sessions)
- More sample hunting on Archive.org (jazz breaks, more dub/reggae, 70s funk breaks, more gabber)
- The `nu-rave-indie-sleaze/` folder is still empty
- Large packs noted for manual download: Ultimate Vintage Drum Machines (5.5GB), Breaks & Drum Loops Collection VOL-1 (353MB ZIP)
- Enriching existing entries with even more contextual notes where they're sparse (some early Mixkit entries have minimal notes)

## How to Use This Package
1. Read `sample_index.json` for the complete inventory with metadata
2. Read `WEBAPP_REQUIREMENTS.md` for the full webapp spec
3. The audio files are all in their respective subfolders, ready to serve
4. Start building the webapp in a `webapp/` subdirectory of this watchfolder
