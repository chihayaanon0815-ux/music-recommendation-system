"""Collect song metadata by artist using Apple, Deezer and MusicBrainz."""
import argparse
import csv
import ctypes
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

APPLE = 'https://itunes.apple.com/'
DEEZER = 'https://api.deezer.com/'
MB = 'https://musicbrainz.org/ws/2/'
AGENT = 'CourseMusicCatalog/1.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)'
FIELDS = ('song_id', 'song_name', 'artist', 'genres')
ALIASES = (
    ('周杰伦', '周杰倫', 'Jay Chou'), ('陈奕迅', '陳奕迅', 'Eason Chan'),
    ('邓丽君', '鄧麗君', 'Teresa Teng'), ('王菲', 'Faye Wong'),
    ('邓紫棋', '鄧紫棋', 'G.E.M.', 'G.E.M. 鄧紫棋'),
    ('林俊杰', '林俊傑', 'JJ Lin'), ('张学友', '張學友', 'Jacky Cheung'),
    ('张惠妹', '張惠妹', 'A-Mei', 'aMEI'), ('蔡依林', 'Jolin Tsai'),
    ('孙燕姿', '孫燕姿', 'Stefanie Sun'), ('刘德华', '劉德華', 'Andy Lau'),
    ('五月天', 'Mayday'), ('梁静茹', '梁靜茹', 'Fish Leong'),
    ('宇多田ヒカル', '宇多田光', 'Hikaru Utada'), ('苏打绿', '蘇打綠', 'Sodagreen'),
)
VERSION = re.compile(
    r'\s*(?:[（(\[]([^）)\]]+)[）)\]]|\s+-\s+(.+))\s*$'
)
VERSION_HINT = re.compile(
    r'^(?:live|remaster(?:ed)?|remix|acoustic|instrumental|demo|radio edit|mono|stereo)\b'
    r'|^(?:19|20)\d{2}\s+(?:remaster(?:ed)?|remix)\b'
    r'|(?:现场|現場|演唱会|演唱會|重制|重製|混音|伴奏|不插电|不插電)(?:版|版本)?$',
    re.I,
)


def simplified(value):
    if not hasattr(ctypes, 'windll') or not value:
        return value
    buf = ctypes.create_unicode_buffer(len(value) * 2 + 1)
    size = ctypes.windll.kernel32.LCMapStringEx(
        'zh-CN', 0x02000000, value, -1, buf, len(buf), None, None, 0
    )
    return buf.value if size else value


@lru_cache(maxsize=250000)
def key(value):
    return ' '.join(simplified(unicodedata.normalize('NFKC', value)).casefold().split())


def song_title(title):
    while match := VERSION.search(title):
        if not VERSION_HINT.search(match.group(1) or match.group(2)):
            break
        title = title[:match.start()].strip()
    return title


@lru_cache(maxsize=50000)
def names_for(name):
    aliases = next((a for a in ALIASES if key(name) in {key(n) for n in a}), ())
    return {key(n) for n in (name, *aliases)}


class Client:
    def __init__(self, cache):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.last = {}
        self.failures = {}
        self.paused_until = {}
        self.locks = {host: threading.Lock() for host in
                      ('itunes.apple.com', 'api.deezer.com', 'musicbrainz.org', 'api.audius.co')}

    def get(self, url, **params):
        if params:
            url += '?' + urllib.parse.urlencode(params)
        host = urllib.parse.urlsplit(url).hostname
        intervals = {'itunes.apple.com': 3.1, 'api.deezer.com': 1.1, 'musicbrainz.org': 1.3, 'api.audius.co': 1.3}
        if host not in intervals or not url.startswith('https://'):
            raise ValueError('Unexpected provider URL')
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        with self.locks[host]:
            if time.monotonic() < self.paused_until.get(host, 0):
                raise urllib.error.URLError('provider temporarily unavailable; queued for later review')
        for attempt in range(2):
            with self.locks[host]:
                time.sleep(max(0, self.last.get(host, 0) + intervals[host] - time.monotonic()))
                self.last[host] = time.monotonic()
            try:
                with tempfile.TemporaryDirectory(dir=self.cache) as directory:
                    body_path = Path(directory) / 'body'
                    error_path = Path(directory) / 'error'
                    try:
                        with body_path.open('wb') as body, error_path.open('wb') as errors:
                            response = subprocess.run(
                                ['curl.exe', '--silent', '--show-error', '--fail', '--location',
                                 '--max-time', '20', '--user-agent', AGENT,
                                 '--header', 'Accept: application/json', url],
                                stdout=body, stderr=errors, timeout=25,
                            )
                    except subprocess.TimeoutExpired as exc:
                        raise urllib.error.URLError('request exceeded wall-clock timeout') from exc
                    if response.returncode:
                        with self.locks[host]:
                            self.failures[host] = self.failures.get(host, 0) + 1
                            if self.failures[host] >= 3:
                                self.paused_until[host] = time.monotonic() + 120
                                self.failures[host] = 0
                        raise urllib.error.URLError(error_path.read_text(encoding='utf-8', errors='replace').strip())
                    data = json.loads(body_path.read_bytes())
                with self.locks[host]:
                    self.failures[host] = 0
                if data.get('error'):
                    raise ValueError(str(data['error']))
                temp = path.with_suffix(f'.{threading.get_ident()}.tmp')
                temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                temp.replace(path)
                return data
            except urllib.error.HTTPError as exc:
                if attempt or exc.code not in (429, 500, 502, 503, 504):
                    raise
                wait = exc.headers.get('Retry-After', '5')
                if not wait.isdigit() or int(wait) > 60:
                    raise
                with self.locks[host]:
                    self.last[host] = max(self.last[host], time.monotonic() + max(5, int(wait)))


def apple_tracks(items, names, artist_id):
    return [
        (str(r['trackId']), r['trackName'], r['artistName'], r.get('primaryGenreName', ''))
        for r in items
        if r.get('kind') == 'song' and r.get('trackId') and r.get('trackName')
        and (r.get('artistId') == artist_id
             or (not r.get('artistId') and key(r.get('artistName', '')) in names))
    ]


def apple(client, name, region, deep):
    country = 'TW' if region.startswith('华语') else ('JP' if re.search('[ぁ-ヿ]', name) else 'US')
    names = names_for(name)
    items = client.get(APPLE+'search', term=name, media='music', entity='song',
                       attribute='artistTerm', country=country, limit=200)['results']
    ids = {r.get('artistId') for r in items if key(r.get('artistName', '')) in names and r.get('artistId')}
    if len(ids) != 1:
        return [], 'ambiguous' if ids else 'no_exact_artist'
    artist_id = ids.pop()
    tracks = apple_tracks(items, names, artist_id)
    if not deep:
        return tracks, 'search_cap' if len(items) >= 200 else 'search_window'
    try:
        catalog = client.get(APPLE+'lookup', id=artist_id, entity='album', country=country, limit=200)['results']
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        return tracks, f'partial_album_list:{exc}'
    albums = {r['collectionId']: r for r in catalog if r.get('collectionId') and r.get('artistId') == artist_id}
    batches = []
    batch, expected_count = [], 0
    for album_id in sorted(albums):
        size = int(albums[album_id].get('trackCount', 200))
        if batch and (len(batch) >= 8 or expected_count + size > 150):
            batches.append(batch)
            batch, expected_count = [], 0
        batch.append(album_id)
        expected_count += size
    if batch:
        batches.append(batch)
    partial_albums = []
    for batch in batches:
        try:
            detail = client.get(APPLE+'lookup', id=','.join(map(str, batch)), entity='song', country=country, limit=200)
            tracks.extend(apple_tracks(detail['results'], names, artist_id))
            for album_id in batch:
                expected = int(albums[album_id].get('trackCount', 0))
                received = sum(r.get('kind') == 'song' and r.get('collectionId') == album_id for r in detail['results'])
                if not received or received < expected:
                    partial_albums.append(str(album_id))
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            partial_albums.extend(map(str, batch))
    if partial_albums:
        return tracks, 'partial_album_tracks:' + ','.join(partial_albums)
    return tracks, 'album_list_cap' if len(catalog) >= 200 else f'albums:{len(albums)}'


def deezer(client, name, region, deep):
    names = names_for(name)
    candidates = client.get(DEEZER+'search/artist', q=name, limit=25)['data']
    matches = {a['id'] for a in candidates if key(a['name']) in names}
    if len(matches) != 1:
        return [], 'ambiguous' if matches else 'no_exact_artist'
    artist_id = matches.pop()
    if not deep:
        page = client.get(DEEZER+f'artist/{artist_id}/top', limit=100)
        return [(str(r['id']), r['title'], r['artist']['name'], '')
                for r in page['data'] if r.get('title') and r.get('artist', {}).get('id') == artist_id], 'top_window'
    page = client.get(DEEZER+f'artist/{artist_id}/albums', limit=100)
    tracks = []
    while True:
        for album in page['data']:
            detail = client.get(DEEZER+f"album/{album['id']}/tracks", limit=100)
            while True:
                for r in detail['data']:
                    artist = r.get('artist', {})
                    if r.get('title') and (artist.get('id') == artist_id or key(artist.get('name', '')) in names):
                        tracks.append((str(r['id']), r['title'], artist['name'], ''))
                if not detail.get('next'):
                    break
                detail = client.get(detail['next'])
        if not page.get('next'):
            break
        page = client.get(page['next'])
    return tracks, 'albums_paged'


def musicbrainz(client, name, region, deep):
    query = name.replace('"', '')
    response = client.get(MB+'artist/', query=f'artist:"{query}" OR alias:"{query}"', fmt='json', limit=25)
    names = names_for(name)
    matches = {
        a['id'] for a in response['artists']
        if names.intersection(key(n) for n in [a['name'], *(x['name'] for x in a.get('aliases', []))])
    }
    if len(matches) != 1:
        return [], 'ambiguous' if matches else 'no_exact_artist'
    artist_id = matches.pop()
    offset = 0
    tracks = []
    while True:
        page = client.get(MB+'recording/', artist=artist_id, inc='artist-credits+genres', fmt='json', limit=100, offset=offset)
        batch = page['recordings']
        for r in batch:
            credit = ''.join(a['name'] + a.get('joinphrase', '') for a in r.get('artist-credit', []))
            tags = '|'.join(sorted({g['name'] for g in r.get('genres', [])}))
            if credit and r.get('title'):
                tracks.append((r['id'], r['title'], credit.strip(), tags))
        offset += len(batch)
        if offset >= page['recording-count'] or not batch or not deep:
            break
    return tracks, 'recordings_partial' if offset < page['recording-count'] else 'recordings_paged'


def write_csv(path, fields, rows):
    temp = path.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
    with temp.open('w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow(fields)
        writer.writerows(rows)
    replace_file(temp, path)


def replace_file(temp, target):
    for attempt in range(30):
        try:
            temp.replace(target)
            return
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(1)


def export(dest, states):
    preferred, evidence = {}, []
    for name, result in states.items():
        for provider, track_id, raw_title, credit, tags in result['tracks']:
            title = song_title(raw_title.strip())
            if not title:
                continue
            artist = name if key(credit) in names_for(name) else credit
            group = (min(names_for(artist)), key(title))
            song_id = 'catalog:' + hashlib.sha256('\0'.join(group).encode()).hexdigest()[:24]
            evidence.append((song_id, name, provider, track_id, raw_title, credit, tags))
            rank = (int(raw_title.strip() == title), int(bool(tags)),
                    {'apple': 3, 'deezer': 2, 'musicbrainz': 1}[provider],
                    title, artist, track_id)
            if group not in preferred or rank > preferred[group][0]:
                preferred[group] = (rank, (song_id, title, artist, tags))
    write_csv(dest/'songs_candidates.csv', FIELDS, sorted(row for _, row in preferred.values()))
    write_csv(dest/'sources.csv', ('song_id','seed_artist','source','source_id','title','artist_credit','genres'), evidence)
    write_csv(dest/'artists.csv', ('artist','tracks','attempts'), (
        (name, len(result['tracks']), ' | '.join(result['attempts'])) for name, result in states.items()
    ))
    return len(preferred)


def collect_one(client, name, region, deep):
    attempts, tracks = [], []
    for provider in (apple, deezer, musicbrainz):
        try:
            rows, status = provider(client, name, region, deep)
            attempts.append(f'{provider.__name__}:{status}')
            tracks.extend((provider.__name__, *r) for r in rows)
            if (rows and status not in ('search_cap', 'album_list_cap', 'top_window')
                    and not status.startswith('partial_') and len({key(r[1]) for r in rows}) >= 10):
                break
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            attempts.append(f'{provider.__name__}:{exc}')
    return {'attempts': attempts, 'tracks': list(dict.fromkeys(tracks))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('artists', type=Path)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--cache', type=Path, help='reuse an existing provider response cache')
    parser.add_argument('--deep', action='store_true')
    parser.add_argument('--retry-empty', action='store_true', help='retry artists that yielded no tracks')
    parser.add_argument('--export-only', action='store_true', help='export the current checkpoint without requests')
    args = parser.parse_args()
    with args.artists.open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        names = list(dict.fromkeys((r['候选名称'].strip(), r['覆盖规划']) for r in reader if r['候选名称'].strip()))
    dest = args.work
    dest.mkdir(parents=True, exist_ok=True)
    client = Client(args.cache or dest/'cache')
    state = dest/('deep.json' if args.deep else 'progress.json')
    states = json.loads(state.read_text(encoding='utf-8')) if state.exists() else {}
    try:
        if args.export_only:
            return
        with ThreadPoolExecutor(max_workers=6) as workers:
            jobs = {workers.submit(collect_one, client, name, region, args.deep): name
                    for name, region in names
                    if name not in states or (args.retry_empty and not states[name]['tracks'])}
            try:
                for future in as_completed(jobs):
                    name = jobs[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {'attempts': [f'worker_error:{type(exc).__name__}:{exc}'], 'tracks': []}
                    states[name] = result
                    temp = state.with_suffix('.tmp')
                    temp.write_text(json.dumps(states, ensure_ascii=False), encoding='utf-8')
                    replace_file(temp, state)
                    print(len(states), '/', len(names), name, len(result['tracks']), ' | '.join(result['attempts']), flush=True)
                    if len(states) % 5 == 0:
                        export(dest, states)
            except KeyboardInterrupt:
                for future in jobs:
                    future.cancel()
    finally:
        print('Artists attempted:', len(states), 'Unique songs:', export(dest, states), flush=True)


if __name__ == '__main__':
    main()
