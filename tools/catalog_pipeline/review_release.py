"""Review remaining source disagreements and candidate duplicates without losing tracks."""
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from catalog import key, names_for, write_csv

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT/'outputs/全量曲库-质量验收'
OUT = ROOT/'outputs/新版曲库-复核版'
OUT.mkdir(exist_ok=True)
CONTENTS = ('song_id', 'song_name', 'artist', 'genres')


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


tracks = {r['song_id']:r for r in read(QA/'songs.csv')}
styles = {r['genre'] for r in read(ROOT/'outputs/全量曲库-统一标签/recommendation_genres.csv')}
conflicts = list(read(QA/'platform_conflicts.csv'))
near_duplicates = defaultdict(list)
for row in read(QA/'title_punctuation_review.csv'):
    near_duplicates[row['artist_normalized'], row['title_without_punctuation']].append(row)
wanted = {r['song_id'] for r in conflicts} | {r['song_id'] for g in near_duplicates.values() for r in g}
lineage = defaultdict(list)
aliases = {}
for row in read(ROOT/'outputs/清洗与标签统一草稿/row_lineage.csv'):
    if row['song_id'] in wanted:
        lineage[row['song_id']].append(row)
        if row['input']=='collected':
            aliases[row['original_id']] = row['song_id']
records = defaultdict(list)
for row in read(ROOT/'outputs/艺人扩充1000/采集结果/sources.csv'):
    if target := aliases.get(row['song_id']):
        records[target].append(row)
taxonomy = {key(r['source_label']):r['recommendation_genre']
            for r in read(ROOT/'outputs/全量曲库-统一标签/source_label_mapping.csv')}

decisions = []
changed = 0
for conflict in conflicts:
    sid = conflict['song_id']
    track = tracks[sid]
    matching = defaultdict(set)
    for ref in records[sid]:
        if (key(ref['title']) == key(track['song_name'])
                and names_for(ref['artist_credit']) & names_for(track['artist'])):
            matching[ref['source']].update(taxonomy.get(key(g),'') for g in ref['genres'].split('|'))
    by_genre = Counter(genre for values in matching.values() for genre in values if genre)
    consensus = sorted(genre for genre,n in by_genre.items() if n >= 2)
    previous = track['genres']
    if len(consensus) == 1:
        track['genres'] = '|'.join(sorted((set(previous.split('|'))-styles)|set(consensus)))
        status = '两平台同曲名同艺人一致'
    else:
        status = '保留多来源证据，单一曲风待核验'
    changed += previous != track['genres']
    decisions.append((sid,track['song_name'],track['artist'],previous,track['genres'],status,
                      conflict['provider_genres'],json.dumps(dict(by_genre),ensure_ascii=False)))

duplicate_rows = []
duplicate_counts = Counter()
for group_id, group in enumerate(near_duplicates.values(),1):
    provider_ids = []
    for row in group:
        sid = row['song_id']
        refs = {(ref['source'],ref['source_id']) for ref in records[sid] if ref['source_id']}
        refs.update(('original',ref['original_id']) for ref in lineage[sid] if ref['input']=='original')
        provider_ids.append(refs)
    shared = set.intersection(*provider_ids) if provider_ids else set()
    status = ('共享来源曲目ID，保留所有记录' if shared else
              '有来源ID，录音关系待核验' if all(provider_ids) else '来源ID不足，暂不归并')
    duplicate_counts[status] += 1
    for row, refs in zip(group,provider_ids,strict=True):
        duplicate_rows.append((group_id,row['song_id'],row['song_name'],row['artist'],status,
                               json.dumps(sorted(refs),ensure_ascii=False),
                               json.dumps(sorted(shared),ensure_ascii=False)))

counts = Counter(g for r in tracks.values() for g in set(r['genres'].split('|')))
write_csv(OUT/'songs.csv',CONTENTS,(tuple(r[k] for k in CONTENTS) for r in tracks.values()))
write_csv(OUT/'genre_counts.csv',('genre','count'),counts.most_common())
write_csv(OUT/'genre_conflict_review.csv',('song_id','song_name','artist','before','after','decision',
          'source_genres','exact_track_votes'),decisions)
write_csv(OUT/'duplicate_review.csv',('group_id','song_id','song_name','artist','decision','source_ids','shared_source_ids'),duplicate_rows)
for f in ('genre_ranking_policy.csv','exclude_from_genre_ranking.csv','stratified_audit.csv'):
    shutil.copyfile(QA/f,OUT/f)
manifest = {'version':'2026-11-24-reviewed','songs':len(tracks),'genre_conflicts_reviewed':len(decisions),
            'genre_conflicts_resolved':sum(r[5]=='两平台同曲名同艺人一致' for r in decisions),
            'genres_changed_in_this_pass':changed,
            'duplicate_groups_reviewed':len(near_duplicates),'duplicate_group_outcomes':dict(duplicate_counts),
            'unmerged_duplicate_rows':len(duplicate_rows),
            'files':{f.name:{'bytes':f.stat().st_size,'sha256':hashlib.file_digest(f.open('rb'),'sha256').hexdigest()}
                     for f in sorted(OUT.glob('*.csv'))}}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in manifest.items() if k!='files'},ensure_ascii=False))
