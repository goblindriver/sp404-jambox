"""Canonical tag vocabularies for the Jambox sample library.

Single source of truth. All scripts (tag_library, smart_retag, fetch_samples,
vibe_generate, etc.) should import from here rather than maintaining parallel lists.
"""

# ── Type codes ──
TYPE_CODES = {
    "KIK", "SNR", "HAT", "CLP", "CYM", "RIM", "PRC", "BRK", "DRM",
    "BAS", "GTR", "KEY", "SYN", "PAD", "STR", "BRS", "PLK", "WND", "VOX",
    "FX", "SFX", "AMB", "FLY", "TPE", "RSR", "HRN",
}

# ── Vibes (mood / feel) ──
VIBES = {
    "dark", "warm", "hype", "dreamy", "nostalgic", "aggressive", "mellow",
    "soulful", "eerie", "playful", "gritty", "ethereal", "triumphant",
    "melancholic", "tense", "chill", "uplifting",
}

# ── Textures (sonic character) ──
TEXTURES = {
    "dusty", "lo-fi", "raw", "clean", "warm", "saturated", "bitcrushed",
    "airy", "crispy", "glassy", "muddy", "vinyl", "tape", "digital",
    "organic", "crunchy", "warbly", "bright", "thick", "thin", "filtered",
}

# ── Genres ──
GENRES = {
    "funk", "soul", "disco", "house", "electronic", "hiphop", "dub",
    "ambient", "jazz", "rock", "punk", "dancehall", "latin", "pop", "rnb",
    "industrial", "boom-bap", "lo-fi", "tropical", "afrobeat",
    "lo-fi-hiphop", "trap", "drill", "gospel", "uk-garage", "footwork",
    "city-pop", "psychedelic", "reggae", "classical", "world",
    "breakcore", "shoegaze", "gqom", "baile-funk", "industrial-techno",
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
    "industrial-techno": "industrial-techno",
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
}


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
