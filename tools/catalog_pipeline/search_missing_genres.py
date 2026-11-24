"""Search more storefronts and infer remaining genres with artist evidence."""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog import Client, key, names_for, song_title, write_csv

root = Path(__file__).resolve().parents[2]
out = root / 'outputs/缺失标签补齐-扩大检索'
out.mkdir(exist_ok=True)
base = root / 'outputs/缺失标签补齐'
mapping_path = root / 'outputs/清洗与标签统一草稿/label_mapping_review.csv'
fields = ('song_id', 'song_name', 'artist', 'genres')


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        yield from csv.DictReader(handle)


def artist_key(artist):
    return min(names_for(artist))


def label(value):
    return labels.get(key(value), key(value))


def query(artist, pending):
    countries = ('JP', 'US') if re.search('[ぁ-ヿ]', artist) else (
        ('HK', 'TW') if re.search('[\u3400-\u9fff]', artist) else ('GB', 'US')
    )
    names = names_for(artist)
    evidence, attempts = [], []
    for country in countries:
        try:
            data = client.get('https://itunes.apple.com/search', term=artist, media='music',
                              entity='song', attribute='artistTerm', country=country, limit=200)
            matches = [r for r in data['results'] if r.get('kind') == 'song'
                       and r.get('artistId') and key(r.get('artistName', '')) in names]
            if len({r['artistId'] for r in matches}) != 1:
                attempts.append((f'Apple {country}', 'artist_not_unique'))
                continue
            for row in matches:
                title, genre = row.get('trackName', ''), row.get('primaryGenreName')
                if genre and key(title) in pending:
                    evidence.append((key(title), label(genre), genre, f'Apple {country}', str(row['trackId'])))
            attempts.append((f'Apple {country}', f'{len(matches)} tracks'))
        except (OSError, ValueError, KeyError) as exc:
            attempts.append((f'Apple {country}', str(exc)))
    try:
        data = client.get('https://api.audius.co/v1/tracks/search', query=artist, limit=100)
        matches = []
        for row in data.get('data', []):
            user = row.get('user') or {}
            # Only accept exact names and verified uploader identities.
            if user.get('is_verified') is True and key(user.get('name', '')) in names:
                matches.append(row)
        if len({r['user']['id'] for r in matches}) == 1:
            for row in matches:
                title, genre = row.get('title', ''), row.get('genre')
                if genre and key(title) in pending:
                    evidence.append((key(title), label(genre), genre, 'Audius', row['id']))
        attempts.append(('Audius', f'{len(matches)} tracks with exact verified uploader'))
    except (OSError, ValueError, KeyError) as exc:
        attempts.append(('Audius', str(exc)))
    return evidence, attempts


parser = argparse.ArgumentParser()
parser.add_argument('--artists', type=int, default=65, help='number of artists prioritized by unlabeled track count')
args = parser.parse_args()
labels = {key(r['raw_label']): r['canonical_label'] for r in read(mapping_path)}
songs = list(read(base/'songs.csv'))
missing = [r for r in songs if not r['genres'] and r['artist']]
groups = defaultdict(list)
for row in missing:
    groups[artist_key(row['artist'])].append(row)
leaders = sorted(groups.values(), key=lambda rows: (-len(rows), rows[0]['artist']))[:args.artists]
client = Client(root/'work/genre_search_cache')
direct = defaultdict(set)
attempt_log = []
with ThreadPoolExecutor(max_workers=6) as pool:
    futures = {pool.submit(query, rows[0]['artist'], {key(r['song_name']) for r in rows}): rows
               for rows in leaders}
    for index, future in enumerate(as_completed(futures), 1):
        rows = futures[future]
        evidence, attempts = future.result()
        by_title = defaultdict(set)
        for title, genre, raw, source, platform_id in evidence:
            if genre:
                by_title[title].add((genre, raw, source, platform_id))
        for row in rows:
            direct[row['song_id']].update(by_title[key(row['song_name'])])
        attempt_log.extend((rows[0]['artist'], source, status) for source, status in attempts)
        if index % 10 == 0:
            print(f'Searched {index}/{len(leaders)} artists', flush=True)

audit = []
conflicts = set()
for row in missing:
    evidence = direct[row['song_id']]
    genres = {item[0] for item in evidence}
    if len(genres) > 1:
        conflicts.add(row['song_id'])
    elif genres:
        row['genres'] = next(iter(genres))
        for genre, raw, source, platform_id in sorted(evidence):
            audit.append((row['song_id'], 'track_match', genre, source, platform_id, raw, '', ''))

# Compare broad styles so mixed granularity does not split evidence for one style.
family_children = {
    '摇滚': '独立摇滚|另类摇滚|硬摇滚|迷幻摇滚|民谣摇滚|蓝调摇滚|流行摇滚',
    '流行': '独立流行|传统流行',
    '爵士': '酸爵士|酷派爵士|融合爵士|自由爵士|柔和爵士|人声爵士|当代爵士',
    '古典': '古典跨界|歌剧|室内乐|管弦乐',
    '电子': '电子乐|浩室|深浩室|科技舞曲|出神舞曲|鼓打贝斯|回响贝斯|碎拍|氛围',
    '嘻哈': '嘻哈/说唱|说唱',
    '灵魂乐': '新灵魂乐',
    '节奏布鲁斯': '当代节奏布鲁斯',
    '金属': '重金属|死亡金属|鞭击金属',
    '民谣': '另类民谣|当代民谣',
    '乡村': '蓝草',
    '朋克': '流行朋克',
}
families = {child: parent for parent, children in family_children.items() for child in children.split('|')}
eligible = set(family_children) | set('华语流行|粤语流行|台湾流行|日语流行|韩语流行|蓝调|雷鬼|拉丁|新世纪|放克|舞曲'.split('|'))
votes, totals = defaultdict(Counter), Counter()
for row in songs:
    if row['genres'] and row['artist']:
        identity = artist_key(row['artist'])
        genres = {families.get(g, g) for g in row['genres'].split('|')} & eligible
        totals[identity] += 1
        votes[identity].update(genres)

for row in missing:
    if row['genres']:
        continue
    identity = artist_key(row['artist'])
    candidates = sorted(votes[identity].items(), key=lambda x: (-x[1], x[0]))
    total = totals[identity]
    if not candidates:
        continue
    genre, support = candidates[0]
    runner_up = candidates[1][1] if len(candidates) > 1 else 0
    if support >= 3 and support / total >= 0.65 and (support-runner_up) / total >= 0.15:
        row['genres'] = genre
        audit.append((row['song_id'], 'artist_style', genre, 'catalog_artist_votes', '', '', support, total))

counts = Counter(g for r in songs for g in set(filter(None, r['genres'].split('|'))))
write_csv(out/'songs.csv', fields, (tuple(r[k] for k in fields) for r in songs))
write_csv(out/'genre_counts.csv', ('genre','count'), counts.most_common())
write_csv(out/'tag_evidence.csv', ('song_id','method','genre','source','source_track_id','raw_genre','support','artist_tagged_tracks'), audit)
write_csv(out/'search_log.csv', ('artist','platform','status'), sorted(attempt_log))
write_csv(out/'track_conflicts.csv', ('song_id','candidate_genres','assigned_genre'),
          [(r['song_id'], '|'.join(sorted({e[0] for e in direct[r['song_id']]})), r['genres'])
           for r in missing if r['song_id'] in conflicts])
remaining = [r for r in songs if not r['genres']]
write_csv(out/'unlabeled_songs.csv', fields, (tuple(r[k] for k in fields) for r in remaining))
methods = {method: len({a[0] for a in audit if a[1] == method}) for method in ('track_match', 'artist_style')}
report = {'songs':len(songs), 'searched_artists':len(leaders), 'songs_in_online_scope':sum(map(len, leaders)),
          'starting_missing':len(missing), 'filled':methods, 'conflicting_track_results':len(conflicts),
          'still_missing':len(remaining), 'coverage_percent':round(100*(1-len(remaining)/len(songs)),2)}
(out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
