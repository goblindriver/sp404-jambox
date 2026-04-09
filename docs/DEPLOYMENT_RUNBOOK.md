# DEPLOYMENT RUNBOOK

**Version:** 1.0
**Date:** 2026-04-08
**Owner:** Chat
**Audience:** Anyone building and deploying banks to the SP-404A

---

## Overview

This is the complete workflow from "I want to jam" to "the card is in the sampler and everything works." Follow the steps in order. Each step has a verify checkpoint — don't skip them.

---

## Prerequisites

- SD card formatted FAT32 (4GB minimum, 32GB recommended)
- SP-404A powered off
- Jambox web UI running: `cd web && python app.py` → http://localhost:5404
- Sample library populated: `~/Music/SP404-Sample-Library/` (30K+ files)
- Tag database current: `_tags.json` exists and is recent

---

## Step 1: Choose Your Banks

**Option A — Use a preset set:**
Open the web UI → Set Selector → pick a set (e.g., `default.yaml`, or a custom set). This loads 10 bank presets across Banks A–J.

**Option B — Build banks manually:**
Open the web UI → click a bank tab → Bank Edit Modal → set name, BPM, key, notes. Repeat for each bank you want to populate.

**Option C — Use a preset per bank:**
Preset Browser → search/filter → drag a preset onto a bank tab. Mix and match presets across banks.

**Verify:** Each bank you want to populate has a name, BPM, and key set. Banks A and B are internal memory on the SP-404A and survive SD card swaps — use them for your most essential sounds or leave A empty for live resampling.

---

## Step 2: Edit Pad Descriptions

For each bank, click individual pads to set descriptions. The description is what the scoring engine matches against.

**Good descriptions:** "dark aggressive kick, punchy, 808 style" — specific type + vibe + texture keywords.

**Bad descriptions:** "cool sound" — too vague, scoring engine has nothing to work with.

**Pad convention:** Pads 1–4 = drum hits (one-shots). Pads 5–12 = loops and melodic content. This isn't enforced but it's how every preset is designed.

**Verify:** At minimum, every pad you want populated has a description with a clear type (kick, snare, loop, pad, etc.).

---

## Step 3: Fetch Samples

**Full fetch (all banks):**
Web UI → Pipeline Controls → "Fetch All"
Or terminal: `python scripts/fetch_samples.py`

**Single bank:**
`python scripts/fetch_samples.py --bank d`

**Single pad:**
`python scripts/fetch_samples.py --bank d --pad 1`

The scoring engine matches each pad description against the tag database, picks the best candidate, converts it to 16-bit/44.1kHz/mono WAV with the RLND header chunk, and places it in the staging directory.

**Verify:**
- Check the web UI pad grid — populated pads show a filename and score
- Pads with "no match" mean the library doesn't have a good candidate for that description. Revise the description or accept the gap.
- Preview audio by clicking populated pads in the web UI

---

## Step 4: Build SD Card Files

**Generate PAD_INFO.BIN:**
Web UI → Pipeline Controls → "Build"
Or terminal: `python scripts/gen_padinfo.py`

This reads playability tags to set loop/gate/one-shot mode per pad. The SP-404 requires this file to know how to trigger each sample.

**Generate starter patterns (optional):**
`python scripts/gen_patterns.py`

Creates basic .PTN pattern files in the PTN directory. These are starting points — you'll build your own patterns on the hardware.

**Verify:** The staging directory contains:
```
sd-card-template/ROLAND/SP-404SX/
├── SMPL/
│   ├── PAD_INFO.BIN
│   ├── A0000001.WAV through A0000012.WAV  (if Bank A populated)
│   └── ... through J0000012.WAV
└── PTN/
    └── PTN00001.BIN ... (if patterns generated)
```

All WAV files should be 16-bit/44.1kHz/mono. Quick check:
```bash
file sd-card-template/ROLAND/SP-404SX/SMPL/C0000001.WAV
# Should show: RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 44100 Hz
```

---

## Step 5: Deploy to SD Card

Insert the SD card into your Mac. It should mount as `/Volumes/SP-404SX` (or whatever you named it).

**Deploy:**
Web UI → Pipeline Controls → "Deploy"
Or terminal: `bash scripts/copy_to_sd.sh`

This copies the staging directory to the SD card, preserving the ROLAND/SP-404SX folder structure.

**Verify:**
- Web UI shows SD card status indicator (green = detected, file count matches)
- Terminal: `ls /Volumes/SP-404SX/ROLAND/SP-404SX/SMPL/ | wc -l` — should match your populated pad count + 1 (PAD_INFO.BIN)
- Eject the card properly: `diskutil eject /Volumes/SP-404SX`

---

## Step 6: Load and Verify on Hardware

1. Power off the SP-404A
2. Insert the SD card
3. Power on while holding the appropriate bank button to verify samples loaded
4. Step through each bank, tapping pads 1–12 to confirm:
   - Correct sample plays on each pad
   - Loop pads loop correctly (not one-shotting)
   - One-shot pads don't loop
   - Volume levels are reasonable across pads (if normalization pipeline is active)
   - BPM feels right when playing loops against each other

**Common issues:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| Pad doesn't play | WAV missing RLND chunk | Re-run fetch — the conversion adds RLND |
| Pad plays garbage/noise | File corruption during copy | Re-deploy, eject card properly |
| Loop doesn't loop | PAD_INFO.BIN has wrong mode | Check playability tag, re-run gen_padinfo |
| Wrong sample on pad | Filename mismatch | Check pad numbering — `G0000007.WAV` = Bank G, Pad 7 |
| All pads silent | SD card not FAT32 | Reformat as FAT32 (not exFAT, not NTFS) |
| Banks A/B empty | A/B are internal memory | Banks A–B are stored in the SP-404's internal memory, not on the SD card. Load them via the hardware's own sample import function, or accept that SD card deploy only covers Banks C–J. |

---

## Step 7: Rollback (If Needed)

If a bank sounds wrong and you want to go back:

**Quick rollback:** Re-deploy from the staging directory — it still has the previous build until you fetch again.

**Full rollback:**
```bash
git stash  # if you changed bank_config.yaml
git checkout main -- sd-card-template/
```

**Save a good build:** Before deploying a new set, copy the current staging directory:
```bash
cp -r sd-card-template/ ~/Music/SP404-Sample-Library/_GOLD/$(date +%Y%m%d)/
```

The `_GOLD` directory preserves known-good bank builds. Useful for gigs — always have a fallback card.

---

## Quick Reference: Full Pipeline in Terminal

```bash
# Complete build from scratch
python scripts/fetch_samples.py          # Match samples to all banks
python scripts/gen_padinfo.py            # Generate PAD_INFO.BIN
python scripts/gen_patterns.py           # Generate starter patterns (optional)
bash scripts/copy_to_sd.sh              # Deploy to SD card

# Single bank rebuild
python scripts/fetch_samples.py --bank d
python scripts/gen_padinfo.py
bash scripts/copy_to_sd.sh

# Full pipeline via web UI
# Open http://localhost:5404 → Fetch All → Build → Deploy
```

---

## Timing Expectations

| Step | Duration | Notes |
|------|----------|-------|
| Fetch (all banks, 120 pads) | 30–90 seconds | Depends on CLAP availability and library size |
| Fetch (single bank, 12 pads) | 3–10 seconds | |
| gen_padinfo | <1 second | |
| gen_patterns | <1 second | |
| copy_to_sd | 5–30 seconds | Depends on SD card write speed |
| **Total pipeline** | **~1–2 minutes** | |

This is fast enough to iterate during a session. Change a pad description, re-fetch that pad, re-deploy, and hear the result in under a minute.
