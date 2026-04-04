# Download Assignments — Close-Out Brief
## Cowork Deliverable | April 4, 2026
### Status: Retiring the scraping workflow. Here's what's worth buying.

---

## Context

The original download assignments (Sessions 2-3) staged 14+ browser tabs across four genre packs, with detailed source lists totaling ~1,300 lines. Those tabs and source files are gone. The library is now 30K+ files with smart retag running. The ingest pipeline auto-handles everything on arrival.

Rebuilding those scraping lists isn't the right move. The free tier of most sample sites has been picked over, and the pipeline is sophisticated enough now that **a few quality purchases beat dozens of free packs.** Here's where each assignment stands and what's worth spending on.

---

## 1. Riot Mode (punk/riot grrrl/ska-punk, 160 BPM, key of E)

### What the library probably already has
- Generic punk drum loops from free packs (MusicRadar, Cymatics)
- Distorted guitar one-shots from various free sources
- Some aggressive vocal chops

### What it's missing (the hard stuff to find free)
- **Authentic riot grrrl energy** — Bikini Kill / Sleater-Kinney style raw guitar tones
- **Ska upstrokes** — clean, snappy ska-punk guitar chops
- **Brass stabs** — ska horn section hits (trumpet/trombone/sax stabs)
- **Fast punk drums** — 160+ BPM blast beats and d-beat patterns with real feel
- **Shouted vocals** — call-and-response chants, protest energy

### Buy recommendation
- **Splice** (if you have a subscription): Search "punk drums," "ska guitar," "brass stabs" — curate 30-40 one-shots and loops. This is the most efficient path for genre-specific content.
- **Loopmasters Punk Rock pack** (~$25-35): Usually includes full drum loops, guitar riffs, bass, and sometimes brass at the right tempos.
- **Your own records**: If you have any Bikini Kill, Operation Ivy, Rancid, Choking Victim, or Leftover Crack on vinyl or in Plex — stem split them via the My Music browser. The Plex metadata will carry through. This is probably the highest quality source for authentic energy.

### Verdict: **Buy one good pack + stem split from Plex.** Don't scrape.

---

## 2. Minneapolis Machine (P.O.S/Doomtree experimental hip-hop, 90 BPM, Db)

### What the library probably already has
- Standard boom-bap drums from free hip-hop packs
- Some lo-fi textures and ambient pads
- Basic bass one-shots

### What it's missing
- **Experimental/glitchy drums** — Doomtree-style chopped, processed, unpredictable percussion
- **Industrial textures** — metal scrapes, factory noise, processed field recordings
- **Minneapolis-specific sound** — P.O.S / Lazerbeak / Paper Tiger production aesthetic is very specific: abrasive but musical, hip-hop skeleton with noise-rock flesh
- **Vocal processing chains** — heavily effected vocal chops, not clean

### Buy recommendation
- **Splice**: Search "experimental drums," "glitch percussion," "industrial texture," "noise" — this is the one genre where Splice's variety really shines
- **Your own Doomtree records in Plex**: Stem split P.O.S, Dessa, Sims, Cecil Otter tracks. The stems ARE the sample pack for this bank. Nobody sells "Minneapolis experimental hip-hop" sample packs.
- **99Sounds Industrial** (free): https://99sounds.org/ — has several free industrial/noise texture packs in 24-bit WAV

### Verdict: **Stem split your own Doomtree collection + Splice for experimental drums.** This genre is too specific for generic packs.

---

## 3. Brat Mode (Charli XCX buzzy detuned synths, 128 BPM, Gm)

### What the library probably already has
- Basic house drums and four-on-the-floor loops
- Some synth pads and leads

### What it's missing
- **Detuned/buzzy synths** — the specific Brat aesthetic: slightly out of tune, aggressive, blown-out synths
- **PC Music / A.G. Cook-adjacent textures** — hyper-processed, digital, bubbly
- **Vocal chops** — pop vocal processing, pitched and chopped
- **808 bass** — heavily distorted, sub-heavy

### Buy recommendation
- **Splice**: Search "hyperpop," "PC Music," "detuned synth," "Charli XCX type" — this genre has excellent Splice coverage since it's current and popular
- **KSHMR Sounds or Cymatics Hyperpop pack** (~$10-25): Several affordable packs exist specifically for this sound
- **Stem split from Plex**: If you have Charli XCX, SOPHIE, 100 gecs, A.G. Cook in your library

### Verdict: **Splice or one hyperpop pack.** This is well-served by commercial sample sites.

---

## 4. Free Essentials (Legowelt, MusicRadar, 99Sounds, Ghosthack, Cymatics)

### Status
These were the "foundational" free packs — stuff that every sample library should have. Given that your library is already 30K+ files, you likely already have most of this from earlier ingest runs.

### What's still worth grabbing (if you haven't already)
- **Legowelt free packs** (https://legowelt.org/software/): Unique analog synth samples from his personal collection. Nothing else sounds like these. Check if already ingested.
- **Cymatics Vault** (https://cymatics.fm/pages/free-download-vault): Large free collection, good general coverage. May already be in library.
- **99Sounds full catalog** (https://99sounds.org/): 24-bit WAV, high quality. Already referenced in Film SFX brief. Worth a full sweep if not done.

### Verdict: **Check if Legowelt packs are already in the library.** If not, grab them — they're unique. The rest is probably redundant at 30K files.

---

## 5. Stem Splitting (Top 20 candidates)

### Status
Was blocked on sandbox pip proxy in previous session. Demucs is now integrated into the ingest pipeline and the My Music browser handles stem splitting with full Plex metadata carryover.

### Verdict: **No longer blocked.** Use the My Music browser in the web UI to stem split directly from your Plex library. Prioritize:
1. Doomtree / P.O.S tracks (for Minneapolis Machine)
2. Charli XCX / SOPHIE (for Brat Mode)
3. Bikini Kill / Operation Ivy (for Riot Mode)
4. Any funk/soul/disco tracks that are in your Plex but not yet split

---

## 6. NearTao Guide + SP-404 Manual

### Status
The SP-404A Field Manual is done (you wrote it in the DOCX). NearTao's guide is a free PDF available online — it should be downloaded and added to the RAG corpus and LLM training data.

### Action
- Download NearTao's Unofficial SP-404 Guide (PDF, free)
- Drop in ~/Downloads — pipeline will ingest
- Flag for Code: this should feed the RAG corpus for vibe parsing, not just live in docs/

---

## Summary: What to Actually Spend Money On

| Priority | What | Est. Cost | Why |
|----------|------|-----------|-----|
| 1 | Splice subscription (1 month) | $10-15 | Covers Riot Mode, Brat Mode, and Minneapolis Machine with targeted searches |
| 2 | Sounds of Shaolin Vol 1 | $5-20 | Kung fu foley for cinema bank (from Film SFX research) |
| 3 | Loopmasters Punk Rock pack | $25-35 | Only if Splice doesn't cover punk drums well enough |
| 4 | Legowelt free packs | Free | Unique analog synths, check if already ingested |

**Total recommended spend: $15-70**

Everything else — stem split from your own Plex library. You have 33,400 tracks across 1,005 artists. That's the best sample source you own.

---

## Closing the Books

After this brief, the download assignments from Sessions 2-3 are retired. The scraping workflow is done. Future sample sourcing should be:

1. **Stem split from Plex** (highest quality, your taste built in)
2. **Targeted Splice searches** (when you need something specific)
3. **Occasional premium purchase** (when a pack is uniquely good)
4. **Pipeline handles everything** (ingest → tag → fingerprint → dedup → done)

The machine is built. Feed it good ingredients.
