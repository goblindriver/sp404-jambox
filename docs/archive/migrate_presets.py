#!/usr/bin/env python3
"""
One-time migration: convert current bank_config.yaml into preset files.

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
    BANK_LETTERS, PRESETS_DIR
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
    bank_refs = {}

    print("Migrating bank_config.yaml to preset system...")
    print(f"Presets dir: {PRESETS_DIR}")
    print()

    for letter in BANK_LETTERS:
        bank_key = f'bank_{letter}'
        bank = config.get(bank_key, {})
        if not isinstance(bank, dict):
            print(f"  Bank {letter.upper()}: invalid config entry, skipping")
            bank_refs[letter] = None
            continue
        name = bank.get('name', f'Bank {letter.upper()}')

        if not bank.get('pads'):
            print(f"  Bank {letter.upper()}: {name} — no pads, skipping")
            bank_refs[letter] = None
            continue

        try:
            preset = bank_to_preset(letter, config)
        except (TypeError, ValueError) as exc:
            print(f"  Bank {letter.upper()}: {name} — migration failed ({exc})")
            bank_refs[letter] = None
            continue
        if not preset:
            print(f"  Bank {letter.upper()}: {name} — could not extract preset")
            bank_refs[letter] = None
            continue

        category = BANK_CATEGORIES.get(letter, 'community')
        ref = f"{category}/{preset['slug']}"

        print(f"  Bank {letter.upper()}: {name}")
        print(f"    → presets/{ref}.yaml ({len(preset['pads'])} pads, {preset.get('bpm')} BPM)")
        print(f"    Tags: {preset.get('tags', [])}")

        if not args.dry_run:
            save_preset(preset, category=category)

        bank_refs[letter] = ref

    print("\n  Preset refs by bank")
    for letter, ref in bank_refs.items():
        status = ref or '(empty)'
        print(f"    {letter.upper()}: {status}")

    # Update bank_config.yaml with preset references
    if not args.dry_run:
        for letter in BANK_LETTERS:
            bank_key = f'bank_{letter}'
            ref = bank_refs.get(letter)
            if ref:
                bank = config.get(bank_key)
                if not isinstance(bank, dict):
                    bank = {}
                    config[bank_key] = bank
                bank['preset'] = ref
        config.pop('active_set', None)
        _save_config(config)
        print("\n  → bank_config.yaml updated (preset refs added)")

    print("\nDone!" if not args.dry_run else "\nDry run complete — no files written.")


if __name__ == '__main__':
    main()
