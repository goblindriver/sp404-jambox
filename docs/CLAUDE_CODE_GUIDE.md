# Using Claude Code with This Project

## Overview

This project uses a multi-agent workflow. Claude Code handles all implementation — scripts, web UI, pipeline, and code changes. Chat handles creative direction and documentation. Cowork handles sample sourcing.

Claude Code reads `CLAUDE.md` in the project root automatically for full context on paths, commands, bank layout, tag system, and coordination rules.

## Getting Started

```bash
npm install -g @anthropic-ai/claude-code
claude login
cd ~/Desktop/SP-404SX/sp404-jambox
claude
```

## Example Workflows

### Curate a Bank
```
> Refetch Bank D with different samples — the current kick is too soft
> and I want a rawer guitar loop on pad 11.
```

### Expand the Library
```
> Ingest whatever's in ~/Downloads right now. Tag the new files
> and tell me what we got.
```

### Edit Bank Layout
```
> Change Bank G to 130 BPM and swap pad 6 from acid bass to
> a distorted bass loop.
```
(This updates `bank_config.yaml`, then re-fetches the affected pads.)

### Full Rebuild
```
> Rebuild the SD card from scratch. Re-fetch all banks,
> regenerate PAD_INFO.BIN and patterns, and deploy.
```

### Library Analysis
```
> How many kicks do we have in the library? Show me the
> distribution of energy tags across all drum samples.
```

### Web UI Development
```
> Add a waveform preview to the pad detail view in the web UI.
> It should show when you click a pad that has a sample loaded.
```

## Key Commands

| Task | Command |
|------|---------|
| Fetch all banks | `python scripts/fetch_samples.py` |
| Fetch one bank | `python scripts/fetch_samples.py --bank d` |
| Fetch one pad | `python scripts/fetch_samples.py --bank d --pad 1` |
| Ingest downloads | `python scripts/ingest_downloads.py` |
| Tag library | `python scripts/tag_library.py` |
| Tag new only | `python scripts/tag_library.py --update` |
| Generate PAD_INFO | `python scripts/gen_padinfo.py` |
| Generate patterns | `python scripts/gen_patterns.py` |
| Deploy to SD | `bash scripts/copy_to_sd.sh` |
| Launch web UI | `cd web && python app.py` |

## Coordination Rules

- **Chat owns docs** — don't create or update documentation files unless the user asks
- **bank_config.yaml is the source of truth** for bank layouts
- **_tags.json is the source of truth** for sample metadata
- After ingesting new samples, always re-tag: `python scripts/tag_library.py --update`
- Cowork drops samples into `~/Downloads/` — ingest them with `ingest_downloads.py`

## Tips

1. Always verify audio format after conversion: `ffprobe -v quiet -print_format json -show_streams file.wav`
2. Test with `--bank` and `--pad` flags before fetching everything
3. The library is the source of truth, not the SD card — the card is just a deployment target
4. Version bank layouts in git so you can roll back
5. The web UI at localhost:5404 is often faster than terminal for browsing and previewing
