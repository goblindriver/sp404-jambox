#!/bin/bash
# Copy SP-404 jam box files to SD card
# Run this from Terminal on your Mac:
#   bash ~/path-to/SP-404SX/copy_to_sd.sh

SD_CARD="/Volumes/SP-404SX"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

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

# Copy ROLAND folder (contains SMPL with all 110 WAVs)
echo "Copying ROLAND folder (samples)..."
rsync -av --progress "$SOURCE_DIR/ROLAND/" "$SD_CARD/ROLAND/"

# Copy PAD_MAP.txt cheat sheet
echo ""
echo "Copying PAD_MAP.txt..."
cp -v "$SOURCE_DIR/PAD_MAP.txt" "$SD_CARD/PAD_MAP.txt"

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
ls -la "$SD_CARD/ROLAND/SP-404SX/SMPL/" | wc -l
echo "sample files copied."
echo ""
echo "Eject the card safely before removing!"
