# Sample Sources

All samples are royalty-free, sourced from MusicRadar SampleRadar and the Freesound API.

## Primary Source: MusicRadar SampleRadar

Direct download links:

| Pack | Size | Contents |
|------|------|----------|
| [80s Synths](https://cdn.mos.musicradar.com/audio/samples/musicradar-80s-synth-samples.zip) | ~200MB | Polys, pads, bass, arps, leads |
| [Drum Samples](https://cdn.mos.musicradar.com/audio/samples/musicradar-drum-samples.zip) | ~250MB | Kicks, snares, hats, cymbals, kits |
| [Funk Samples](https://cdn.mos.musicradar.com/audio/samples/musicradar-funk-samples.zip) | ~150MB | Bass, guitar, organ, clavinet, piano |
| [Hip-Hop Essentials](https://cdn.mos.musicradar.com/audio/samples/musicradar-hiphop-essentials.zip) | ~300MB | Drum hits, Oberheim DX, beats, loops |
| [IDM Samples](https://cdn.mos.musicradar.com/audio/samples/musicradar-idm-samples.zip) | ~180MB | 5 kits at 100–165 BPM |
| [Lo-Fi Samples](https://cdn.mos.musicradar.com/audio/samples/musicradar-lofi-samples.zip) | ~200MB | Construction kits, drum loops, SFX |
| [Soul-Funk Samples](https://cdn.mos.musicradar.com/audio/samples/musicradar-soul-funk-samples.zip) | ~150MB | Construction kits at 100–120 BPM |
| [Synth Percussion](https://cdn.mos.musicradar.com/audio/samples/musicradar-synth-percussion-samples.zip) | ~80MB | Vermona DRM1, WaveDrum loops |

**MusicRadar total: ~1.5GB compressed, ~2.9GB uncompressed, 4,886 WAV files**

### License
MusicRadar SampleRadar samples are royalty-free for use in music production. From their site: these samples are provided free of charge and can be used in your music productions without restriction.

### Browse More Packs
https://www.musicradar.com/news/tech/free-music-samples-royalty-free-loops-hits-and-multis-702616

## Secondary Source: Freesound API

When `fetch_samples.py` can't find a good local match for a pad description, it falls back to the Freesound API.

**Setup:** Add `FREESOUND_API_KEY=your_key_here` to `.env` in the project root.

**How it works:**
1. Fetcher builds a search query from the pad description keywords
2. Hits Freesound API, filters for Creative Commons licensed samples
3. Downloads the best match to `~/Music/SP404-Sample-Library/Freesound/{bank-name}/`
4. Converts to SP-404 format (16-bit/44.1kHz/mono)
5. Stores attribution metadata alongside the file

**Get an API key:** https://freesound.org/apiv2/apply/

Freesound downloads are stored separately from the MusicRadar library so attribution requirements stay clear.

## Adding New Packs

1. Download ZIPs to `~/Downloads/`
2. Run `python scripts/ingest_downloads.py` — extracts, categorizes, and archives
3. Run `python scripts/tag_library.py --update` — tags new files only
4. New samples are immediately available to `fetch_samples.py`

## Current Library Stats

~9,600+ WAVs across all categories, tagged in `_tags.json`.

## Pack Contents Detail

### 80s-synths (932 WAVs)
- Polys and Pads — Lush analog pad recordings at various BPMs
- Bass Loops — Synth bass loops
- Arps and Leads — Sequenced arpeggios and lead lines
- BPMs: 80, 95, 100, 105, 110, 120, 125, 130

### drum-samples (934 WAVs)
- Assorted Hits — Kicks, Snares, Hi Hats, Cymbals (one-shots)
- Drum Kits — Electro Kit, Vinyl Kit, IDM Kit, etc. (loops per kit)

### funk-samples (376 WAVs)
- Organized by instrument: Bass, Guitar, Organ, Clavinet, Piano, Electric Piano, Monosynth
- BPMs: 90, 110

### hiphop-essentials (974 WAVs)
- Drum Hits — Kicks, Snares, Hats, Claps, Percussion, Oberheim DX
- Beats — Full drum loops
- Loops — Instrument loops

### idm-samples (500 WAVs)
- 5 kits organized by BPM: 100, 120, 140, 160, 165
- Each kit has Base Kit and Alternate folders

### lofi-samples (587 WAVs)
- Lo-Fi Drum Loops, Construction Kits at 70/90/100/120 BPM, SFX

### soul-funk-samples (393 WAVs)
- Construction kits at 100, 110, 120 BPM
- Per-instrument: Bass, Guitar, Organ, Beats

### synth-percussion (190 WAVs)
- Misc Synth Perc Loops, Vermona DRM1 MK3 Loops, WaveDrum Loops
