# CLAP Model Comparison Research
## Cowork Deliverable | April 4, 2026
### For: Jambox Tier 3 Audio Similarity — CLAP Embedding Pass

---

## Recommendation: LAION `laion/larger_clap_music`

Use this checkpoint. It outperforms all alternatives on music-specific tasks, runs on M3 24GB with room to spare, and integrates cleanly with your existing librosa + transformers stack.

---

## The Contenders

### LAION-CLAP (`laion/larger_clap_music`)
- **Architecture:** SWINTransformer audio encoder + RoBERTa text encoder, joint 512-dim projection
- **Training data:** LAION-Audio-630K (633,526 audio-text pairs), music-focused variant
- **Embedding dimensions:** 512 (matches your spec exactly)
- **HF checkpoint:** `laion/larger_clap_music`
- **Python package:** `transformers>=4.27.0` (native support)

**Other LAION checkpoints available:**
- `laion/clap-htsat-unfused` — base model, separate encoders
- `laion/clap-htsat-fused` — fused feature processing, variable-length audio
- `laion/larger_clap_music_and_speech` — hybrid music + speech + general
- `laion/larger_clap_general` — general purpose

### Microsoft CLAP (`microsoft/msclap`)
- **Architecture:** CNN14 audio encoder (80.8M params) + BERT text encoder (110M params), 512-dim output
- **Key difference:** CNN-based audio encoder vs LAION's transformer
- **Versions:** 2022, 2023, clapcap releases via Zenodo/HF

### Newer Variants (2025-2026)
- **tinyCLAP:** Distilled CLAP, only 6% of original parameters, <5% performance drop. Good fallback if memory becomes an issue.
- **GLAP (2025):** 145-language CLAP. Overkill for your use case — designed for multilingual audio.
- **T-CLAP:** Temporal/event-order-sensitive. Up to 30pp improvement in temporal retrieval. Unnecessary for static sample analysis.
- **CoLLAP:** Long-form music temporal understanding. Irrelevant for short samples.

---

## Music Performance Benchmarks

| Benchmark | `larger_clap_music` | `larger_clap_music_and_speech` | Microsoft CLAP |
|-----------|--------------------|-----------------------------|----------------|
| GTZAN Genre Classification | **71%** | 69% | ~65% (CNN weaker) |
| ESC50 Environmental Sound | **90.14%** | 89.25% | comparable |
| GTZAN Music vs Speech | **100%** | 100% | — |
| Zero-shot Instrument Classification | 47% | — | — |

**Verdict:** The music-only LAION model consistently outperforms the hybrid and Microsoft alternatives on music tasks. The transformer-based audio encoder captures more nuanced musical features than CNN14.

---

## Apple Silicon M3 24GB Compatibility

### MPS (Metal Performance Shaders) Support
- PyTorch MPS backend fully supports CLAP inference
- Unified memory architecture = no PCIe transfer overhead (big advantage)
- M3 GPU acceleration with Dynamic Caching works with transformer models

### Memory Footprint
| Component | Memory |
|-----------|--------|
| Model weights | ~500MB–1.5GB |
| Audio buffer (batch_size=32) | ~60MB at 48kHz float32 |
| **Total inference memory** | **~2–3GB** (well within 24GB) |

### Performance Notes
- Float16 mixed precision is often **slower** on Apple Silicon than float32 (no Tensor Cores)
- MPS performs best with higher batch sizes (16-32) — tiny batches have dispatch overhead
- Some PyTorch ops may fall back to CPU; set `PYTORCH_ENABLE_MPS_FALLBACK=1`
- Use float32 for best M3 performance

### Estimated Processing Time
- ~5-10 samples/second with MPS at batch_size=32
- **30,000 files: ~1-2 hours overnight** (batched, with MPS)
- CPU-only fallback: 2-3x slower (~3-6 hours)

---

## Practical Integration

### Dependencies
```
torch (with MPS support)
transformers>=4.27.0
librosa
numpy
```

### Usage Pattern
```python
from transformers import ClapModel, ClapProcessor
import librosa, torch, numpy as np

model = ClapModel.from_pretrained("laion/larger_clap_music").to("mps")
processor = ClapProcessor.from_pretrained("laion/larger_clap_music")

# CLAP expects 48kHz audio
audio, sr = librosa.load(file_path, sr=48000)

with torch.inference_mode():
    inputs = processor(audios=[audio], return_tensors="pt").to("mps")
    embedding = model.get_audio_features(**inputs).cpu().numpy()  # (1, 512)
```

### Natural Language Search
```python
# "Find me something that sounds like a dusty vinyl break"
text_inputs = processor(text=["dusty vinyl break"], return_tensors="pt").to("mps")
text_embedding = model.get_text_features(**text_inputs).cpu().numpy()  # (1, 512)

# Cosine similarity against all stored audio embeddings
from numpy.linalg import norm
similarities = [np.dot(text_embedding[0], audio_emb) / (norm(text_embedding[0]) * norm(audio_emb))
                for audio_emb in all_audio_embeddings]
```

### Storage Estimates
- Per file: 512 floats x 4 bytes = 2,048 bytes (~2KB)
- 30,000 files: ~60MB as raw vectors
- JSON sidecar overhead: ~192MB total (with key names)
- SQLite BLOB storage: similar footprint, faster queries

### Batch Processing for 30K Files
- Process in chunks of 32 files
- Write embeddings to `_tags.json` (or SQLite) after each batch
- Checkpoint progress so interrupted runs can resume
- Run overnight — estimated 1-2 hours total

---

## Storage Architecture Decision

Two options for where CLAP embeddings live:

**Option A: In `_tags.json`** (current architecture)
- Add `clap_embedding` key per file entry
- Pro: Single source of truth
- Con: JSON file grows to ~250MB+; slower reads

**Option B: Separate SQLite table** (recommended if migrating to SQLite)
- `CREATE TABLE clap_embeddings (file_path TEXT PRIMARY KEY, embedding BLOB)`
- Pro: Fast vector lookups, doesn't bloat tag DB
- Con: Second data store to manage

Chat's bug hunt flagged `_tags.json` → SQLite migration as critical before the re-vibe pass. If that migration happens first, embeddings should go directly into SQLite.

---

## What NOT to Use
- **Microsoft CLAP:** CNN-based, weaker on music tasks, no compelling advantage
- **GLAP:** Multilingual overkill, adds overhead
- **T-CLAP:** Temporal analysis unnecessary for static samples
- **tinyCLAP:** Only if memory becomes a problem (it won't on 24GB)

---

## Sources
- [LAION CLAP GitHub](https://github.com/LAION-AI/CLAP)
- [laion/larger_clap_music on HF](https://huggingface.co/laion/larger_clap_music)
- [HF Transformers CLAP docs](https://huggingface.co/docs/transformers/en/model_doc/clap)
- [Microsoft CLAP GitHub](https://github.com/microsoft/CLAP)
- [tinyCLAP paper](https://arxiv.org/abs/2311.14517)
- [GLAP paper](https://arxiv.org/abs/2506.11350)
- [T-CLAP paper](https://arxiv.org/abs/2404.17806)
- [Apple Metal PyTorch](https://developer.apple.com/metal/pytorch/)
