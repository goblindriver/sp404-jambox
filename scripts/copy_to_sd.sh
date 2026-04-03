#!/bin/bash
# Copy SP-404 jam box files to SD card
# Run this from Terminal on your Mac:
#   bash ~/path-to/SP-404SX/copy_to_sd.sh

set -euo pipefail

SD_CARD="${SP404_SD_CARD:-/Volumes/SP-404SX}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/sd-card-template"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -z "$SD_CARD" ] || [ "$SD_CARD" = "/" ]; then
    echo "ERROR: Refusing to copy to unsafe SD card path: $SD_CARD"
    exit 1
fi
if [ ! -d "$SOURCE_DIR/ROLAND" ]; then
    echo "ERROR: Source card template not found at $SOURCE_DIR/ROLAND"
    exit 1
fi

# Check SD card is mounted
if [ ! -d "$SD_CARD" ]; then
    echo "ERROR: SD card not found at $SD_CARD"
    echo "Make sure the card is inserted and mounted."
    exit 1
fi

echo "=== SP-404 Jam Box SD Card Setup ==="
echo "Source: $SOURCE_DIR"
echo "Destination: $SD_CARD"
echo ""

# Copy ROLAND folder (contains SMPL with samples + PAD_INFO.BIN, and PTN with patterns)
# Exclude macOS resource forks and git files that confuse the SP-404
echo "Copying ROLAND folder (samples + patterns)..."
rsync -av --progress \
    --exclude="._*" --exclude=".DS_Store" --exclude=".gitkeep" \
    "$SOURCE_DIR/ROLAND/" "$SD_CARD/ROLAND/"

# Clean any macOS junk that may have been left from prior copies
echo ""
echo "Cleaning macOS resource fork files..."
find "$SD_CARD/ROLAND" -name "._*" -delete 2>/dev/null
find "$SD_CARD/ROLAND" -name ".DS_Store" -delete 2>/dev/null
find "$SD_CARD/ROLAND" -name ".gitkeep" -delete 2>/dev/null

# Copy PAD_MAP.txt cheat sheet
echo ""
echo "Copying PAD_MAP.txt..."
cp -v "$REPO_DIR/PAD_MAP.txt" "$SD_CARD/PAD_MAP.txt"

# Copy BKUP and FCTRY if they exist (factory data)
if [ -d "$SOURCE_DIR/BKUP" ]; then
    echo "Copying BKUP folder..."
    rsync -av "$SOURCE_DIR/BKUP/" "$SD_CARD/BKUP/"
fi
if [ -d "$SOURCE_DIR/FCTRY" ]; then
    echo "Copying FCTRY folder..."
    rsync -av "$SOURCE_DIR/FCTRY/" "$SD_CARD/FCTRY/"
fi

echo ""
echo "=== Done! ==="
echo "Files on SD card:"
if [ -d "$SD_CARD/ROLAND/SP-404SX/SMPL" ]; then
    find "$SD_CARD/ROLAND/SP-404SX/SMPL" -type f -name "*.WAV" | wc -l
else
    echo "0"
fi
echo "sample files copied."
echo ""
echo "Eject the card safely before removing!"
