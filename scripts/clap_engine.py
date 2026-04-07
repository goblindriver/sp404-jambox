#!/usr/bin/env python3
"""CLAP Audio Intelligence Engine.

Embeds audio files and text queries into a shared 512-dimensional vector space
using LAION-CLAP. Provides batch embedding, persistent storage (numpy memmap),
and cosine-similarity search for fetch scoring and semantic browsing.

Usage:
    python scripts/clap_engine.py --embed-all          # embed full library
    python scripts/clap_engine.py --embed-path FILE     # embed one file
    python scripts/clap_engine.py --query "warm funky bass"  # similarity search
    python scripts/clap_engine.py --status              # show embedding coverage
"""

import argparse
import json
import os
import sys
import time

import numpy as np

# ---------------------------------------------------------------------------
# Lazy CLAP model singleton
# ---------------------------------------------------------------------------

_clap_model = None
_EMBED_DIM = 512


def _get_model():
    """Load the CLAP model once, reuse across calls."""
    global _clap_model
    if _clap_model is not None:
        return _clap_model

    import laion_clap

    device = "cpu"
    try:
        import torch
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
    except ImportError:
        pass

    # HTSAT-tiny + roberta is the default and most widely tested combo
    model = laion_clap.CLAP_Module(enable_fusion=False, device=device)
    model.load_ckpt(verbose=False)
    model.eval()
    _clap_model = model
    return _clap_model


# ---------------------------------------------------------------------------
# Core embedding functions
# ---------------------------------------------------------------------------

def embed_audio_file(filepath):
    """Embed a single audio file. Returns a 512-dim numpy vector (float32).

    CLAP expects 48kHz audio internally. The library handles resampling.
    """
    model = _get_model()
    emb = model.get_audio_embedding_from_filelist(
        x=[filepath], use_tensor=False
    )
    return emb[0].astype(np.float32)


def embed_audio_data(audio_np, sr=48000):
    """Embed raw audio data (numpy array, mono, 48kHz expected).

    If sample rate differs from 48kHz, resample first via librosa.
    """
    if sr != 48000:
        import librosa
        audio_np = librosa.resample(audio_np, orig_sr=sr, target_sr=48000)

    model = _get_model()
    data = audio_np.reshape(1, -1).astype(np.float32)
    emb = model.get_audio_embedding_from_data(x=data, use_tensor=False)
    return emb[0].astype(np.float32)


def embed_text(queries):
    """Embed one or more text queries. Returns (N, 512) numpy array."""
    model = _get_model()
    if isinstance(queries, str):
        queries = [queries]
    emb = model.get_text_embedding(queries, use_tensor=False)
    return emb.astype(np.float32)


def cosine_similarity(a, b):
    """Cosine similarity between vector(s) a and matrix b.

    a: (D,) or (1, D) — single query vector
    b: (N, D) — matrix of candidate vectors
    Returns: (N,) similarity scores in [-1, 1]
    """
    a = np.atleast_2d(a)
    b = np.atleast_2d(b)
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    return (a_norm @ b_norm.T).flatten()


# ---------------------------------------------------------------------------
# EmbeddingStore — persistent numpy memmap + path-to-index mapping
# ---------------------------------------------------------------------------

class EmbeddingStore:
    """Manages a (N, 512) numpy memmap and a path→row-index mapping.

    Files:
        embeddings_path: .npy memmap file (N x 512 float32)
        index_path:      .json mapping {relative_path: row_index}
    """

    def __init__(self, library_root):
        self.library_root = os.path.expanduser(library_root)
        self.embeddings_path = os.path.join(self.library_root, "_embeddings.npy")
        self.index_path = os.path.join(self.library_root, "_embed_index.json")
        self._index = None
        self._mmap = None
        self._count = 0

    @property
    def index(self):
        if self._index is None:
            self._load_index()
        return self._index

    def _load_index(self):
        if os.path.exists(self.index_path):
            with open(self.index_path, "r") as f:
                self._index = json.load(f)
        else:
            self._index = {}
        self._count = len(self._index)

    def _save_index(self):
        tmp = self.index_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.index, f)
        os.replace(tmp, self.index_path)

    def _open_mmap(self, mode="r"):
        if not os.path.exists(self.embeddings_path):
            return None
        return np.memmap(
            self.embeddings_path,
            dtype=np.float32,
            mode=mode,
            shape=(len(self.index), _EMBED_DIM),
        )

    def _ensure_mmap_capacity(self, needed_rows):
        """Grow the memmap file to hold at least needed_rows."""
        if os.path.exists(self.embeddings_path):
            current = os.path.getsize(self.embeddings_path) // (_EMBED_DIM * 4)
            if current >= needed_rows:
                return
        fp = np.memmap(
            self.embeddings_path,
            dtype=np.float32,
            mode="w+" if not os.path.exists(self.embeddings_path) else "r+",
            shape=(needed_rows, _EMBED_DIM),
        )
        del fp

    @property
    def count(self):
        return len(self.index)

    def has(self, rel_path):
        return rel_path in self.index

    def get(self, rel_path):
        """Get embedding for a file by relative path. Returns (512,) or None."""
        idx = self.index.get(rel_path)
        if idx is None:
            return None
        mmap = self._open_mmap("r")
        if mmap is None or idx >= mmap.shape[0]:
            return None
        return np.array(mmap[idx])

    def add(self, rel_path, embedding):
        """Add or update an embedding for a relative path."""
        existing_idx = self.index.get(rel_path)
        if existing_idx is not None:
            row = existing_idx
        else:
            row = len(self.index)
            self.index[rel_path] = row

        self._ensure_mmap_capacity(row + 1)
        fp = np.memmap(
            self.embeddings_path,
            dtype=np.float32,
            mode="r+",
            shape=(row + 1, _EMBED_DIM),
        )
        fp[row] = embedding.astype(np.float32)
        fp.flush()
        del fp

    def save(self):
        """Persist the index to disk."""
        self._save_index()

    def load_matrix(self):
        """Load the full embedding matrix for bulk operations. Returns (N, 512) ndarray."""
        if not os.path.exists(self.embeddings_path) or len(self.index) == 0:
            return np.zeros((0, _EMBED_DIM), dtype=np.float32)
        return np.memmap(
            self.embeddings_path,
            dtype=np.float32,
            mode="r",
            shape=(len(self.index), _EMBED_DIM),
        )

    def paths_array(self):
        """Return list of relative paths ordered by index row."""
        inv = [""] * len(self.index)
        for path, idx in self.index.items():
            if idx < len(inv):
                inv[idx] = path
        return inv

    def bulk_query(self, text_query_embed, type_filter=None, tag_db=None, top_k=20):
        """Search the embedding store by text query embedding.

        Args:
            text_query_embed: (512,) text embedding vector
            type_filter: optional type_code string to filter candidates
            tag_db: tag database dict (needed if type_filter is set)
            top_k: number of results to return

        Returns:
            list of (rel_path, similarity_score) sorted by score descending
        """
        matrix = self.load_matrix()
        if matrix.shape[0] == 0:
            return []

        scores = cosine_similarity(text_query_embed, matrix)
        paths = self.paths_array()

        if type_filter and tag_db:
            mask = np.zeros(len(paths), dtype=bool)
            for i, p in enumerate(paths):
                entry = tag_db.get(p, {})
                if entry.get("type_code") == type_filter:
                    mask[i] = True
            scores = np.where(mask, scores, -2.0)

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] > -2.0 and idx < len(paths) and paths[idx]:
                results.append((paths[idx], float(scores[idx])))
        return results


# ---------------------------------------------------------------------------
# Batch embedding
# ---------------------------------------------------------------------------

def _walk_library_audio(library_root, skip_dirs):
    """Yield (rel_path, abs_path) for all audio files in the library."""
    audio_exts = {".flac", ".wav", ".mp3", ".aif", ".aiff", ".ogg"}
    for dirpath, dirnames, filenames in os.walk(library_root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in audio_exts:
                abs_path = os.path.join(dirpath, fn)
                rel_path = os.path.relpath(abs_path, library_root)
                yield rel_path, abs_path


def batch_embed(library_root, store, skip_dirs=None, checkpoint_every=200,
                limit=None, resume=True):
    """Embed all audio files in the library that don't yet have embeddings.

    Args:
        library_root: absolute path to sample library
        store: EmbeddingStore instance
        skip_dirs: set of directory names to skip
        checkpoint_every: save index every N files
        limit: optional max files to process (for testing)
        resume: if True, skip files already in the store
    """
    if skip_dirs is None:
        skip_dirs = {"_RAW-DOWNLOADS", "_GOLD", "_DUPES", "_QUARANTINE",
                     "Stems", "_LONG-HOLD"}

    all_files = list(_walk_library_audio(library_root, skip_dirs))
    if resume:
        pending = [(r, a) for r, a in all_files if not store.has(r)]
    else:
        pending = all_files

    if limit:
        pending = pending[:limit]

    total = len(pending)
    if total == 0:
        print(f"[CLAP] All {len(all_files)} files already embedded.")
        return

    print(f"[CLAP] Embedding {total} files ({len(all_files) - total} already done)...")
    t0 = time.time()
    errors = 0

    for i, (rel_path, abs_path) in enumerate(pending):
        try:
            emb = embed_audio_file(abs_path)
            store.add(rel_path, emb)
        except Exception as e:
            errors += 1
            print(f"  ERROR [{rel_path}]: {e}", file=sys.stderr)
            continue

        if (i + 1) % checkpoint_every == 0:
            store.save()
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{total}] {rate:.1f} files/sec, "
                  f"ETA {eta/60:.0f}m, errors={errors}")

    store.save()
    elapsed = time.time() - t0
    print(f"[CLAP] Done. {total - errors} embedded, {errors} errors, "
          f"{elapsed:.0f}s ({(total - errors)/elapsed:.1f} files/sec)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from jambox_config import load_settings, load_tag_db, LIBRARY_SKIP_DIRS

    parser = argparse.ArgumentParser(description="CLAP Audio Intelligence Engine")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--embed-all", action="store_true",
                       help="Embed all library files (resume-safe)")
    group.add_argument("--embed-path", metavar="FILE",
                       help="Embed a single file and add to store")
    group.add_argument("--query", metavar="TEXT",
                       help="Search library by text query")
    group.add_argument("--status", action="store_true",
                       help="Show embedding store stats")

    parser.add_argument("--limit", type=int, default=None,
                        help="Max files to embed (for testing)")
    parser.add_argument("--top-k", type=int, default=10,
                        help="Number of search results")
    parser.add_argument("--type-code", metavar="CODE", default=None,
                        help="Filter search results by type_code")
    parser.add_argument("--no-resume", action="store_true",
                        help="Re-embed all files even if already stored")

    args = parser.parse_args()
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings = load_settings(repo_dir)
    library = settings["SAMPLE_LIBRARY"]
    store = EmbeddingStore(library)

    if args.status:
        all_files = list(_walk_library_audio(library, LIBRARY_SKIP_DIRS))
        print(f"Library audio files: {len(all_files)}")
        print(f"Embedded:            {store.count}")
        print(f"Coverage:            {store.count/max(len(all_files),1)*100:.1f}%")
        print(f"Store path:          {store.embeddings_path}")
        return 0

    if args.embed_all:
        batch_embed(
            library, store,
            skip_dirs=LIBRARY_SKIP_DIRS,
            limit=args.limit,
            resume=not args.no_resume,
        )
        return 0

    if args.embed_path:
        filepath = os.path.abspath(args.embed_path)
        if not os.path.isfile(filepath):
            print(f"File not found: {filepath}", file=sys.stderr)
            return 1
        rel = os.path.relpath(filepath, library)
        emb = embed_audio_file(filepath)
        store.add(rel, emb)
        store.save()
        print(f"Embedded: {rel} (norm={np.linalg.norm(emb):.3f})")
        return 0

    if args.query:
        t0 = time.time()
        text_emb = embed_text(args.query)
        tag_db = None
        if args.type_code:
            tags_file = settings["TAGS_FILE"]
            tag_db = load_tag_db(tags_file)

        results = store.bulk_query(
            text_emb[0], type_filter=args.type_code,
            tag_db=tag_db, top_k=args.top_k
        )
        elapsed = time.time() - t0
        print(f"Query: \"{args.query}\"" +
              (f"  type_code={args.type_code}" if args.type_code else ""))
        print(f"Results ({elapsed:.2f}s):\n")
        for path, score in results:
            print(f"  {score:+.4f}  {path}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
