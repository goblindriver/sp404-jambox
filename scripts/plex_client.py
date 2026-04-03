#!/usr/bin/env python3
"""
Read-only Plex database client for the SP-404 Jam Box.

Reads directly from the Plex SQLite database to extract rich music metadata:
artists, albums, tracks, moods, styles, genres, album art, play counts,
loudness analysis, and file paths.

NEVER writes to the Plex database. Read-only.

Usage:
    from plex_client import PlexMusicDB
    plex = PlexMusicDB()
    browse = plex.browse()           # artists, genres, moods, decades
    artist = plex.artist('Converge') # albums + tracks
    track = plex.track(12345)        # full metadata for one track
    results = plex.search('dark electronic')
"""
import json
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

# Plex database path (macOS default)
PLEX_DB_PATH = os.path.expanduser(
    "~/Library/Application Support/Plex Media Server/"
    "Plug-in Support/Databases/com.plexapp.plugins.library.db"
)

# Music library section ID (auto-detected on first use, fallback to 3)
MUSIC_SECTION_ID_DEFAULT = 3  # fallback if auto-detect fails

# Plex metadata_type constants
TYPE_ARTIST = 8
TYPE_ALBUM = 9
TYPE_TRACK = 10
TYPE_PLAYLIST = 15

# Plex tag_type constants
TAG_GENRE = 1
TAG_STUDIO = 4    # record label
TAG_COUNTRY = 8
TAG_MOOD = 300
TAG_STYLE = 301
TAG_COLLECTION = 303

# Mood → vibe dimension mapping
# Maps Plex's 298 mood tags to our 15 vibe tags
MOOD_TO_VIBE = {
    # → aggressive
    'aggressive': 'aggressive', 'hostile': 'aggressive', 'menacing': 'aggressive',
    'confrontational': 'aggressive', 'volatile': 'aggressive', 'angry': 'aggressive',
    'fierce': 'aggressive', 'savage': 'aggressive', 'ferocious': 'aggressive',
    'brutal': 'aggressive', 'ruthless': 'aggressive', 'vicious': 'aggressive',
    # → hype
    'energetic': 'hype', 'rousing': 'hype', 'lively': 'hype',
    'boisterous': 'hype', 'raucous': 'hype', 'exuberant': 'hype',
    'rollicking': 'hype', 'rowdy': 'hype', 'jubilant': 'hype',
    'anthemic': 'hype', 'celebratory': 'hype', 'freewheeling': 'hype',
    # → dark
    'brooding': 'dark', 'ominous': 'dark', 'sinister': 'dark',
    'foreboding': 'dark', 'malevolent': 'dark', 'bleak': 'dark',
    'somber': 'dark', 'funereal': 'dark', 'macabre': 'dark',
    'haunting': 'dark', 'eerie': 'dark', 'creepy': 'dark',
    # → tense
    'tense/anxious': 'tense', 'urgent': 'tense', 'intense': 'tense',
    'suspenseful': 'tense', 'paranoid': 'tense', 'restless': 'tense',
    'edgy': 'tense', 'anxious': 'tense', 'nervous': 'tense',
    # → dreamy
    'dreamy': 'dreamy', 'ethereal': 'dreamy', 'hypnotic': 'dreamy',
    'meditative': 'dreamy', 'transcendent': 'dreamy', 'spacious': 'dreamy',
    'atmospheric': 'dreamy', 'shimmering': 'dreamy', 'otherworldly': 'dreamy',
    # → nostalgic
    'nostalgic': 'nostalgic', 'wistful': 'nostalgic', 'sentimental': 'nostalgic',
    'bittersweet': 'nostalgic', 'poignant': 'nostalgic', 'yearning': 'nostalgic',
    'longing': 'nostalgic', 'reflective': 'nostalgic', 'reminiscent': 'nostalgic',
    # → melancholic
    'melancholy': 'melancholic', 'mournful': 'melancholic', 'sorrowful': 'melancholic',
    'plaintive': 'melancholic', 'elegiac': 'melancholic', 'grief-stricken': 'melancholic',
    'desolate': 'melancholic', 'despondent': 'melancholic', 'gloomy': 'melancholic',
    # → soulful
    'passionate': 'soulful', 'earnest': 'soulful', 'heartfelt': 'soulful',
    'warm': 'soulful', 'tender': 'soulful', 'intimate': 'soulful',
    'sincere': 'soulful', 'soulful': 'soulful', 'emotive': 'soulful',
    # → gritty
    'brash': 'gritty', 'visceral': 'gritty', 'raw': 'gritty',
    'gritty': 'gritty', 'abrasive': 'gritty', 'unpolished': 'gritty',
    'rough': 'gritty', 'coarse': 'gritty', 'lo-fi': 'gritty',
    # → mellow
    'mellow': 'mellow', 'gentle': 'mellow', 'calm': 'mellow',
    'peaceful': 'mellow', 'serene': 'mellow', 'soothing': 'mellow',
    'laid-back': 'mellow', 'relaxed': 'mellow', 'tranquil': 'mellow',
    # → eerie
    'eerie': 'eerie', 'mysterious': 'eerie', 'enigmatic': 'eerie',
    'unsettling': 'eerie', 'uncanny': 'eerie', 'spectral': 'eerie',
    # → uplifting
    'uplifting': 'uplifting', 'optimistic': 'uplifting', 'hopeful': 'uplifting',
    'triumphant': 'uplifting', 'joyous': 'uplifting', 'euphoric': 'uplifting',
    'exhilarating': 'uplifting', 'inspiring': 'uplifting',
    # → playful
    'playful': 'playful', 'whimsical': 'playful', 'quirky': 'playful',
    'humorous': 'playful', 'witty': 'playful', 'irreverent': 'playful',
    'tongue-in-cheek': 'playful', 'fun': 'playful', 'silly': 'playful',
    # → chill
    'chill': 'chill', 'cool': 'chill', 'detached': 'chill',
    'aloof': 'chill', 'nonchalant': 'chill', 'understated': 'chill',
    # → catch-all for unmapped
    'dramatic': 'tense', 'cathartic': 'aggressive', 'fiery': 'hype',
    'swaggering': 'gritty', 'confident': 'hype', 'rebellious': 'gritty',
    'defiant': 'aggressive', 'provocative': 'gritty',
}

# Style → genre dimension mapping
STYLE_TO_GENRE = {
    'alternative/indie rock': 'rock', 'heavy metal': 'rock',
    'alternative pop/rock': 'rock', 'indie rock': 'rock',
    'alternative metal': 'rock', 'punk revival': 'rock',
    'punk/new wave': 'rock', 'hardcore punk': 'rock',
    'pop punk': 'rock', 'death metal': 'rock',
    'hard rock': 'rock', 'post-hardcore': 'rock',
    'indie electronic': 'electronic', 'club/dance': 'house',
    'experimental rock': 'rock', 'progressive metal': 'rock',
    'doom metal': 'rock', 'grindcore': 'rock',
    'electroclash': 'electronic', 'synth pop': 'electronic',
    'new wave': 'electronic', 'post-punk': 'rock',
    'industrial': 'electronic', 'ebm': 'electronic',
    'trip-hop': 'electronic', 'downtempo': 'ambient',
    'ambient': 'ambient', 'shoegaze': 'rock',
    'dream pop': 'rock', 'noise pop': 'rock',
    'folk-rock': 'rock', 'country-rock': 'rock',
    'americana': 'soul', 'neo-soul': 'soul',
    'funk': 'funk', 'disco': 'disco',
    'soul': 'soul', 'r&b': 'soul',
    'jazz': 'jazz', 'hip-hop': 'electronic',
    'rap': 'electronic', 'reggae': 'reggae',
    'dub': 'dub', 'ska': 'rock',
    'latin': 'latin', 'afrobeat': 'afrobeat',
    'house': 'house', 'techno': 'electronic',
    'trance': 'electronic', 'drum and bass': 'electronic',
    'uk garage': 'uk-garage', 'garage rock': 'rock',
    'psychedelic': 'psychedelic', 'blues': 'soul',
    'gospel': 'gospel', 'classical': 'classical',
}


class PlexMusicDB:
    """Read-only interface to the Plex music database."""

    def __init__(self, db_path=None):
        self.db_path = db_path or PLEX_DB_PATH
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(
                f"Plex database not found at {self.db_path}. "
                "Is Plex Media Server installed?"
            )
        self._section_id = self._detect_music_section()

    def _detect_music_section(self):
        """Auto-detect the music library section ID (section_type=8 for music)."""
        try:
            conn = self._connect()
            row = conn.execute("""
                SELECT id FROM library_sections
                WHERE section_type = 8
                ORDER BY id LIMIT 1
            """).fetchone()
            conn.close()
            if row:
                return row['id']
        except Exception:
            pass
        return MUSIC_SECTION_ID_DEFAULT

    def _connect(self):
        """Open a read-only connection to the Plex database."""
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=3000")
        except sqlite3.DatabaseError:
            pass
        return conn

    def _get_tags(self, conn, metadata_item_id, tag_type):
        """Get all tags of a given type for a metadata item."""
        rows = conn.execute("""
            SELECT t.tag FROM tags t
            JOIN taggings tg ON t.id = tg.tag_id
            WHERE tg.metadata_item_id = ? AND t.tag_type = ?
        """, (metadata_item_id, tag_type)).fetchall()
        return [r['tag'] for r in rows if isinstance(r['tag'], str) and r['tag']]

    def _get_tags_bulk(self, conn, item_ids, tag_type):
        """Get tags for multiple items at once. Returns {item_id: [tags]}.
        Chunks queries to stay within SQLite variable limits."""
        if not item_ids:
            return {}
        result = defaultdict(list)
        # SQLite has a variable limit (default 999). Chunk to be safe.
        chunk_size = 900
        for i in range(0, len(item_ids), chunk_size):
            chunk = item_ids[i:i + chunk_size]
            placeholders = ','.join('?' * len(chunk))
            rows = conn.execute(f"""
                SELECT tg.metadata_item_id, t.tag FROM tags t
                JOIN taggings tg ON t.id = tg.tag_id
                WHERE tg.metadata_item_id IN ({placeholders}) AND t.tag_type = ?
            """, list(chunk) + [tag_type]).fetchall()
            for r in rows:
                if isinstance(r['tag'], str) and r['tag']:
                    result[r['metadata_item_id']].append(r['tag'])
        return dict(result)

    def _moods_to_vibes(self, moods):
        """Convert Plex mood tags to our vibe dimension tags."""
        vibes = set()
        for mood in moods:
            if not isinstance(mood, str):
                continue
            vibe = MOOD_TO_VIBE.get(mood.lower())
            if vibe:
                vibes.add(vibe)
        return sorted(vibes)

    def _styles_to_genres(self, styles):
        """Convert Plex style tags to our genre dimension tags."""
        genres = set()
        for style in styles:
            if not isinstance(style, str):
                continue
            genre = STYLE_TO_GENRE.get(style.lower())
            if genre:
                genres.add(genre)
        return sorted(genres)

    def is_available(self):
        """Check if Plex database is accessible."""
        try:
            conn = self._connect()
            conn.execute("SELECT 1 FROM library_sections WHERE id=?",
                         (self._section_id,)).fetchone()
            conn.close()
            return True
        except Exception:
            return False

    def stats(self):
        """Get library statistics."""
        conn = self._connect()
        try:
            counts = {}
            for mtype, label in [(TYPE_ARTIST, 'artists'),
                                 (TYPE_ALBUM, 'albums'),
                                 (TYPE_TRACK, 'tracks')]:
                row = conn.execute("""
                    SELECT COUNT(*) as c FROM metadata_items
                    WHERE library_section_id=? AND metadata_type=?
                """, (self._section_id, mtype)).fetchone()
                counts[label] = row['c']

            # Mood count
            row = conn.execute("""
                SELECT COUNT(DISTINCT t.tag) as c FROM tags t
                JOIN taggings tg ON t.id = tg.tag_id
                JOIN metadata_items mi ON tg.metadata_item_id = mi.id
                WHERE mi.library_section_id=? AND t.tag_type=?
            """, (self._section_id, TAG_MOOD)).fetchone()
            counts['moods'] = row['c']

            # Style count
            row = conn.execute("""
                SELECT COUNT(DISTINCT t.tag) as c FROM tags t
                JOIN taggings tg ON t.id = tg.tag_id
                JOIN metadata_items mi ON tg.metadata_item_id = mi.id
                WHERE mi.library_section_id=? AND t.tag_type=?
            """, (self._section_id, TAG_STYLE)).fetchone()
            counts['styles'] = row['c']

            # Root path
            row = conn.execute("""
                SELECT root_path FROM section_locations
                WHERE library_section_id=?
            """, (self._section_id,)).fetchone()
            counts['root_path'] = row['root_path'] if row else None

            return counts
        finally:
            conn.close()

    def browse(self):
        """Get browseable aggregates: artists, genres, moods, styles, decades."""
        conn = self._connect()
        try:
            # Artists with album/track counts
            artists = conn.execute("""
                SELECT mi.id, mi.title as name, mi.summary,
                       COUNT(DISTINCT album.id) as album_count,
                       COUNT(DISTINCT track.id) as track_count
                FROM metadata_items mi
                LEFT JOIN metadata_items album ON album.parent_id = mi.id
                    AND album.metadata_type = ?
                LEFT JOIN metadata_items track ON track.parent_id = album.id
                    AND track.metadata_type = ?
                WHERE mi.library_section_id = ? AND mi.metadata_type = ?
                GROUP BY mi.id
                ORDER BY mi.title_sort COLLATE NOCASE
            """, (TYPE_ALBUM, TYPE_TRACK, self._section_id, TYPE_ARTIST)).fetchall()

            artist_list = [{
                'id': a['id'],
                'name': a['name'],
                'album_count': a['album_count'],
                'track_count': a['track_count'],
                'has_bio': bool(a['summary']),
            } for a in artists]

            # Genres (from tracks)
            genres = conn.execute("""
                SELECT t.tag, COUNT(*) as c
                FROM tags t
                JOIN taggings tg ON t.id = tg.tag_id
                JOIN metadata_items mi ON tg.metadata_item_id = mi.id
                WHERE mi.library_section_id=? AND t.tag_type=?
                GROUP BY t.tag ORDER BY c DESC
            """, (self._section_id, TAG_GENRE)).fetchall()

            # Moods (from tracks — most interesting)
            moods = conn.execute("""
                SELECT t.tag, COUNT(*) as c
                FROM tags t
                JOIN taggings tg ON t.id = tg.tag_id
                JOIN metadata_items mi ON tg.metadata_item_id = mi.id
                WHERE mi.library_section_id=? AND t.tag_type=?
                  AND mi.metadata_type=?
                GROUP BY t.tag ORDER BY c DESC
            """, (self._section_id, TAG_MOOD, TYPE_TRACK)).fetchall()

            # Styles
            styles = conn.execute("""
                SELECT t.tag, COUNT(*) as c
                FROM tags t
                JOIN taggings tg ON t.id = tg.tag_id
                JOIN metadata_items mi ON tg.metadata_item_id = mi.id
                WHERE mi.library_section_id=? AND t.tag_type=?
                GROUP BY t.tag ORDER BY c DESC
            """, (self._section_id, TAG_STYLE)).fetchall()

            # Decades (tracks rarely have year, use album year)
            decades = conn.execute("""
                SELECT (COALESCE(mi.year, album.year) / 10) * 10 as decade,
                       COUNT(*) as c
                FROM metadata_items mi
                LEFT JOIN metadata_items album ON mi.parent_id = album.id
                WHERE mi.library_section_id=? AND mi.metadata_type=?
                  AND COALESCE(mi.year, album.year) IS NOT NULL
                  AND COALESCE(mi.year, album.year) >= 1900
                GROUP BY decade ORDER BY decade
            """, (self._section_id, TYPE_TRACK)).fetchall()

            return {
                'artists': artist_list,
                'genres': {r['tag']: r['c'] for r in genres},
                'moods': {r['tag']: r['c'] for r in moods},
                'styles': {r['tag']: r['c'] for r in styles},
                'decades': {f"{r['decade']}s": r['c'] for r in decades},
                'total_tracks': sum(a['track_count'] for a in artist_list),
                'total_artists': len(artist_list),
            }
        finally:
            conn.close()

    def artist(self, artist_name=None, artist_id=None):
        """Get full artist detail: bio, albums, tracks with moods."""
        conn = self._connect()
        try:
            if artist_id:
                artist_row = conn.execute("""
                    SELECT * FROM metadata_items
                    WHERE id=? AND metadata_type=?
                """, (artist_id, TYPE_ARTIST)).fetchone()
            else:
                artist_row = conn.execute("""
                    SELECT * FROM metadata_items
                    WHERE library_section_id=? AND metadata_type=?
                      AND title=? COLLATE NOCASE
                """, (self._section_id, TYPE_ARTIST, artist_name)).fetchone()

            if not artist_row:
                return None

            # Artist-level tags
            artist_genres = self._get_tags(conn, artist_row['id'], TAG_GENRE)
            artist_moods = self._get_tags(conn, artist_row['id'], TAG_MOOD)
            artist_styles = self._get_tags(conn, artist_row['id'], TAG_STYLE)
            artist_country = self._get_tags(conn, artist_row['id'], TAG_COUNTRY)

            # Albums
            album_rows = conn.execute("""
                SELECT * FROM metadata_items
                WHERE parent_id=? AND metadata_type=?
                ORDER BY year, title_sort
            """, (artist_row['id'], TYPE_ALBUM)).fetchall()

            albums = []
            for album in album_rows:
                # Tracks in this album
                track_rows = conn.execute("""
                    SELECT mi.id, mi.title, mi.'index' as track_num,
                           mi.duration, mi.year,
                           mitem.bitrate, mitem.container, mitem.audio_codec,
                           mp.file as file_path, mp.size as file_size
                    FROM metadata_items mi
                    LEFT JOIN media_items mitem ON mitem.metadata_item_id = mi.id
                    LEFT JOIN media_parts mp ON mp.media_item_id = mitem.id
                    WHERE mi.parent_id=? AND mi.metadata_type=?
                    ORDER BY mi.'index'
                """, (album['id'], TYPE_TRACK)).fetchall()

                # Bulk fetch moods for all tracks in album
                track_ids = [t['id'] for t in track_rows]
                track_moods = self._get_tags_bulk(conn, track_ids, TAG_MOOD)
                track_genres = self._get_tags_bulk(conn, track_ids, TAG_GENRE)
                track_styles = self._get_tags_bulk(conn, track_ids, TAG_STYLE)

                tracks = []
                for t in track_rows:
                    moods = track_moods.get(t['id'], [])
                    tracks.append({
                        'id': t['id'],
                        'title': t['title'],
                        'track_num': t['track_num'],
                        'duration': t['duration'],
                        'duration_str': _format_duration(t['duration']),
                        'year': t['year'],
                        'bitrate': t['bitrate'],
                        'codec': t['audio_codec'],
                        'container': t['container'],
                        'file_path': t['file_path'],
                        'file_size': t['file_size'],
                        'moods': moods,
                        'vibes': self._moods_to_vibes(moods),
                        'genres': track_genres.get(t['id'], []),
                        'styles': track_styles.get(t['id'], []),
                    })

                album_genres = self._get_tags(conn, album['id'], TAG_GENRE)
                album_moods = self._get_tags(conn, album['id'], TAG_MOOD)
                album_styles = self._get_tags(conn, album['id'], TAG_STYLE)

                albums.append({
                    'id': album['id'],
                    'title': album['title'],
                    'year': album['year'],
                    'studio': album['studio'],  # record label
                    'summary': album['summary'],
                    'thumb': album['user_thumb_url'],
                    'genres': album_genres,
                    'moods': album_moods,
                    'styles': album_styles,
                    'tracks': tracks,
                })

            return {
                'id': artist_row['id'],
                'name': artist_row['title'],
                'summary': artist_row['summary'],
                'thumb': artist_row['user_thumb_url'],
                'country': artist_country,
                'genres': artist_genres,
                'moods': artist_moods,
                'vibes': self._moods_to_vibes(artist_moods),
                'styles': artist_styles,
                'albums': albums,
            }
        finally:
            conn.close()

    def track(self, track_id):
        """Get full metadata for a single track."""
        conn = self._connect()
        try:
            row = conn.execute("""
                SELECT mi.id, mi.title, mi.'index' as track_num,
                       mi.duration, mi.year, mi.guid,
                       album.id as album_id, album.title as album,
                       album.year as album_year, album.studio as label,
                       album.user_thumb_url as album_thumb,
                       artist.id as artist_id, artist.title as artist,
                       artist.summary as artist_bio,
                       mitem.bitrate, mitem.container, mitem.audio_codec,
                       mp.file as file_path, mp.size as file_size
                FROM metadata_items mi
                LEFT JOIN metadata_items album ON mi.parent_id = album.id
                LEFT JOIN metadata_items artist ON album.parent_id = artist.id
                LEFT JOIN media_items mitem ON mitem.metadata_item_id = mi.id
                LEFT JOIN media_parts mp ON mp.media_item_id = mitem.id
                WHERE mi.id=? AND mi.metadata_type=?
            """, (track_id, TYPE_TRACK)).fetchone()

            if not row:
                return None

            moods = self._get_tags(conn, track_id, TAG_MOOD)
            genres = self._get_tags(conn, track_id, TAG_GENRE)
            styles = self._get_tags(conn, track_id, TAG_STYLE)

            # Loudness data from media_streams
            loudness = {}
            stream = conn.execute("""
                SELECT ms.extra_data FROM media_streams ms
                JOIN media_items mitem ON ms.media_item_id = mitem.id
                WHERE mitem.metadata_item_id=? AND ms.stream_type_id=2
                LIMIT 1
            """, (track_id,)).fetchone()
            if stream and stream['extra_data']:
                _parse_loudness(stream['extra_data'], loudness)

            # Play count
            play_count = 0
            last_played = None
            settings = conn.execute("""
                SELECT view_count, last_viewed_at FROM metadata_item_settings
                WHERE guid=?
            """, (row['guid'],)).fetchone()
            if settings:
                play_count = settings['view_count'] or 0
                last_played = settings['last_viewed_at']

            return {
                'id': row['id'],
                'title': row['title'],
                'track_num': row['track_num'],
                'duration': row['duration'],
                'duration_str': _format_duration(row['duration']),
                'year': row['year'] or row['album_year'],
                'artist': row['artist'],
                'artist_id': row['artist_id'],
                'album': row['album'],
                'album_id': row['album_id'],
                'album_thumb': row['album_thumb'],
                'label': row['label'],
                'bitrate': row['bitrate'],
                'codec': row['audio_codec'],
                'container': row['container'],
                'file_path': row['file_path'],
                'file_size': row['file_size'],
                'moods': moods,
                'vibes': self._moods_to_vibes(moods),
                'genres': genres,
                'styles': styles,
                'loudness': loudness,
                'play_count': play_count,
                'last_played': last_played,
            }
        finally:
            conn.close()

    def search(self, query, limit=100):
        """Search tracks, albums, and artists by text."""
        conn = self._connect()
        try:
            q = f"%{query}%"
            results = []

            # Search tracks
            tracks = conn.execute("""
                SELECT mi.id, mi.title, mi.duration,
                       album.title as album, artist.title as artist,
                       album.user_thumb_url as thumb, mi.year
                FROM metadata_items mi
                LEFT JOIN metadata_items album ON mi.parent_id = album.id
                LEFT JOIN metadata_items artist ON album.parent_id = artist.id
                WHERE mi.library_section_id=? AND mi.metadata_type=?
                  AND (mi.title LIKE ? OR artist.title LIKE ?
                       OR album.title LIKE ?)
                LIMIT ?
            """, (self._section_id, TYPE_TRACK, q, q, q, limit)).fetchall()

            for t in tracks:
                score = 0
                ql = query.lower()
                if ql in (t['artist'] or '').lower():
                    score += 3
                if ql in (t['title'] or '').lower():
                    score += 2
                if ql in (t['album'] or '').lower():
                    score += 1
                results.append({
                    'type': 'track',
                    'id': t['id'],
                    'title': t['title'],
                    'artist': t['artist'],
                    'album': t['album'],
                    'thumb': t['thumb'],
                    'duration': t['duration'],
                    'duration_str': _format_duration(t['duration']),
                    'year': t['year'],
                    'score': score,
                })

            results.sort(key=lambda r: -r['score'])
            return results[:limit]
        finally:
            conn.close()

    def search_by_mood(self, mood, limit=100):
        """Find tracks tagged with a specific Plex mood."""
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT mi.id, mi.title, mi.duration,
                       album.title as album, artist.title as artist,
                       album.user_thumb_url as thumb, mi.year
                FROM metadata_items mi
                JOIN taggings tg ON tg.metadata_item_id = mi.id
                JOIN tags t ON t.id = tg.tag_id
                LEFT JOIN metadata_items album ON mi.parent_id = album.id
                LEFT JOIN metadata_items artist ON album.parent_id = artist.id
                WHERE mi.library_section_id=? AND mi.metadata_type=?
                  AND t.tag_type=? AND t.tag=? COLLATE NOCASE
                LIMIT ?
            """, (self._section_id, TYPE_TRACK, TAG_MOOD, mood, limit)).fetchall()

            return [{
                'id': r['id'],
                'title': r['title'],
                'artist': r['artist'],
                'album': r['album'],
                'thumb': r['thumb'],
                'duration': r['duration'],
                'duration_str': _format_duration(r['duration']),
                'year': r['year'],
            } for r in rows]
        finally:
            conn.close()

    def search_by_style(self, style, limit=100):
        """Find tracks tagged with a specific Plex style."""
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT mi.id, mi.title, mi.duration,
                       album.title as album, artist.title as artist,
                       album.user_thumb_url as thumb, mi.year
                FROM metadata_items mi
                JOIN taggings tg ON tg.metadata_item_id = mi.id
                JOIN tags t ON t.id = tg.tag_id
                LEFT JOIN metadata_items album ON mi.parent_id = album.id
                LEFT JOIN metadata_items artist ON album.parent_id = artist.id
                WHERE mi.library_section_id=? AND mi.metadata_type=?
                  AND t.tag_type=? AND t.tag=? COLLATE NOCASE
                LIMIT ?
            """, (self._section_id, TYPE_TRACK, TAG_STYLE, style, limit)).fetchall()

            return [{
                'id': r['id'],
                'title': r['title'],
                'artist': r['artist'],
                'album': r['album'],
                'thumb': r['thumb'],
                'duration': r['duration'],
                'duration_str': _format_duration(r['duration']),
                'year': r['year'],
            } for r in rows]
        finally:
            conn.close()

    def playlists(self):
        """Get all user playlists."""
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT id, title, media_item_count, duration,
                       created_at, updated_at
                FROM metadata_items
                WHERE metadata_type=?
                ORDER BY title
            """, (TYPE_PLAYLIST,)).fetchall()

            return [{
                'id': r['id'],
                'title': r['title'],
                'track_count': r['media_item_count'] or 0,
                'duration': r['duration'],
            } for r in rows]
        finally:
            conn.close()

    def most_played(self, limit=50):
        """Get most-played tracks (from Plex play history)."""
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT miv.grandparent_title as artist,
                       miv.parent_title as album,
                       miv.title, miv.guid,
                       COUNT(*) as play_count,
                       MAX(miv.viewed_at) as last_played
                FROM metadata_item_views miv
                WHERE miv.library_section_id=?
                GROUP BY miv.guid
                ORDER BY play_count DESC
                LIMIT ?
            """, (self._section_id, limit)).fetchall()

            return [{
                'artist': r['artist'],
                'album': r['album'],
                'title': r['title'],
                'play_count': r['play_count'],
                'last_played': r['last_played'],
            } for r in rows]
        finally:
            conn.close()

    def build_music_index(self):
        """Build a complete music index from Plex data.

        Returns a dict keyed by relative file path with full metadata
        including moods, styles, genres, vibes, loudness, and play counts.
        This replaces the old ID3-based index_music.py output.
        """
        conn = self._connect()
        try:
            # Get the music root path
            root_row = conn.execute("""
                SELECT root_path FROM section_locations
                WHERE library_section_id=?
            """, (self._section_id,)).fetchone()
            root_path = root_row['root_path'] if root_row else ''

            # All tracks with file paths
            tracks = conn.execute("""
                SELECT mi.id, mi.title, mi.'index' as track_num,
                       mi.duration, mi.year, mi.guid,
                       album.id as album_id, album.title as album,
                       album.year as album_year, album.studio as label,
                       album.user_thumb_url as album_thumb,
                       artist.id as artist_id, artist.title as artist,
                       mitem.bitrate, mitem.audio_codec,
                       mp.file as file_path
                FROM metadata_items mi
                LEFT JOIN metadata_items album ON mi.parent_id = album.id
                LEFT JOIN metadata_items artist ON album.parent_id = artist.id
                LEFT JOIN media_items mitem ON mitem.metadata_item_id = mi.id
                LEFT JOIN media_parts mp ON mp.media_item_id = mitem.id
                WHERE mi.library_section_id=? AND mi.metadata_type=?
            """, (self._section_id, TYPE_TRACK)).fetchall()

            # Bulk fetch all tags
            all_track_ids = [t['id'] for t in tracks]
            all_moods = self._get_tags_bulk(conn, all_track_ids, TAG_MOOD)
            all_genres = self._get_tags_bulk(conn, all_track_ids, TAG_GENRE)
            all_styles = self._get_tags_bulk(conn, all_track_ids, TAG_STYLE)

            # Build index
            index = {}
            for t in tracks:
                file_path = t['file_path']
                if not file_path:
                    continue

                # Make path relative to music root
                if root_path and file_path.startswith(root_path):
                    rel_path = file_path[len(root_path):].lstrip('/')
                else:
                    rel_path = file_path

                moods = all_moods.get(t['id'], [])
                genres = all_genres.get(t['id'], [])
                styles = all_styles.get(t['id'], [])

                index[rel_path] = {
                    'plex_id': t['id'],
                    'title': t['title'],
                    'artist': t['artist'],
                    'artist_id': t['artist_id'],
                    'album': t['album'],
                    'album_id': t['album_id'],
                    'album_thumb': t['album_thumb'],
                    'year': t['year'] or t['album_year'],
                    'label': t['label'],
                    'track_num': t['track_num'],
                    'duration': t['duration'],
                    'bitrate': t['bitrate'],
                    'codec': t['audio_codec'],
                    'moods': moods,
                    'vibes': self._moods_to_vibes(moods),
                    'genres': genres,
                    'styles': styles,
                    'genre': genres[0] if genres else None,
                    'file_path': file_path,
                }

            return {
                'tracks': index,
                'root_path': root_path,
                'total_tracks': len(index),
            }
        finally:
            conn.close()


def _format_duration(ms):
    """Format milliseconds to M:SS string."""
    if not ms:
        return ''
    try:
        s = int(float(ms) // 1000)
    except (TypeError, ValueError):
        return ''
    return f"{s // 60}:{s % 60:02d}"


def _parse_loudness(extra_data_str, out):
    """Parse loudness data from media_stream extra_data JSON."""
    if not isinstance(extra_data_str, str):
        return
    try:
        if extra_data_str.startswith('{'):
            data = json.loads(extra_data_str)
        else:
            # URL-encoded key=value format
            data = {}
            for part in extra_data_str.split('&'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    data[k] = v

        for key in ('ld:gain', 'ld:peak', 'ld:loudness', 'ld:lra'):
            if key in data:
                try:
                    out[key.split(':')[1]] = float(data[key])
                except ValueError:
                    pass
    except (json.JSONDecodeError, ValueError):
        pass


# ── CLI for testing ──

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Plex Music DB client')
    parser.add_argument('--stats', action='store_true', help='Show library stats')
    parser.add_argument('--browse', action='store_true', help='Show browse data')
    parser.add_argument('--artist', type=str, help='Show artist detail')
    parser.add_argument('--track', type=int, help='Show track detail by ID')
    parser.add_argument('--search', type=str, help='Search tracks')
    parser.add_argument('--mood', type=str, help='Find tracks by mood')
    parser.add_argument('--style', type=str, help='Find tracks by style')
    parser.add_argument('--playlists', action='store_true', help='List playlists')
    parser.add_argument('--most-played', action='store_true', help='Most played tracks')
    parser.add_argument('--build-index', action='store_true', help='Build full music index')
    args = parser.parse_args()

    plex = PlexMusicDB()

    if args.stats:
        s = plex.stats()
        print(f"Artists: {s['artists']}")
        print(f"Albums:  {s['albums']}")
        print(f"Tracks:  {s['tracks']}")
        print(f"Moods:   {s['moods']}")
        print(f"Styles:  {s['styles']}")
        print(f"Root:    {s['root_path']}")

    elif args.browse:
        b = plex.browse()
        print(f"\nTotal: {b['total_tracks']} tracks, {b['total_artists']} artists")
        print(f"\nTop genres:")
        for g, c in list(b['genres'].items())[:15]:
            print(f"  {g}: {c}")
        print(f"\nTop moods:")
        for m, c in list(b['moods'].items())[:20]:
            print(f"  {m}: {c}")
        print(f"\nTop styles:")
        for s, c in list(b['styles'].items())[:15]:
            print(f"  {s}: {c}")
        print(f"\nDecades:")
        for d, c in b['decades'].items():
            print(f"  {d}: {c}")

    elif args.artist:
        a = plex.artist(args.artist)
        if not a:
            print(f"Artist '{args.artist}' not found")
        else:
            print(f"\n{a['name']}")
            print(f"Genres: {', '.join(a['genres'])}")
            print(f"Moods: {', '.join(a['moods'][:10])}")
            print(f"Vibes: {', '.join(a['vibes'])}")
            print(f"Styles: {', '.join(a['styles'][:10])}")
            if a['country']:
                print(f"Country: {', '.join(a['country'])}")
            if a['summary']:
                print(f"\nBio: {a['summary'][:200]}...")
            print(f"\nAlbums ({len(a['albums'])}):")
            for alb in a['albums']:
                print(f"  {alb['year'] or '???'} — {alb['title']} ({len(alb['tracks'])} tracks)")
                if alb['studio']:
                    print(f"         Label: {alb['studio']}")

    elif args.track:
        t = plex.track(args.track)
        if not t:
            print(f"Track {args.track} not found")
        else:
            print(json.dumps(t, indent=2, default=str))

    elif args.search:
        results = plex.search(args.search, limit=20)
        for r in results:
            print(f"  {r['artist']} — {r['title']} ({r['album']}) [{r['duration_str']}]")

    elif args.mood:
        results = plex.search_by_mood(args.mood, limit=20)
        print(f"\nTracks with mood '{args.mood}':")
        for r in results:
            print(f"  {r['artist']} — {r['title']} [{r['duration_str']}]")

    elif args.style:
        results = plex.search_by_style(args.style, limit=20)
        print(f"\nTracks with style '{args.style}':")
        for r in results:
            print(f"  {r['artist']} — {r['title']} [{r['duration_str']}]")

    elif args.playlists:
        for p in plex.playlists():
            print(f"  {p['title']}: {p['track_count']} tracks")

    elif args.most_played:
        results = plex.most_played()
        if not results:
            print("No play history found")
        else:
            for r in results:
                print(f"  {r['play_count']}x — {r['artist']} — {r['title']}")

    elif args.build_index:
        print("Building music index from Plex...")
        result = plex.build_music_index()
        out_path = os.path.expanduser("~/Music/SP404-Sample-Library/_music_index.json")
        with open(out_path, 'w') as f:
            json.dump(result, f, indent=1)
        print(f"Saved {result['total_tracks']} tracks to {out_path}")

    else:
        # Default: show stats
        s = plex.stats()
        print(f"Plex Music Library: {s['tracks']} tracks, {s['artists']} artists, "
              f"{s['albums']} albums, {s['moods']} moods, {s['styles']} styles")
