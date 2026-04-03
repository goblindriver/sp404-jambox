#!/usr/bin/env python3
"""LLM-powered sample retagging — enriches _tags.json with smarter classifications.

Sends filename, path context, and existing rule-based tags to a local LLM,
which returns enriched/corrected tags based on cultural knowledge of music
production, genre conventions, and sample naming patterns.

Usage:
    python scripts/smart_retag.py                     # retag up to 50 untagged samples
    python scripts/smart_retag.py --type FX --limit 100  # retag FX samples
    python scripts/smart_retag.py --path "SFX/"       # retag samples under SFX/
    python scripts/smart_retag.py --all --limit 500   # retag everything, 500 at a time
    python scripts/smart_retag.py --dry-run            # preview without saving
    python scripts/smart_retag.py --file "Drums/Kicks/boom_808.wav"  # retag one file
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from jambox_config import ConfigError, load_settings_for_script
from taste_engine import get_system_prompt

SETTINGS = load_settings_for_script(__file__)
TAGS_FILE = SETTINGS["TAGS_FILE"]

# ═══════════════════════════════════════════════════════════
# Valid tag vocabularies (must match tag_library.py)
# ═══════════════════════════════════════════════════════════

VALID_TYPE_CODES = {
    "KIK", "SNR", "HAT", "CLP", "CYM", "RIM", "PRC", "BRK", "DRM",
    "BAS", "GTR", "KEY", "SYN", "PAD", "STR", "BRS", "PLK", "WND", "VOX", "SMP",
    "FX", "SFX", "AMB", "FLY", "TPE", "RSR",
}

VALID_VIBES = {
    "dark", "mellow", "hype", "dreamy", "gritty", "nostalgic", "eerie",
    "uplifting", "melancholic", "aggressive", "playful", "soulful",
    "ethereal", "tense", "chill",
}

VALID_TEXTURES = {
    "dusty", "clean", "lo-fi", "saturated", "airy", "crunchy", "warm",
    "glassy", "warbly", "bitcrushed", "tape-saturated", "bright", "muddy",
    "thin", "thick", "filtered", "raw",
}

VALID_GENRES = {
    "boom-bap", "lo-fi-hiphop", "trap", "drill", "funk", "soul", "jazz",
    "gospel", "r&b", "house", "uk-garage", "electronic", "footwork",
    "afrobeat", "city-pop", "psychedelic", "dub", "disco", "reggae",
    "latin", "classical", "ambient", "rock", "world",
}

VALID_ENERGIES = {"low", "mid", "high"}

VALID_PLAYABILITIES = {"one-shot", "loop", "chop-ready", "chromatic", "layer", "transition"}


# ═══════════════════════════════════════════════════════════
# LLM interface
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPT = get_system_prompt(
    "You classify audio samples for an SP-404 sampler library. "
    "Given a sample's filename, directory path, and current auto-generated tags, return improved tags.\n\n"
    "Rules:\n"
    "- Return ONLY valid JSON, no markdown fences, no explanation\n"
    "- type_code: use ONLY from the valid list. Correct misclassifications (e.g., a spoken word file tagged SFX should be VOX)\n"
    "- vibe: 1-2 tags from the valid list. Use your knowledge of the genre/context\n"
    "- texture: 1-2 tags from the valid list\n"
    "- genre: 1-2 tags from the valid list. Infer from pack name, artist references, style cues\n"
    "- energy: one of low/mid/high\n"
    "- playability: one of the valid options\n"
    "- rationale: one short sentence explaining your classification\n"
    "- If the existing tags are already good, return them unchanged\n"
    "- NEVER invent tags outside the valid lists"
)

BATCH_SIZE = 1  # one sample per LLM call — local models are too slow for batches


def _build_batch_prompt(samples):
    """Build a prompt for a batch of samples."""
    items = []
    for s in samples:
        items.append({
            "path": s["path"],
            "filename": os.path.basename(s["path"]),
            "current_type_code": s.get("type_code", ""),
            "current_vibe": s.get("vibe", []),
            "current_texture": s.get("texture", []),
            "current_genre": s.get("genre", []),
            "current_energy": s.get("energy", ""),
            "current_playability": s.get("playability", ""),
            "duration": s.get("duration", 0),
        })

    if len(items) == 1:
        # Single sample — simpler prompt for faster response
        return json.dumps({
            "task": "Classify this audio sample. Return a single JSON object.",
            "valid_type_codes": sorted(VALID_TYPE_CODES),
            "valid_vibes": sorted(VALID_VIBES),
            "valid_textures": sorted(VALID_TEXTURES),
            "valid_genres": sorted(VALID_GENRES),
            "valid_energies": sorted(VALID_ENERGIES),
            "valid_playabilities": sorted(VALID_PLAYABILITIES),
            "sample": items[0],
        })

    return json.dumps({
        "task": "Classify these audio samples. Return a JSON array with one object per sample.",
        "valid_type_codes": sorted(VALID_TYPE_CODES),
        "valid_vibes": sorted(VALID_VIBES),
        "valid_textures": sorted(VALID_TEXTURES),
        "valid_genres": sorted(VALID_GENRES),
        "valid_energies": sorted(VALID_ENERGIES),
        "valid_playabilities": sorted(VALID_PLAYABILITIES),
        "samples": items,
    })


def _call_llm(prompt):
    """Send prompt to LLM and return parsed response."""
    endpoint = SETTINGS.get("LLM_ENDPOINT", "").strip()
    if not endpoint:
        raise ConfigError("SP404_LLM_ENDPOINT is required for smart retagging")

    body = json.dumps({
        "model": SETTINGS.get("LLM_MODEL", "qwen3"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = SETTINGS.get("LLM_TIMEOUT", 30)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc.reason}") from exc

    # Extract content from response
    content = ""
    if isinstance(payload, dict):
        if "choices" in payload and payload["choices"]:
            message = payload["choices"][0].get("message", {})
            content = message.get("content", "")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        elif "message" in payload and isinstance(payload["message"], dict):
            content = payload["message"].get("content", "")

    # Strip code fences
    content = content.strip()
    if content.startswith("```"):
        import re
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    content = content.strip()

    if not content:
        raise RuntimeError("LLM returned empty response")

    return json.loads(content)


# ═══════════════════════════════════════════════════════════
# Tag validation and merging
# ═══════════════════════════════════════════════════════════

def _validate_and_merge(existing, llm_result):
    """Validate LLM output and merge into existing tags. Returns updated entry."""
    updated = dict(existing)

    # Type code — only update if valid and different
    tc = llm_result.get("type_code", "").upper().strip()
    if tc in VALID_TYPE_CODES:
        updated["type_code"] = tc

    # Vibe — validate each, merge with existing
    new_vibes = llm_result.get("vibe", [])
    if isinstance(new_vibes, str):
        new_vibes = [v.strip().lower() for v in new_vibes.split(",") if v.strip()]
    elif isinstance(new_vibes, list):
        new_vibes = [str(v).strip().lower() for v in new_vibes if str(v).strip()]
    valid_vibes = [v for v in new_vibes if v in VALID_VIBES]
    if valid_vibes:
        # LLM vibes replace existing (enrichment, not append)
        updated["vibe"] = valid_vibes[:2]

    # Texture
    new_tex = llm_result.get("texture", [])
    if isinstance(new_tex, str):
        new_tex = [t.strip().lower() for t in new_tex.split(",") if t.strip()]
    elif isinstance(new_tex, list):
        new_tex = [str(t).strip().lower() for t in new_tex if str(t).strip()]
    valid_tex = [t for t in new_tex if t in VALID_TEXTURES]
    if valid_tex:
        updated["texture"] = valid_tex[:2]

    # Genre
    new_genre = llm_result.get("genre", [])
    if isinstance(new_genre, str):
        new_genre = [g.strip().lower() for g in new_genre.split(",") if g.strip()]
    elif isinstance(new_genre, list):
        new_genre = [str(g).strip().lower() for g in new_genre if str(g).strip()]
    valid_genre = [g for g in new_genre if g in VALID_GENRES]
    if valid_genre:
        updated["genre"] = valid_genre[:2]

    # Energy
    energy = str(llm_result.get("energy", "")).strip().lower()
    if energy in VALID_ENERGIES:
        updated["energy"] = energy

    # Playability
    play = str(llm_result.get("playability", "")).strip().lower()
    if play in VALID_PLAYABILITIES:
        updated["playability"] = play

    # Rebuild flat tags set
    tags = set()
    tags.add(updated.get("type_code", "FX"))
    for v in updated.get("vibe", []):
        tags.add(v)
    for t in updated.get("texture", []):
        tags.add(t)
    for g in updated.get("genre", []):
        tags.add(g)
    tags.add(updated.get("source", "kit"))
    tags.add(updated.get("energy", "mid"))
    tags.add(updated.get("playability", "one-shot"))
    if updated.get("bpm"):
        tags.add(f"{updated['bpm']}bpm")
    updated["tags"] = sorted(tags)

    # Mark as LLM-enriched
    updated["llm_enriched"] = True
    updated["llm_rationale"] = llm_result.get("rationale", "")

    return updated


# ═══════════════════════════════════════════════════════════
# Selection and filtering
# ═══════════════════════════════════════════════════════════

def select_samples(db, type_code=None, path_prefix=None, single_file=None,
                   retag_all=False, skip_enriched=True, limit=50):
    """Select samples to retag based on filters."""
    candidates = []
    for rel_path, entry in db.items():
        # Skip already enriched unless forced
        if skip_enriched and entry.get("llm_enriched"):
            continue

        if single_file and rel_path != single_file:
            continue

        if type_code and entry.get("type_code") != type_code.upper():
            continue

        if path_prefix and not rel_path.startswith(path_prefix):
            continue

        candidates.append(entry)

    # Prioritize samples with sparse tags (fewer vibes/textures/genres)
    def sparseness(entry):
        score = 0
        if not entry.get("vibe"):
            score += 3
        if not entry.get("texture"):
            score += 2
        if not entry.get("genre"):
            score += 2
        return -score  # sort descending

    candidates.sort(key=sparseness)
    return candidates[:limit]


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def retag_samples(db, samples, dry_run=False, verbose=True):
    """Retag a list of samples using the LLM. Returns count of updated entries."""
    updated_count = 0
    total = len(samples)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = samples[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        if verbose:
            paths = [os.path.basename(s["path"]) for s in batch]
            print(f"\n[Batch {batch_num}/{total_batches}] {', '.join(paths[:3])}{'...' if len(paths) > 3 else ''}")

        try:
            prompt = _build_batch_prompt(batch)
            llm_results = _call_llm(prompt)

            # Handle both array and single-object responses
            if isinstance(llm_results, dict):
                llm_results = [llm_results]

            for i, sample in enumerate(batch):
                if i >= len(llm_results):
                    if verbose:
                        print(f"  ⚠ No LLM result for {sample['path']}")
                    continue

                result = llm_results[i]
                rel_path = sample["path"]

                if dry_run:
                    old_tc = sample.get("type_code", "?")
                    new_tc = result.get("type_code", old_tc)
                    old_vibe = sample.get("vibe", [])
                    new_vibe = result.get("vibe", old_vibe)
                    rationale = result.get("rationale", "")
                    tc_changed = " ← CHANGED" if new_tc.upper() != old_tc else ""
                    print(f"  {rel_path}")
                    print(f"    type: {old_tc} → {new_tc}{tc_changed}")
                    print(f"    vibe: {old_vibe} → {new_vibe}")
                    print(f"    reason: {rationale}")
                else:
                    updated = _validate_and_merge(sample, result)
                    db[rel_path] = updated
                    updated_count += 1

                    if verbose:
                        tc_change = ""
                        if updated["type_code"] != sample.get("type_code"):
                            tc_change = f" (was {sample.get('type_code', '?')})"
                        print(f"  ✓ {rel_path}: {updated['type_code']}{tc_change} | "
                              f"vibe={updated.get('vibe', [])} | "
                              f"genre={updated.get('genre', [])}")

        except Exception as e:
            print(f"  ✗ Batch {batch_num} failed: {e}")
            continue

        # Brief pause between batches to be nice to the LLM
        if batch_start + BATCH_SIZE < total:
            time.sleep(0.5)

    return updated_count


def main():
    parser = argparse.ArgumentParser(description="LLM-powered smart sample retagging")
    parser.add_argument("--type", help="Filter by type code (e.g., FX, SFX, VOX)")
    parser.add_argument("--path", help="Filter by path prefix (e.g., 'SFX/')")
    parser.add_argument("--file", help="Retag a single file by relative path")
    parser.add_argument("--all", action="store_true", help="Include all samples, not just sparse ones")
    parser.add_argument("--force", action="store_true", help="Re-process already LLM-enriched samples")
    parser.add_argument("--limit", type=int, default=50, help="Max samples to process (default: 50)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without saving")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()

    # Load tag database
    if not os.path.exists(TAGS_FILE):
        print(f"Tag database not found: {TAGS_FILE}")
        print("Run: python scripts/tag_library.py first")
        sys.exit(1)

    with open(TAGS_FILE) as fh:
        db = json.load(fh)
    print(f"Loaded {len(db)} samples from tag database")

    # Select samples
    samples = select_samples(
        db,
        type_code=args.type,
        path_prefix=args.path,
        single_file=args.file,
        retag_all=args.all,
        skip_enriched=not args.force,
        limit=args.limit,
    )

    if not samples:
        print("No samples matched the filter criteria.")
        if not args.force:
            print("(Use --force to re-process already enriched samples)")
        sys.exit(0)

    print(f"Selected {len(samples)} samples to retag")
    if args.dry_run:
        print("(DRY RUN — no changes will be saved)\n")

    # Retag
    t0 = time.time()
    updated = retag_samples(db, samples, dry_run=args.dry_run, verbose=not args.quiet)
    elapsed = time.time() - t0

    if args.dry_run:
        print(f"\nDry run complete — {len(samples)} samples previewed in {elapsed:.1f}s")
    else:
        # Save
        with open(TAGS_FILE, "w") as fh:
            json.dump(db, fh, indent=1, sort_keys=True)
        print(f"\nUpdated {updated} samples in {elapsed:.1f}s")
        print(f"Saved to {TAGS_FILE}")

    # Summary of changes
    enriched = sum(1 for e in db.values() if e.get("llm_enriched"))
    print(f"Total LLM-enriched samples in library: {enriched}/{len(db)}")


if __name__ == "__main__":
    main()
