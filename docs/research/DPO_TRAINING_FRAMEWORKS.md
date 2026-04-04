# DPO Training Frameworks Research
## Cowork Deliverable | April 4, 2026
### For: Jambox Vibe Intelligence — Distilling qwen3:32b → 7B with User Preference Training

---

## Recommended Pipeline: SFT First, Then DPO

Don't go straight to DPO. The proven path is:

1. **SFT** on 32B teacher outputs → teaches the 7B model the task
2. **DPO** on user corrections → aligns it to Jason's specific taste

This two-stage approach converges faster, needs fewer preference pairs, and produces better results than DPO alone.

---

## Framework Recommendation: Unsloth + TRL

You already use Unsloth for SFT with QLoRA. Good news: **Unsloth fully supports DPO training** with the same 2x speed / 30% less VRAM benefits. The API is a thin wrapper around HuggingFace TRL's DPOTrainer.

### Unsloth DPO API
```python
from unsloth import FastLanguageModel, PatchDPOTrainer
from trl import DPOTrainer, DPOConfig

# MUST call before DPOTrainer init
PatchDPOTrainer()

# Load model with 4-bit quantization (same as your SFT setup)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="Qwen/Qwen3-8B",
    max_seq_length=2048,
    load_in_4bit=True,
)

# Add LoRA adapters (your existing hyperparameters work)
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    bias="none",
    task_type="CAUSAL_LM",
)

trainer = DPOTrainer(
    model=model,
    tokenizer=tokenizer,
    args=DPOConfig(
        per_device_train_batch_size=2,
        gradient_checkpointing=True,
        learning_rate=5e-5,        # Lower than SFT (2e-4)
        num_train_epochs=1,         # DPO converges fast
        output_dir="./dpo_output",
    ),
    train_dataset=preference_dataset,
    beta=0.1,
)
trainer.train()
```

### Key Differences from SFT Setup
| Parameter | SFT (current) | DPO (new) |
|-----------|---------------|-----------|
| Learning rate | 2e-4 | **5e-5** (lower for alignment) |
| Epochs | 3 | **1** (DPO converges fast) |
| LoRA r/alpha | 16/32 | 16/32 (keep same) |
| Batch size | 2-4 | **2** (DPO uses more memory per step) |

---

## TRL DPOTrainer Details

HuggingFace TRL (v0.7.11+) handles the heavy lifting:

### Memory Optimization (Critical)
- TRL does NOT keep a separate reference model when using PEFT/LoRA
- Instead, it temporarily disables LoRA adapters during reference inference
- This saves ~50% memory vs methods that duplicate the reference model
- **Constraint:** `sync_ref_model=True` is NOT supported with PEFT (use adapter-based reference instead)

### QLoRA + DPO: Fully Supported
- `load_in_4bit=True` works directly with DPOTrainer
- Unsloth's patched DPOTrainer adds 2x speed on top
- Must handle adapter merging carefully for GGUF export (see below)

---

## Minimum Preference Pairs

### Academic Guidance
| Dataset | Pairs | Result |
|---------|-------|--------|
| Zephyr-7B-beta | 66,000 | Strong alignment |
| Intel Orca DPO | 13,000 | Good improvement |
| Anthropic HH-RLHF | 169,550 | Research benchmark |
| AWS minimum recommendation | **1,000** | Minimum viable |

### Practical for Jambox
- **500 pairs:** Noticeable but inconsistent improvement
- **1,000 pairs:** Minimum viable — expect measurable gains on eval suite
- **5,000 pairs:** Sweet spot for a domain-specific task like audio tagging
- **Quality > quantity:** Diverse pairs (easy + hard corrections) matter more than volume

### How to Get There
Your review UI generates preference pairs naturally:
- User sees model output, corrects it → `(user_version=chosen, model_version=rejected)`
- Each correction is one preference pair
- At 10-20 corrections per session, 1,000 pairs = ~50-100 review sessions
- Accelerator: batch-review mode in the retag review UI (review multiple tags per screen)

---

## Apple Silicon M3 24GB: DPO Training

### Memory Reality
| Configuration | Memory Required |
|---------------|----------------|
| 7B model FP16 (baseline) | ~14GB |
| 7B model + LoRA (FP16) | ~16-20GB |
| 7B model + QLoRA (4-bit) | **~8-10GB** |

**24GB unified memory is sufficient** for DPO with QLoRA.

### MPS Training Notes
- PyTorch MPS backend supports training (macOS 12.3+)
- Unified memory = no PCIe overhead (advantage over discrete GPU setups)
- Set `PYTORCH_ENABLE_MPS_FALLBACK=1` for unsupported ops
- MPS does NOT support distributed training (irrelevant for single-M3)
- Some float16 ops are slower on MPS than float32 — test both
- **Expected speed:** 3-5x slower than NVIDIA GPU (normal for Apple Silicon)
- **Expected time:** 1-2 hours for 5,000 pairs with QLoRA settings above

### Optimization Checklist
1. QLoRA with r=16, alpha=32 (keep your SFT values)
2. `max_seq_length=1024` (reduce to 512 if tight)
3. `per_device_train_batch_size=2` (start here, increase if memory allows)
4. `gradient_checkpointing=True` (always)
5. Close heavy background apps during training

---

## The Full Pipeline: 32B → 7B Distillation + DPO

```
Stage 0: Collect Teacher Data
├── Run qwen3:32b smart retag on 30K files
├── Store outputs in _tags.json / SQLite
└── These become SFT training examples

Stage 1: SFT Fine-Tuning (Distillation)
├── Dataset: 1,000-2,000 high-quality (input, 32B_output) pairs
├── Framework: Unsloth + QLoRA (your existing pipeline)
├── Hyperparams: r=16, α=32, lr=2e-4, 3 epochs
├── Result: Qwen3 7B that mimics 32B behavior
└── Save: LoRA adapter checkpoint

Stage 2: Deploy SFT Model + Collect Corrections
├── Merge SFT adapter → export GGUF → serve via Ollama
├── Run inline inference on new samples
├── Users review/correct tags in retag review UI
└── Each correction = one preference pair

Stage 3: DPO Fine-Tuning (Alignment)
├── Dataset: 1,000+ preference pairs from corrections
├── Framework: Unsloth PatchDPOTrainer() + TRL DPOTrainer
├── Hyperparams: r=16, α=32, lr=5e-5, 1 epoch, β=0.1
├── Start from SFT checkpoint (not base model)
├── Result: 7B model aligned to Jason's aesthetic
└── Save: DPO LoRA adapter checkpoint

Stage 4: Export + Deploy
├── Merge DPO adapter into base model (FP16)
├── Convert HF → GGUF via llama.cpp convert_hf_to_gguf.py
├── Quantize to Q4/Q5/Q6 (your choice of size vs quality)
├── Create Ollama Modelfile
└── Serve inline at 7B speed
```

### Why SFT → DPO (Not DPO Alone)
- SFT establishes baseline task understanding first
- Reduces KL divergence magnitude during DPO (more stable)
- Converges faster with fewer DPO pairs
- DPO alone on a base model often produces incoherent outputs

### Why Not SFT Alone
- SFT copies 32B behavior but can't improve on it
- DPO encodes human preferences the 32B model doesn't have
- Specifically: Jason's aesthetic preference for `hype > warm > soulful` over `nostalgic > dark > dreamy`

---

## DPO Dataset Format

```python
# Each preference pair
{
    "prompt": "Tag this audio sample:\nFilename: funk_bass_loop_112bpm.flac\nDuration: 4.2s\nBPM: 112\nKey: Em\nLoudness: -14.2 dB",
    "chosen": "type_code: BAS\nvibe: warm, soulful\ntexture: organic, saturated\ngenre: funk\nenergy: mid\nplayability: loop\ninstrument_hint: bass guitar\nquality_score: 4\nsonic_description: Warm, round bass guitar loop with subtle overdrive and a syncopated funk groove.",
    "rejected": "type_code: BAS\nvibe: nostalgic, mellow\ntexture: dusty, lo-fi\ngenre: soul\nenergy: low\nplayability: loop\ninstrument_hint: bass\nquality_score: 3\nsonic_description: A mellow bass loop with vintage character."
}
```

---

## GGUF Export Path

### After DPO Training
```
1. Merge LoRA → FP16 Weights
   └── Unsloth's built-in merge utilities

2. Convert HF → GGUF
   └── llama.cpp convert_hf_to_gguf.py
   └── OR: HuggingFace Space "gguf-my-repo" (automated)

3. Quantize (optional)
   └── llama.cpp quantize utility
   └── Q4: ~3.5GB | Q5: ~4.5GB | Q6: ~5.5GB

4. Deploy to Ollama
   └── Create Modelfile pointing to GGUF
   └── ollama create jambox-vibe -f Modelfile
```

### Important: Training Quantization ≠ Export Quantization
Your 4-bit QLoRA training only affects training-time memory. After merging adapters, you have full FP16 weights. Export quantization is a separate step.

---

## Library Versions (2025-2026)

```
unsloth>=2025.1       # DPO support
transformers>=4.42
trl>=0.7.11           # DPOTrainer with PEFT
peft>=0.13
torch>=2.2            # MPS support
bitsandbytes>=0.42.0  # Quantization on M-series
```

---

## Sources
- [Unsloth DPO/ORPO/KTO Guide](https://unsloth.ai/docs/get-started/reinforcement-learning-rl-guide/preference-dpo-orpo-and-kto)
- [HuggingFace TRL DPO Trainer](https://huggingface.co/docs/trl/dpo_trainer)
- [HuggingFace Blog: Unsloth + TRL](https://huggingface.co/blog/unsloth-trl)
- [AWS SageMaker DPO Guide](https://docs.aws.amazon.com/sagemaker/latest/dg/nova-dpo.html)
- [HuggingFace Blog: Preference Tuning](https://huggingface.co/blog/pref-tuning)
- [Apple Metal PyTorch](https://developer.apple.com/metal/pytorch/)
- [GGUF-my-LoRA](https://huggingface.co/blog/ngxson/gguf-my-lora)
- [llama.cpp convert_hf_to_gguf.py](https://github.com/ggml-org/llama.cpp)
