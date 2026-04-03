#!/bin/bash
# Initialize git repo and push to GitHub
# Run from inside the sp404-jambox folder:
#   cd ~/path-to/sp404-jambox && bash setup_repo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== SP-404 Jam Box — GitHub Setup ==="

# Check gh is authenticated
if ! gh auth status &>/dev/null; then
    echo "ERROR: gh CLI not authenticated. Run 'gh auth login' first."
    exit 1
fi

# Get GitHub username
GH_USER=$(gh api user --jq '.login')
echo "GitHub user: $GH_USER"

# Initialize git repo
if [ ! -d .git ]; then
    git init
    echo "Initialized git repo"
else
    echo "Git repo already exists"
fi

# Stage all files
git add -A
if git diff --cached --quiet; then
    echo "No changes to commit"
else
    git commit -m "Initial commit: SP-404 Jam Box

Complete SD card builder for SP-404A/SX sampler with:
- 10-bank genre layout (lo-fi hip-hop, witch house, nu-rave, electroclash, funk, IDM, ambient, utility)
- Sample curation pipeline (download → organize → pick → convert → deploy)
- Numpy-synthesized novelty FX bank
- Comprehensive documentation and Claude Code integration guide
- All samples sourced from MusicRadar SampleRadar (royalty-free)"
fi

# Create GitHub repo
echo ""
echo "Creating GitHub repo..."
gh repo create sp404-jambox --public --source=. --description "SP-404A/SX sampler SD card builder — genre banks, sample curation pipeline, and jam-ready deployment" --push

echo ""
echo "=== Done! ==="
echo "Repo: https://github.com/$GH_USER/sp404-jambox"
