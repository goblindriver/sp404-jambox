---
name: troubleshooting
description: Common Jambox issues and fixes. Use when the user reports an "error", "not working", "broke", "crash", "won't start", "debug", or needs help diagnosing a problem with the sampler pipeline, web UI, LLM, or audio processing.
version: 0.2.0
---

# Troubleshooting

## Ollama Not Responding

**Symptoms:** Smart retag hangs, vibe generate fails, "connection refused" errors.

**Diagnose:**
```bash
curl http://localhost:11434/api/tags
```

**Fix:**
- If not running: `ollama serve`
- If running but slow: check `ollama ps` for loaded models (32b uses ~20GB VRAM)
- Smart retag falls back to filename-based tags if Ollama is down
- Vibe parser falls back to `base` mode (keyword extraction, no LLM)

## Watcher Not Detecting Files

**Symptoms:** Files sit in `~/Downloads/` without being ingested.

**Diagnose:**
- Check Power Button dashboard — watcher status should show "running"
- Check `GET /api/pipeline/watcher/status` for activity log

**Fix:**
- Restart watcher: toggle the Watch button in the UI
- One-shot fallback: `python scripts/ingest_downloads.py`
- Docs only: `python scripts/ingest_downloads.py --docs-only`
- Known issue (fixed): simple folder names (not scene-release patterns) were previously missed

## Fetch Returns Wrong Samples

**Symptoms:** Pad gets a completely unrelated sound, or "no match" for everything.

**Most likely cause:** Tags are hollow — only ~108 of 30K files had real dimensional tags before the retag run started.

**Diagnose:**
```bash
cat data/retag_checkpoint.json    # Check retag progress
python -c "import json; t=json.load(open('$HOME/Music/SP404-Sample-Library/_tags.json')); print(sum(1 for v in t.values() if v.get('vibe')))"
```

**Fix:**
- Wait for smart retag to complete — fetch quality improves dramatically with real tags
- Check scoring weights in `config/scoring.yaml` — type_exact (10) should dominate
- Try more specific pad descriptions: `KIK hard 808 one-shot` instead of just `KIK`
- Use fewer keywords — 3-4 total gets better matches than 6-7

## SD Card Not Detected

**Symptoms:** Deploy fails, SD card status shows "not mounted".

**Diagnose:**
```bash
ls /Volumes/SP-404SX/ROLAND/SP-404SX/SMPL/
diskutil info /Volumes/SP-404SX
```

**Fix:**
- Must be **FAT32** formatted
- Must have `ROLAND/SP-404SX/SMPL/` folder structure
- Format IN the SP-404A first for correct structure, then populate via Jambox
- Always safely eject before removing from computer
- Clean macOS metadata: `find /Volumes/SP-404SX -name "._*" -delete`

## librosa Errors on Specific Files

**Symptoms:** Smart retag or audio analysis crashes on certain files.

**Diagnose:**
```bash
ffprobe <file>          # Check if file is valid audio
stat <file>             # Check file size (0 = incomplete download)
file <file>             # Check actual file type
```

**Fix:**
- Corrupt audio: re-download or remove from library
- Wrong format: ensure FLAC or WAV, 44.1kHz. Re-convert if needed.
- Zero-length: incomplete download — re-download or remove
- Smart retag skips errors and continues (check `data/retag_checkpoint.json` for error count)

## Web UI Blank or Unresponsive

**Symptoms:** Page loads but content is missing, buttons don't work.

**Diagnose:**
- Check Flask console for Python errors
- Check browser console for JavaScript errors
- Check `GET /api/pipeline/server/status` for feature availability

**Fix:**
- Use the **Restart Server** button in the power menu
- Or restart manually: kill the Flask process and `cd web && python app.py`
- Known fix (commit 58d65be): watcher UI going dark during initial ingest

## bank_config.yaml Corruption

**Symptoms:** Banks missing, duplicated, or showing wrong content.

**Diagnose:**
```bash
python -c "import yaml; d=yaml.safe_load(open('bank_config.yaml')); print([b['letter'] for b in d['banks']])"
```

**Fix:**
- Known incident (commit 2eeacdb): Banks A & B were replaced by duplicate I
- Prevention: use the preset/set system instead of manual YAML editing
- Recovery: `git checkout bank_config.yaml` to restore last committed version
- Or load a saved set: `POST /api/sets/<slug>/apply`

## Smart Retag High Error Rate

**Symptoms:** `data/retag_checkpoint.json` shows high error percentage.

**Diagnose:**
```bash
python -c "import json; c=json.load(open('data/retag_checkpoint.json')); print(f'Errors: {c.get(\"errors\", 0)}/{c.get(\"processed\", 0)}')"
```

**Fix:**
- qwen3:8b had 38% error rate on structured JSON — upgraded to qwen3:32b
- Check Ollama memory: 32b model needs ~20GB VRAM
- Increase timeout: set `SP404_LLM_TIMEOUT=120` if getting timeout errors
- LLM retry logic with backoff is on the roadmap but not yet implemented

## ffmpeg Conversion Failures

**Symptoms:** Samples don't play on the SP-404A, or audio is distorted.

**Diagnose:**
```bash
ffprobe -v quiet -print_format json -show_streams output.WAV
```

Verify: 44100 Hz, 1 channel, s16 (16-bit), pcm_s16le codec.

**Fix:**
- All output WAVs must be: 16-bit / 44.1kHz / Mono / PCM
- Convert with: `ffmpeg -y -i input -ar 44100 -ac 1 -sample_fmt s16 -c:a pcm_s16le output.WAV`
- ffmpeg is at `/opt/homebrew/bin/ffmpeg` — all scripts use absolute paths
