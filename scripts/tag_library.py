#!/usr/bin/env python3
"""Auto-tag the SP-404 sample library using the TAGGING_SPEC dimensions.

Walks ~/Music/SP404-Sample-Library/, extracts tags from directory structure,
filenames, and audio duration, then saves a JSON tag database.

Tag dimensions (per TAGGING_SPEC.md):
  type_code  — 3-letter instrument/category code (KIK, SNR, SYN, etc.)
  vibe       — emotional mood (dark, chill, hype, etc.)
  texture    — sonic character (dusty, warm, bright, etc.)
  genre      — aesthetic lineage (boom-bap, house, funk, etc.)
  source     — how obtained (kit, dug, synth, field, etc.)
  energy     — intensity (low, mid, high)
  playability — usage intent (one-shot, loop, chop-ready, etc.)

Usage:
    python scripts/tag_library.py            # full scan
    python scripts/tag_library.py --update   # only new/changed files
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from jambox_config import LIBRARY_SKIP_DIRS, LONG_HOLD_DIRNAME, load_settings_for_script

try:
    from audio_analysis import analyze_audio, is_available as librosa_available
except ImportError:
    analyze_audio = None
    librosa_available = lambda: False

SETTINGS = load_settings_for_script(__file__)
LIBRARY = SETTINGS["SAMPLE_LIBRARY"]
TAGS_FILE = SETTINGS["TAGS_FILE"]
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}
FFPROBE = SETTINGS["FFPROBE_BIN"]
SKIP_DIRS = LIBRARY_SKIP_DIRS

# ═══════════════════════════════════════════════════════════
# Type Code Detection (3-letter codes per TAGGING_SPEC)
# ═══════════════════════════════════════════════════════════

# Directory name → type code
DIR_TYPE_MAP = {
    # Percussive
    "kicks": "KIK", "kick": "KIK",
    "snares": "SNR", "snare": "SNR", "snares-claps": "SNR",
    "claps": "CLP", "clap": "CLP",
    "hi-hats": "HAT", "hihats": "HAT", "hihat": "HAT", "hats": "HAT",
    "cymbals": "CYM", "cymbal": "CYM", "crashes": "CYM",
    "rimshots": "RIM", "rimshot": "RIM",
    "percussion": "PRC", "perc": "PRC",
    "drum-loops": "BRK", "drum loops": "BRK", "breaks": "BRK",
    # Melodic
    "bass": "BAS",
    "guitar": "GTR", "guitars": "GTR",
    "keys-piano": "KEY", "keys": "KEY", "piano": "KEY", "organ": "KEY",
    "synths-pads": "SYN", "synths": "SYN", "synth": "SYN",
    "pads": "PAD", "pad": "PAD",
    "strings": "STR", "orchestral": "STR",
    "brass": "BRS",
    "plucks": "PLK",
    "woodwind": "WND", "flute": "WND", "sax": "WND",
    "vocals": "VOX", "vocal": "VOX", "chops": "VOX",
    # Utility
    "fx": "FX", "sfx": "FX",
    "stabs-hits": "SFX", "stabs": "SFX", "hits": "SFX",
    "ambient-textural": "AMB", "ambient": "AMB", "atmospheres": "AMB",
    "foley": "FLY",
    "risers": "RSR", "sweeps": "RSR",
    "tape": "TPE", "vinyl": "TPE",
    "instrument-loops": "BRK",
}

# Filename patterns → type code (pre-compiled for hot-path performance)
FILENAME_TYPE_PATTERNS = [
    (re.compile(r"\bkick\b|\bbd\b|\bbass[\s_-]?drum\b"), "KIK"),
    (re.compile(r"\bsnare\b|\bsd\b|\bsnr\b"), "SNR"),
    (re.compile(r"\bclap\b|\bcp\b|\bsnap\b"), "CLP"),
    (re.compile(r"\bh(?:i[\s_-]?)?hat\b|\bhh\b|\bopen[\s_-]?h(?:at)?\b|\boh[\s_-]?hat\b|\bclosed[\s_-]?h(?:at)?\b|\bch[\s_-]?hat\b"), "HAT"),
    (re.compile(r"\bcymbal\b|\bcrash\b|\bride\b"), "CYM"),
    (re.compile(r"\brimshot\b|\brim\b"), "RIM"),
    (re.compile(r"\bperc\b|\bconga\b|\bbongo\b|\btom\b|\bshaker\b|\btambourine\b|\bcowbell\b"), "PRC"),
    (re.compile(r"\bbass\b|\bsub\b|\b808\b"), "BAS"),
    (re.compile(r"\bguitar\b|\bgtr\b"), "GTR"),
    (re.compile(r"\bkeys?\b|\bpiano\b|\borgan\b|\brhodes\b|\bwurlitzer\b|\bclavinet\b"), "KEY"),
    (re.compile(r"\bsynth\b|\blead\b|\barp\b|\bchord\b"), "SYN"),
    (re.compile(r"\bpad\b|\batmosphere\b|\batmos\b"), "PAD"),
    (re.compile(r"\bstring\b|\bviolin\b|\bcello\b|\bviola\b|\borchestra\b"), "STR"),
    (re.compile(r"\bbrass\b|\btrumpet\b|\btrombone\b"), "BRS"),
    (re.compile(r"\bpluck\b|\bpizz\b|\bkalimba\b|\bmbira\b|\bharp\b"), "PLK"),
    (re.compile(r"\bflute\b|\bclarinet\b|\bsax\b|\bsaxophone\b|\boboe\b|\bwoodwind\b"), "WND"),
    (re.compile(r"\bvox\b|\bvocal\b|\bvoice\b|\bchoir\b|\bspoken\b"), "VOX"),
    (re.compile(r"\briser\b|\bsweep\b|\bbuild\b"), "RSR"),
    (re.compile(r"\bfoley\b|\bfootstep\b"), "FLY"),
    (re.compile(r"\btape\b|\bvinyl\b|\bcrackle\b|\bhiss\b"), "TPE"),
    (re.compile(r"\bstab\b|\bhit\b|\bimpact\b|\bboom\b"), "SFX"),
    (re.compile(r"\bfx\b|\bsfx\b|\btransition\b"), "FX"),
    (re.compile(r"\bsampl\b|\bphrase\b|\bchop\b"), "BRK"),
]

# Top-level dir → broad category (for fallback)
DIR_CATEGORY_MAP = {
    "drums": "DRM",
    "melodic": "SYN",
    "loops": "BRK",
    "sfx": "FX",
    "vocals": "VOX",
    "ambient-textural": "AMB",
}

# ═══════════════════════════════════════════════════════════
# Vibe (mood) detection
# ═══════════════════════════════════════════════════════════

VIBE_KEYWORDS = {
    "dark": ["dark", "evil", "occult", "horror", "noir", "sinister"],
    "mellow": ["mellow", "calm", "gentle", "relaxed"],
    "hype": ["hype", "energy", "rave", "party", "anthem"],
    "dreamy": ["dreamy", "dream", "float", "lush"],
    "gritty": ["gritty", "grit", "dirty", "grimy"],
    "nostalgic": ["nostalgic", "vintage", "retro", "old-school", "oldschool"],
    "eerie": ["eerie", "creepy", "spooky", "haunted", "ghostly"],
    "uplifting": ["uplifting", "happy", "positive", "joyful"],
    "melancholic": ["melancholic", "sad", "lonely", "somber"],
    "aggressive": ["aggressive", "hard", "heavy", "industrial", "intense"],
    "playful": ["playful", "fun", "cartoon", "quirky", "weird", "funny"],
    "soulful": ["soulful", "gospel"],
    "ethereal": ["ethereal", "angelic", "heavenly"],
    "tense": ["tense", "suspense", "cinematic", "dramatic", "tension"],
    "chill": ["chill", "smooth", "muted"],
}

# ═══════════════════════════════════════════════════════════
# Texture (sonic character) detection
# ═══════════════════════════════════════════════════════════

TEXTURE_KEYWORDS = {
    "dusty": ["dusty", "dust"],
    "clean": ["clean", "pure", "clear"],
    "lo-fi": ["lo-fi", "lofi", "low-fi"],
    "saturated": ["saturated", "driven", "overdriven"],
    "airy": ["airy", "spacious", "open"],
    "crunchy": ["crunchy", "crunch", "crispy"],
    "warm": ["warm"],
    "glassy": ["glassy", "glass", "crystal", "crystalline"],
    "warbly": ["warbly", "warble", "wobble", "detuned", "woozy"],
    "bitcrushed": ["bitcrushed", "bitcrush", "8-bit", "8bit", "chiptune"],
    "tape": ["cassette", "tape-saturated"],
    "bright": ["bright"],
    "muddy": ["muddy", "murky"],
    "thin": ["thin"],
    "thick": ["thick", "fat", "dense"],
    "filtered": ["filtered", "filter", "muffled"],
    "raw": ["raw", "unprocessed"],
}

# ═══════════════════════════════════════════════════════════
# Genre detection
# ═══════════════════════════════════════════════════════════

GENRE_PATTERNS = [
    (re.compile(r"boom[\s_-]?bap"), "boom-bap"),
    (re.compile(r"lo-?fi[\s_-]?hip[\s_-]?hop"), "lo-fi-hiphop"),
    (re.compile(r"lo-?fi|lofi"), "lo-fi"),
    (re.compile(r"hip-?hop|hiphop"), "hiphop"),
    (re.compile(r"trap"), "trap"),
    (re.compile(r"drill"), "drill"),
    (re.compile(r"funk"), "funk"),
    (re.compile(r"soul"), "soul"),
    (re.compile(r"jazz"), "jazz"),
    (re.compile(r"gospel"), "gospel"),
    (re.compile(r"r&b|rnb"), "rnb"),
    (re.compile(r"house"), "house"),
    (re.compile(r"uk[\s_-]?garage"), "uk-garage"),
    (re.compile(r"\bgarage\b(?!\s*rock)"), "uk-garage"),
    (re.compile(r"techno"), "electronic"),
    (re.compile(r"electro[\s_-]?clash"), "electronic"),
    (re.compile(r"electro"), "electronic"),
    (re.compile(r"idm"), "electronic"),
    (re.compile(r"witch[\s_-]?house"), "electronic"),
    (re.compile(r"nu[\s_-]?rave"), "electronic"),
    (re.compile(r"synth[\s_-]?wave|synthwave"), "electronic"),
    (re.compile(r"80s[\s_-]?synth"), "electronic"),
    (re.compile(r"dnb|drum[\s_-]?(?:and|n|&)[\s_-]?bass"), "electronic"),
    (re.compile(r"dub[\s_-]?step"), "electronic"),
    (re.compile(r"footwork|juke"), "footwork"),
    (re.compile(r"afrobeat|afro"), "afrobeat"),
    (re.compile(r"city[\s_-]?pop"), "city-pop"),
    (re.compile(r"psychedelic|psych"), "psychedelic"),
    (re.compile(r"\bdub\b(?!step)"), "dub"),
    (re.compile(r"disco"), "disco"),
    (re.compile(r"reggae"), "reggae"),
    (re.compile(r"latin|salsa|bossa"), "latin"),
    (re.compile(r"classical|orchestral"), "classical"),
    (re.compile(r"ambient"), "ambient"),
    (re.compile(r"pop"), "pop"),
    (re.compile(r"rock"), "rock"),
    (re.compile(r"metal"), "rock"),
    (re.compile(r"punk"), "punk"),
    (re.compile(r"breakbeat"), "electronic"),
    (re.compile(r"glitch"), "electronic"),
    (re.compile(r"minimal"), "electronic"),
    (re.compile(r"tribal"), "world"),
    (re.compile(r"world"), "world"),
    (re.compile(r"industrial"), "industrial"),
    (re.compile(r"dancehall"), "dancehall"),
]

# ═══════════════════════════════════════════════════════════
# BPM + Key extraction
# ═══════════════════════════════════════════════════════════

BPM_PATTERNS = [
    re.compile(r"(\d{2,3})\s*bpm", re.IGNORECASE),
    re.compile(r"bpm\s*(\d{2,3})", re.IGNORECASE),
    re.compile(r"[\-_](\d{2,3})[\-_]", re.IGNORECASE),
    re.compile(r"\((\d{2,3})\)"),
]

KEY_PATTERN = re.compile(
    r"[\s_\-]([A-G][#bs]?)\s*(?:m(?:in(?:or)?)?|maj(?:or)?)?[\s_\-\.]",
    re.IGNORECASE,
)
KEY_PATTERN_SUFFIX = re.compile(
    r"[\s_\-]([A-G][#bs]?(?:m|min|maj)?)\s*\.",
    re.IGNORECASE,
)


def get_duration(filepath):
    """Get audio duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", filepath],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, FileNotFoundError):
        pass
    return 0.0


def extract_bpm(filename, dirpath):
    """Try to extract BPM from filename or directory path."""
    text = filename + " " + dirpath
    for pat in BPM_PATTERNS:
        m = pat.search(text)
        if m:
            bpm = int(m.group(1))
            if 50 <= bpm <= 250:
                return bpm
    return None


def extract_key(filename):
    """Try to extract musical key from filename. Normalizes # to s per spec."""
    for pat in [KEY_PATTERN, KEY_PATTERN_SUFFIX]:
        m = pat.search(filename)
        if m:
            raw = m.group(1).strip()
            if len(raw) >= 1:
                root = raw[0].upper()
                rest = raw[1:].replace("#", "s")
                return root + rest
    return None


# ═══════════════════════════════════════════════════════════
# Type code extraction
# ═══════════════════════════════════════════════════════════

def extract_type_code_from_dir(rel_path):
    """Get type code from directory structure."""
    parts = rel_path.lower().replace("\\", "/").split("/")
    for part in reversed(parts[:-1]):
        if part in DIR_TYPE_MAP:
            return DIR_TYPE_MAP[part]
    return None


def extract_type_code_from_filename(filename):
    """Get type code from filename patterns."""
    fname_lower = filename.lower().replace("_", " ").replace("-", " ")
    for pattern, code in FILENAME_TYPE_PATTERNS:
        if pattern.search(fname_lower):
            return code
    return None


def extract_type_code_from_category(rel_path):
    """Fallback: get type code from top-level directory."""
    parts = rel_path.lower().replace("\\", "/").split("/")
    if parts:
        return DIR_CATEGORY_MAP.get(parts[0])
    return None


def extract_type_code(rel_path, filename):
    """Extract 3-letter type code using all available signals.

    Priority: specific directory > filename pattern > broad directory > fallback.
    When the directory is a generic top-level category (Drums, Melodic, Loops, etc.),
    prefer the filename pattern since it's more specific.
    """
    dir_code = extract_type_code_from_dir(rel_path)
    fname_code = extract_type_code_from_filename(filename)
    cat_code = extract_type_code_from_category(rel_path)

    # If directory gives a specific code (not just a category fallback), trust it
    if dir_code:
        # But if filename contradicts with a more specific code, prefer filename
        # e.g., file named "kick_hard.wav" in /drums/percussion/ should be KIK not PRC
        if fname_code and fname_code != dir_code:
            # Filename wins for percussive specificity
            percussive_specific = {"KIK", "SNR", "CLP", "HAT", "CYM", "RIM"}
            if fname_code in percussive_specific and dir_code in ("PRC", "DRM", "BRK"):
                return fname_code
        return dir_code

    if fname_code:
        return fname_code
    if cat_code:
        return cat_code
    return "FX"  # fallback


# ═══════════════════════════════════════════════════════════
# Vibe + Texture extraction
# ═══════════════════════════════════════════════════════════

def extract_tags_from_keywords(text, keyword_map):
    """Generic: find matching tags from a keyword→tag mapping."""
    text_lower = text.lower().replace("-", " ").replace("_", " ")
    found = []
    for tag, keywords in keyword_map.items():
        for kw in keywords:
            kw_clean = kw.replace("-", " ")
            if kw_clean in text_lower:
                if tag not in found:
                    found.append(tag)
                break
    return found


# Infer vibe/texture from type_code and directory context when
# the filename/path keywords alone produce nothing.
TYPE_VIBE_DEFAULTS = {
    "KIK": [], "SNR": [], "HAT": [], "CLP": [], "CYM": [], "RIM": [],
    "PRC": [], "BRK": [],
    "BAS": [], "GTR": [], "KEY": [], "SYN": [],
    "PAD": ["dreamy"], "STR": ["soulful"], "BRS": [],
    "PLK": [], "WND": [],
    "VOX": [],
    "FX": [], "SFX": [], "RSR": [],
    "AMB": ["chill"], "FLY": [], "TPE": ["nostalgic"],
}

TYPE_TEXTURE_DEFAULTS = {
    "KIK": [], "SNR": [], "HAT": [], "CLP": [], "CYM": [], "RIM": [],
    "PRC": [], "BRK": ["raw"],
    "BAS": [], "GTR": [], "KEY": ["clean"], "SYN": [],
    "PAD": ["warm"], "STR": ["warm"], "BRS": ["bright"],
    "PLK": ["glassy"], "WND": ["airy"],
    "VOX": [],
    "FX": [], "SFX": [], "RSR": [],
    "AMB": ["airy"], "FLY": ["raw"], "TPE": ["warm"],
}

# Pack/directory name hints for vibe + texture
DIR_VIBE_HINTS = {
    "dark": "dark", "evil": "dark", "horror": "dark", "noir": "dark",
    "chill": "chill", "smooth": "chill", "mellow": "mellow",
    "lofi": "mellow", "lo-fi": "mellow",
    "hype": "hype", "energy": "hype", "rave": "hype", "party": "hype",
    "funk": "playful", "disco": "playful",
    "ambient": "dreamy", "ethereal": "ethereal",
    "industrial": "aggressive", "hard": "aggressive", "heavy": "aggressive",
    "vintage": "nostalgic", "retro": "nostalgic", "old": "nostalgic", "classic": "nostalgic",
    "soul": "soulful", "gospel": "soulful",
    "glitch": "tense", "cinematic": "tense",
}

DIR_TEXTURE_HINTS = {
    "lofi": "lo-fi", "lo-fi": "lo-fi", "low-fi": "lo-fi",
    "dusty": "dusty", "dust": "dusty",
    "clean": "clean", "pure": "clean", "crisp": "clean",
    "raw": "raw", "dirty": "raw", "gritty": "raw",
    "analog": "warm", "analogue": "warm", "tape": "warm", "vinyl": "warm",
    "digital": "clean", "fm": "glassy",
    "80s": "bright", "neon": "bright",
    "glitch": "bitcrushed", "8bit": "bitcrushed", "chiptune": "bitcrushed",
    "saturated": "saturated", "driven": "saturated",
}


def extract_vibe(rel_path, filename, type_code=None):
    """Extract vibe/mood tags from text, directory hints, and type defaults."""
    text = rel_path + " " + filename
    found = extract_tags_from_keywords(text, VIBE_KEYWORDS)

    # Directory/pack name hints
    if not found:
        dir_lower = rel_path.lower().replace("-", " ").replace("_", " ")
        for hint_word, vibe_tag in DIR_VIBE_HINTS.items():
            if hint_word in dir_lower and vibe_tag not in found:
                found.append(vibe_tag)
                break  # one hint is enough

    # Type-code defaults as last resort
    if not found and type_code and type_code in TYPE_VIBE_DEFAULTS:
        found = list(TYPE_VIBE_DEFAULTS[type_code])

    return found


def extract_texture(rel_path, filename, type_code=None):
    """Extract texture/sonic character tags from text, directory hints, and type defaults."""
    text = rel_path + " " + filename
    found = extract_tags_from_keywords(text, TEXTURE_KEYWORDS)

    # Directory/pack name hints
    if not found:
        dir_lower = rel_path.lower().replace("-", " ").replace("_", " ")
        for hint_word, tex_tag in DIR_TEXTURE_HINTS.items():
            if hint_word in dir_lower and tex_tag not in found:
                found.append(tex_tag)
                break

    # Type-code defaults as last resort
    if not found and type_code and type_code in TYPE_TEXTURE_DEFAULTS:
        found = list(TYPE_TEXTURE_DEFAULTS[type_code])

    return found


# ═══════════════════════════════════════════════════════════
# Genre extraction
# ═══════════════════════════════════════════════════════════

def extract_genres(rel_path):
    """Extract genre tags from path and filename."""
    text = rel_path.lower().replace("_", " ").replace("-", " ")
    genres = []
    for pattern, genre in GENRE_PATTERNS:
        if pattern.search(text):
            if genre not in genres:
                genres.append(genre)
    return genres


# ═══════════════════════════════════════════════════════════
# Source classification
# ═══════════════════════════════════════════════════════════

_RE_FIELD = re.compile(r"field[\s_-]?record|foley|nature|outdoor|ambience")
_RE_DUG = re.compile(r"vinyl[\s_-]?rip|crate|digg?ing|sampled|chop")
_RE_GENERATED = re.compile(r"generated|noise[\s_-]?gen|test[\s_-]?tone|sine|saw[\s_-]?wave")
_RE_PROCESSED = re.compile(r"mangled|granular|processed|glitch[\s_-]?fx")
_RE_SYNTH = re.compile(r"synth|analog|digital|fm|wave")
_RE_SPOKEN = re.compile(r"speech|spoken|dialogue")


def classify_source(rel_path, filename, type_code):
    """Classify sample source: kit, dug, synth, field, generated, processed."""
    text = (rel_path + " " + filename).lower()

    if _RE_FIELD.search(text):
        return "field"
    if _RE_DUG.search(text):
        return "dug"
    if _RE_GENERATED.search(text):
        return "generated"
    if _RE_PROCESSED.search(text):
        return "processed"

    if type_code in ("SYN", "PAD", "BAS") and _RE_SYNTH.search(text):
        return "synth"
    if type_code in ("AMB", "FLY"):
        return "field"
    if type_code in ("FX", "RSR", "SFX", "TPE"):
        return "processed"
    if type_code in ("VOX",) and _RE_SPOKEN.search(text):
        return "dug"

    return "kit"


# ═══════════════════════════════════════════════════════════
# Energy classification
# ═══════════════════════════════════════════════════════════

PERCUSSIVE_CODES = {"KIK", "SNR", "CLP", "HAT", "PRC", "CYM", "RIM", "BRK", "DRM"}
HIGH_ENERGY_GENRES = {"trap", "drill", "house", "electronic", "footwork", "rock"}
LOW_ENERGY_GENRES = {"ambient", "lo-fi-hiphop", "classical", "dub"}


def classify_energy(bpm, type_code, genres, vibes):
    """Classify energy as low/mid/high using a simple scoring model."""
    score = 0

    # BPM
    if bpm:
        if bpm < 80:
            score -= 2
        elif bpm > 130:
            score += 2
        elif bpm > 110:
            score += 1

    # Type code
    if type_code in PERCUSSIVE_CODES:
        score += 1
    if type_code in ("PAD", "AMB", "TPE"):
        score -= 1

    # Genre
    for g in genres:
        if g in HIGH_ENERGY_GENRES:
            score += 1
            break
    for g in genres:
        if g in LOW_ENERGY_GENRES:
            score -= 1
            break

    # Vibe
    for v in vibes:
        if v in ("hype", "aggressive"):
            score += 2
        elif v in ("chill", "mellow", "dreamy"):
            score -= 2
        elif v in ("dark", "tense"):
            score += 1

    if score <= -2:
        return "low"
    elif score >= 2:
        return "high"
    return "mid"


# ═══════════════════════════════════════════════════════════
# Playability classification
# ═══════════════════════════════════════════════════════════

_RE_CHROMATIC = re.compile(r"c[3-5]|d[3-5]|e[3-5]|chromatic")


def classify_playability(duration, type_code, filename, bpm):
    """Classify how the sample is intended to be used."""
    fname_lower = filename.lower()

    if duration <= 0:
        return "one-shot"

    # Short samples
    if duration < 2:
        if type_code in PERCUSSIVE_CODES:
            return "one-shot"
        if _RE_CHROMATIC.search(fname_lower):
            return "chromatic"
        if type_code in ("FX", "RSR", "SFX"):
            return "transition"
        return "one-shot"

    # Longer samples
    is_loop_hint = "loop" in fname_lower or type_code == "BRK"
    if is_loop_hint:
        return "loop"
    if bpm and duration >= 4 and type_code not in PERCUSSIVE_CODES:
        return "loop"
    if type_code in ("VOX", "BRK") and duration < 10:
        return "chop-ready"
    if type_code in ("PAD", "AMB", "STR", "TPE"):
        return "layer"
    if type_code in ("FX", "RSR"):
        return "transition"
    if duration > 8:
        return "chop-ready"

    return "loop" if duration >= 4 else "one-shot"


# ═══════════════════════════════════════════════════════════
# Main tagging function
# ═══════════════════════════════════════════════════════════

def tag_file(rel_path, full_path, get_dur=True, use_librosa=True):
    """Generate all tags for a single file using the spec dimensions.

    When use_librosa is True and librosa is available, falls back to
    audio analysis for BPM/key when filename extraction returns nothing.
    Also adds loudness_db and source indicators (bpm_source, key_source).
    """
    filename = os.path.basename(rel_path)
    dirpath = os.path.dirname(rel_path)

    # Duration
    duration = get_duration(full_path) if get_dur else 0.0

    # Core dimensions
    type_code = extract_type_code(rel_path, filename)
    bpm = extract_bpm(filename, dirpath)
    key = extract_key(filename)

    bpm_source = "filename" if bpm else None
    key_source = "filename" if key else None
    loudness_db = None

    # Librosa fallback for BPM/key + loudness enrichment
    if use_librosa and analyze_audio and librosa_available():
        needs_analysis = (bpm is None) or (key is None)
        if needs_analysis:
            analysis = analyze_audio(full_path)
            if analysis:
                if bpm is None and analysis.get('bpm'):
                    bpm = analysis['bpm']
                    bpm_source = "librosa"
                if key is None and analysis.get('key'):
                    key = analysis['key']
                    key_source = "librosa"
                if analysis.get('loudness_db') is not None:
                    loudness_db = analysis['loudness_db']
                if duration <= 0 and analysis.get('duration'):
                    duration = analysis['duration']

    source = classify_source(rel_path, filename, type_code)
    playability = classify_playability(duration, type_code, filename, bpm)

    # Subjective tags (vibe, texture, genre, energy) are retired.
    # CLAP embeddings now handle subjective audio understanding.
    # Kept for backward compatibility during migration — populated as empty.
    vibe = extract_vibe(rel_path, filename, type_code)
    texture = extract_texture(rel_path, filename, type_code)
    genres = extract_genres(rel_path)
    energy = classify_energy(bpm, type_code, genres, vibe)

    # Build flat tag set (structural only)
    tags = set()
    tags.add(type_code)
    tags.add(source)
    tags.add(playability)
    if bpm:
        tags.add(f"{int(bpm)}bpm")

    try:
        mtime = os.path.getmtime(full_path)
    except OSError:
        mtime = 0.0

    entry = {
        "path": rel_path,
        "type_code": type_code,
        "vibe": vibe,
        "texture": texture,
        "genre": genres,
        "source": source,
        "energy": energy,
        "playability": playability,
        "bpm": bpm,
        "bpm_source": bpm_source,
        "key": key,
        "key_source": key_source,
        "loudness_db": loudness_db,
        "duration": round(duration, 3),
        "tags": sorted(tags),
        "mtime": mtime,
    }
    return entry


# ═══════════════════════════════════════════════════════════
# Library walker
# ═══════════════════════════════════════════════════════════

def walk_library(path_filter=None, skip_dirs=None):
    """Walk library and return (rel_path, full_path) for all audio files.

    *path_filter*: absolute path to limit the walk to a subdirectory.
    *skip_dirs*: override the default SKIP_DIRS set (e.g. to include _LONG-HOLD).
    """
    root_dir = path_filter or LIBRARY
    excluded = skip_dirs if skip_dirs is not None else SKIP_DIRS
    files = []
    for root, dirs, filenames in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".")]
        for f in filenames:
            if f.startswith("."):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in AUDIO_EXTS:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, LIBRARY)
                files.append((rel, full))
    return files


def load_existing_tags():
    """Load existing tag database (prefers SQLite, falls back to JSON)."""
    from jambox_config import load_tag_db
    return load_tag_db(TAGS_FILE)


def save_tags(db):
    """Save tag database via jambox_config (SQLite + JSON).

    Uses allow_shrink=True because a full tag_library scan is the authoritative
    source — stale entries from deleted/moved files should be cleaned up.
    """
    from jambox_config import save_tag_db
    save_tag_db(TAGS_FILE, db, allow_shrink=True)
    print(f"Saved {len(db)} entries to tag DB")


def print_summary(db):
    """Print tag frequency summary by dimension."""
    type_counts = Counter()
    vibe_counts = Counter()
    texture_counts = Counter()
    genre_counts = Counter()
    source_counts = Counter()
    energy_counts = Counter()
    play_counts = Counter()

    for entry in db.values():
        tc = entry.get("type_code")
        if tc:
            type_counts[tc] += 1
        for v in entry.get("vibe", []):
            vibe_counts[v] += 1
        for t in entry.get("texture", []):
            texture_counts[t] += 1
        for g in entry.get("genre", []):
            genre_counts[g] += 1
        s = entry.get("source")
        if s:
            source_counts[s] += 1
        e = entry.get("energy")
        if e:
            energy_counts[e] += 1
        p = entry.get("playability")
        if p:
            play_counts[p] += 1

    print(f"\n{'='*60}")
    print(f"LIBRARY TAG SUMMARY — {len(db)} files")
    print(f"{'='*60}")

    print(f"\n--- Type Codes ---")
    for code, count in type_counts.most_common():
        bar = "#" * min(count // 20, 40)
        print(f"  {code:<6s} {count:>5d}  {bar}")

    print(f"\n--- Vibe ---")
    for v, count in vibe_counts.most_common(15):
        print(f"  {v:<15s} {count:>5d}")

    print(f"\n--- Texture ---")
    for t, count in texture_counts.most_common(15):
        print(f"  {t:<15s} {count:>5d}")

    print(f"\n--- Genre ---")
    for g, count in genre_counts.most_common(15):
        print(f"  {g:<15s} {count:>5d}")

    print(f"\n--- Source ---")
    for s, count in source_counts.most_common():
        print(f"  {s:<15s} {count:>5d}")

    print(f"\n--- Energy ---")
    for e, count in energy_counts.most_common():
        print(f"  {e:<15s} {count:>5d}")

    print(f"\n--- Playability ---")
    for p, count in play_counts.most_common():
        print(f"  {p:<15s} {count:>5d}")


def main():
    parser = argparse.ArgumentParser(description="Auto-tag the SP-404 sample library")
    parser.add_argument("--update", action="store_true",
                        help="Only tag new or changed files")
    parser.add_argument("--no-duration", action="store_true",
                        help="Skip ffprobe duration detection (faster)")
    parser.add_argument("--path", type=str,
                        help="Tag a specific subdirectory (relative or absolute)")
    parser.add_argument("--include-long-hold", action="store_true",
                        help="Include _LONG-HOLD/ in the scan (normally skipped)")
    args = parser.parse_args()

    path_filter = None
    if args.path:
        p = os.path.expanduser(args.path)
        path_filter = p if os.path.isabs(p) else os.path.join(LIBRARY, p)
        if not os.path.isdir(path_filter):
            print(f"ERROR: path does not exist: {path_filter}", file=sys.stderr)
            sys.exit(1)

    effective_skip = set(SKIP_DIRS)
    if args.include_long_hold:
        effective_skip.discard(LONG_HOLD_DIRNAME)

    scan_label = path_filter or LIBRARY
    print(f"Scanning: {scan_label}")
    if args.include_long_hold:
        print("  (including _LONG-HOLD/)")
    files = walk_library(path_filter=path_filter, skip_dirs=effective_skip)
    print(f"Found {len(files)} audio files")

    db = load_existing_tags() if (args.update or args.path) else {}
    skipped = 0
    tagged = 0

    t0 = time.time()
    for i, (rel, full) in enumerate(files):
        if args.update and rel in db:
            try:
                mtime = os.path.getmtime(full)
                if db[rel].get("mtime") and mtime <= db[rel]["mtime"]:
                    skipped += 1
                    continue
            except OSError:
                pass

        entry = tag_file(rel, full, get_dur=not args.no_duration)
        db[rel] = entry
        tagged += 1

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  [{i+1}/{len(files)}] {rate:.0f} files/sec — {rel[:60]}")

    elapsed = time.time() - t0
    print(f"\nTagged {tagged} files in {elapsed:.1f}s", end="")
    if skipped:
        print(f" (skipped {skipped} unchanged)")
    else:
        print()

    # Remove stale entries — only for the scope we scanned.
    # A --path run should not delete entries outside its target directory.
    # Preserve entries under SKIP_DIRS (quarantine, dupes, etc.) since those
    # directories are intentionally excluded from scanning.
    if not args.path:
        existing_rels = {rel for rel, _ in files}
        skip_prefixes = tuple(d + "/" for d in SKIP_DIRS)
        removed = [k for k in db
                    if k not in existing_rels and not k.startswith(skip_prefixes)]
        for k in removed:
            del db[k]
        if removed:
            print(f"Removed {len(removed)} stale entries")

    save_tags(db)
    print_summary(db)


if __name__ == "__main__":
    main()
