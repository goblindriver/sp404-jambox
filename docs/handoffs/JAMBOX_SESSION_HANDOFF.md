# Jambox Session Handoff
## Session Date: April 3-4, 2026 (continued from crashed session)

---

## Deliverables Produced This Session

### 1. SP-404A Field Manual (DOCX)
**File:** `SP404A_Field_Manual_FINAL.docx` (in Downloads)
**Build script:** The Node.js source that generates the manual is `build_manual_v4.js`. Jason reviewed and corrected Chapter 7 pipeline details, cover styling (Jambox orange #FF8C00), and renamed "Tiger Dust Default Set" to "Tiger Dust Block Party Set". SD card path corrected to `ROLAND/SP-404SX/SMPL/`.

**Contents (8 chapters + 5 magazine story spreads):**
- Ch 1: The Machine (hardware layout, core concepts, 404A specs)
- Story: "How a Sampler Built a Genre" (SP-404 origin, Madvillainy, Low End Theory)
- Ch 2: Sampling Fundamentals (external recording, SD/USB loading, resampling loop, editing by ear)
- Story: "Dibiase and the Art of Chain Resampling" (SP-303/404 bounce technique)
- Ch 3: The 29 Effects (complete reference table with CTRL knob assignments, Essential Five, effect stacking via resample, per-bank effect chains)
- Story: "Spacebase Was the Place" (Ras G, 404 Day origin)
- Ch 4: Patterns & Performance (real-time recording, quantize, muting, bank switching, resample-as-looper)
- Story: "From Shibuya to the World" (Nujabes, Tokyo beat scene, global SP-404 community)
- Ch 5: Tiger Dust Block Party Set (full 10-bank layout with 3x4 pad grids for Banks A-H, I-J empty for scratch)
- Story: "Knxwledge and the Infinity of Vinyl" (prolific workflow, Meek Mill remixes)
- Ch 6: Cheat Codes (button combos, sample prep rules, performance techniques, SD card management)
- Ch 7: Jambox Pipeline (corrected by Jason: librosa analysis, Chromaprint dedup, Qwen3 8B LLM with type_code/vibe/texture/genre output, _tags.json, Flask Web UI at localhost:5404)
- Ch 8: Resources (documentation, communities, sample packs, producers to study)

**Open items on the manual:**
- Sub pad description updated to "retrigger" behavior (verified via manuals) but Jason flagged for hardware verification on his specific unit
- Full dark background treatment on cover page not fully achievable in docx-js (text colors darkened but no true page background fill)

### 2. Open-Source Tools Research (MD)
**File:** Was at `mnt/outputs/Jambox_Open_Source_Tools_Research.md` (may need regeneration from context)
**Key findings:** Essentia, audio-separator, CLAP/LAION-CLAP (Tier 1); OneTagger, Mel-Band RoFormer, madmom, librosa (Tier 2); Beets, LabelBuddy, aubio, StemRoller (Tier 3). Full pipeline architecture diagram mapping tools to ingest stages. Jason's review shifted the actual pipeline to use librosa over Essentia and Chromaprint over CLAP for the production system.

### 3. SP-404 Ecosystem Research (MD)
**File:** Was at `mnt/outputs/SP404_Ecosystem_Research.md` (may need regeneration)
**Key findings:** Premade bank sources (LofiAndy, CremaSound, SPVIDZ, Roland 404 Day packs), producer techniques (resample loop, effect stacking, resampling as looper), NearTao's unofficial guide as best training doc for LLM, pad mapping convention (1-4 rhythm, 5-8 melodic, 9-12 texture), firmware history, community resources.

### 4. Riot Mode Sources (TXT)
**File:** Was at `mnt/outputs/RIOT_MODE_SOURCES.txt` (629 lines, from earlier session)
**Content:** 50+ free sources across drums, guitar, brass, bass, vocals, noise for the Riot Mode bank. Top 10 priority downloads identified.

### 5. Minneapolis Machine Sources (TXT)
**File:** Was at `mnt/outputs/MINNEAPOLIS_MACHINE_SOURCES.txt` (699 lines, from earlier session)
**Content:** 40+ sources across boom-bap drums, experimental drums, noise/glitch, bass, vocals, ambient. Core 5 + expansion sources identified.

### 6. LLM Post-Training Research (MD)
**File:** Was at `mnt/outputs/Jambox_LLM_Post_Training_Research.md` (from earlier session)
**Content:** QLoRA via Unsloth, Qwen3 8B base model recommendation, RAG with ChromaDB, training data strategy (500-2000 examples from existing library), 4-week timeline, sample Ollama Modelfile.

---

## Jason's Pipeline Corrections (Important for Future Sessions)

Jason reviewed the Jambox pipeline chapter and made these corrections that reflect the ACTUAL system being built:

| What I Had | What Jason Corrected To |
|---|---|
| Essentia for analysis | **librosa** for BPM, key, loudness, MFCCs, spectral centroid, rolloff, onsets |
| CLAP for bank scoring | **Chromaprint (fpcalc)** for audio fingerprinting and deduplication |
| audio-separator | **Demucs** directly |
| OneTagger for metadata | **_tags.json** sidecar files, quality 1-2 quarantined |
| madmom for beats | **Ollama + Qwen3 8B** for smart tagging |
| ChromaDB vector store | **Flask Web UI** at localhost:5404 for pad grid, vibe prompts, preset browser |
| LLM outputs bank assignment | LLM outputs **type_code, vibe, texture, genre, energy, quality score (1-5), sonic description** |
| SD path ROLAND/SP-404A/SMPL/ | **ROLAND/SP-404SX/SMPL/** (404A uses SX folder structure) |

---

## Pending / Unfinished Work

### Downloads (Staged but not executed)
From the previous session, 14 browser tabs were staged and triaged for sample downloads:
- **8 direct-download** ready
- **5 email-gated** (user needs to complete checkout)
- **1 account-required**
- Browser tabs from that session are gone; sources are documented in the source files above

### Stem Splitting (Assignment 5)
Blocked in sandbox (pip proxy). Needs to run locally on Jason's machine using Demucs. Top 20 stem split candidates were identified from playlist mining.

### Brat Mode Downloads
Original 9 tabs from Session 2 are gone. Sources documented in BRAT_MODE_SOURCES.txt (lost from outputs).

### Free Essentials Downloads
Legowelt packs, MusicRadar archives, 99Sounds packs, Ghosthack, Cymatics vault.

---

## Key Context for Next Session

- Jason has an **SP-404A** (not MK2) - 12 pads, 29 effects, no screen, no firmware updates, RCA outputs, MIDI IN only
- The SP-404A uses the **SP-404SX folder structure** on SD cards
- The flagship bank is called **Tiger Dust Block Party**
- Jambox accent color is **#FF8C00** (orange)
- The pipeline uses **librosa + Chromaprint + Qwen3 8B + Flask**, not Essentia + CLAP + OneTagger
- LLM outputs: **type_code, vibe, texture, genre, energy, quality (1-5), sonic description**
- Low quality files (score 1-2) are **quarantined**, not auto-assigned
- Tags go to **_tags.json** sidecars
- Flask Web UI runs at **localhost:5404**
- Jason's YouTube library has **57 playlists**; Tiger Dust (123 tracks) and tiger tingtingtingting (54 tracks) were fully extracted
- The project has **20,925 files** in the existing sample library
- **NearTao's unofficial guide** is the recommended primary training document for the LLM
- Jason prefers direct action over hedging - if a tool goes down, ask him to reconnect rather than declaring it lost
