"""Publish corrections to estimates with consistent track evidence."""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from catalog import key, names_for, write_csv

root = Path(__file__).resolve().parents[2]
out = root/'outputs/全量曲库-质量验收'
base = root/'outputs/全曲库-曲风补全'
tax = root/'outputs/全量曲库-统一标签'
fields = ('song_id', 'song_name', 'artist', 'genres')


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        yield from csv.DictReader(handle)


def signature(title, artist):
    return min(names_for(artist)), re.sub(r'[^\w]+', ' ', key(title)).strip()


rows = list(read(base/'songs.csv'))
ids = {r['song_id']:r for r in rows}
styles = {r['genre'] for r in read(tax/'recommendation_genres.csv')}
mapping = {key(r['source_label']):r['recommendation_genre'] for r in read(tax/'source_label_mapping.csv')}
mapping.update({key(r['original_label']):r['recommendation_genre'] for r in read(tax/'label_mapping.csv')})
estimates = {r['song_id']:r for r in read(base/'genre_estimates.csv')}
earlier = set()
for path in ('缺失标签补齐-扩大检索/tag_evidence.csv', '标签补齐完整交付/final_fill_evidence.csv',
             '全量曲库-风格覆盖/coverage_evidence.csv'):
    earlier.update(r['song_id'] for r in read(root/'outputs'/path) if r['method'] in
                   ('artist_style','lead_artist_style','performers_agree','艺人主风格推断'))
targets = {signature(ids[i]['song_name'],ids[i]['artist']) for i in estimates if ids[i]['artist']}
references = defaultdict(set)
for r in read(root/'outputs/艺人扩充1000/采集结果/sources.csv'):
    sig = signature(r['title'],r['artist_credit'])
    if sig in targets:
        for raw in r['genres'].split('|'):
            if genre := mapping.get(key(raw)):
                references[sig].add((genre,r['source'],r['source_id']))
fresh = {}
for r in read(out/'stratified_audit.csv'):
    candidates = json.loads(r['references'])
    if len({v[3] for v in candidates}) == 1:
        fresh[r['song_id']] = {(v[3],v[0],v[1]) for v in candidates}

corrections = []
for ident, estimate in estimates.items():
    row = ids[ident]
    evidence = fresh.get(ident,set()) | references.get(signature(row['song_name'],row['artist']),set())
    choices = {ref[0] for ref in evidence}
    if len(choices) != 1:
        continue
    genre = next(iter(choices))
    existing = set(row['genres'].split('|'))
    row['genres'] = '|'.join(sorted((existing-styles)|{genre}))
    corrections.append((ident,row['song_name'],row['artist'],estimate['assigned_genre'],genre,
                        'fresh_lookup' if ident in fresh else 'same_title_and_credit',
                        json.dumps(sorted(evidence),ensure_ascii=False)))

promoted = {r[0] for r in corrections}
conflicts = {r['song_id'] for r in read(out/'platform_conflicts.csv')}
policy = []
for ident in sorted(set(estimates)|conflicts|earlier):
    if ident in conflicts:
        policy.append((ident,.25,'平台曲风不一致'))
    elif ident in promoted:
        policy.append((ident,1,'曲目来源支持'))
    elif ident in estimates:
        method = estimates[ident]['method']
        policy.append((ident,{'全库风格分布兜底':0,'曲名与标签模型':.25}.get(method,.5),method))
    else:
        policy.append((ident,.5,'早期艺人风格推断'))

counts = Counter(g for r in rows for g in set(r['genres'].split('|')))
write_csv(out/'songs.csv', fields, (tuple(r[k] for k in fields) for r in rows))
write_csv(out/'genre_counts.csv', ('genre','count'),counts.most_common())
write_csv(out/'corrections.csv', ('song_id','song_name','artist','previous_estimate','supported_genre','method','references'),corrections)
write_csv(out/'genre_ranking_policy.csv', ('song_id','suggested_genre_weight','reason'),policy)
write_csv(out/'exclude_from_genre_ranking.csv', ('song_id','reason'),[(i,r) for i,w,r in policy if w==0])
report = json.loads((out/'audit_report.json').read_text(encoding='utf-8'))
report['estimates_supported_by_track_evidence'] = len(corrections)
report['changed_genres'] = sum(item[3]!=item[4] for item in corrections)
report['ranking_weight_counts'] = dict(Counter(str(r[1]) for r in policy))
report['exclude_from_genre_ranking'] = sum(w == 0 for _,w,_ in policy)
(out/'audit_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
