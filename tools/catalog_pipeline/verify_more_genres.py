"""Search additional sources for remaining tracks, accepting consistent song-level genres."""
import csv
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog import Client, key, musicbrainz, names_for, write_csv

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'outputs/全量曲库-风格覆盖'
OUT = ROOT/'outputs/风格复查-扩大搜索'
OUT.mkdir(exist_ok=True)
UNKNOWN = '风格待确认'
FIELDS = ('song_id', 'song_name', 'artist', 'genres')


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        yield from csv.DictReader(handle)


client = Client(ROOT/'work/genre_search_cache')
categories = {key(r['source_label']): r['recommendation_genre']
              for r in read(ROOT/'outputs/全量曲库-统一标签/source_label_mapping.csv')}
categories.update({key(r['original_label']): r['recommendation_genre']
                   for r in read(ROOT/'outputs/全量曲库-统一标签/label_mapping.csv')})


def search(artist, targets):
    aliases = names_for(artist)
    evidence, logs = [], []
    country = ('JP' if re.search('[ぁ-ヿ]', artist) else
               'SG' if re.search('[\u3400-\u9fff]', artist) else
               'KR' if re.search('[가-힣]', artist) else
               'BR' if re.search(r'[ãõç]', artist, re.I) else 'CA')
    queries = [
        (f'Apple {country}', lambda: apple(artist, aliases, country)),
        ('MusicBrainz', lambda: musicbrainz(client, artist, '', True)[0]),
        ('Audius', lambda: audius(artist, aliases)),
    ]
    for site, fetch in queries:
        try:
            records = fetch()
            accepted = 0
            for track_id, title, credit, labels in records:
                if key(credit) not in aliases or key(title) not in targets:
                    continue
                for raw in labels.split('|'):
                    genre = categories.get(key(raw))
                    if genre:
                        evidence.append((key(title), genre, raw, site, track_id))
                        accepted += 1
            logs.append((artist, site, 'ok', len(records), accepted))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logs.append((artist, site, str(exc), 0, 0))
    return evidence, logs


def apple(artist, aliases, country):
    data = client.get('https://itunes.apple.com/search', term=artist, media='music',
                      entity='song', attribute='artistTerm', country=country, limit=200)
    matched = [r for r in data['results'] if r.get('kind') == 'song'
               and r.get('artistId') and key(r.get('artistName','')) in aliases]
    if len({r['artistId'] for r in matched}) > 1:
        raise ValueError('multiple exact platform artist IDs')
    return [(r['trackId'], r.get('trackName',''), r['artistName'], r.get('primaryGenreName',''))
            for r in matched]


def audius(artist, aliases):
    data = client.get('https://api.audius.co/v1/tracks/search', query=artist, limit=100)
    matches = [r for r in data['data']
               if (r.get('user') or {}).get('is_verified') is True
               and key(r['user'].get('name','')) in aliases]
    if len({r['user']['id'] for r in matches}) > 1:
        raise ValueError('multiple exact verified Audius artists')
    return [(r['id'],r.get('title',''),r['user']['name'],r.get('genre') or '') for r in matches]


rows = list(read(BASE/'songs.csv'))
groups = defaultdict(list)
for r in rows:
    if r['genres'] == UNKNOWN and r['artist']:
        groups[min(names_for(r['artist']))].append(r)
selected = sorted(groups.values(), key=lambda batch: (-len(batch), batch[0]['artist']))[:80]
audit, logs, conflicts = [], [], []
with ThreadPoolExecutor(max_workers=8) as pool:
    jobs = {pool.submit(search, group[0]['artist'], {key(r['song_name']) for r in group}):group
            for group in selected}
    for n, job in enumerate(as_completed(jobs), 1):
        evidence, source_log = job.result()
        logs.extend(source_log)
        by_title = defaultdict(set)
        for title, genre, raw, site, track_id in evidence:
            by_title[title].add((genre, raw, site, track_id))
        for row in jobs[job]:
            options = by_title[key(row['song_name'])]
            styles = {option[0] for option in options}
            if len(styles) > 1:
                conflicts.append((row['song_id'], row['song_name'], row['artist'], '|'.join(sorted(styles))))
            elif styles:
                row['genres'] = next(iter(styles))
                audit.extend((row['song_id'], row['song_name'], row['artist'], *option) for option in sorted(options))
        if n % 10 == 0:
            print(f'Checked {n}/{len(selected)} artist names', flush=True)

counts = Counter(g for r in rows for g in set(r['genres'].split('|')))
write_csv(OUT/'songs.csv', FIELDS, (tuple(r[k] for k in FIELDS) for r in rows))
write_csv(OUT/'genre_counts.csv', ('genre','count'), counts.most_common())
write_csv(OUT/'track_evidence.csv', ('song_id','song_name','artist','genre','raw_genre','source','source_track_id'), sorted(audit))
write_csv(OUT/'search_log.csv', ('artist','source','status','tracks','matching_tag_observations'), sorted(logs))
write_csv(OUT/'conflicts.csv', ('song_id','song_name','artist','candidate_genres'), conflicts)
write_csv(OUT/'genre_unconfirmed.csv', FIELDS, (tuple(r[k] for k in FIELDS) for r in rows if r['genres']==UNKNOWN))
report = {'artists_searched':len(selected),'tracks_in_search_scope':sum(map(len,selected)),
          'confirmed_additions':len({r[0] for r in audit}),'conflicts':len(conflicts),
          'still_unconfirmed':counts[UNKNOWN], 'sources_attempted':dict(Counter(r[1] for r in logs))}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
