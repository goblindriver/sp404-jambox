# Using Claude Code with This Project

This project was built using Claude (Anthropic's AI assistant) in Cowork mode and can be extended further using [Claude Code](https://docs.claude.com/en/docs/claude-code) for command-line agentic workflows.

## Why Claude Code?

Claude Code runs directly in your terminal and can:
- Read/write files, run shell commands, and interact with git
- Execute Python scripts and debug errors in real-time
- Browse the web to find new sample packs
- Manage the full pipeline from download → organize → curate → convert → deploy

This is ideal for an SP-404 workflow because:
- Sample pack discovery and download
- Audio format conversion (ffmpeg pipelines)
- Library organization and deduplication
- Bank curation based on genre/BPM matching
- SD card deployment

## Getting Started with Claude Code

### Install
```bash
npm install -g @anthropic-ai/claude-code
```

### Authenticate
```bash
claude login
```

### Use with This Project
```bash
cd ~/path-to/sp404-jambox
claude
```

Then ask Claude to help with tasks like:
- "Download the MusicRadar breakbeat samples pack and add it to the library"
- "Create a new bank layout for dub techno at 125bpm"
- "Find the best kick drums in the library and preview them"
- "Convert all samples in _READY-TO-LOAD to SP-404 format"
- "Deploy the current card setup to /Volumes/SP-404SX"

## Example Workflows

### Add a New Genre Bank
```
> Replace Bank J with a Dub Techno bank at 125bpm. Pick the best
> samples from the library — kicks should be deep and subby,
> hats should be minimal, and I want long reverby chord stabs
> for pads 5-12.
```

### Rebuild the Entire Card
```
> Rebuild the SD card from scratch. Use the current bank layout
> but re-pick all samples — prioritize variety and avoid any
> samples that clip or have DC offset.
```

### Expand the Library
```
> Search MusicRadar SampleRadar for any drum & bass or jungle
> sample packs. Download them, organize into the library, and
> tell me what we got.
```

### Analyze What's On the Card
```
> Read the SD card at /Volumes/SP-404SX and tell me what's on
> each bank. Check audio quality — are there any samples that
> are too quiet, clip, or have issues?
```

## CLAUDE.md Project Instructions

If you create a `CLAUDE.md` file in the project root, Claude Code will automatically read it for project context. Here's a recommended setup:

```markdown
# SP-404 Jam Box

## Project Context
SP-404A/SX sampler SD card builder. Curates royalty-free samples
into genre banks for live jamming.

## Key Paths
- SD card mount: /Volumes/SP-404SX
- Sample library: ~/Music/SP404-Sample-Library
- Working folder: this repo

## Audio Format
All output WAVs must be: 16-bit / 44.1kHz / Mono / PCM
Convert with: ffmpeg -y -i input -ar 44100 -ac 1 -sample_fmt s16 -c:a pcm_s16le output.WAV

## SP-404 File Naming
Bank letter + 7-digit pad number: A0000001.WAV through J0000012.WAV
Place in: ROLAND/SP-404SX/SMPL/

## Bank Layout
Pads 1-4 = drum hits, Pads 5-12 = loops & melodic
See PAD_MAP.txt for current contents.

## Commands
- Organize library: python scripts/organize_library.py
- Pick samples: python scripts/pick_best_samples.py
- Generate Bank B: python scripts/gen_novelty.py
- Deploy to SD: bash scripts/copy_to_sd.sh
```

## Tips for Working with Claude Code on Audio Projects

1. **Always verify audio format** after conversion: `ffprobe -v quiet -print_format json -show_streams file.wav`
2. **Test with small batches** before processing hundreds of files
3. **Keep backups** — the `_BACKUP_ORIGINAL/` folder on the SD card is there for a reason
4. **Use the library** as your source of truth, not the SD card — the card is just a deployment target
5. **Version your bank layouts** in git so you can roll back changes
