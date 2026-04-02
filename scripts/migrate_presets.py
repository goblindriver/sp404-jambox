#!/usr/bin/env python3
"""
One-time migration: convert current bank_config.yaml into preset files + default set.

Usage:
    python scripts/migrate_presets.py              # migrate
    python scripts/migrate_presets.py --dry-run    # preview only
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preset_utils import (
    _load_config, _save_config, bank_to_preset, save_preset,
    save_set, slugify, BANK_LETTERS, PRESETS_DIR, SETS_DIR
)

# Map bank letters to categories
BANK_CATEGORIES = {
    'b': 'genre',   # Sessions
    'c': 'genre',   # Drum Loops
    'd': 'genre',   # Funk
    'e': 'genre',   # Disco
    'f': 'genre',   # Electroclash
    'g': 'genre',   # Nu-Rave
    'h': 'genre',   # Aggressive
    'i': 'utility', # Textures & Transitions
    'j': 'utility', # Utility & Fun
}


def main():
    parser = argparse.ArgumentParser(description='Migrate bank_config.yaml to presets')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    args = parser.parse_args()

    config = _load_config()
    set_banks = {}

    print("Migrating bank_config.yaml to preset system...")
    print(f"Presets dir: {PRESETS_DIR}")
    print(f"Sets dir: {SETS_DIR}")
    print()

    for letter in BANK_LETTERS:
        bank_key = f'bank_{letter}'
        bank = config.get(bank_key, {})
        name = bank.get('name', f'Bank {letter.upper()}')

        if not bank.get('pads'):
            print(f"  Bank {letter.upper()}: {name} — no pads, skipping")
            set_banks[letter] = None
            continue

        preset = bank_to_preset(letter, config)
        if not preset:
            print(f"  Bank {letter.upper()}: {name} — could not extract preset")
            set_banks[letter] = None
            continue

        category = BANK_CATEGORIES.get(letter, 'community')
        ref = f"{category}/{preset['slug']}"

        print(f"  Bank {letter.upper()}: {name}")
        print(f"    → presets/{ref}.yaml ({len(preset['pads'])} pads, {preset.get('bpm')} BPM)")
        print(f"    Tags: {preset.get('tags', [])}")

        if not args.dry_run:
            save_preset(preset, category=category)

        set_banks[letter] = ref

    # Create default set
    set_data = {
        'name': 'Default Set',
        'slug': 'default',
        'author': 'jambox',
        'created': '2026-04-01',
        'notes': 'Original v3 bank layout — funk/disco/electroclash/nu-rave/aggressive',
        'banks': set_banks,
    }

    print(f"\n  Set: default")
    for letter, ref in set_banks.items():
        status = ref or '(empty)'
        print(f"    {letter.upper()}: {status}")

    if not args.dry_run:
        save_set(set_data)
        print(f"\n  → sets/default.yaml")

    # Update bank_config.yaml with preset references and active_set
    if not args.dry_run:
        for letter in BANK_LETTERS:
            bank_key = f'bank_{letter}'
            ref = set_banks.get(letter)
            if ref:
                config[bank_key]['preset'] = ref
        config['active_set'] = 'default'
        _save_config(config)
        print(f"\n  → bank_config.yaml updated (active_set: default, preset refs added)")

    print("\nDone!" if not args.dry_run else "\nDry run complete — no files written.")


if __name__ == '__main__':
    main()
