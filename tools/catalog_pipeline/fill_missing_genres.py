"""Recover missing tags from locally cached catalog evidence."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from catalog import key, names_for, song_title, write_csv

ROOT = Path(__file__).resolve().parents[2]
DRAFT = ROOT / 'outputs/清洗与标签统一草稿'
SOURCE = ROOT / 'outputs/艺人扩充1000/采集结果'
OUT = ROOT / 'outputs/缺失标签补齐'
OUT.mkdir(exist_ok=True)
FIELDS = ('song_id', 'song_name', 'artist', 'genres')


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        yield from csv.DictReader(file)


def tags(value):
    return {tag.strip() for tag in value.split('|') if tag.strip()}


def signature(title, artist):
    return key(title), min(names_for(artist))


def canonical(raw):
    return mapping.get(key(raw), key(raw))


songs = list(read(DRAFT / 'songs.csv'))
missing = {row['song_id']: row for row in songs if not row['genres'].strip()}
mapping = {key(r['raw_label']): r['canonical_label'] for r in read(DRAFT / 'label_mapping_review.csv')}
lineage = {r['original_id']: r['song_id'] for r in read(DRAFT / 'row_lineage.csv')
           if r['song_id'] in missing and r['input'] == 'collected'}
target_sources = defaultdict(set)
exact_names = defaultdict(set)
for row in read(SOURCE / 'sources.csv'):
    if sid := lineage.get(row['song_id']):
        target_sources[row['source'], row['source_id']].add(sid)
        if row['title'] and row['artist_credit']:
            exact_names[signature(row['title'], row['artist_credit'])].add(sid)

direct = defaultdict(set)
album_tracks = defaultdict(set)
albums = defaultdict(set)
bad_files = 0
cache = ROOT / 'work/catalog_run/cache'
for path in sorted(cache.glob('*.json')):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        bad_files += 1
        continue
    for row in data.get('results', []):
        genre = row.get('primaryGenreName')
        album = str(row.get('collectionId') or '')
        artist_id = str(row.get('artistId') or '')
        if row.get('wrapperType') == 'collection' and genre and album and artist_id:
            albums[album, artist_id].add(genre)
        if row.get('kind') != 'song' or not row.get('trackId'):
            continue
        track = str(row['trackId'])
        for sid in target_sources.get(('apple', track), ()):
            if genre:
                direct[sid].add((genre, 'apple_track_id', track))
            if album and artist_id:
                album_tracks[sid].add((album, artist_id))
        if genre and row.get('trackName') and row.get('artistName'):
            matches = exact_names.get(signature(row['trackName'], row['artistName']), ())
            if len(matches) == 1:
                sid = next(iter(matches))
                direct[sid].add((genre, 'exact_title_credit', track))
    for row in data.get('recordings', []):
        for sid in target_sources.get(('musicbrainz', row.get('id')), ()):
            for genre in row.get('genres', []):
                if genre.get('name'):
                    direct[sid].add((genre['name'], 'musicbrainz_recording_id', row['id']))

generic_or_nonmusic = {key(v) for v in (
    'Music', 'Worldwide', 'World Music', 'Chinese', 'Asia', 'Various Artists',
    'Spoken Word', 'non-music', 'Interview', 'Comedy', 'Standup Comedy',
)}
filled = Counter()
audit = []
conflicts = []
for sid, row in missing.items():
    evidence = direct[sid]
    ids = {item for item in evidence if item[1] != 'exact_title_credit'}
    options = ids or evidence
    method = 'recording_id' if ids else 'exact_title_credit'
    if not options:
        method = 'same_artist_album'
        options = {(raw, method, album) for album, artist_id in album_tracks[sid]
                   for raw in albums.get((album, artist_id), ())
                   if key(raw) not in generic_or_nonmusic}
    values = {canonical(raw) for raw, _, _ in options}
    if len(values) > 1 and method != 'recording_id':
        conflicts.append((sid, row['song_name'], row['artist'], method, '|'.join(sorted(values))))
        continue
    if values:
        row['genres'] = '|'.join(sorted(values))
        filled[method] += 1
        for raw, rule, reference in sorted(options):
            audit.append((sid, row['song_name'], row['artist'], canonical(raw), raw, rule, reference))

# Suggest a broad artist style for review only when the catalog is highly consistent.
families = '''流行|摇滚|华语流行|粤语流行|日语流行|韩语流行|乡村|爵士|蓝调|古典|电子|嘻哈|节奏布鲁斯|灵魂乐|雷鬼|金属|朋克|民谣|拉丁'''.split('|')
artist_styles = defaultdict(Counter)
artist_total = Counter()
needed_artists = {min(names_for(row['artist'])) for row in missing.values() if not row['genres'] and row['artist']}
for row in songs:
    if row['song_id'] in missing or not row['genres'] or not row['artist']:
        continue
    artist = min(names_for(row['artist']))
    if artist in needed_artists:
        artist_total[artist] += 1
        artist_styles[artist].update(tags(row['genres']).intersection(families))
suggestions = []
remaining = [row for row in missing.values() if not row['genres']]
for row in remaining:
    artist = min(names_for(row['artist']))
    best = artist_styles[artist].most_common(2)
    total = artist_total[artist]
    if best and total >= 10 and best[0][1] / total >= 0.9 and (len(best) == 1 or best[1][1] / total < 0.25):
        suggestions.append((row['song_id'], row['song_name'], row['artist'], best[0][0], best[0][1], total))

counts = Counter(tag for row in songs for tag in tags(row['genres']))
write_csv(OUT / 'songs.csv', FIELDS, [tuple(row[field] for field in FIELDS) for row in songs])
write_csv(OUT / 'genre_counts.csv', ('genre', 'count'), counts.most_common())
write_csv(OUT / 'tag_evidence.csv', ('song_id','song_name','artist','genre','raw_genre','evidence','source_id'), audit)
write_csv(OUT / 'unlabeled_songs.csv', FIELDS, [tuple(row[field] for field in FIELDS) for row in remaining])
write_csv(OUT / 'conflicts.csv', ('song_id','song_name','artist','evidence','conflicting_genres'), conflicts)
write_csv(OUT / 'artist_suggestions.csv', ('song_id','song_name','artist','suggested_genre','support','tagged_artist_songs'), suggestions)
assert sum(filled.values()) + len(remaining) == len(missing)
report = {'songs': len(songs), 'originally_missing': len(missing), 'filled': sum(filled.values()),
          'by_evidence': dict(filled), 'still_missing': len(remaining), 'conflicts': len(conflicts),
          'artist_suggestions_for_review': len(suggestions), 'coverage_percent': round(100 * (len(songs)-len(remaining))/len(songs), 2),
          'unreadable_cache_files': bad_files}
(OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
