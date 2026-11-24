"""Validate catalog integrity and audit genres against source evidence."""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog import Client, key, names_for, song_title, write_csv

root = Path(__file__).resolve().parents[2]
out = root/'outputs/全量曲库-质量验收'
out.mkdir(exist_ok=True)
source = root/'outputs/全曲库-曲风补全'
taxonomy = root/'outputs/全量曲库-统一标签'
HAN = re.compile('[\u3400-\u9fff]')
FIELDS = ('song_id', 'song_name', 'artist', 'genres')


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        yield from csv.DictReader(file)


def split(value):
    return {v.strip() for v in value.split('|') if v.strip()}


rows = list(read(source/'songs.csv'))
by_id = {r['song_id']: r for r in rows}
assert len(by_id) == len(rows) == 293864
assert all(r['song_id'] and r['song_name'] and r['genres'] for r in rows)
counts = Counter(g for r in rows for g in split(r['genres']))
assert dict(counts) == {r['genre']:int(r['count']) for r in read(source/'genre_counts.csv')}
for old, current in zip(read(taxonomy/'songs.csv'), rows, strict=True):
    assert tuple(old[k] for k in FIELDS[:3]) == tuple(current[k] for k in FIELDS[:3])

genres = {r['genre'] for r in read(taxonomy/'recommendation_genres.csv')}
labels = {key(r['source_label']):r['recommendation_genre'] for r in read(taxonomy/'source_label_mapping.csv')}
labels.update({key(r['original_label']):r['recommendation_genre'] for r in read(taxonomy/'label_mapping.csv')})
labels.update({key(g):g for g in genres})

methods = {r['song_id']:r['method'] for r in read(source/'genre_estimates.csv')}
for path in ('缺失标签补齐-扩大检索/tag_evidence.csv', '标签补齐完整交付/final_fill_evidence.csv',
             '全量曲库-风格覆盖/coverage_evidence.csv'):
    for row in read(root/'outputs'/path):
        if row['method'] in ('artist_style', 'lead_artist_style', 'performers_agree', '艺人主风格推断'):
            methods.setdefault(row['song_id'], '早期艺人主风格')
nonmusic = {r['song_id'] for r in read(source/'non_music.csv')}


def stratum(row):
    ident = row['song_id']
    method = methods.get(ident, '')
    if ident in nonmusic:
        return '非音乐内容'
    if method == '全库风格分布兜底':
        return '全库分布兜底'
    if method == '曲名与标签模型':
        return '曲名与标签模型'
    if method:
        return '艺人风格推断'
    return '已有曲目或目录标签'


prior_identity = {r['original_id']:r['song_id'] for r in read(root/'outputs/清洗与标签统一草稿/row_lineage.csv')
                  if r['input']=='collected'}
evidence = defaultdict(lambda: defaultdict(set))
for record in read(root/'outputs/艺人扩充1000/采集结果/sources.csv'):
    ident = prior_identity.get(record['song_id'])
    mapped = {labels.get(key(g)) for g in split(record['genres'])} - {None, ''}
    if ident and mapped:
        evidence[ident][record['source']].update(mapped)

disputes = []
cross_platform = Counter()
for ident, providers in evidence.items():
    if len(providers) < 2:
        continue
    common = set.intersection(*providers.values())
    cross_platform['both_tagged'] += 1
    if common:
        cross_platform['some_common_genre'] += 1
    else:
        cross_platform['disjoint'] += 1
        row = by_id[ident]
        disputes.append((ident,row['song_name'],row['artist'],row['genres'],
                         json.dumps({p:sorted(v) for p,v in sorted(providers.items())},ensure_ascii=False)))
write_csv(out/'platform_conflicts.csv', ('song_id','song_name','artist','catalog_genres','provider_genres'), sorted(disputes))

# Unresolved same-title collisions are candidates for review, never merged here.
name_groups = defaultdict(list)
for row in rows:
    if row['artist'].strip():
        name_groups[min(names_for(row['artist'])), key(song_title(row['song_name']))].append(row)
duplicates = [(row['song_id'],row['song_name'],row['artist'],len(group))
              for group in name_groups.values() if len(group)>1 for row in group]
write_csv(out/'duplicate_review.csv', ('song_id','song_name','artist','group_size'), duplicates)
safe = [r for r in rows if methods.get(r['song_id'])=='全库风格分布兜底']
write_csv(out/'exclude_from_genre_ranking.csv', ('song_id','reason'),
          [(r['song_id'],'缺乏可用曲目及艺人特征，标签来自全库频率') for r in safe])

groups = defaultdict(list)
for row in rows:
    groups[stratum(row)].append(row)


def sample_order(row):
    return hashlib.sha256(('catalog-audit-v1:'+row['song_id']).encode()).digest()


sample = []
for kind, population in sorted(groups.items()):
    if kind == '非音乐内容':
        continue
    east_asian = sorted((r for r in population if HAN.search(r['song_name']+' '+r['artist'])), key=sample_order)
    others = sorted((r for r in population if not HAN.search(r['song_name']+' '+r['artist'])), key=sample_order)
    sample.extend((kind, r) for r in east_asian[:5]+others[:7])

client = Client(root/'work/genre_quality_cache')


def verify(item):
    kind, row = item
    aliases = names_for(row['artist'])
    title = key(row['song_name'])
    found = set()
    errors = []
    country = 'JP' if re.search('[ぁ-ヿ]', row['song_name']+row['artist']) else (
        'TW' if HAN.search(row['artist']) else 'US')
    try:
        data = client.get('https://itunes.apple.com/search', term=row['song_name']+' '+row['artist'],
                          entity='song', media='music', country=country, limit=30)
        matched = [r for r in data['results'] if r.get('kind')=='song' and key(r.get('trackName',''))==title
                   and key(r.get('artistName','')) in aliases]
        if len({r.get('artistId') for r in matched}) == 1:
            for track in matched:
                raw = track.get('primaryGenreName','')
                if genre := labels.get(key(raw)):
                    found.add(('Apple '+country, str(track['trackId']), raw, genre))
    except (OSError, ValueError, KeyError) as exc:
        errors.append('Apple '+str(exc))
    try:
        title_query = row['song_name'].replace('"','')
        artist_query = row['artist'].replace('"','')
        result = client.get('https://musicbrainz.org/ws/2/recording/', fmt='json',limit=25,
                            query=f'recording:"{title_query}" AND artist:"{artist_query}"')
        for track in result['recordings']:
            credit = ''.join(a['name']+a.get('joinphrase','') for a in track.get('artist-credit',[]))
            if key(credit) in aliases and key(track['title'])==title:
                for tag in track.get('genres',[]):
                    if genre := labels.get(key(tag['name'])):
                        found.add(('MusicBrainz',track['id'],tag['name'],genre))
    except (OSError, ValueError, KeyError) as exc:
        errors.append('MusicBrainz '+str(exc))
    references = {item[3] for item in found}
    assigned = split(row['genres']) & genres
    if not references:
        status = '无法核验'
    elif len(references)>1:
        status = '参考标签分歧'
    elif assigned & references:
        status = '与参考标签一致'
    else:
        status = '与参考标签不一致'
    return (kind,row['song_id'],row['song_name'],row['artist'],row['genres'],status,
            '|'.join(sorted(references)),json.dumps(sorted(found),ensure_ascii=False),' | '.join(errors))


sample_results = []
with ThreadPoolExecutor(max_workers=6) as pool:
    futures = [pool.submit(verify,item) for item in sample]
    for n, future in enumerate(as_completed(futures),1):
        sample_results.append(future.result())
        if n%12==0:
            print(f'Finished {n}/{len(sample)} sampled tracks',flush=True)
sample_results.sort()
write_csv(out/'stratified_audit.csv',
          ('stratum','song_id','song_name','artist','catalog_genres','status','reference_genres','references','request_errors'),
          sample_results)
sample_counts = defaultdict(Counter)
for record in sample_results:
    sample_counts[record[0]][record[5]] += 1
report = {'tracks':len(rows),'stratum_populations':{name:len(values) for name,values in groups.items()},
          'sample_counts':dict(sample_counts),'cross_platform':dict(cross_platform),
          'duplicate_rows_for_review':len(duplicates),'exclude_from_genre_ranking':len(safe)}
(out/'audit_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
