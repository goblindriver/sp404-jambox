#!/usr/bin/env python3
"""
Fetch samples for the SP-404 based on bank_config.yaml.
1. Search local library for matches
2. Fall back to Freesound.org for missing sounds
3. Download to library, convert, and stage for SD card

Usage:
    python scripts/fetch_samples.py              # all banks
    python scripts/fetch_samples.py --bank b     # single bank
    python scripts/fetch_samples.py --bank b --pad 1  # single pad
"""
import os, sys, glob, re, yaml, argparse, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from wav_utils import convert_and_tag, build_sp404_wav
import freesound_client as fs

LIBRARY = os.path.expanduser("~/Music/SP404-Sample-Library")
FREESOUND_DIR = os.path.join(LIBRARY, "Freesound")
CONFIG_PATH = os.path.join(REPO_DIR, "bank_config.yaml")
STAGING = os.path.join(REPO_DIR, "_CARD_STAGING")
SMPL_DIR = os.path.join(REPO_DIR, "sd-card-template", "ROLAND", "SP-404SX", "SMPL")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def score_local_file(filepath, query, bank_config):
    """Score how well a local file matches a pad query. Higher = better match."""
    fname = os.path.basename(filepath).lower()
    dirpath = os.path.dirname(filepath).lower()
    query_words = set(re.findall(r'[a-z]+', query.lower()))
    # Remove very common words that don't help matching
    stop_words = {'a', 'an', 'the', 'or', 'and', 'in', 'for', 'not', 'but', 'with', 'style'}
    query_words -= stop_words

    score = 0

    # Keyword matches in filename
    for word in query_words:
        if word in fname:
            score += 2
        if word in dirpath:
            score += 1

    # BPM matching
    bpm = bank_config.get('bpm')
    if bpm:
        # Look for BPM in filename like (110) or 110bpm
        bpm_matches = re.findall(r'(\d{2,3})(?:bpm|\((\d{2,3})\))', fname)
        for m in bpm_matches:
            file_bpm = int(m[0] or m[1])
            if abs(file_bpm - bpm) <= 5:
                score += 3
            elif abs(file_bpm - bpm) <= 15:
                score += 1

    # Directory context matching
    dir_parts = dirpath.split(os.sep)
    if any('drum' in p for p in dir_parts) and any(w in query_words for w in ['kick', 'snare', 'hat', 'drum', 'clap', 'percussion']):
        score += 2
    if any('bass' in p for p in dir_parts) and 'bass' in query_words:
        score += 2
    if any('synth' in p or 'pad' in p for p in dir_parts) and any(w in query_words for w in ['synth', 'pad', 'lead', 'arp']):
        score += 2
    if any('vocal' in p or 'voice' in p for p in dir_parts) and any(w in query_words for w in ['voice', 'vocal', 'spoken', 'whisper']):
        score += 2
    if any('fx' in p or 'sfx' in p for p in dir_parts) and any(w in query_words for w in ['fx', 'effect', 'riser', 'impact', 'scratch']):
        score += 2
    if any('loop' in p for p in dir_parts) and any(w in query_words for w in ['loop', 'beat', 'groove', 'break']):
        score += 1

    return score


def search_local(query, bank_config, min_score=3):
    """Search the local library for a matching sample.
    Returns (filepath, score) or (None, 0).
    """
    best_path = None
    best_score = 0

    # Walk organized library (skip _RAW-DOWNLOADS for now — it's messy)
    for root, dirs, files in os.walk(LIBRARY):
        # Skip raw downloads and freesound cache on first pass
        if '_RAW-DOWNLOADS' in root:
            continue
        for f in files:
            if not f.lower().endswith(('.wav', '.aif', '.aiff', '.mp3')):
                continue
            filepath = os.path.join(root, f)
            score = score_local_file(filepath, query, bank_config)
            if score > best_score:
                best_score = score
                best_path = filepath

    if best_score >= min_score:
        return best_path, best_score
    return None, 0


def fetch_pad(bank_letter, pad_number, pad_query, bank_config):
    """Fetch a sample for one pad. Returns the path to the staged file or None."""
    bank_name = bank_config.get('name', bank_letter)
    sp404_name = f"{bank_letter.upper()}{pad_number:07d}.WAV"
    staged_path = os.path.join(STAGING, sp404_name)

    # 1. Search local library
    local_path, score = search_local(pad_query, bank_config)
    if local_path:
        print(f"    LOCAL (score={score}): {os.path.basename(local_path)}")
        if convert_and_tag(local_path, staged_path, bank_letter.upper(), pad_number):
            return staged_path
        print(f"    Conversion failed, trying Freesound...")

    # 2. Search Freesound
    is_oneshot = pad_number <= 4
    dur_min = 0.1 if is_oneshot else 1.0
    dur_max = 10.0 if is_oneshot else 60.0

    # Build a good search query
    search_query = pad_query
    # Add bank genre context if helpful
    genre = bank_config.get('name', '')
    if genre and len(pad_query.split()) < 4:
        search_query = f"{pad_query} {genre}"

    print(f"    FREESOUND: searching '{search_query}'...")
    time.sleep(0.3)  # respect rate limits

    # Download to library
    dl_dir = os.path.join(FREESOUND_DIR, re.sub(r'[^\w\-]', '_', bank_name))
    os.makedirs(dl_dir, exist_ok=True)
    dl_base = re.sub(r'[^\w\-]', '_', pad_query)[:60]
    dl_path = os.path.join(dl_dir, f"{bank_letter}{pad_number}_{dl_base}")

    downloaded, sound_info = fs.search_and_download(
        search_query, dl_path, duration_min=dur_min, duration_max=dur_max,
    )

    if not downloaded:
        # Try simpler query
        simple_words = pad_query.split()[:3]
        simple_query = ' '.join(simple_words)
        print(f"    FREESOUND: retrying '{simple_query}'...")
        time.sleep(0.3)
        downloaded, sound_info = fs.search_and_download(
            simple_query, dl_path, duration_min=dur_min, duration_max=dur_max,
        )

    if downloaded and sound_info:
        print(f"    FOUND: '{sound_info['name']}' by {sound_info['username']} ({sound_info['duration']:.1f}s)")

        # Save attribution
        attr_path = dl_path + '.attribution.txt'
        with open(attr_path, 'w') as f:
            f.write(f"Sound: {sound_info['name']}\n")
            f.write(f"Author: {sound_info['username']}\n")
            f.write(f"License: {sound_info['license']}\n")
            f.write(f"URL: https://freesound.org/people/{sound_info['username']}/sounds/{sound_info['id']}/\n")

        # Convert to SP-404 format
        if convert_and_tag(downloaded, staged_path, bank_letter.upper(), pad_number):
            return staged_path
        print(f"    Conversion failed for {downloaded}")
    else:
        print(f"    NO MATCH found on Freesound")

    return None


def fetch_bank(bank_letter, bank_config):
    """Fetch all samples for one bank."""
    name = bank_config.get('name', bank_letter)
    pads = bank_config.get('pads', {})
    if not pads:
        return

    print(f"\n=== Bank {bank_letter.upper()}: {name} ===")
    fetched = 0
    for pad_num, pad_query in pads.items():
        pad_num = int(pad_num)
        print(f"  Pad {pad_num}: {pad_query}")
        result = fetch_pad(bank_letter, pad_num, pad_query, bank_config)
        if result:
            fetched += 1
    print(f"  → {fetched}/{len(pads)} pads filled")
    return fetched


def main():
    parser = argparse.ArgumentParser(description='Fetch samples for SP-404 banks')
    parser.add_argument('--bank', '-b', help='Single bank letter to fetch (e.g., b)')
    parser.add_argument('--pad', '-p', type=int, help='Single pad number (use with --bank)')
    parser.add_argument('--freesound-only', action='store_true', help='Skip local library search')
    args = parser.parse_args()

    config = load_config()
    os.makedirs(STAGING, exist_ok=True)
    os.makedirs(FREESOUND_DIR, exist_ok=True)

    total_fetched = 0
    total_pads = 0

    for key, bank_config in config.items():
        if not key.startswith('bank_') or not bank_config:
            continue
        bank_letter = key.split('_')[1]

        if args.bank and bank_letter.lower() != args.bank.lower():
            continue

        pads = bank_config.get('pads', {})
        if not pads:
            continue

        if args.pad:
            # Single pad mode
            pad_query = pads.get(args.pad) or pads.get(str(args.pad))
            if pad_query:
                print(f"\n=== Bank {bank_letter.upper()} Pad {args.pad} ===")
                print(f"  {pad_query}")
                result = fetch_pad(bank_letter, args.pad, pad_query, bank_config)
                if result:
                    total_fetched += 1
                total_pads += 1
        else:
            fetched = fetch_bank(bank_letter, bank_config)
            if fetched:
                total_fetched += fetched
            total_pads += len(pads)

    print(f"\n{'='*50}")
    print(f"Total: {total_fetched}/{total_pads} pads filled")
    print(f"Staged in: {STAGING}")

    # Copy to SMPL template dir
    if total_fetched > 0:
        os.makedirs(SMPL_DIR, exist_ok=True)
        import shutil
        for f in glob.glob(os.path.join(STAGING, "*.WAV")):
            shutil.copy2(f, SMPL_DIR)
        print(f"Copied to: {SMPL_DIR}")


if __name__ == '__main__':
    main()
