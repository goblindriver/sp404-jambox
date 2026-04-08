#!/usr/bin/env python3
"""Discogs Genre Classification + Danceability Engine.

Uses the Discogs-EffNet ONNX model (18MB) to classify audio files into 400
music styles and derive a danceability score. No essentia dependency — runs
on onnxruntime + librosa preprocessing.

Usage:
    python scripts/discogs_engine.py --classify-all       # classify full library
    python scripts/discogs_engine.py --classify-path FILE  # classify one file
    python scripts/discogs_engine.py --status              # show coverage
"""

import argparse
import gc
import json
import os
import sys
import time
import urllib.request

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EMBED_DIM = 400
_SAMPLE_RATE = 16000
_N_MELS = 96
_N_FFT = 512
_HOP_LENGTH = 256
_PATCH_FRAMES = 128  # each input patch is 128 mel-spectrogram frames
_PATCH_HOP = 62      # overlap between patches (from Essentia defaults)
# Genre model only needs an excerpt; cap load so long files cannot exhaust RAM.
_CLASSIFY_MAX_AUDIO_SEC = 120

MODEL_URL = "https://essentia.upf.edu/models/music-style-classification/discogs-effnet/discogs-effnet-bsdynamic-1.onnx"
META_URL = "https://essentia.upf.edu/models/music-style-classification/discogs-effnet/discogs-effnet-bs64-1.json"

# ---------------------------------------------------------------------------
# Danceability weights for Discogs styles
# ---------------------------------------------------------------------------

_DANCE_HIGH = {
    "Electronic---Acid House", "Electronic---Bassline", "Electronic---Big Beat",
    "Electronic---Breakbeat", "Electronic---Breaks", "Electronic---Dance-pop",
    "Electronic---Deep House", "Electronic---Disco", "Electronic---Disco Polo",
    "Electronic---Donk", "Electronic---Drum n Bass", "Electronic---Dubstep",
    "Electronic---Electro House", "Electronic---Euro House", "Electronic---Euro-Disco",
    "Electronic---Eurobeat", "Electronic---Eurodance", "Electronic---Freestyle",
    "Electronic---Gabber", "Electronic---Garage House", "Electronic---Ghetto House",
    "Electronic---Grime", "Electronic---Hands Up", "Electronic---Happy Hardcore",
    "Electronic---Hard House", "Electronic---Hardcore", "Electronic---Hardstyle",
    "Electronic---Hi NRG", "Electronic---Hip-House", "Electronic---House",
    "Electronic---Italo House", "Electronic---Italo-Disco", "Electronic---Italodance",
    "Electronic---Jazzdance", "Electronic---Juke", "Electronic---Jumpstyle",
    "Electronic---Jungle", "Electronic---Makina", "Electronic---New Beat",
    "Electronic---Nu-Disco", "Electronic---Progressive House", "Electronic---Speed Garage",
    "Electronic---Tech House", "Electronic---Tribal House", "Electronic---Tropical House",
    "Electronic---UK Garage",
    "Funk / Soul---Afrobeat", "Funk / Soul---Boogie", "Funk / Soul---Disco",
    "Funk / Soul---Funk", "Funk / Soul---New Jack Swing", "Funk / Soul---P.Funk",
    "Funk / Soul---Swingbeat",
    "Hip Hop---Bass Music", "Hip Hop---Bounce", "Hip Hop---Crunk",
    "Hip Hop---Miami Bass",
    "Latin---Batucada", "Latin---Cumbia", "Latin---Merengue", "Latin---Reggaeton",
    "Latin---Salsa", "Latin---Samba",
    "Reggae---Dancehall", "Reggae---Ragga", "Reggae---Ska", "Reggae---Soca",
}

_DANCE_MEDIUM = {
    "Electronic---Acid", "Electronic---Bleep", "Electronic---Broken Beat",
    "Electronic---Dub Techno", "Electronic---EBM", "Electronic---Electro",
    "Electronic---Electroclash", "Electronic---Goa Trance",
    "Electronic---Hard Techno", "Electronic---Hard Trance", "Electronic---Latin",
    "Electronic---Minimal", "Electronic---Minimal Techno",
    "Electronic---Progressive Breaks", "Electronic---Progressive Trance",
    "Electronic---Psy-Trance", "Electronic---Schranz", "Electronic---Synth-pop",
    "Electronic---Synthwave", "Electronic---Tech Trance", "Electronic---Techno",
    "Electronic---Trance", "Electronic---Tribal",
    "Funk / Soul---Contemporary R&B", "Funk / Soul---Neo Soul",
    "Funk / Soul---Rhythm & Blues", "Funk / Soul---Soul",
    "Funk / Soul---UK Street Soul",
    "Hip Hop---Boom Bap", "Hip Hop---Cut-up/DJ", "Hip Hop---Electro",
    "Hip Hop---G-Funk", "Hip Hop---Gangsta", "Hip Hop---Pop Rap",
    "Hip Hop---RnB/Swing", "Hip Hop---Trap",
    "Jazz---Afro-Cuban Jazz", "Jazz---Bossa Nova", "Jazz---Fusion",
    "Jazz---Jazz-Funk", "Jazz---Latin Jazz", "Jazz---Soul-Jazz", "Jazz---Swing",
    "Latin---Beguine", "Latin---Bolero", "Latin---Boogaloo", "Latin---Bossanova",
    "Latin---Cha-Cha", "Latin---Charanga", "Latin---Cubano", "Latin---Descarga",
    "Latin---Guaracha", "Latin---Mambo", "Latin---Pachanga", "Latin---Son",
    "Latin---Son Montuno", "Latin---Tango", "Latin---Tejano",
    "Pop---Bollywood", "Pop---Bubblegum", "Pop---City Pop", "Pop---Europop",
    "Pop---J-pop", "Pop---K-pop",
    "Reggae---Lovers Rock", "Reggae---Reggae", "Reggae---Reggae-Pop",
    "Reggae---Rocksteady", "Reggae---Roots Reggae",
    "Rock---Garage Rock", "Rock---Glam", "Rock---Pop Punk", "Rock---Pop Rock",
    "Rock---Punk", "Rock---Rock & Roll", "Rock---Rockabilly", "Rock---Surf",
    "Rock---Twist",
    "Blues---Boogie Woogie", "Blues---Jump Blues", "Blues---Rhythm & Blues",
    "Folk, World, & Country---Highlife", "Folk, World, & Country---Soukous",
    "Folk, World, & Country---Zouk",
}


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------

_onnx_session = None
_class_labels = None


def _models_dir():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(repo, "data", "models")
    os.makedirs(d, exist_ok=True)
    return d


def _download_if_needed(url, dest):
    if os.path.exists(dest):
        return dest
    print(f"[Discogs] Downloading {os.path.basename(dest)}...")
    tmp = dest + ".tmp"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dest)
    print(f"[Discogs] Saved to {dest}")
    return dest


def _get_model():
    """Load the ONNX model and class labels. Lazy singleton."""
    global _onnx_session, _class_labels
    if _onnx_session is not None:
        return _onnx_session, _class_labels

    import onnxruntime as ort

    models = _models_dir()
    onnx_path = _download_if_needed(MODEL_URL, os.path.join(models, "discogs-effnet-bsdynamic-1.onnx"))
    meta_path = _download_if_needed(META_URL, os.path.join(models, "discogs-effnet.json"))

    with open(meta_path) as f:
        meta = json.load(f)
    _class_labels = meta["classes"]

    _onnx_session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    return _onnx_session, _class_labels


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def _compute_mel_patches(filepath):
    """Load audio, compute mel spectrogram, and return patches for the model.

    Returns ndarray of shape (num_patches, 128, 96) or None on failure.
    """
    import librosa

    audio, _ = librosa.load(
        filepath, sr=_SAMPLE_RATE, mono=True, duration=_CLASSIFY_MAX_AUDIO_SEC
    )
    if len(audio) < _HOP_LENGTH * _PATCH_FRAMES:
        pad_len = _HOP_LENGTH * _PATCH_FRAMES - len(audio)
        audio = np.pad(audio, (0, pad_len), mode="constant")

    mels = librosa.feature.melspectrogram(
        y=audio, sr=_SAMPLE_RATE,
        n_fft=_N_FFT, hop_length=_HOP_LENGTH, n_mels=_N_MELS,
    )
    mels = np.log10(10000 * mels + 1).T  # (time_frames, 96)

    n_frames = mels.shape[0]
    patches = []
    offset = 0
    while offset + _PATCH_FRAMES <= n_frames:
        patch = mels[offset : offset + _PATCH_FRAMES]
        patches.append(patch)
        offset += _PATCH_HOP

    if not patches and n_frames > 0:
        pad = np.zeros((_PATCH_FRAMES, _N_MELS), dtype=np.float32)
        pad[:n_frames] = mels[:_PATCH_FRAMES]
        patches.append(pad)

    if not patches:
        return None

    return np.array(patches, dtype=np.float32)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_styles(filepath):
    """Classify a single audio file into Discogs styles.

    Returns dict with:
        styles: list of {"label": str, "probability": float} (top 5, p > 0.05)
        parent_genre: str (top-level Discogs category)
        danceability: float 0.0-1.0
    """
    session, labels = _get_model()
    patches = _compute_mel_patches(filepath)
    if patches is None:
        return {"styles": [], "parent_genre": "Unknown", "danceability": 0.0}

    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    preds = session.run([output_name], {input_name: patches})[0]

    avg_probs = preds.mean(axis=0)

    top_indices = np.argsort(avg_probs)[::-1]
    styles = []
    for idx in top_indices:
        p = float(avg_probs[idx])
        if p < 0.05 and len(styles) >= 3:
            break
        if len(styles) >= 8:
            break
        styles.append({"label": labels[idx], "probability": round(p, 4)})

    parent_counts = {}
    for idx in top_indices[:20]:
        parent = labels[idx].split("---")[0]
        parent_counts[parent] = parent_counts.get(parent, 0) + float(avg_probs[idx])
    parent_genre = max(parent_counts, key=parent_counts.get) if parent_counts else "Unknown"

    dance_score = 0.0
    _MIN_DANCE_P = 0.02
    for idx, p in enumerate(avg_probs):
        if float(p) < _MIN_DANCE_P:
            continue
        label = labels[idx]
        if label in _DANCE_HIGH:
            dance_score += float(p) * 1.0
        elif label in _DANCE_MEDIUM:
            dance_score += float(p) * 0.5
    danceability = min(1.0, dance_score)

    return {
        "styles": styles,
        "parent_genre": parent_genre,
        "danceability": round(danceability, 4),
    }


# ---------------------------------------------------------------------------
# Batch classification
# ---------------------------------------------------------------------------

def _walk_library_audio(library_root, skip_dirs):
    from library_walker import walk_library_audio
    return walk_library_audio(library_root, skip_dirs=skip_dirs)


def batch_classify(library_root, tag_db, tags_file, skip_dirs=None,
                   checkpoint_every=200, limit=None, resume=True):
    """Classify all audio files and store results in the tag DB.

    Checkpoints use upsert_tag_entries (only changed rows) to avoid OOM from
    re-serializing the entire tag DB every N files.
    """
    from jambox_config import upsert_tag_entries
    if skip_dirs is None:
        skip_dirs = {"_RAW-DOWNLOADS", "_GOLD", "_DUPES", "_QUARANTINE",
                     "Stems", "_LONG-HOLD"}

    all_files = list(_walk_library_audio(library_root, skip_dirs))
    if resume:
        pending = [(r, a) for r, a in all_files
                   if not tag_db.get(r, {}).get("discogs_styles")]
    else:
        pending = all_files

    already_done = len(all_files) - len(pending)
    if limit:
        pending = pending[:limit]
    total = len(pending)
    if total == 0:
        print(f"[Discogs] All {len(all_files)} files already classified.")
        return tag_db

    print(f"[Discogs] Classifying {total} files ({already_done} already done)...")
    t0 = time.time()
    errors = 0
    pending_save = []

    for i, (rel_path, abs_path) in enumerate(pending):
        try:
            result = classify_styles(abs_path)
            entry = tag_db.get(rel_path, {})
            entry["discogs_styles"] = result["styles"]
            entry["parent_genre"] = result["parent_genre"]
            entry["danceability"] = result["danceability"]
            tag_db[rel_path] = entry
            pending_save.append(rel_path)
        except Exception as e:
            errors += 1
            print(f"  ERROR [{rel_path}]: {e}", file=sys.stderr)
            continue

        if (i + 1) % checkpoint_every == 0 and pending_save:
            upsert_tag_entries(tags_file, {r: tag_db[r] for r in pending_save})
            pending_save.clear()
            gc.collect()
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{total}] {rate:.1f} files/sec, "
                  f"ETA {eta/60:.0f}m, errors={errors}")

    if pending_save:
        upsert_tag_entries(tags_file, {r: tag_db[r] for r in pending_save})
    elapsed = time.time() - t0
    rate = (total - errors) / max(elapsed, 1)
    print(f"[Discogs] Done. {total - errors} classified, {errors} errors, "
          f"{elapsed:.0f}s ({rate:.1f} files/sec)")
    return tag_db


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    sys.path.insert(0, os.path.dirname(__file__))
    from jambox_config import load_settings, load_tag_db, save_tag_db, LIBRARY_SKIP_DIRS

    parser = argparse.ArgumentParser(description="Discogs Genre Classification Engine")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--classify-all", action="store_true",
                       help="Classify all library files (resume-safe)")
    group.add_argument("--classify-path", metavar="FILE",
                       help="Classify a single file")
    group.add_argument("--status", action="store_true",
                       help="Show classification stats")

    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-resume", action="store_true")

    args = parser.parse_args()
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings = load_settings(repo_dir)
    library = settings["SAMPLE_LIBRARY"]
    tags_file = settings["TAGS_FILE"]

    if args.status:
        db = load_tag_db(tags_file)
        all_files = list(_walk_library_audio(library, LIBRARY_SKIP_DIRS))
        classified = sum(1 for r, _ in all_files
                         if db.get(r, {}).get("discogs_styles"))
        danceable = sum(1 for r, _ in all_files
                        if (db.get(r, {}).get("danceability") or 0) > 0.6)
        print(f"Library audio files: {len(all_files)}")
        print(f"Classified:          {classified} ({classified/max(len(all_files),1)*100:.1f}%)")
        print(f"Danceable (>0.6):    {danceable}")

        from collections import Counter
        genres = Counter()
        for r, _ in all_files:
            pg = db.get(r, {}).get("parent_genre")
            if pg:
                genres[pg] += 1
        if genres:
            print("\nParent genres:")
            for g, c in genres.most_common():
                print(f"  {g:30s} {c:6d}")
        return 0

    if args.classify_path:
        filepath = os.path.abspath(args.classify_path)
        if not os.path.isfile(filepath):
            print(f"File not found: {filepath}", file=sys.stderr)
            return 1
        result = classify_styles(filepath)
        print(f"Parent genre: {result['parent_genre']}")
        print(f"Danceability: {result['danceability']:.3f}")
        print("Styles:")
        for s in result["styles"]:
            print(f"  {s['probability']:.3f}  {s['label']}")
        return 0

    if args.classify_all:
        db = load_tag_db(tags_file)
        batch_classify(
            library, db, tags_file,
            skip_dirs=LIBRARY_SKIP_DIRS,
            limit=args.limit,
            resume=not args.no_resume,
        )
        save_tag_db(tags_file, db, allow_shrink=False)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
