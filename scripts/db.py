"""Jambox SQLite database — normalized tag store.

Replaces the flat _tags.json / KV-store SQLite with a proper relational schema.
All writes use transactions. Thread-safe via sqlite3's built-in serialization.

Usage:
    from db import JamboxDB
    db = JamboxDB()                      # default: data/jambox.db
    db.upsert_sample(filepath, meta)     # insert or update sample metadata
    db.upsert_tags(filepath, tags)       # set dimensional tags for a sample
    sample = db.get_sample(filepath)     # full sample + tags dict
    results = db.query_by_tag(type_code='KIK', vibe='warm')
    db.assign_pad('tiger-dust', 'B', 3, filepath)
"""

import json
import os
import sqlite3
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPTS_DIR)
DEFAULT_DB_PATH = os.path.join(REPO_DIR, "data", "jambox.db")

SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- Core sample metadata
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    format TEXT,
    sample_rate INTEGER,
    bit_depth INTEGER,
    duration_ms INTEGER,
    bpm REAL,
    bpm_source TEXT,
    key TEXT,
    key_source TEXT,
    loudness_db REAL,
    file_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dimensional tags (many-to-one with samples)
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    tag_key TEXT NOT NULL,
    tag_value TEXT NOT NULL,
    confidence REAL,
    model_version TEXT,
    tagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sample_id, tag_key, tag_value)
);

-- Preset/bank assignments
CREATE TABLE IF NOT EXISTS pad_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER NOT NULL REFERENCES samples(id),
    preset_name TEXT NOT NULL,
    bank TEXT NOT NULL,
    pad INTEGER NOT NULL,
    UNIQUE(preset_name, bank, pad)
);

-- Tag taxonomy reference
CREATE TABLE IF NOT EXISTS taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_key TEXT NOT NULL,
    tag_value TEXT NOT NULL,
    parent_value TEXT,
    description TEXT,
    UNIQUE(tag_key, tag_value)
);

-- Feature vectors (stored as JSON blobs — queried in Python, not SQL)
CREATE TABLE IF NOT EXISTS features (
    sample_id INTEGER PRIMARY KEY REFERENCES samples(id) ON DELETE CASCADE,
    mfcc TEXT,
    chroma TEXT,
    spectral_centroid REAL,
    spectral_rolloff REAL,
    zero_crossing_rate REAL,
    onset_strength REAL,
    onset_count INTEGER,
    rms_peak REAL,
    rms_mean REAL,
    attack_position REAL
);

-- DPO preference pairs for taste model training
CREATE TABLE IF NOT EXISTS dpo_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER NOT NULL REFERENCES samples(id),
    prompt TEXT NOT NULL,
    chosen TEXT NOT NULL,
    rejected TEXT NOT NULL,
    source TEXT NOT NULL,
    preset_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tags_key_value ON tags(tag_key, tag_value);
CREATE INDEX IF NOT EXISTS idx_tags_sample ON tags(sample_id);
CREATE INDEX IF NOT EXISTS idx_samples_filepath ON samples(filepath);
CREATE INDEX IF NOT EXISTS idx_samples_hash ON samples(file_hash);
CREATE INDEX IF NOT EXISTS idx_pad_preset_bank ON pad_assignments(preset_name, bank);
CREATE INDEX IF NOT EXISTS idx_dpo_source ON dpo_pairs(source);
CREATE INDEX IF NOT EXISTS idx_dpo_sample ON dpo_pairs(sample_id);
"""

# Tag keys that are lists in _tags.json (multi-valued)
LIST_TAG_KEYS = {'vibe', 'texture', 'genre', 'production_tag'}
# Tag keys that are scalars
SCALAR_TAG_KEYS = {
    'type_code', 'playability', 'energy', 'source', 'scene',
    # Re-vibe pass sub-dimensions + composite
    'danceability', 'warmth', 'soul', 'tension', 'texture_fit', 'vibe_score',
    'set_context', 'production_fit',
}


class JamboxDB:
    """Normalized SQLite tag store for the sample library."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = None
        self._ensure_schema()

    def _connect(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, timeout=30)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_schema(self):
        conn = self._connect()
        conn.executescript(SCHEMA_SQL)
        # Set schema version if not present
        existing = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if not existing:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)",
                         (SCHEMA_VERSION,))
        conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Sample CRUD ──

    def upsert_sample(self, filepath, meta=None):
        """Insert or update a sample. Returns the sample_id.

        Args:
            filepath: Relative path within the library (the key).
            meta: Dict with optional keys: filename, format, sample_rate,
                  bit_depth, duration_ms, bpm, bpm_source, key, key_source,
                  loudness_db, file_hash.
        """
        meta = meta or {}
        conn = self._connect()
        filename = meta.get('filename') or os.path.basename(filepath)
        fmt = meta.get('format') or os.path.splitext(filepath)[1].lstrip('.')

        # Duration: accept seconds (float) or ms (int)
        duration_ms = meta.get('duration_ms')
        if duration_ms is None and meta.get('duration'):
            duration_ms = int(meta['duration'] * 1000)

        conn.execute("""
            INSERT INTO samples (filepath, filename, format, sample_rate,
                                 bit_depth, duration_ms, bpm, bpm_source,
                                 key, key_source, loudness_db, file_hash,
                                 updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(filepath) DO UPDATE SET
                filename=excluded.filename,
                format=excluded.format,
                sample_rate=COALESCE(excluded.sample_rate, samples.sample_rate),
                bit_depth=COALESCE(excluded.bit_depth, samples.bit_depth),
                duration_ms=COALESCE(excluded.duration_ms, samples.duration_ms),
                bpm=COALESCE(excluded.bpm, samples.bpm),
                bpm_source=COALESCE(excluded.bpm_source, samples.bpm_source),
                key=COALESCE(excluded.key, samples.key),
                key_source=COALESCE(excluded.key_source, samples.key_source),
                loudness_db=COALESCE(excluded.loudness_db, samples.loudness_db),
                file_hash=COALESCE(excluded.file_hash, samples.file_hash),
                updated_at=excluded.updated_at
        """, (filepath, filename, fmt,
              meta.get('sample_rate'), meta.get('bit_depth'),
              duration_ms,
              meta.get('bpm'), meta.get('bpm_source'),
              meta.get('key'), meta.get('key_source'),
              meta.get('loudness_db'), meta.get('file_hash'),
              datetime.now().isoformat()))
        conn.commit()

        row = conn.execute(
            "SELECT id FROM samples WHERE filepath=?", (filepath,)
        ).fetchone()
        return row['id'] if row else None

    def get_sample(self, filepath):
        """Get full sample dict including tags and features. Returns None if not found."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM samples WHERE filepath=?", (filepath,)
        ).fetchone()
        if not row:
            return None

        result = dict(row)
        sample_id = result['id']

        # Attach tags
        tag_rows = conn.execute(
            "SELECT tag_key, tag_value, confidence, model_version "
            "FROM tags WHERE sample_id=?", (sample_id,)
        ).fetchall()

        for tr in tag_rows:
            key = tr['tag_key']
            val = tr['tag_value']
            if key in LIST_TAG_KEYS:
                result.setdefault(key, []).append(val)
            else:
                result[key] = val

        # Attach features
        feat_row = conn.execute(
            "SELECT * FROM features WHERE sample_id=?", (sample_id,)
        ).fetchone()
        if feat_row:
            features = {}
            for k in ('spectral_centroid', 'spectral_rolloff', 'zero_crossing_rate',
                       'onset_strength', 'onset_count', 'rms_peak', 'rms_mean',
                       'attack_position'):
                if feat_row[k] is not None:
                    features[k] = feat_row[k]
            for k in ('mfcc', 'chroma'):
                if feat_row[k]:
                    try:
                        features[k] = json.loads(feat_row[k])
                    except (json.JSONDecodeError, TypeError):
                        pass
            if features:
                result['features'] = features

        return result

    def get_sample_id(self, filepath):
        """Get sample_id for a filepath. Returns None if not found."""
        conn = self._connect()
        row = conn.execute(
            "SELECT id FROM samples WHERE filepath=?", (filepath,)
        ).fetchone()
        return row['id'] if row else None

    # ── Tag operations ──

    def upsert_tags(self, filepath, tags, model_version=None):
        """Set dimensional tags for a sample. Creates the sample if needed.

        Args:
            filepath: Relative path within the library.
            tags: Dict with tag_key -> tag_value (scalar) or tag_key -> [values] (list).
                  Keys: type_code, playability, energy, source, vibe, texture, genre,
                        sonic_description, instrument_hint, quality_score.
            model_version: Optional model identifier (e.g. 'qwen3:32b').
        """
        sample_id = self.get_sample_id(filepath)
        if sample_id is None:
            sample_id = self.upsert_sample(filepath)

        conn = self._connect()
        now = datetime.now().isoformat()

        rows = []
        for key, value in tags.items():
            if key in ('sonic_description', 'instrument_hint', 'quality_score'):
                # Store as scalar tag
                rows.append((sample_id, key, str(value), None, model_version, now))
            elif key in LIST_TAG_KEYS:
                vals = value if isinstance(value, list) else [value]
                for v in vals:
                    rows.append((sample_id, key, str(v), None, model_version, now))
            elif key in SCALAR_TAG_KEYS:
                rows.append((sample_id, key, str(value), None, model_version, now))

        if rows:
            # Clear old tags for these keys, then insert new ones
            keys_to_clear = set(r[1] for r in rows)
            for key in keys_to_clear:
                conn.execute(
                    "DELETE FROM tags WHERE sample_id=? AND tag_key=?",
                    (sample_id, key))
            conn.executemany(
                "INSERT INTO tags (sample_id, tag_key, tag_value, confidence, "
                "model_version, tagged_at) VALUES (?, ?, ?, ?, ?, ?)", rows)
            conn.commit()

    def upsert_features(self, filepath, features):
        """Store feature vectors for a sample."""
        sample_id = self.get_sample_id(filepath)
        if sample_id is None:
            sample_id = self.upsert_sample(filepath)

        conn = self._connect()
        conn.execute("""
            INSERT INTO features (sample_id, mfcc, chroma, spectral_centroid,
                                  spectral_rolloff, zero_crossing_rate,
                                  onset_strength, onset_count, rms_peak,
                                  rms_mean, attack_position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sample_id) DO UPDATE SET
                mfcc=excluded.mfcc,
                chroma=excluded.chroma,
                spectral_centroid=excluded.spectral_centroid,
                spectral_rolloff=excluded.spectral_rolloff,
                zero_crossing_rate=excluded.zero_crossing_rate,
                onset_strength=excluded.onset_strength,
                onset_count=excluded.onset_count,
                rms_peak=excluded.rms_peak,
                rms_mean=excluded.rms_mean,
                attack_position=excluded.attack_position
        """, (
            sample_id,
            json.dumps(features.get('mfcc')) if features.get('mfcc') else None,
            json.dumps(features.get('chroma')) if features.get('chroma') else None,
            features.get('spectral_centroid'),
            features.get('spectral_rolloff'),
            features.get('zero_crossing_rate'),
            features.get('onset_strength'),
            features.get('onset_count'),
            features.get('rms_peak'),
            features.get('rms_mean'),
            features.get('attack_position'),
        ))
        conn.commit()

    # ── Query operations ──

    def query_by_tag(self, **kwargs):
        """Query samples by tag dimensions. AND across keys, OR within list keys.

        Returns list of sample dicts (with tags).

        Example:
            db.query_by_tag(type_code='KIK', vibe='warm', genre='funk')
        """
        conn = self._connect()

        # Build subqueries for each filter
        conditions = []
        params = []
        for key, value in kwargs.items():
            values = value if isinstance(value, list) else [value]
            placeholders = ','.join('?' * len(values))
            conditions.append(
                "s.id IN (SELECT sample_id FROM tags "
                "WHERE tag_key=? AND tag_value IN (%s))" % placeholders
            )
            params.append(key)
            params.extend(str(v) for v in values)

        if not conditions:
            return []

        sql = "SELECT s.* FROM samples s WHERE " + " AND ".join(conditions)
        rows = conn.execute(sql, params).fetchall()

        results = []
        for row in rows:
            d = dict(row)
            # Attach tags
            tag_rows = conn.execute(
                "SELECT tag_key, tag_value FROM tags WHERE sample_id=?",
                (d['id'],)).fetchall()
            for tr in tag_rows:
                k = tr['tag_key']
                v = tr['tag_value']
                if k in LIST_TAG_KEYS:
                    d.setdefault(k, []).append(v)
                else:
                    d[k] = v
            results.append(d)

        return results

    def search(self, query, limit=50):
        """Full-text search across filepath, filename, and sonic_description."""
        conn = self._connect()
        pattern = f'%{query}%'
        rows = conn.execute("""
            SELECT DISTINCT s.* FROM samples s
            LEFT JOIN tags t ON t.sample_id = s.id
                AND t.tag_key = 'sonic_description'
            WHERE s.filepath LIKE ?
               OR s.filename LIKE ?
               OR t.tag_value LIKE ?
            LIMIT ?
        """, (pattern, pattern, pattern, limit)).fetchall()
        return [dict(r) for r in rows]

    def tag_counts(self, tag_key=None):
        """Get tag value frequencies, optionally filtered by key.

        Returns list of (tag_key, tag_value, count) tuples.
        """
        conn = self._connect()
        if tag_key:
            rows = conn.execute(
                "SELECT tag_key, tag_value, COUNT(*) as cnt "
                "FROM tags WHERE tag_key=? GROUP BY tag_key, tag_value "
                "ORDER BY cnt DESC", (tag_key,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT tag_key, tag_value, COUNT(*) as cnt "
                "FROM tags GROUP BY tag_key, tag_value "
                "ORDER BY tag_key, cnt DESC"
            ).fetchall()
        return [(r['tag_key'], r['tag_value'], r['cnt']) for r in rows]

    # ── Pad assignment ──

    def assign_pad(self, preset_name, bank, pad, filepath):
        """Assign a sample to a bank/pad slot in a preset."""
        sample_id = self.get_sample_id(filepath)
        if sample_id is None:
            sample_id = self.upsert_sample(filepath)

        conn = self._connect()
        conn.execute("""
            INSERT INTO pad_assignments (sample_id, preset_name, bank, pad)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(preset_name, bank, pad) DO UPDATE SET
                sample_id=excluded.sample_id
        """, (sample_id, preset_name, bank, pad))
        conn.commit()

    def get_pad_assignments(self, preset_name):
        """Get all pad assignments for a preset. Returns dict of (bank, pad) -> sample dict."""
        conn = self._connect()
        rows = conn.execute("""
            SELECT pa.bank, pa.pad, s.filepath, s.filename
            FROM pad_assignments pa
            JOIN samples s ON s.id = pa.sample_id
            WHERE pa.preset_name = ?
            ORDER BY pa.bank, pa.pad
        """, (preset_name,)).fetchall()
        return {(r['bank'], r['pad']): dict(r) for r in rows}

    # ── Taxonomy ──

    def upsert_taxonomy(self, tag_key, tag_value, parent_value=None, description=None):
        """Add or update a taxonomy entry."""
        conn = self._connect()
        conn.execute("""
            INSERT INTO taxonomy (tag_key, tag_value, parent_value, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tag_key, tag_value) DO UPDATE SET
                parent_value=COALESCE(excluded.parent_value, taxonomy.parent_value),
                description=COALESCE(excluded.description, taxonomy.description)
        """, (tag_key, tag_value, parent_value, description))
        conn.commit()

    # ── Bulk operations ──

    def import_from_tag_dict(self, tag_dict, model_version=None):
        """Bulk import from a _tags.json-style dict (rel_path -> entry).

        This is the migration path from _tags.json → jambox.db.
        """
        conn = self._connect()
        count = 0

        for filepath, entry in tag_dict.items():
            # 1. Upsert sample metadata
            duration = entry.get('duration')
            meta = {
                'filename': os.path.basename(filepath),
                'format': os.path.splitext(filepath)[1].lstrip('.'),
                'duration_ms': int(duration * 1000) if duration else None,
                'bpm': entry.get('bpm'),
                'bpm_source': entry.get('bpm_source'),
                'key': entry.get('key'),
                'key_source': entry.get('key_source'),
                'loudness_db': entry.get('loudness_db'),
                'file_hash': entry.get('file_hash'),
            }
            sample_id = self.upsert_sample(filepath, meta)
            if sample_id is None:
                continue

            # 2. Upsert tags
            tag_rows = []
            now = datetime.now().isoformat()
            mv = entry.get('retag_model') or model_version

            for key in SCALAR_TAG_KEYS:
                val = entry.get(key)
                if val:
                    tag_rows.append((sample_id, key, str(val), None, mv, now))

            for key in LIST_TAG_KEYS:
                vals = entry.get(key, [])
                if isinstance(vals, str):
                    vals = [vals]
                for v in vals:
                    if v:
                        tag_rows.append((sample_id, key, str(v), None, mv, now))

            for key in ('sonic_description', 'instrument_hint', 'quality_score'):
                val = entry.get(key)
                if val is not None:
                    tag_rows.append((sample_id, key, str(val), None, mv, now))

            if tag_rows:
                # Clear existing tags for this sample
                conn.execute("DELETE FROM tags WHERE sample_id=?", (sample_id,))
                conn.executemany(
                    "INSERT INTO tags (sample_id, tag_key, tag_value, confidence, "
                    "model_version, tagged_at) VALUES (?, ?, ?, ?, ?, ?)",
                    tag_rows)

            # 3. Store features if present
            features = entry.get('features')
            if features:
                conn.execute("""
                    INSERT INTO features (sample_id, mfcc, chroma,
                        spectral_centroid, spectral_rolloff, zero_crossing_rate,
                        onset_strength, onset_count, rms_peak, rms_mean,
                        attack_position)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(sample_id) DO UPDATE SET
                        mfcc=excluded.mfcc, chroma=excluded.chroma,
                        spectral_centroid=excluded.spectral_centroid,
                        spectral_rolloff=excluded.spectral_rolloff,
                        zero_crossing_rate=excluded.zero_crossing_rate,
                        onset_strength=excluded.onset_strength,
                        onset_count=excluded.onset_count,
                        rms_peak=excluded.rms_peak,
                        rms_mean=excluded.rms_mean,
                        attack_position=excluded.attack_position
                """, (
                    sample_id,
                    json.dumps(features.get('mfcc')) if features.get('mfcc') else None,
                    json.dumps(features.get('chroma')) if features.get('chroma') else None,
                    features.get('spectral_centroid'),
                    features.get('spectral_rolloff'),
                    features.get('zero_crossing_rate'),
                    features.get('onset_strength'),
                    features.get('onset_count'),
                    features.get('rms_peak'),
                    features.get('rms_mean'),
                    features.get('attack_position'),
                ))

            count += 1
            if count % 1000 == 0:
                conn.commit()
                print("  ... %d entries imported" % count)

        conn.commit()
        return count

    def sample_count(self):
        """Total number of samples in the database."""
        conn = self._connect()
        row = conn.execute("SELECT COUNT(*) as cnt FROM samples").fetchone()
        return row['cnt']

    def tag_coverage(self):
        """Report how many samples have each tag dimension populated."""
        conn = self._connect()
        total = self.sample_count()
        rows = conn.execute(
            "SELECT tag_key, COUNT(DISTINCT sample_id) as cnt "
            "FROM tags GROUP BY tag_key ORDER BY cnt DESC"
        ).fetchall()
        return {'total_samples': total,
                'dimensions': {r['tag_key']: r['cnt'] for r in rows}}

    def export_to_tag_dict(self):
        """Export the full database back to a _tags.json-style dict.

        For backward compatibility and human readability.
        """
        conn = self._connect()
        samples = conn.execute("SELECT * FROM samples").fetchall()

        result = {}
        for s in samples:
            entry = {
                'path': s['filepath'],
                'duration': s['duration_ms'] / 1000.0 if s['duration_ms'] else None,
                'bpm': s['bpm'],
                'bpm_source': s['bpm_source'],
                'key': s['key'],
                'key_source': s['key_source'],
                'loudness_db': s['loudness_db'],
                'file_hash': s['file_hash'],
            }

            # Tags
            tag_rows = conn.execute(
                "SELECT tag_key, tag_value FROM tags WHERE sample_id=?",
                (s['id'],)).fetchall()
            flat_tags = set()
            for tr in tag_rows:
                k, v = tr['tag_key'], tr['tag_value']
                if k in LIST_TAG_KEYS:
                    entry.setdefault(k, []).append(v)
                    flat_tags.add(v)
                elif k in SCALAR_TAG_KEYS:
                    entry[k] = v
                    flat_tags.add(v)
                elif k == 'quality_score':
                    try:
                        entry[k] = int(v)
                    except ValueError:
                        entry[k] = v
                else:
                    entry[k] = v

            if entry.get('type_code'):
                flat_tags.add(entry['type_code'])
            if entry.get('bpm'):
                flat_tags.add("%dbpm" % int(entry['bpm']))
            entry['tags'] = sorted(flat_tags)

            # Features
            feat_row = conn.execute(
                "SELECT * FROM features WHERE sample_id=?",
                (s['id'],)).fetchone()
            if feat_row:
                features = {}
                for k in ('spectral_centroid', 'spectral_rolloff',
                          'zero_crossing_rate', 'onset_strength', 'onset_count',
                          'rms_peak', 'rms_mean', 'attack_position'):
                    if feat_row[k] is not None:
                        features[k] = feat_row[k]
                for k in ('mfcc', 'chroma'):
                    if feat_row[k]:
                        try:
                            features[k] = json.loads(feat_row[k])
                        except (json.JSONDecodeError, TypeError):
                            pass
                if features:
                    entry['features'] = features

            result[s['filepath']] = entry

        return result
