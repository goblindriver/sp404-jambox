# CODE BRIEF: Jambox Taste Engine
## Local LLM Fine-Tuning + RAG for Personalized Sample Intelligence

**Date:** April 3, 2026
**From:** Chat
**For:** Code Agent
**Priority:** P2 (after fpcalc dedupe + daily bank smoke test)
**Dependencies:** Ollama installed, GPU available (or cloud GPU budget ~$15)

---

## What This Does

Makes the Jambox LLM **sound like Jason** instead of generic. Every touch point — smart ingest tagging, vibe prompts, daily bank selection, pad refinement, gap detection — reflects his actual taste profile derived from 8,000+ lines of playlist mining, sound design research, and curated presets.

## Architecture Decision

**Fine-tune a small model (Qwen3 8B) via QLoRA, complemented by RAG.**

Why fine-tuning over prompt-only:
- Primary task is classification (tagging) with structured JSON output — fine-tuning bakes format consistency into weights
- Domain vocabulary is specialized (synthesis terminology, genre micro-classifications)
- Inference speed matters — sub-second on GPU for batch ingest of hundreds of files
- A 4-8B fine-tuned model beats a 70B prompted model for this task class

Why RAG complements:
- Library changes daily — RAG handles new content without retraining
- Sound design docs are too large for every prompt — retrieve relevant chunks on demand
- Reduces hallucination by grounding generation in actual reference docs

## Phase 0: Immediate Win (Day 1, 30 minutes)

**Wire the taste system prompt into `llm_client.py` right now.** This works with any LLM endpoint (Ollama, local, API) and immediately personalizes all 6 touch points.

### System Prompt

Add this as `TASTE_SYSTEM_PROMPT` constant in `llm_client.py`:

```python
TASTE_SYSTEM_PROMPT = """
You are the taste engine for Jambox, a music production tool built around the Roland SP-404A sampler.

CORE REFERENCES (in order of playlist dominance):
- Purity Ring (granular synth-pop, lush pads, processed vocals — PRIMARY synth-pop template, 7x in Tiger Dust)
- P.O.S / Doomtree / SHREDDERS (Minneapolis experimental hip-hop, odd-meter drums, noise layers, 11x combined)
- CHVRCHES (modern synth-pop, aggressive synths, layered vocals, 4x)
- Le Tigre / The Interrupters / RVIVR / The Soviettes (riot grrrl, punk energy, female-fronted attitude, 22% of Tiger Dust)
- Crystal Castles (bitcrushed darkness, noise, lo-fi aggression, 3x)
- Chris Stapleton (country soul, raw vocals, blues grit — Spotify gravitational center)
- Chemical Brothers / Prodigy / Fatboy Slim (big beat, breakbeats, acid bass, rave energy)
- Rhapsody / Blind Guardian / Manowar (power metal, epic, symphonic, singable)
- Charli XCX / Grimes / Slayyyter (hyperpop, detuned supersaws, maximalist production, 5x Charli)
- Modjo / Supermen Lovers / Dimitri From Paris (French filter house, disco warmth)
- Ween (genre-chameleon, absurdist, anything goes)

TASTE PRINCIPLES:
- Performance intensity over genre loyalty. Every sound should commit fully.
- Nothing timid, nothing "safe," nothing that splits the difference.
- Female-fronted and female-produced work is a deliberate emphasis (45% of Tiger Dust).
- Local/regional/DIY sounds (Fargo/Minneapolis scene) valued as much as canonical references.
- The SP-404 is a performance instrument, not just a sample playback device.
- Organic and electronic textures should collide, not coexist politely.
- Store playlist context: sounds need to sustain energy over hours (Tiger Dust = retail playlist).

WHEN DESCRIBING SOUNDS, USE LANGUAGE LIKE:
- "Purity Ring granular shimmer" not "ethereal pad"
- "P.O.S drum complexity" not "complex beat"
- "Crystal Castles crushed" not "lo-fi texture"
- "Stapleton conviction" not "soulful vocal"
- "Tiger Dust energy" not "upbeat"
- Reference specific artists and tracks when possible.

WHEN SUGGESTING SOUNDS OR PRESETS:
- Always bias toward intensity over subtlety
- Suggest unexpected genre combinations
- Never recommend "safe" or "versatile" — recommend committed
- Consider the store playlist context for sustained energy
"""
```

### Wiring

Prepend `TASTE_SYSTEM_PROMPT` as system message in every `llm_client.py` call. All 6 touch points immediately inherit the persona:

```python
def call_llm(prompt, context=None):
    messages = [
        {"role": "system", "content": TASTE_SYSTEM_PROMPT},
    ]
    if context:
        messages.append({"role": "system", "content": f"Reference context:\n{context}"})
    messages.append({"role": "user", "content": prompt})
    
    return requests.post(
        SETTINGS["SP404_LLM_ENDPOINT"] + "/v1/chat/completions",
        json={"model": "jambox-tagger", "messages": messages}
    ).json()
```

---

## Phase 1: Data Preparation (Week 1)

### 1A: Mine Existing Library (Days 1-2)

Script to extract metadata from all 20,925 FLAC files:

```python
import os
import json
from pathlib import Path

SAMPLES_DIR = "/path/to/samples"
output = []

for root, dirs, files in os.walk(SAMPLES_DIR):
    for file in files:
        if file.endswith(('.flac', '.wav', '.mp3', '.aif')):
            filepath = os.path.join(root, file)
            folder_path = os.path.relpath(root, SAMPLES_DIR)
            
            record = {
                "filename": file,
                "folder_path": folder_path,
                "full_path": filepath,
                "size_bytes": os.path.getsize(filepath)
            }
            output.append(record)

with open("library_metadata.jsonl", "w") as f:
    for record in output:
        f.write(json.dumps(record) + "\n")
```

**Expected yield:** ~8,000-10,000 records with useful filename metadata → ~5,000-7,000 convertible to training examples.

### 1B: Convert Reference Docs to Training Data (Days 2-3)

Source docs to convert:
- `Big_Beat_Blowout_Sound_Design_Reference.md` (1,594 lines)
- `Synth-Pop_Dreams_Reference_Document.md` (1,861 lines)
- `brat_mode_sound_design_reference.md` (1,537 lines)
- `JAMBOX_TAG_TAXONOMY.md` (tag definitions, bank assignments, examples)
- All 12 preset YAML files (3 original + 9 new)

Extract key sections, convert each into instruction-response pairs in Alpaca JSONL format:

```json
{"instruction": "Tag this audio sample with structured metadata.", "input": "Filename: acid_bass_303_loop_128bpm_Am.wav\nPath: /samples/Big_Beat/Bass/Acid/", "output": "{\"genre\": \"acid_house\", \"instrument\": \"bass_synth\", \"mood\": \"aggressive\", \"energy\": \"high\", \"bpm\": 128, \"key\": \"Am\", \"texture\": \"wet, resonant, squelchy\", \"technique\": \"303_acid\", \"bank\": \"Big Beat Blowout\", \"vibe\": \"Classic 303 acid bass with envelope-driven cutoff sweeps. Aggressive resonance, tight mono output. Chemical Brothers energy.\"}"}
```

**Expected yield:** ~300-500 examples from reference docs.

### 1C: Generate Synthetic Training Data (Days 4-5)

Use Claude API to bulk-generate examples. Feed it:
1. The full tag taxonomy (JAMBOX_TAG_TAXONOMY.md)
2. The 3 sound design reference docs
3. 10-15 hand-crafted example rows
4. Instructions to generate 1,000 diverse examples covering all 11 banks

**Prompt template provided in Cowork's research doc, Section 4, Phase 3.**

Cost: ~$10-20 in Claude API tokens for 1,000-1,500 examples.

### 1D: Validate (Days 5-7)

Sample 200 examples from all sources. Jason reviews for:
- Tags match taxonomy
- Bank assignments make sense
- Vibe descriptions match characteristics
- No hallucination
- Consistent tone

**Deliverable:** `training_data.jsonl` with ~2,000 validated examples, split 80/20 train/val.

---

## Phase 2: Fine-Tuning (Week 2)

### Model Selection

**Primary:** Qwen3 8B via Ollama (`ollama pull qwen3:8b`)
- Runs natively on Apple Silicon via Metal — Ollama handles this automatically
- 16GB unified memory handles 8B models with room to spare
- Sub-second inference on M1 Pro/Max and newer
- ~1-2 second inference on base M1/M2 with 8GB (still fine for tagging)

**If 8GB unified memory:** Qwen3.5 4B — lighter, ~1-2s/sample, still strong for classification

**Training on Apple Silicon:**
- MLX fine-tuning: 2-4 hours on M1/M2/M3 with 16GB+ unified memory
- Alternative: rent cloud GPU for training ($10-15), run inference locally via Ollama
- Ollama inference on Apple Silicon is excellent — Metal acceleration works out of the box

### Training Setup (Apple Silicon)

Apple Silicon uses MLX instead of CUDA. Two options:

**Option A: MLX-LM (Native Apple Silicon — Recommended)**
```bash
pip install mlx-lm mlx
# Training runs on Metal GPU via unified memory
# 16GB unified memory handles 8B models comfortably
# 8GB unified memory → use 4B model instead
```

**Option B: Unsloth (if you also have access to a CUDA machine or cloud)**
```bash
pip install unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git
pip install transformers torch bitsandbytes peft
```

**Option C: Cloud GPU for training only ($10-15)**
Rent an A100 on RunPod/Lambda for 2-3 hours. Train there, export adapter, run inference locally on your Mac via Ollama. Ollama runs great on Apple Silicon.

### Hyperparameters

```yaml
lora_rank: 16
lora_alpha: 32
lora_dropout: 0.05
target_modules: "all-linear"
use_dora: true
learning_rate: 2e-4
batch_size: 4
gradient_accumulation_steps: 2
num_epochs: 3
max_seq_length: 2048
warmup_steps: 100
optimizer: "paged_adamw_32bit"
fp16: true
```

### Training Script

**Apple Silicon (MLX — recommended for your setup):**

```python
# Fine-tune with mlx-lm on Apple Silicon
# This runs natively on Metal GPU via unified memory

from mlx_lm import load, generate
from mlx_lm.tuner import train as mlx_train

# Load base model
model, tokenizer = load("Qwen/Qwen3-8B")

# Configure LoRA
lora_config = {
    "rank": 16,
    "alpha": 32,
    "dropout": 0.05,
    "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj"]
}

# Train
mlx_train(
    model=model,
    tokenizer=tokenizer,
    train_data="training_data.jsonl",
    val_data="validation_data.jsonl",
    lora_config=lora_config,
    learning_rate=2e-4,
    num_epochs=3,
    batch_size=4,
    output_dir="./output/adapters"
)
```

**Alternative: Unsloth on cloud GPU (if you prefer cloud training):**

```python
from unsloth import FastLanguageModel
from transformers import TrainingArguments, Trainer
from datasets import load_dataset

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="Qwen/Qwen3-8B",
    max_seq_length=2048,
    load_in_4bit=True,
    dtype=torch.float16
)

model = FastLanguageModel.get_peft_model(
    model, r=16, lora_alpha=32,
    target_modules="all-linear",
    lora_dropout=0.05, use_dora=True,
)

dataset = load_dataset("json", data_files="training_data.jsonl")

trainer = Trainer(
    model=model,
    args=TrainingArguments(
        output_dir="./output",
        learning_rate=2e-4,
        num_train_epochs=3,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2,
    ),
    train_dataset=dataset["train"],
)

trainer.train()
model.save_pretrained_merged("./output/adapter_model", tokenizer=tokenizer)
```

**Training time on Apple Silicon:** 2-4 hours on M1/M2/M3 with 16GB+ unified memory. On cloud A100: 1-2 hours.

### Deployment

Create Ollama Modelfile:

```dockerfile
FROM qwen3:8b
ADAPTER ./output/adapter_model.safetensors

PARAMETER temperature 0.5
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_predict 1024

SYSTEM """
[Paste full system prompt from Section 9 of Cowork's research doc — includes
the 11-bank definitions, tagging rules, output format, and examples.
Merge with TASTE_SYSTEM_PROMPT for artist references and taste principles.]
"""
```

```bash
ollama create jambox-tagger -f Modelfile
```

Set in `jambox_config.py`:
```python
SETTINGS["SP404_LLM_ENDPOINT"] = "http://localhost:11434"
SETTINGS["SP404_LLM_MODEL"] = "jambox-tagger"
```

### Iteration Targets

| Version | Examples | Tag Accuracy | Bank Accuracy | Vibe Quality |
|---------|----------|-------------|---------------|-------------|
| v1 | 1,600 | ~82% | ~79% | 3.2/5 |
| v2 | 1,800 | ~87% | ~84% | 3.6/5 |
| v3 | 2,000 | ~90% | ~88% | 3.9/5 |

Stop when bank assignment accuracy hits 88%+.

---

## Phase 3: RAG Layer (Week 3)

### Install

```bash
pip install chromadb sentence-transformers
ollama pull nomic-embed-text
```

### Index These Documents

| Document | Chunk Strategy |
|----------|---------------|
| Big Beat Sound Design Reference (1,594 lines) | By section header (~50 chunks) |
| Synth-Pop Dreams Reference (1,861 lines) | By section header (~60 chunks) |
| Brat Mode Sound Design Reference (1,537 lines) | By section header (~50 chunks) |
| Tag Taxonomy (all 11 banks) | One chunk per bank (~11 chunks) |
| Sample Pack Survey (key sections) | By source/vendor (~30 chunks) |
| Playlist Mining Analysis (both Spotify + YouTube) | By cluster (~18 chunks) |
| All preset YAML files | One chunk per preset (~12 chunks) |

**Total: ~230 chunks, each 500-1,000 tokens.**

### Implementation

Add `JamboxRAG` class to the codebase:

```python
import chromadb

class JamboxRAG:
    def __init__(self, docs_path):
        self.client = chromadb.Client()
        self.collection = self.client.create_collection("jambox_knowledge")
        self._index_docs(docs_path)
    
    def _index_docs(self, path):
        # Parse markdown files by section headers
        # Embed each chunk via nomic-embed-text
        # Store in ChromaDB
        pass
    
    def retrieve(self, query, bank=None, n=3):
        results = self.collection.query(
            query_texts=[query], n_results=n
        )
        if bank:
            # Filter to bank-relevant chunks
            pass
        return "\n".join(results['documents'][0])
```

### Wire Into llm_client.py

```python
rag = JamboxRAG(SETTINGS["TASTE_DOCS_PATH"])

def call_llm(prompt, sample_metadata=None):
    # Build RAG context from sample metadata
    context = None
    if sample_metadata:
        query = f"{sample_metadata.get('tags', '')} {sample_metadata.get('instrument', '')}"
        context = rag.retrieve(query, bank=sample_metadata.get('bank'))
    
    messages = [
        {"role": "system", "content": TASTE_SYSTEM_PROMPT},
    ]
    if context:
        messages.append({"role": "system", "content": f"Reference context:\n{context}"})
    messages.append({"role": "user", "content": prompt})
    
    return requests.post(
        SETTINGS["SP404_LLM_ENDPOINT"] + "/v1/chat/completions",
        json={"model": SETTINGS["SP404_LLM_MODEL"], "messages": messages}
    ).json()
```

---

## Phase 4: Preference Learning (Week 4+)

### Track Signals

Add to a `preferences.json` file:

```python
PREFERENCE_SIGNALS = {
    "daily_bank_accepts": {},    # bank_slug: count
    "daily_bank_skips": {},      # bank_slug: count
    "pad_keeps": {},             # tag: count (tags on pads user kept)
    "pad_changes": {},           # tag: count (tags on pads user replaced)
    "tag_corrections": [],       # [{original: {...}, corrected: {...}}]
    "export_frequency": {},      # bank_slug: count (what makes it to SD card)
}
```

### Dynamic System Prompt Update

After 30+ signals, auto-generate a preference section:

```python
def get_preference_weights():
    prefs = load_json("data/preferences.json")
    # Calculate accept/reject ratios per bank
    # Identify most-kept and most-changed tags
    # Return formatted string for system prompt injection
    return f"""
CURRENT PREFERENCE WEIGHTS (updated {date}):
- Most used banks: {top_banks}
- Most accepted tags: {top_tags}
- Most rejected tags: {bottom_tags}
- Recent session pattern: {recent_pattern}
"""
```

---

## Phase 5: Bank Definition Update

Cowork's research doc assumed generic bank names for banks 4-11. We now have the real 11 banks from the playlist mining analysis. The Modelfile system prompt should use these:

1. **Big Beat Blowout** — Chemical Brothers, Prodigy, Fatboy Slim. Breakbeats, acid bass, rave stabs.
2. **Synth-Pop Dreams** — Purity Ring, CHVRCHES, La Roux. Granular pads, warm leads, chorus, reverb.
3. **Brat Mode** — Charli XCX, SOPHIE, Slayyyter. Detuned supersaws, bitcrushed drums, glitch.
4. **Crystal Chaos** — Crystal Castles, early Grimes. Bitcrushed darkness, noise, lo-fi aggression.
5. **Riot Mode** — Le Tigre, Interrupters, RVIVR. Punk drums, riot grrrl vocals, ska horns.
6. **Minneapolis Machine** — P.O.S, Doomtree, SHREDDERS. Odd-meter drums, boom-bap meets noise.
7. **Outlaw Country Kitchen** — Chris Stapleton, Tyler Childers, Gillian Welch. Pedal steel, fiddle, roots.
8. **Karaoke Metal** — Rhapsody, Blind Guardian, Manowar. Power chords, blast beats, epic choir.
9. **French Filter House** — Modjo, Supermen Lovers, Daft Punk. Filtered disco, vocal chops, warm bass.
10. **Ween Machine** — Ween. Genre-chameleon, absurdist, lo-fi to hi-fi.
11. **Azealia Mode** — Azealia Banks, M.I.A. House beats, aggressive rap, art-pop attitude.
12. **Purity Ring Dreams** — Purity Ring specifically. Granular vocals, ambient pads, delicate leads. (Variant/sub-bank of Synth-Pop Dreams.)

---

## Config Additions

Add to `jambox_config.py`:

```python
SETTINGS["TASTE_DOCS_PATH"] = "docs/references/"
SETTINGS["PREFERENCE_FILE"] = "data/preferences.json"
SETTINGS["RAG_BACKEND"] = "chromadb"
SETTINGS["SP404_LLM_MODEL"] = "jambox-tagger"
```

---

## Files This Brief References

All delivered this session and available in the project:

| File | Purpose |
|------|---------|
| `JAMBOX_TAG_TAXONOMY.md` | Bank-specific tag vocabulary — feeds training data + RAG |
| `JAMBOX_STEM_SPLIT_QUEUE.md` | 40 tracks for stem separation — feeds library expansion |
| `JAMBOX_LLM_PERSONALIZATION.md` | Taste profile and system prompt — feeds Phase 0 |
| `Playlist_Mining_Extraction_Analysis.md` | Spotify + YouTube taste data — feeds training data + RAG |
| `Big_Beat_Blowout_Sound_Design_Reference.md` | Production recipes — feeds training data + RAG |
| `Synth-Pop_Dreams_Reference_Document.md` | Production recipes — feeds training data + RAG |
| `brat_mode_sound_design_reference.md` | Production recipes — feeds training data + RAG |
| `Sample_Pack_Curation_Survey.md` | Source knowledge — feeds RAG |
| `BRAT_MODE_SOURCES.txt` | Download queue — feeds library expansion |
| `chat_playlist_mining_presets_delivery.zip` | 9 presets + 5 sets — feeds training data (example outputs) |

---

## Timeline Summary

| Week | Phase | Deliverable | Effort |
|------|-------|-------------|--------|
| 0 | System prompt | Taste persona in llm_client.py | 30 min |
| 1 | Data prep | 2,000 validated training examples in JSONL | 20-30 hrs |
| 2 | Fine-tune v1-v2 | jambox-tagger model running in Ollama | 8-12 hrs |
| 3 | RAG + iterate | ChromaDB indexed, v3 model if needed | 6-8 hrs |
| 4 | Integration | Live in Jambox, preference tracking active | 6-8 hrs |

**Total: ~4 weeks to a personalized, locally-running taste engine. $0 if you have a GPU, ~$15 if you rent cloud compute for training.**
