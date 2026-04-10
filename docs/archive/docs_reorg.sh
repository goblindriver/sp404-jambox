#!/bin/bash
# docs_reorg.sh — Reorganize docs/ per CONVENTIONS.md
# Run from repo root: bash docs/docs_reorg.sh
# DRY RUN by default — set DRY_RUN=0 to execute

DRY_RUN=${DRY_RUN:-1}
DOCS="docs"

run_cmd() {
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[DRY RUN] $1"
    else
        eval "$1"
    fi
}

# Convert filename to SCREAMING_SNAKE_CASE (preserving lowercase extension)
screaming_snake() {
    local base="$1"
    local name="${base%.*}"
    local ext="${base##*.}"
    name=$(echo "$name" | tr '-' '_' | tr '[:lower:]' '[:upper:]')
    echo "${name}.${ext}"
}

echo "=== Jambox docs/ reorganization ==="
echo "DRY_RUN=$DRY_RUN (set DRY_RUN=0 to execute)"
echo ""

# Create subdirectories
for dir in briefs research references sources handoffs hardware archive; do
    run_cmd "mkdir -p $DOCS/$dir"
done

# --- BRIEFS ---
echo "--- Moving briefs ---"
for f in "$DOCS"/CODE_BRIEF_*.md "$DOCS"/COWORK_BRIEF_*.md; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    upper=$(screaming_snake "$base")
    run_cmd "mv '$f' '$DOCS/briefs/$upper'"
done
# Special cases
[ -f "$DOCS/HANDOFF_CHAT_RL_RESPONSE.md" ] && run_cmd "mv '$DOCS/HANDOFF_CHAT_RL_RESPONSE.md' '$DOCS/briefs/CHAT_RESPONSE_RL_PIPELINE.md'"
[ -f "$DOCS/RL_TRAINING_PIPELINE_PITCH.md" ] && run_cmd "mv '$DOCS/RL_TRAINING_PIPELINE_PITCH.md' '$DOCS/briefs/CHAT_RESPONSE_RL_PIPELINE_PITCH.md'"

# --- RESEARCH ---
echo "--- Moving research ---"
move_research() {
    local old="$1" new="$2"
    [ -f "$DOCS/$old" ] && run_cmd "mv '$DOCS/$old' '$DOCS/research/$new'"
}
move_research "CLAP_Model_Comparison_Research.md" "CLAP_MODEL_COMPARISON.md"
move_research "DPO_Training_Frameworks_Research.md" "DPO_TRAINING_FRAMEWORKS.md"
move_research "Film_SFX_Databases_Research.md" "FILM_SFX_DATABASES.md"
move_research "MIDI_Corpus_Research.md" "MIDI_CORPUS.md"
move_research "Sample_Pack_Curation_Survey.md" "SAMPLE_PACK_CURATION_SURVEY.md"
move_research "Playlist_Mining_Extraction_Analysis.md" "PLAYLIST_MINING_ANALYSIS.md"
move_research "Unified_Tag_System_Research.md" "UNIFIED_TAG_SYSTEM.md"
move_research "SP404_ECOSYSTEM_RESEARCH.md" "SP404_ECOSYSTEM.md"

# --- REFERENCES ---
echo "--- Moving references ---"
move_ref() {
    local old="$1" new="$2"
    [ -f "$DOCS/$old" ] && run_cmd "mv '$DOCS/$old' '$DOCS/references/$new'"
}
move_ref "Big_Beat_Blowout_Sound_Design_Reference.md" "BIG_BEAT_BLOWOUT_REFERENCE.md"
move_ref "Synth-Pop_Dreams_Reference_Document.md" "SYNTH_POP_DREAMS_REFERENCE.md"
move_ref "brat_mode_sound_design_reference.md" "BRAT_MODE_REFERENCE.md"
move_ref "playlist_tracklist.txt" "PLAYLIST_TRACKLIST.txt"

# --- SOURCES ---
echo "--- Moving sources ---"
# Handle SOURCES_*.txt prefix pattern
for f in "$DOCS"/SOURCES_*.txt; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    # Strip SOURCES_ prefix, normalize rest, append _SOURCE
    topic=$(echo "${base#SOURCES_}" | sed 's/\.txt$//' | tr '-' '_' | tr '[:lower:]' '[:upper:]')
    run_cmd "mv '$f' '$DOCS/sources/${topic}_SOURCE.txt'"
done
# Handle *_SOURCE.txt and *_SOURCES.txt suffix patterns
for f in "$DOCS"/*_SOURCE.txt "$DOCS"/*_SOURCES.txt; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    upper=$(screaming_snake "$base")
    # Normalize _SOURCES to _SOURCE
    upper=$(echo "$upper" | sed 's/_SOURCES\.txt$/_SOURCE.txt/')
    run_cmd "mv '$f' '$DOCS/sources/$upper'"
done

# --- HARDWARE ---
echo "--- Moving hardware ---"
for f in "$DOCS"/SP-404A_*.pdf "$DOCS"/SP404A_*.pdf; do
    [ -f "$f" ] || continue
    run_cmd "mv '$f' '$DOCS/hardware/'"
done
[ -f "$DOCS/SP404A_Field_Manual.docx" ] && run_cmd "mv '$DOCS/SP404A_Field_Manual.docx' '$DOCS/hardware/SP404A_FIELD_MANUAL.docx'"

# --- HANDOFFS ---
echo "--- Moving handoffs ---"
[ -f "$DOCS/HANDOFF_SESSION3_FINAL.md" ] && run_cmd "mv '$DOCS/HANDOFF_SESSION3_FINAL.md' '$DOCS/handoffs/'"
[ -f "$DOCS/BUG_HUNT_SESSION3.md" ] && run_cmd "mv '$DOCS/BUG_HUNT_SESSION3.md' '$DOCS/handoffs/'"
[ -f "$DOCS/JAMBOX_SESSION_HANDOFF.md" ] && run_cmd "mv '$DOCS/JAMBOX_SESSION_HANDOFF.md' '$DOCS/handoffs/'"

# --- ARCHIVE (superseded docs) ---
echo "--- Archiving superseded docs ---"
[ -f "$DOCS/HANDOFF.md" ] && run_cmd "mv '$DOCS/HANDOFF.md' '$DOCS/archive/'"
[ -f "$DOCS/HANDOFF_SESSION3.md" ] && run_cmd "mv '$DOCS/HANDOFF_SESSION3.md' '$DOCS/archive/'"
[ -f "$DOCS/CLAUDE_CODE_HANDOFF.md" ] && run_cmd "mv '$DOCS/CLAUDE_CODE_HANDOFF.md' '$DOCS/archive/'"
[ -f "$DOCS/SP404A_Field_Manual_FINAL.docx" ] && run_cmd "mv '$DOCS/SP404A_Field_Manual_FINAL.docx' '$DOCS/archive/'"
[ -f "$DOCS/SP404A_Field_Manual_reviewed.docx" ] && run_cmd "mv '$DOCS/SP404A_Field_Manual_reviewed.docx' '$DOCS/archive/'"

echo ""
echo "=== Done ==="
echo "Remaining at docs/ root (should be system docs only):"
if [ "$DRY_RUN" -eq 0 ]; then
    ls -1 "$DOCS"/*.md "$DOCS"/*.txt "$DOCS"/*.json 2>/dev/null
else
    echo "[DRY RUN — run with DRY_RUN=0 to see results]"
fi
