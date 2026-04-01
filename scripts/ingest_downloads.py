#!/usr/bin/env python3
"""
Ingest sample packs from ~/Downloads into the SP-404 sample library.
1. Find sample pack folders (RAR archives or already-extracted WAVs)
2. Extract RAR archives
3. Categorize WAVs by filename/folder keywords
4. Copy to ~/Music/SP404-Sample-Library/ in the right category

Usage:
    python scripts/ingest_downloads.py              # process all packs
    python scripts/ingest_downloads.py --dry-run     # show what would happen
    python scripts/ingest_downloads.py --watch       # keep watching for new packs
"""
import os, sys, re, shutil, glob, time, argparse, subprocess

DOWNLOADS = os.path.expanduser("~/Downloads")
LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
RAW_ARCHIVE = os.path.join(LIBRARY, "_RAW-DOWNLOADS")

# Patterns that identify sample pack folders (vs. music albums)
SAMPLE_PACK_SUFFIXES = [
    'WAV-MASCHiNE', 'WAV-FMASCHiNE', 'WAV-EXPANSION', 'WAV-SONiTUS',
    'MULTiFORMAT-MASCHiNE', 'WAV-DISCOVER', 'WAV-FANTASTiC',
    'WAV-DECiBEL', 'WAV-PHOTONE', 'WAV-AUDIOSTRiKE',
]

# Already-processed marker file
MARKER = '.sp404-ingested'


def is_sample_pack(dirname):
    """Check if a directory name looks like a sample pack."""
    for suffix in SAMPLE_PACK_SUFFIXES:
        if suffix in dirname:
            return True
    # Also match folders that are clearly sample-related
    name_lower = dirname.lower()
    if any(kw in name_lower for kw in ['prime loops', 'sample magic', 'loopmasters']):
        return True
    return False


def has_rar_files(folder):
    """Check if folder contains RAR archives."""
    return any(f.endswith('.rar') for f in os.listdir(folder))


def extract_rar(folder, dest):
    """Extract RAR archive from a folder using unar."""
    rar_file = None
    for f in os.listdir(folder):
        if f.endswith('.rar'):
            rar_file = os.path.join(folder, f)
            break
    if not rar_file:
        return False

    os.makedirs(dest, exist_ok=True)
    print(f"  Extracting: {os.path.basename(rar_file)}...")
    result = subprocess.run(
        ['/opt/homebrew/bin/unar', '-o', dest, '-f', rar_file],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  Extract failed: {result.stderr[:200]}")
        return False
    return True


def categorize_wav(filepath, pack_name):
    """Determine library category for a WAV file based on filename and path."""
    fname = os.path.basename(filepath).lower()
    dirpath = os.path.dirname(filepath).lower()
    parts = (fname + ' ' + dirpath).lower()

    # Drum hits
    if re.search(r'\bkick|bd\b|bassdrum', parts):
        return 'Drums/Kicks'
    if re.search(r'\bsnare|snr|sd\b|rimshot', parts):
        return 'Drums/Snares-Claps'
    if re.search(r'\bclap|handclap', parts):
        return 'Drums/Snares-Claps'
    if re.search(r'\bhi.?hat|hh\b|closed.?hat|open.?hat|hihat', parts):
        return 'Drums/Hi-Hats'
    if re.search(r'\bcymbal|crash|ride|splash', parts):
        return 'Drums/Percussion'
    if re.search(r'\bperc|shaker|tamb|conga|bongo|tom\b|cowbell|clave|rim', parts):
        return 'Drums/Percussion'

    # Drum loops
    if re.search(r'\bdrum.?loop|beat.?loop|break|drum.?break|full.?loop|top.?loop', parts):
        return 'Drums/Drum-Loops'
    if re.search(r'\b(loop|groove|pattern)\b', parts) and re.search(r'\b(drum|beat|perc|hat)\b', parts):
        return 'Drums/Drum-Loops'

    # Vocals
    if re.search(r'\bvocal|voice|vox|sing|choir|spoken|whisper|shout', parts):
        return 'Vocals/Chops'

    # Bass
    if re.search(r'\bbass|sub\b|808\b', parts) and not re.search(r'\bdrum', parts):
        return 'Melodic/Bass'

    # Guitar
    if re.search(r'\bguitar|gtr|riff\b|strum', parts):
        return 'Melodic/Guitar'

    # Keys / Piano
    if re.search(r'\bpiano|keys|rhodes|organ|clav|ep\b|electric.?piano', parts):
        return 'Melodic/Keys-Piano'

    # Synths and pads
    if re.search(r'\bsynth|pad\b|lead\b|arp\b|pluck|stab|chord', parts):
        return 'Melodic/Synths-Pads'

    # Ambient / textural
    if re.search(r'\bambient|atmosphere|atmos|texture|drone|field|foley|noise|space', parts):
        return 'Ambient-Textural/Atmospheres'

    # FX / SFX
    if re.search(r'\bfx|sfx|effect|riser|sweep|impact|down|transition|reverse', parts):
        return 'SFX/Stabs-Hits'

    # If it has "loop" in name, put in instrument loops
    if re.search(r'\bloop\b', parts):
        return 'Loops/Instrument-Loops'

    # Default: use pack context
    pack_lower = pack_name.lower()
    if 'drum' in pack_lower:
        return 'Drums/Percussion'
    if 'vocal' in pack_lower:
        return 'Vocals/Chops'
    if 'guitar' in pack_lower:
        return 'Melodic/Guitar'
    if 'piano' in pack_lower or 'keys' in pack_lower:
        return 'Melodic/Keys-Piano'
    if 'synth' in pack_lower or 'wave' in pack_lower:
        return 'Melodic/Synths-Pads'
    if 'ambient' in pack_lower or 'space' in pack_lower:
        return 'Ambient-Textural/Atmospheres'
    if 'funk' in pack_lower or 'soul' in pack_lower:
        return 'Loops/Instrument-Loops'
    if 'bass' in pack_lower:
        return 'Melodic/Bass'

    return 'Loops/Instrument-Loops'


def make_prefix(pack_name):
    """Create a short prefix from the pack name for organized files."""
    # Clean up scene naming: "Black.Octopus.Sound.Delicious.House.Drums" -> "BOS-House-Drums"
    clean = pack_name.split('.WAV')[0].split('.MULTi')[0]
    clean = clean.replace('.', ' ').replace('-', ' ').replace('_', ' ')
    words = clean.split()
    # Remove common filler words
    skip = {'wav', 'maschine', 'expansion', 'sonitus', 'loops', 'samples', 'and', 'the', 'for'}
    words = [w for w in words if w.lower() not in skip]
    if len(words) > 4:
        words = words[:4]
    return '-'.join(words)


def ingest_pack(pack_dir, dry_run=False):
    """Process one sample pack folder."""
    pack_name = os.path.basename(pack_dir)
    marker_path = os.path.join(pack_dir, MARKER)

    if os.path.exists(marker_path):
        return 0  # Already processed

    print(f"\n{'='*60}")
    print(f"Processing: {pack_name}")

    # Step 1: Extract if needed
    extract_dir = pack_dir
    if has_rar_files(pack_dir):
        extract_dir = os.path.join(RAW_ARCHIVE, pack_name)
        if not os.path.exists(extract_dir) or not any(
            f.endswith('.wav') for _, _, files in os.walk(extract_dir) for f in files
        ):
            if dry_run:
                print(f"  Would extract RAR to: {extract_dir}")
            else:
                if not extract_rar(pack_dir, extract_dir):
                    return 0
        else:
            print(f"  Already extracted to: {extract_dir}")

    # Step 2: Find all WAV files
    wav_files = []
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if f.lower().endswith(('.wav', '.aif', '.aiff')):
                wav_files.append(os.path.join(root, f))

    if not wav_files:
        print(f"  No WAV files found")
        return 0

    print(f"  Found {len(wav_files)} audio files")

    # Step 3: Categorize and copy
    prefix = make_prefix(pack_name)
    counts = {}
    for wav in wav_files:
        category = categorize_wav(wav, pack_name)
        dest_dir = os.path.join(LIBRARY, category)
        fname = os.path.basename(wav)
        dest_path = os.path.join(dest_dir, f"{prefix}_{fname}")

        if os.path.exists(dest_path):
            continue

        if dry_run:
            counts[category] = counts.get(category, 0) + 1
        else:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(wav, dest_path)
            counts[category] = counts.get(category, 0) + 1

    for cat in sorted(counts):
        print(f"  → {cat}: {counts[cat]} files")
    total = sum(counts.values())
    print(f"  Total: {total} files {'would be ' if dry_run else ''}organized")

    # Mark as processed and move out of Downloads
    if not dry_run and total > 0:
        with open(marker_path, 'w') as f:
            f.write(f"Ingested {total} files at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Move the processed pack folder to _RAW-DOWNLOADS to declutter ~/Downloads
        archive_dest = os.path.join(RAW_ARCHIVE, pack_name)
        if pack_dir.startswith(DOWNLOADS) and not os.path.exists(archive_dest):
            try:
                shutil.move(pack_dir, archive_dest)
                print(f"  Moved to: {archive_dest}")
            except Exception as e:
                print(f"  Could not move pack: {e}")

    return total


def find_sample_packs():
    """Find sample pack folders in Downloads."""
    packs = []
    for item in sorted(os.listdir(DOWNLOADS)):
        full_path = os.path.join(DOWNLOADS, item)
        if not os.path.isdir(full_path):
            continue
        if is_sample_pack(item):
            packs.append(full_path)
    return packs


def main():
    parser = argparse.ArgumentParser(description='Ingest sample packs from Downloads')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen')
    parser.add_argument('--watch', action='store_true', help='Keep watching for new packs')
    parser.add_argument('--interval', type=int, default=60, help='Watch interval in seconds')
    args = parser.parse_args()

    os.makedirs(LIBRARY, exist_ok=True)
    os.makedirs(RAW_ARCHIVE, exist_ok=True)

    while True:
        packs = find_sample_packs()
        if not packs:
            if not args.watch:
                print("No sample packs found in Downloads.")
                break
        else:
            total = 0
            for pack in packs:
                total += ingest_pack(pack, dry_run=args.dry_run)

            print(f"\n{'='*60}")
            print(f"Processed {len(packs)} packs, {total} files organized")
            print(f"Library: {LIBRARY}")

        if not args.watch:
            break

        print(f"\nWatching for new packs (every {args.interval}s)... Ctrl+C to stop")
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
