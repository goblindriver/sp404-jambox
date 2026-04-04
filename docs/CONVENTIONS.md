# Docs Conventions — Jambox

> Rules for how all agents (Chat, Code, Cowork) name, organize, and manage docs.
> This file lives at `docs/CONVENTIONS.md`. All agents must follow it.

---

## Folder Structure

```
docs/
├── CONVENTIONS.md          # This file
├── TODO.md                 # Shared task tracker (updated by Chat)
├── ARCHITECTURE.md         # System architecture (updated by Code)
├── TAGGING_SPEC.md         # Tag schema and rules
├── SMART_RETAG_SPEC.md     # Smart retag pipeline spec
├── OPTIMIZATION_PLAN.md    # Performance optimization plan
├── WEBAPP_REQUIREMENTS.md  # Web UI requirements
├── CLAUDE_CODE_GUIDE.md    # Code agent operating guide
├── SAMPLE_SOURCES.md       # Master sample source list
│
├── briefs/                 # Task assignments to agents (ephemeral)
│   ├── CODE_BRIEF_session4.md
│   ├── COWORK_BRIEF_session4.md
│   └── ...
│
├── research/               # Cowork research deliverables
│   ├── CLAP_MODEL_COMPARISON.md
│   ├── DPO_TRAINING_FRAMEWORKS.md
│   ├── UNIFIED_TAG_SYSTEM.md
│   └── ...
│
├── references/             # Sound design refs, preset documentation
│   ├── BIG_BEAT_BLOWOUT_REFERENCE.md
│   ├── SYNTH_POP_DREAMS_REFERENCE.md
│   ├── BRAT_MODE_REFERENCE.md
│   └── ...
│
├── sources/                # Raw link/source lists for sample packs
│   ├── musicradar_rave_SOURCE.txt
│   ├── legowelt_sample_packs_SOURCE.txt
│   └── ...
│
├── handoffs/               # Session transition docs
│   ├── HANDOFF_SESSION3_FINAL.md
│   ├── HANDOFF_SESSION4.md
│   └── ...
│
├── hardware/               # SP-404A PDFs, manuals, field manual
│   ├── SP404A_Reference.pdf
│   ├── SP404A_Field_Manual.docx
│   └── ...
│
└── archive/                # Superseded or stale docs (don't delete, move here)
    ├── HANDOFF_SESSION3.md
    ├── HANDOFF.md
    └── ...
```

### What stays at `docs/` root
Only **living system docs** that are actively referenced by agents and rarely superseded:
- `TODO.md`, `ARCHITECTURE.md`, `TAGGING_SPEC.md`, `SMART_RETAG_SPEC.md`
- `CONVENTIONS.md` (this file)
- `CLAUDE_CODE_GUIDE.md`, `SAMPLE_SOURCES.md`, `WEBAPP_REQUIREMENTS.md`, `OPTIMIZATION_PLAN.md`

Everything else goes in a subdirectory.

---

## Naming Conventions

### Case Rule
**`SCREAMING_SNAKE_CASE`** for all doc filenames. No exceptions.

- ✅ `CODE_BRIEF_SESSION4.md`
- ✅ `DPO_TRAINING_FRAMEWORKS.md`
- ✅ `BIG_BEAT_BLOWOUT_REFERENCE.md`
- ❌ `Big_Beat_Blowout_Sound_Design_Reference.md`
- ❌ `brat_mode_sound_design_reference.md`
- ❌ `808-linndrum-knobcon_SOURCE.txt`

### Prefix Rules

| Doc Type | Prefix | Folder | Example |
|----------|--------|--------|---------|
| Code agent task | `CODE_BRIEF_` | `briefs/` | `CODE_BRIEF_SESSION4.md` |
| Cowork agent task | `COWORK_BRIEF_` | `briefs/` | `COWORK_BRIEF_SESSION4.md` |
| Chat response/pitch | `CHAT_RESPONSE_` | `briefs/` | `CHAT_RESPONSE_RL_PIPELINE.md` |
| Research deliverable | *(topic name)* | `research/` | `CLAP_MODEL_COMPARISON.md` |
| Sound design reference | *(bank name)*`_REFERENCE` | `references/` | `RIOT_MODE_REFERENCE.md` |
| Source list | *(source)*`_SOURCE` | `sources/` | `MUSICRADAR_RAVE_SOURCE.txt` |
| Session handoff | `HANDOFF_SESSION`*{N}* | `handoffs/` | `HANDOFF_SESSION4.md` |
| Spec / architecture | *(feature)*`_SPEC` | root | `SMART_RETAG_SPEC.md` |

### Session Numbering
Briefs and handoffs include a session number: `CODE_BRIEF_SESSION4.md`, not `CODE_BRIEF_session4.md`.

For topic-specific briefs within a session, append the topic: `CODE_BRIEF_SESSION4_SQLITE.md`.

### No "_FINAL" or "_reviewed" Suffixes
Don't create `_FINAL`, `_reviewed`, `_v2` variants. If a doc is superseded:
1. Move the old version to `archive/`
2. The new version keeps the original name

---

## Lifecycle Rules

### Creating a Doc
1. Follow naming conventions above
2. Place in the correct subdirectory
3. Include a header block:

```markdown
# Title
**Date:** YYYY-MM-DD
**From:** Chat | Code | Cowork
**To:** Chat | Code | Cowork | All
**Status:** Active | Superseded | Archived
```

### Superseding a Doc
1. Move the old doc to `archive/`
2. New doc takes the same name (or an updated session number)
3. Never have two versions of the same doc in the same folder

### Archiving
- Docs in `archive/` are read-only reference — they don't drive any active work
- Handoffs older than 2 sessions go to archive
- Briefs go to archive once all tasks are complete
- Research stays in `research/` permanently (it's reference material)

---

## Watcher Routing Rules

When the file watcher in `ingest_downloads.py` is expanded to handle docs, it should use these rules:

| Filename Pattern | Routes To |
|-----------------|-----------|
| `CODE_BRIEF_*` | `docs/briefs/` |
| `COWORK_BRIEF_*` | `docs/briefs/` |
| `CHAT_RESPONSE_*` | `docs/briefs/` |
| `HANDOFF_*` | `docs/handoffs/` |
| `*_REFERENCE.md` | `docs/references/` |
| `*_SOURCE.txt` | `docs/sources/` |
| `*_SPEC.md` | `docs/` (root) |
| `*_RESEARCH.md` or `*_Research.md` | `docs/research/` |
| `CLAUDE.md` | repo root |
| `*.yaml` (preset schema) | `presets/` |
| `*.yaml` (set schema) | `sets/` |

The watcher should normalize filenames to `SCREAMING_SNAKE_CASE` on ingest.

---

## Current Cleanup Plan

These files need to be reorganized from the current flat `docs/` directory:

### Move to `briefs/`
- `CODE_BRIEF_ambient_llm_integration.md` → rename `CODE_BRIEF_AMBIENT_LLM.md`
- `CODE_BRIEF_bug_fixes.md` → rename `CODE_BRIEF_BUG_FIXES.md`
- `CODE_BRIEF_doc_ingest.md` → rename `CODE_BRIEF_DOC_INGEST.md`
- `CODE_BRIEF_pattern_generation_revised.md` → rename `CODE_BRIEF_PATTERN_GENERATION.md`
- `CODE_BRIEF_session3_wrap.md` → rename `CODE_BRIEF_SESSION3_WRAP.md`
- `CODE_BRIEF_session4.md` → rename `CODE_BRIEF_SESSION4.md`
- `CODE_BRIEF_taste_engine.md` → rename `CODE_BRIEF_TASTE_ENGINE.md`
- `CODE_BRIEF_ui_streamlining.md` → rename `CODE_BRIEF_UI_STREAMLINING.md`
- `COWORK_BRIEF_download_closeout.md` → rename `COWORK_BRIEF_DOWNLOAD_CLOSEOUT.md`
- `COWORK_BRIEF_minneapolis_machine_sources.md` → rename `COWORK_BRIEF_MINNEAPOLIS_MACHINE.md`
- `COWORK_BRIEF_riot_mode_sources.md` → rename `COWORK_BRIEF_RIOT_MODE.md`
- `COWORK_BRIEF_session4.md` → rename `COWORK_BRIEF_SESSION4.md`
- `HANDOFF_CHAT_RL_RESPONSE.md` → rename `CHAT_RESPONSE_RL_PIPELINE.md`
- `RL_TRAINING_PIPELINE_PITCH.md` → rename `CHAT_RESPONSE_RL_PIPELINE_PITCH.md`

### Move to `research/`
- `CLAP_Model_Comparison_Research.md` → rename `CLAP_MODEL_COMPARISON.md`
- `DPO_Training_Frameworks_Research.md` → rename `DPO_TRAINING_FRAMEWORKS.md`
- `Film_SFX_Databases_Research.md` → rename `FILM_SFX_DATABASES.md`
- `MIDI_Corpus_Research.md` → rename `MIDI_CORPUS.md`
- `Sample_Pack_Curation_Survey.md` → rename `SAMPLE_PACK_CURATION_SURVEY.md`
- `Playlist_Mining_Extraction_Analysis.md` → rename `PLAYLIST_MINING_ANALYSIS.md`

### Move to `references/`
- `Big_Beat_Blowout_Sound_Design_Reference.md` → rename `BIG_BEAT_BLOWOUT_REFERENCE.md`
- `Synth-Pop_Dreams_Reference_Document.md` → rename `SYNTH_POP_DREAMS_REFERENCE.md`
- `brat_mode_sound_design_reference.md` → rename `BRAT_MODE_REFERENCE.md`
- `playlist_tracklist.txt` → rename `PLAYLIST_TRACKLIST.txt`

### Move to `sources/`
All `*_SOURCE.txt` and `SOURCES_*.txt` files, renamed to `SCREAMING_SNAKE`:
- `808-linndrum-knobcon_SOURCE.txt` → `808_LINNDRUM_KNOBCON_SOURCE.txt`
- `BRAT_MODE_SOURCES.txt` → `BRAT_MODE_SOURCE.txt`
- `NASA-audio-highlights_SOURCE.txt` → `NASA_AUDIO_HIGHLIGHTS_SOURCE.txt`
- `SOURCES_big_beat_blowout.txt` → `BIG_BEAT_BLOWOUT_SOURCE.txt`
- `SOURCES_synth_pop_dreams.txt` → `SYNTH_POP_DREAMS_SOURCE.txt`
- All `musicradar-*` and `sp404-*` and `legowelt-*` and `voice-*` SOURCE files → normalize to `SCREAMING_SNAKE`

### Move to `hardware/`
- `SP-404A_Reference_eng01_W.pdf`
- `SP-404A_eng01_W.pdf`
- `SP-404A_l_loopmaeters_eng01_W.pdf`
- `SP-404A_l_supplement_eng01_W.pdf`
- `SP404A_Field_Manual.docx` → keep as canonical (move `_FINAL` and `_reviewed` to archive)

### Move to `handoffs/`
- `HANDOFF_SESSION3_FINAL.md` (canonical for session 3)
- `HANDOFF_SESSION3.md` → archive (superseded by _FINAL)
- `HANDOFF.md` → archive (superseded)
- `JAMBOX_SESSION_HANDOFF.md` → archive (superseded)
- `CLAUDE_CODE_HANDOFF.md` → archive (superseded)
- `BUG_HUNT_SESSION3.md` → keep as `BUG_HUNT_SESSION3.md` in handoffs

### Move to `archive/`
- `SP404A_Field_Manual_FINAL.docx`
- `SP404A_Field_Manual_reviewed.docx`
- All superseded handoffs (see above)

### Stay at `docs/` root
- `ARCHITECTURE.md`
- `CLAUDE_CODE_GUIDE.md`
- `CONVENTIONS.md` (this file)
- `OPTIMIZATION_PLAN.md`
- `PAD_MAP.txt`
- `SAMPLE_SOURCES.md`
- `SMART_RETAG_SPEC.md`
- `TAGGING_SPEC.md`
- `TODO.md`
- `WEBAPP_REQUIREMENTS.md`
- `sample_index.json`

---

*Created by Chat — April 4, 2026 (Session 4)*
