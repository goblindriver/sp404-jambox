#!/usr/bin/env python3
"""Cross-media taste profiler for RL training.

Reads across ALL media collections — movies, music, TV, anime, books,
audiobooks, games, video productions — to build a comprehensive taste
fingerprint. This becomes the training signal for what "good" means
in the context of SP-404 bank curation.

Output: JSON taste profile with weighted vibe/genre/energy/texture
preferences derived from the full media collection.

Usage:
    python scripts/taste_profiler.py                   # full profile
    python scripts/taste_profiler.py --export           # export for training
    python scripts/taste_profiler.py --summary          # quick overview
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from jambox_config import load_settings_for_script

SETTINGS = load_settings_for_script(__file__)
REPO_DIR = SETTINGS["REPO_DIR"]

# External drive paths
QNAP = "/Volumes/Temp QNAP"
DROBO = "/Volumes/Jansen's FL Drobo"

# ── Vibe signal mappings ──

# Book topics → vibe weights
BOOK_CATEGORY_VIBES = {
    'The Dark Arts': {'dark': 3, 'eerie': 3, 'dreamy': 1},
    'Fiction': {'dark': 1, 'dreamy': 1, 'nostalgic': 1},
    'Psychology and Sociology': {'tense': 1, 'eerie': 1},
    'Science and Engineering': {'eerie': 1},
    'History': {'nostalgic': 2, 'soulful': 1},
    'Arts and Entertainment': {'playful': 1, 'dreamy': 1},
    'Pop Culture': {'playful': 1, 'nostalgic': 1},
    'Screenprinting': {'gritty': 2},
    'Self Help': {'uplifting': 1},
}

# Audiobook author → vibe signals
AUTHOR_VIBES = {
    'Chuck Palahniuk': {'dark': 3, 'gritty': 3, 'aggressive': 2},
    'Cormac McCarthy': {'dark': 3, 'gritty': 2, 'melancholic': 2},
    'Clive Barker': {'dark': 3, 'eerie': 3, 'aggressive': 1},
    'Carl Jung': {'dreamy': 2, 'eerie': 2, 'dark': 1},
    'Albert Hofmann': {'dreamy': 3, 'eerie': 2, 'playful': 1},
    'Frank Herbert': {'eerie': 2, 'dark': 2, 'tense': 2},
    'William Gibson': {'dark': 2, 'gritty': 2, 'tense': 1},
    'Neil Gaiman': {'dreamy': 2, 'dark': 2, 'playful': 1},
    'Brandon Sanderson': {'hype': 2, 'dreamy': 1},
    'Ian Banks': {'dark': 1, 'eerie': 2, 'tense': 1},
    'Michael Crichton': {'tense': 2, 'hype': 1},
    'Adam Neville': {'dark': 3, 'eerie': 3, 'tense': 2},
    'Richard Matheson': {'dark': 2, 'eerie': 2, 'tense': 1},
    'Caitlin Doughty': {'dark': 2, 'mellow': 1},
    'Louise Erdrich': {'soulful': 2, 'nostalgic': 2},
    'Gemma Files': {'dark': 2, 'eerie': 2},
    'Craig DiLouie': {'dark': 2, 'aggressive': 2, 'tense': 1},
    'Don Winslow': {'gritty': 3, 'tense': 2, 'aggressive': 1},
    'Robert Jordan': {'hype': 1, 'dreamy': 1},
    'Yuval Noah Harari': {'nostalgic': 1},
}

# Game platform → aesthetic vibe (retro consoles = nostalgic)
GAME_PLATFORM_VIBES = {
    'Atari': {'nostalgic': 3, 'playful': 1},
    'NES': {'nostalgic': 3, 'playful': 2, 'hype': 1},
    'SNES': {'nostalgic': 3, 'dreamy': 1, 'hype': 1},
    'Genesis': {'nostalgic': 2, 'aggressive': 1, 'hype': 1},
    'N64': {'nostalgic': 2, 'playful': 2},
    'GameBoy': {'nostalgic': 3, 'mellow': 1},
    'PSX': {'nostalgic': 2, 'dark': 1},
    'Dreamcast': {'nostalgic': 2, 'playful': 1},
    'Arcade': {'hype': 2, 'playful': 2, 'nostalgic': 1},
    'Neo Geo': {'hype': 2, 'aggressive': 1},
    'MSX': {'nostalgic': 3},
    'Amiga': {'nostalgic': 2, 'dreamy': 1},
}

# Film genre keywords in own productions → vibe
OWN_FILM_VIBES = {
    'Ancient Forest': {'dreamy': 2, 'mellow': 1, 'eerie': 1},
    'Benefactor': {'soulful': 1, 'dark': 1},
    'North Dakota Backroads': {'nostalgic': 2, 'mellow': 2},
    'NorwestPassages': {'nostalgic': 2, 'dreamy': 1},
    'Urban Harvest': {'gritty': 1, 'soulful': 1},
    'urbanexploration': {'eerie': 2, 'gritty': 2},
    'RIESAGE': {'nostalgic': 1, 'soulful': 1},
    'The Lost Smile': {'melancholic': 2, 'soulful': 1},
    'PrairieTrilogy': {'nostalgic': 3, 'soulful': 2},
}


def _scan_dir(path):
    """List directory contents, returning [] if not accessible."""
    try:
        return os.listdir(path)
    except OSError:
        return []


def profile_books():
    """Extract taste signal from book collection."""
    vibes = defaultdict(float)
    inventory = {}

    books_dir = os.path.join(QNAP, "Books")
    for category in _scan_dir(books_dir):
        cat_path = os.path.join(books_dir, category)
        if not os.path.isdir(cat_path):
            continue
        count = len(_scan_dir(cat_path))
        inventory[category] = count
        for vibe, weight in BOOK_CATEGORY_VIBES.get(category, {}).items():
            vibes[vibe] += weight * count

    # MYanonamouse (occult/psychedelia collection)
    myan_dir = os.path.join(QNAP, "MYanonamouse")
    myan_count = len(_scan_dir(myan_dir))
    if myan_count > 0:
        inventory['MYanonamouse (occult/psychedelia)'] = myan_count
        vibes['dark'] += myan_count * 0.5
        vibes['eerie'] += myan_count * 0.5
        vibes['dreamy'] += myan_count * 0.3

    # Calibre libraries
    for lib_name in ('Calibre Library', 'Calibre Master Library'):
        lib_path = os.path.join(QNAP, lib_name)
        count = len(_scan_dir(lib_path))
        if count:
            inventory[lib_name] = count

    return {'vibes': dict(vibes), 'inventory': inventory, 'source': 'books'}


def profile_audiobooks():
    """Extract taste signal from audiobook collection."""
    vibes = defaultdict(float)
    inventory = {}

    ab_dir = os.path.join(QNAP, "Audiobooks")
    for author in _scan_dir(ab_dir):
        if not os.path.isdir(os.path.join(ab_dir, author)):
            continue
        inventory[author] = 1
        for vibe, weight in AUTHOR_VIBES.get(author, {}).items():
            vibes[vibe] += weight

    return {'vibes': dict(vibes), 'inventory': inventory, 'source': 'audiobooks'}


def profile_games():
    """Extract taste signal from retro game collection."""
    vibes = defaultdict(float)
    inventory = {}

    games_dir = os.path.join(QNAP, "GazelleGames")
    for item in _scan_dir(games_dir):
        item_lower = item.lower()
        for platform, pvibes in GAME_PLATFORM_VIBES.items():
            if platform.lower() in item_lower:
                inventory[item] = platform
                for vibe, weight in pvibes.items():
                    vibes[vibe] += weight
                break

    return {'vibes': dict(vibes), 'inventory': inventory, 'source': 'games',
            'total_items': len(_scan_dir(games_dir))}


def profile_own_films():
    """Extract taste signal from personal video productions."""
    vibes = defaultdict(float)
    inventory = {}

    film_dir = os.path.join(QNAP, "Video Production", "Finished Movies")
    for f in _scan_dir(film_dir):
        name = os.path.splitext(f)[0]
        inventory[name] = f
        for key, fvibes in OWN_FILM_VIBES.items():
            if key.lower() in name.lower():
                for vibe, weight in fvibes.items():
                    vibes[vibe] += weight
                break

    return {'vibes': dict(vibes), 'inventory': inventory, 'source': 'own_films'}


def profile_multitrack_sessions():
    """Extract taste from multitrack session collection (what you chose to record/mix)."""
    vibes = defaultdict(float)
    inventory = {}

    sessions_dir = os.path.join(QNAP, "Video Production", "Multitrack Sessions", "FUN SESSIONS")
    for artist in _scan_dir(sessions_dir):
        if not os.path.isdir(os.path.join(sessions_dir, artist)):
            continue
        if artist in ('MIXDOWNS',):
            continue
        inventory[artist] = True
        # Having multitrack sessions = deep interest in that artist's sound
        # Weight: soul/funk classics → warm/soulful, rock → aggressive/hype
        artist_lower = artist.lower()
        if any(k in artist_lower for k in ('marvin', 'stevie', 'bob marley', 'doobie')):
            vibes['soulful'] += 5
            vibes['warm'] += 3
            vibes['nostalgic'] += 3
        elif any(k in artist_lower for k in ('nirvana', 'nine inch', 'def leppard', 'queen')):
            vibes['aggressive'] += 4
            vibes['gritty'] += 3
            vibes['hype'] += 2
        elif any(k in artist_lower for k in ('phoenix', 'fdeluxe')):
            vibes['hype'] += 3
            vibes['playful'] += 2
        elif any(k in artist_lower for k in ('beatles',)):
            vibes['nostalgic'] += 4
            vibes['playful'] += 2
        elif any(k in artist_lower for k in ('counting crows', 'switchfoot')):
            vibes['soulful'] += 2
            vibes['nostalgic'] += 2

    return {'vibes': dict(vibes), 'inventory': inventory, 'source': 'multitrack_sessions'}


def profile_plex():
    """Get Plex movie/TV/music taste profile."""
    try:
        from plex_client import PlexMediaDB
        plex = PlexMediaDB()
        return plex.taste_profile()
    except Exception as e:
        return {'error': str(e)}


def build_production_profile():
    """Build the PRODUCTION profile — what Jambox should optimize for.

    Derived from: Tiger Dust Block Party bank vibes, genre preset descriptions,
    multitrack session choices (warm/hype artists weighted higher), and the
    fundamental insight that the SP-404 is the antidote to the darkness in the
    consumption profile, not a reflection of it.

    "We know how dark it is out there, and we're choosing to dance anyway."
    """
    # Base weights from Tiger Dust Block Party energy arc
    production_vibes = {
        'hype': 0.220,       # Funk Muscle, Disco Inferno, Caribbean Heat, Neon Rave, Peak Hour
        'warm': 0.200,       # Soul Kitchen, Dub Cooldown — the golden hour feeling
        'soulful': 0.180,    # Soul Kitchen, Boom Bap Cipher — the emotional core
        'nostalgic': 0.120,  # Dusty records, vinyl warmth, crate-dug texture
        'playful': 0.100,    # Electro Sweat, Weapons Cache — the fun factor
        'dreamy': 0.080,     # Dub Cooldown echoes, synth pads, spacious reverb
        'dark': 0.050,       # Contrast and tension — not the goal, but adds depth
        'aggressive': 0.050, # Peak Hour intensity, Boom Bap weight
    }

    return production_vibes


def build_full_profile():
    """Combine all media sources into consumption + production profiles.

    The consumption profile reflects what Jason consumes (dark, nostalgic, dreamy).
    The production profile reflects what Jambox should optimize for (hype, warm, soulful).
    Both are exported — consumption as context, production as target.
    """
    t0 = time.time()

    sources = {}
    sources['plex'] = profile_plex()
    sources['books'] = profile_books()
    sources['audiobooks'] = profile_audiobooks()
    sources['games'] = profile_games()
    sources['own_films'] = profile_own_films()
    sources['multitrack_sessions'] = profile_multitrack_sessions()

    # ── Consumption profile (all media combined) ──
    combined_vibes = defaultdict(float)
    plex_vibes = sources['plex'].get('vibe_weights', {})
    for vibe, weight in plex_vibes.items():
        combined_vibes[vibe] += weight * 100
    for src_name in ('books', 'audiobooks', 'games', 'own_films', 'multitrack_sessions'):
        src_vibes = sources[src_name].get('vibes', {})
        for vibe, weight in src_vibes.items():
            combined_vibes[vibe] += weight

    total = sum(combined_vibes.values()) or 1
    consumption = {k: round(v / total, 4)
                   for k, v in sorted(combined_vibes.items(), key=lambda x: -x[1])}

    # ── Production profile (what Jambox optimizes for) ──
    production = build_production_profile()

    elapsed = time.time() - t0

    return {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'build_time_sec': round(elapsed, 1),
        'consumption_profile': consumption,
        'production_profile': production,
        'philosophy': (
            "Consumption is context, not target. The world is dark — "
            "the SP-404 is the antidote. Quality 5 means 'makes people dance "
            "at a block party,' not 'sounds like a McCarthy novel.' The best "
            "Tiger Dust sounds live in the overlap: warm nostalgic funk that "
            "makes you dance but has dusty degraded character underneath."
        ),
        'sources': sources,
        'summary': {
            'top_consumption_vibes': list(consumption.keys())[:5],
            'top_production_vibes': list(production.keys())[:5],
            'top_plex_directors': list(sources['plex'].get('movie_directors', {}).keys())[:5],
            'audiobook_authors': list(sources['audiobooks'].get('inventory', {}).keys()),
            'multitrack_artists': list(sources['multitrack_sessions'].get('inventory', {}).keys()),
            'book_categories': list(sources['books'].get('inventory', {}).keys()),
        },
    }


def main():
    parser = argparse.ArgumentParser(description='Cross-media taste profiler')
    parser.add_argument('--export', action='store_true',
                        help='Export full profile as JSON for training')
    parser.add_argument('--summary', action='store_true', help='Quick overview')
    args = parser.parse_args()

    profile = build_full_profile()

    if args.export:
        data_dir = os.path.join(REPO_DIR, 'data')
        os.makedirs(data_dir, exist_ok=True)

        # Export both profiles
        consumption_path = os.path.join(data_dir, 'taste_profile_consumption.json')
        production_path = os.path.join(data_dir, 'taste_profile_production.json')
        combined_path = os.path.join(data_dir, 'taste_profile.json')

        with open(consumption_path, 'w') as f:
            json.dump({
                'mode': 'consumption',
                'description': 'What Jason consumes — context for vibe vocabulary, NOT the optimization target',
                'vibe_weights': profile['consumption_profile'],
                'sources': profile['sources'],
            }, f, indent=2)

        with open(production_path, 'w') as f:
            json.dump({
                'mode': 'production',
                'description': 'What Jambox optimizes for — quality_score 5 means makes people dance at a block party',
                'philosophy': profile['philosophy'],
                'vibe_weights': profile['production_profile'],
            }, f, indent=2)

        with open(combined_path, 'w') as f:
            json.dump(profile, f, indent=2)

        print(f"Exported:")
        print(f"  {consumption_path}")
        print(f"  {production_path}")
        print(f"  {combined_path}")
        return

    # Display
    print(f"\n{'='*60}")
    print(f"CROSS-MEDIA TASTE PROFILE")
    print(f"{'='*60}")

    print(f"\n--- PRODUCTION (optimization target) ---")
    for vibe, weight in profile['production_profile'].items():
        bar = '#' * int(weight * 60)
        print(f"  {vibe:15s} {weight:.3f} {bar}")

    print(f"\n--- CONSUMPTION (context, not target) ---")
    for vibe, weight in profile['consumption_profile'].items():
        bar = '#' * int(weight * 60)
        print(f"  {vibe:15s} {weight:.3f} {bar}")

    print(f"\n\"{profile['philosophy']}\"")

    print(f"\nSources:")
    s = profile['summary']
    print(f"  Top directors: {', '.join(s.get('top_plex_directors', []))}")
    print(f"  Audiobooks: {', '.join(s.get('audiobook_authors', [])[:6])}")
    print(f"  Multitrack sessions: {', '.join(s.get('multitrack_artists', [])[:6])}")
    print(f"\nBuilt in {profile['build_time_sec']}s")


if __name__ == '__main__':
    main()
