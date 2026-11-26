import csv
import json
import re
import sqlite3
import time
import unicodedata
from functools import lru_cache
from threading import Lock
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from web.catalog_snapshot import catalog_paths


FIELDS = ('song_id', 'song_name', 'artist', 'genres')
MBID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.executescript("""
        CREATE TABLE IF NOT EXISTS catalog (
            song_id TEXT PRIMARY KEY, song_name TEXT NOT NULL, artist TEXT NOT NULL,
            genres TEXT NOT NULL, name_key TEXT NOT NULL, artist_key TEXT NOT NULL,
            source TEXT NOT NULL CHECK (source IN ('csv', 'musicbrainz'))
        );
        CREATE INDEX IF NOT EXISTS catalog_name_artist ON catalog(name_key, artist_key);
        CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            requested INTEGER CHECK (requested BETWEEN 1 AND 100)
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY, playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
            song_id TEXT NOT NULL, song_name TEXT NOT NULL, artist TEXT NOT NULL,
            genres TEXT NOT NULL, matched INTEGER NOT NULL,
            score INTEGER, reason TEXT, UNIQUE (playlist_id, song_id)
        );
    """)
    return db


def sync_catalog(db, path):
    parts = catalog_paths(path)
    fingerprint = json.dumps([(str(item.resolve()), s.st_size, s.st_mtime_ns)
                              for item in parts for s in (item.stat(),)])
    sql = "SELECT value FROM metadata WHERE name = 'catalog_csv'"
    row = db.execute(sql).fetchone()
    if row and row['value'] == fingerprint:
        return
    with db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute(sql).fetchone()
        if row and row['value'] == fingerprint:
            return
        db.execute("DELETE FROM catalog WHERE source = 'csv'")
        for item in parts:
            with item.open(encoding='utf-8-sig', newline='') as file:
                reader = csv.DictReader(file)
                if not set(FIELDS).issubset(reader.fieldnames or ()):
                    raise ValueError('歌曲库缺少必需字段。')
                def rows():
                    for raw in reader:
                        song_id, name, artist, genres = [(raw[key] or '').strip() for key in FIELDS]
                        if song_id and name:
                            yield song_id, name, artist, genres, normalize(name), normalize(artist), 'csv'
                db.executemany('INSERT INTO catalog VALUES (?, ?, ?, ?, ?, ?, ?)', rows())
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('catalog_csv', ?)", (fingerprint,))


def local_search(db, text):
    key = normalize(text)
    return [dict(row) for row in db.execute("""
        SELECT song_id, song_name, artist, genres, source FROM catalog
        WHERE instr(name_key, ?) > 0 OR instr(artist_key, ?) > 0
        ORDER BY CASE WHEN name_key = ? THEN 0 WHEN artist_key = ? THEN 1 ELSE 2 END, song_id
        LIMIT 20
    """, (key, key, key, key))]


_lock = Lock()
_last_request = 0.0


def _musicbrainz(path, params):
    global _last_request
    url = 'https://musicbrainz.org/ws/2/' + path + '?' + urlencode({**params, 'fmt': 'json'})
    request = Request(url, headers={
        'User-Agent': 'MusicRecommendationCourse/2.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)',
        'Accept': 'application/json',
    })
    with _lock:
        time.sleep(max(0.0, 1.1 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        with urlopen(request, timeout=6) as response:
            return json.load(response)


@lru_cache(maxsize=128)
def genre_mapping(path):
    if not path.is_file():
        return {}
    with path.open(encoding='utf-8-sig', newline='') as file:
        return {re.sub(r'[\s_-]+', '-', row['genre'].strip().lower()): row['group_zh']
                for row in csv.DictReader(file)}


def _from_recording(entry, mapping, fallback_tags=False):
    mbid = entry.get('id', '')
    title = (entry.get('title') or '').strip()
    if not MBID.fullmatch(mbid) or not title:
        return None
    artists = [credit.get('name') or credit.get('artist', {}).get('name', '')
               for credit in entry.get('artist-credit', [])]
    tags = entry.get('genres', []) or (entry.get('tags', []) if fallback_tags else [])
    genres = set()
    for tag in tags:
        if tag.get('count', 1) > 0:
            key = re.sub(r'[\s_-]+', '-', tag['name'].strip().lower())
            genres.update(filter(None, mapping.get(key, '').split('|')))
    return dict(song_id='mb:' + mbid, song_name=title,
                artist=' & '.join(filter(None, artists)), genres='|'.join(sorted(genres)),
                source='musicbrainz', version=entry.get('disambiguation') or '',
                release=next((item['title'] for item in entry.get('releases', [])
                              if item.get('title')), ''))


@lru_cache(maxsize=128)
def online_search(text, map_path):
    term = ''.join(' ' if c in '"\\' else c for c in text)
    result = _musicbrainz('recording', {'query': f'recording:"{term}" OR artist:"{term}"', 'limit': 10})
    mapping = genre_mapping(map_path)
    return tuple(song for entry in result.get('recordings', [])
                 if (song := _from_recording(entry, mapping, fallback_tags=True)))


def online_recording(mbid, map_path):
    if not MBID.fullmatch(mbid):
        return None
    return _from_recording(_musicbrainz('recording/' + mbid, {'inc': 'genres+artist-credits'}),
                           genre_mapping(map_path))
