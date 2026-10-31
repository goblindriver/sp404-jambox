"""Canonical tag vocabularies for the Jambox sample library.

Single source of truth. All scripts (tag_library, smart_retag, fetch_samples,
vibe_generate, etc.) should import from here rather than maintaining parallel lists.
"""

import re

# ── Type codes ──
TYPE_CODES = {
    "KIK", "SNR", "HAT", "CLP", "CYM", "RIM", "PRC", "BRK", "DRM",
    "BAS", "GTR", "KEY", "SYN", "PAD", "STR", "BRS", "PLK", "WND", "VOX",
    "FX", "SFX", "AMB", "FLY", "TPE", "RSR", "HRN",
}

# ── Vibes (mood / feel — emotional, not sonic) ──
# NOTE: "dusty", "raw", "warm" moved to texture-only (they describe sonic
# character, not emotional mood). Replacements added here for the emotional
# meanings those words used to carry:
#   dusty -> nostalgic (was already here, now more prominent)
#   raw -> unfiltered (emotional honesty/directness)
#   warm -> comforting (emotional warmth, safety, intimacy)
VIBES = {
    "dark", "hype", "dreamy", "nostalgic", "aggressive", "mellow",
    "soulful", "eerie", "playful", "gritty", "ethereal", "triumphant",
    "melancholic", "tense", "chill", "uplifting", "unfiltered", "comforting",
}

# ── Textures (sonic character) ──
TEXTURES = {
    "dusty", "lo-fi", "raw", "clean", "warm", "saturated", "bitcrushed",
    "airy", "crispy", "glassy", "muddy", "vinyl", "tape", "digital",
    "organic", "crunchy", "warbly", "bright", "thick", "thin", "filtered",
}

# ── Genres ──
GENRES = {
    "afrobeat", "ambient", "baile-funk", "boom-bap", "breakbeat", "breakcore",
    "city-pop", "classical", "dancehall", "disco", "drill", "drum-and-bass",
    "dub", "dubstep", "electronic", "experimental", "footwork", "funk",
    "gqom", "gospel", "hiphop", "house", "industrial", "industrial-techno",
    "jazz", "jungle", "latin", "lo-fi", "lo-fi-hiphop", "pop", "psychedelic",
    "punk", "reggae", "rnb", "rock", "shoegaze", "soul", "techno", "trap",
    "trance", "tropical", "uk-garage", "world",
}

# ── Energy levels ──
ENERGIES = {"low", "mid", "high"}

# ── Playability modes ──
PLAYABILITIES = {"one-shot", "loop", "chop-ready", "chromatic", "layer", "transition"}

# ── Aliases: map variant spellings to canonical forms ──
GENRE_ALIASES = {
    "hip-hop": "hiphop", "hip hop": "hiphop",
    "lofi": "lo-fi", "lo fi": "lo-fi", "lo-fi-hip-hop": "lo-fi-hiphop",
    "r&b": "rnb",
    "edm": "electronic", "dance": "house",
    "dancehall": "dancehall", "punk": "punk",
    "riddim": "dancehall",
    "baile funk": "baile-funk", "favela funk": "baile-funk",
    "industrial techno": "industrial-techno",
    "boom bap": "boom-bap", "boombap": "boom-bap",
    "industrial-techno": "industrial-techno",
    "drum n bass": "drum-and-bass",
    "drum and bass": "drum-and-bass",
    "drum & bass": "drum-and-bass",
    "dnb": "drum-and-bass",
    "d&b": "drum-and-bass",
    "jungle dnb": "jungle",
    "juke": "footwork",
    "tech house": "house",
    "tech-house": "house",
}

TEXTURE_ALIASES = {
    "lofi": "lo-fi", "crisp": "crispy", "wide": "airy",
    "tape-saturated": "tape", "metallic": "crispy",
    "metallic-hit": "crispy", "metal-hit": "crispy",
    "ringy": "glassy",
}

VIBE_ALIASES = {
    "happy": "uplifting", "sad": "melancholic", "angry": "aggressive",
    "smooth": "chill", "spooky": "eerie", "moody": "dark",
    "energetic": "hype", "energy": "hype", "fun": "playful",
    "relaxed": "chill", "calm": "mellow", "groovy": "soulful",
    "scary": "eerie",
    # Migrate old vibe uses of texture terms to emotional equivalents
    "warm": "comforting", "raw": "unfiltered", "dusty": "nostalgic",
}


# ── Musical keys ──
# Canonical spelling: uppercase root, "s" for sharp / "b" for flat, "m" for
# minor -- "Am", "Csm", "Bb", "Ebm". Matches audio_analysis output.
_KEY_RE = re.compile(
    r"^([A-Ga-g])(#|s|b|sharp|flat)?\s*(?i:(minor|min|major|maj|m))?$"
)


def canonical_key(raw):
    """'A min' -> 'Am', 'c#m' -> 'Csm', 'Bbmaj' -> 'Bb', 'F#' -> 'Fs'.

    Returns None for anything that isn't a key (including 'XX' = any key).
    """
    if not raw or not isinstance(raw, str):
        return None
    m = _KEY_RE.match(raw.strip())
    if not m:
        return None
    root, accidental, quality = m.groups()
    accidental = {"#": "s", "s": "s", "sharp": "s", "b": "b", "flat": "b"}.get(accidental or "", "")
    minor = bool(quality) and not quality.lower().startswith("maj")
    return root.upper() + accidental + ("m" if minor else "")


def pad_type_and_playability(description):
    """(type_code, playability) from a 'TYPE keywords playability' pad description."""
    type_code = playability = None
    for word in str(description or "").split():
        upper = word.upper()
        if upper == "SMP":
            upper = "BRK"
        if type_code is None and upper in TYPE_CODES:
            type_code = upper
        elif word.lower() in PLAYABILITIES:
            playability = word.lower()
    return type_code, playability


def normalize_genre(value):
    """Normalize a genre string to canonical form or None if unknown."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    v = GENRE_ALIASES.get(v, v)
    return v if v in GENRES else None


def normalize_texture(value):
    """Normalize a texture string to canonical form or None if unknown."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    v = TEXTURE_ALIASES.get(v, v)
    return v if v in TEXTURES else None


def normalize_vibe(value):
    """Normalize a vibe string to canonical form or None if unknown."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    v = VIBE_ALIASES.get(v, v)
    return v if v in VIBES else None


def normalize_energy(value):
    """Normalize an energy string to canonical form or None if unknown."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    return v if v in ENERGIES else None


def normalize_playability(value):
    """Normalize a playability string to canonical form or None if unknown."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    return v if v in PLAYABILITIES else None
