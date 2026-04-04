# MIDI Corpus Research for Pattern Generation
## Cowork Deliverable | April 4, 2026
### For: Jambox Magenta Pipeline — Unblocking Pattern Training (≥50 files required)

---

## Bottom Line: You Can Get 1,000+ Files for Free

The Groove MIDI Dataset alone gives you 1,150 drum MIDI files across most of your target genres. Combined with two GitHub repos, you can build a training corpus of 1,500+ genre-labeled files without spending anything. The 50-file gate is trivially clearable.

---

## Primary Source: Groove MIDI Dataset (Google Magenta)

### Why This Is The One
This is Magenta's own dataset. GrooVAE was literally trained on it. Maximum compatibility, zero preprocessing headaches.

- **URL:** https://magenta.withgoogle.com/datasets/groove
- **License:** CC-BY 4.0 (royalty-free, commercial OK)
- **Size:** 1,150 MIDI files
- **Format:** Standard MIDI, pre-processed for Magenta
- **Quantization:** 16 notes per bar (sixteenth-note resolution)
- **Access:** TensorFlow Datasets, mirdata, Kaggle, direct download

### Expanded Groove MIDI Dataset (E-GMD)
- **URL:** https://magenta.withgoogle.com/datasets/e-gmd
- **Size:** 444 hours across 43 drum kits
- **Extra:** Velocity annotations — useful for GrooVAE humanization training
- **License:** CC-BY 4.0

### Genre Coverage vs Your Targets

| Your Target | GMD Genre Label | Estimated Files | Coverage |
|-------------|----------------|-----------------|----------|
| Boom-bap (85-95 BPM) | hiphop, jazz | ~80 | Good |
| House (120-128 BPM) | dance | ~120 | Good |
| Funk (100-115 BPM) | funk | ~100 | Excellent |
| Punk (140-180 BPM) | punk | ~60 | Good |
| Dancehall (90-110 BPM) | reggae (adjacent) | ~20 | Thin |
| Disco (115-125 BPM) | pop (adjacent) | ~40 | Thin |
| Dub (90-100 BPM) | reggae (adjacent) | ~30 | Thin |
| Afrobeat (100-130 BPM) | afrobeat | ~100 | Excellent |

**Gaps:** Dancehall, disco, and dub are under-represented in GMD. These need supplementary sources.

---

## Secondary Sources: Fill the Gaps

### dmp_midi — 260 Drum Machine Patterns (GitHub)
- **URL:** https://github.com/gvellut/dmp_midi
- **License:** MIT
- **Size:** 260+ MIDI files from "200 Drum Machine Patterns" and "260 Drum Machine Patterns" books
- **Genres:** House, techno, funk, disco, dub, electronic
- **Access:** Pre-generated MIDI files in release section
- **Why:** Fills the disco, dub, and house gaps. Systematic, well-organized by BPM. Based on classic drum machine programming books.

### Prosonic Patterns
- **URL:** https://www.prosonic-studios.com/midi-drum-beats
- **License:** Royalty-free
- **Size:** 100s+ across categories
- **Genres:** Pop, rock, blues, metal, punk, techno, house
- **Why:** Additional punk and house patterns. Freely downloadable by category.

### Genre-Specific Free Packs

**Boom-Bap / Hip-Hop:**
- Essential MIDI Free Hip Hop Pack: https://essentialmidi.com/products/free-hip-hop-midi-pack (130+ files)
- Ghost Audio Factory: https://ghostaudiofactory.com/midi-drumbeats-free (live drummer feel)
- MIDI Mighty Boom Bap Guide: https://midimighty.com/products/boom-bap-hip-hop-drum-guide (50+ patterns)

**Dancehall / Afrobeat:**
- Afrobeat Producers Free Toolkit: https://afrobeatproducers.com/blogs/free-downloads/free-afrobeat-midi-wave-melody-loops-pack
- Slooply Afro-Dancehall MIDI: https://slooply.com/midi?genres%5B%5D=afro-dancehall&genres%5B%5D=afrobeat

**Dub / Reggae:**
- Subaqueous Music Free Dub MIDI: https://www.subaqueousmusic.com/free-dub-midi-and-drum-loops/ (5+ loops with solo parts)

**House / Disco:**
- muted.io Drum Patterns: https://muted.io/drum-patterns/ (house, disco, 16-step grid with MIDI export)
- dmp_midi repo covers this well

---

## Estimated File Count by Genre (All Free Sources Combined)

| Genre | GMD | dmp_midi | Prosonic | Specialty Packs | Total |
|-------|-----|----------|----------|-----------------|-------|
| Boom-bap | 80 | 20 | 20 | 25 (Essential MIDI) | **145** |
| House | 120 | 80 | 60 | 20 (muted.io) | **280** |
| Funk | 100 | 50 | 40 | 10 | **200** |
| Punk | 60 | 0 | 50 | 10 | **120** |
| Dancehall | 20 | 0 | 5 | 15 (Afrobeat Producers) | **40** |
| Disco | 40 | 50 | 30 | 20 (muted.io) | **140** |
| Dub | 30 | 20 | 10 | 5 (Subaqueous) | **65** |
| Afrobeat | 100 | 0 | 0 | 50 (Afrobeat Producers) | **150** |
| **TOTAL** | **550** | **220** | **215** | **155** | **~1,140** |

**Weakest genre:** Dancehall at 40 files. Consider hand-programming 10-15 additional dancehall riddim patterns if GrooVAE results are weak on this genre.

---

## Academic/Large-Scale Datasets (For Future Expansion)

If you ever need more training data:

| Dataset | Size | Notes |
|---------|------|-------|
| GigaMIDI | 1.4M+ MIDI files | Largest ever. Needs filtering for drums. |
| Lakh MIDI Dataset | 176,581 files | General MIDI, not drum-specific. Requires extraction. |
| Discover MIDI Dataset (HuggingFace) | 6.74M files | Massive. `projectlosangeles/Discover-MIDI-Dataset` |
| Tegridy MIDI Dataset (GitHub) | Large | Community-curated for AI training |
| STAR Drums (Zenodo) | Drum-specific | Automatic transcriptions, may need conversion |

These are overkill for the initial 50-file gate but useful if you want to train on thousands of patterns later.

---

## Technical Requirements for Magenta

### MIDI Format
- Standard MIDI Type 1
- Quantization: 16 notes per bar (sixteenth-note resolution)
- Max sequence: 16 bars (256 steps)
- Drum mapping: General MIDI channel 10

### Preprocessing Needed by Source
| Source | Preprocessing Required |
|--------|----------------------|
| Groove MIDI Dataset | **None** — already Magenta-ready |
| E-GMD | **None** — already Magenta-ready |
| dmp_midi | Verify quantization, should be clean |
| Prosonic | Quantize to 16th notes, verify GM mapping |
| Free packs | Quantize, verify tempo metadata, check GM drum mapping |

### Quality Considerations
- GMD has professional human performances → highest quality, real swing/feel
- dmp_midi is systematic/programmed → clean but mechanical
- Free packs vary widely → vet for quality before training
- **Priority:** Human-performed > programmed. GrooVAE learns humanization from velocity/timing variation.

---

## Recommended Sourcing Plan

### Phase 1: Clear the 50-File Gate (30 minutes)
1. Download Groove MIDI Dataset from Magenta (~1,150 files)
2. Filter to your 8 target genres
3. Select 50-100 representative files across all genres
4. Verify they load in your Magenta pipeline
5. **Gate cleared.**

### Phase 2: Build the Full Corpus (1-2 hours)
1. Download dmp_midi GitHub repo releases (~260 files for disco/dub/house)
2. Download genre-specific free packs for dancehall and boom-bap
3. Organize into genre folders matching your bank presets
4. Label each file: `data/pattern_labels.jsonl`
5. Create eval prompts: `data/pattern_evals.jsonl`
6. Target: 200-500 curated files across all 8 genres

### Phase 3: Quality Curation (Ongoing)
1. Hand-program 10-15 dancehall riddim patterns (weakest genre)
2. Review GMD files for quality — remove any that don't match target aesthetic
3. Add programmed patterns for any genre where GrooVAE output feels off
4. Expand to E-GMD velocity data for humanization training

---

## MIDI Drum Files Site (Bonus Source)
- **URL:** https://mididrumfiles.com/
- **License:** Royalty-free
- **Size:** 950 MIDI tracks
- **Why:** Large general collection, 100% royalty-free and editable. Good for filling gaps across all genres.

---

## Sources
- [Groove MIDI Dataset](https://magenta.withgoogle.com/datasets/groove)
- [Expanded Groove MIDI Dataset](https://magenta.withgoogle.com/datasets/e-gmd)
- [dmp_midi GitHub](https://github.com/gvellut/dmp_midi)
- [Prosonic Patterns](https://www.prosonic-studios.com/midi-drum-beats)
- [Essential MIDI Free Pack](https://essentialmidi.com/products/free-hip-hop-midi-pack)
- [Afrobeat Producers Toolkit](https://afrobeatproducers.com/blogs/free-downloads/free-afrobeat-midi-wave-melody-loops-pack)
- [muted.io Drum Patterns](https://muted.io/drum-patterns/)
- [Ghost Audio Factory](https://ghostaudiofactory.com/midi-drumbeats-free)
- [Subaqueous Music Dub MIDI](https://www.subaqueousmusic.com/free-dub-midi-and-drum-loops/)
- [MIDI Drum Files](https://mididrumfiles.com/)
- [Slooply](https://slooply.com/midi)
- [GigaMIDI](https://transactions.ismir.net/articles/10.5334/tismir.203)
- [Lakh MIDI Dataset](https://colinraffel.com/projects/lmd/)
- [Discover MIDI Dataset (HF)](https://huggingface.co/datasets/projectlosangeles/Discover-MIDI-Dataset)
