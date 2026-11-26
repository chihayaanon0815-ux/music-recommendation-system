"""Extend catalog coverage while preserving the type of evidence for each addition."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from catalog import key, names_for, write_csv

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'outputs/全量曲库-统一标签'
OUT = ROOT/'outputs/全量曲库-风格覆盖'
OUT.mkdir(exist_ok=True)
UNKNOWN = '风格待确认'
FIELDS = ('song_id', 'song_name', 'artist', 'genres')
SPECIAL = {
    'christmas: pop': '流行', '圣诞节:流行乐': '流行',
    'christmas: rock': '摇滚', 'christmas: country': '乡村',
    'christmas: jazz': '爵士', 'christmas: r&b': '节奏布鲁斯与灵魂乐',
    'comedy rock': '摇滚', 'brazilian pop': '流行', 'arabic classical': '古典',
}
DIRECT_GROUPS = {
    '儿童音乐': ('儿童音乐', '儿童', '摇篮曲', "christmas: children's"),
    '影视原声': ('影视原声', '影视', '电视原声', '原创配乐', 'bollywood', 'filmi'),
    '动画音乐': ('动画音乐', 'acg'),
    '游戏音乐': ('电子游戏',),
    '音乐剧': ('音乐剧',),
    '节庆音乐': ('节庆音乐', '圣诞音乐', 'easter', 'halloween', 'thanksgiving'),
    '喜剧与单口': ('喜剧', '单口喜剧'),
    '朗读与访谈': ('朗读', '访谈', 'stories'),
    '环境声音': ('自然声音',),
    '非音乐音频': ('non-music',),
}
CONTENT = {label: group for group, labels in DIRECT_GROUPS.items() for label in labels}
NON_MUSIC = {'喜剧与单口', '朗读与访谈', '环境声音', '非音乐音频'}
RULES = {'曲目标签中的风格', '同一歌曲的现有风格'}


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        yield from csv.DictReader(file)


def tags(value):
    return {tag for tag in value.split('|') if tag}


def artist(credit):
    return min(names_for(credit))


rows = list(read(BASE/'songs.csv'))
details = {row['song_id']: tags(row['original_labels']) for row in read(BASE/'song_label_details.csv')}
inferred = set()
for bundle in ('缺失标签补齐-扩大检索/tag_evidence.csv', '标签补齐完整交付/final_fill_evidence.csv'):
    for r in read(ROOT/'outputs'/bundle):
        if r['method'] in ('artist_style', 'lead_artist_style', 'performers_agree'):
            inferred.add(r['song_id'])

votes, totals = defaultdict(Counter), Counter()
recording = defaultdict(set)
for row in rows:
    if row['genres'] == UNKNOWN or row['song_id'] in inferred or not row['artist']:
        continue
    ident = artist(row['artist'])
    found = tags(row['genres'])
    votes[ident].update(found)
    totals[ident] += 1
    recording[key(row['song_name']), ident].update(found)

audit = []
method_counts = Counter()
for row in rows:
    if row['genres'] != UNKNOWN:
        continue
    raw = {key(r) for r in details[row['song_id']]}
    original = '|'.join(sorted(details[row['song_id']]))
    styles = {SPECIAL[tag] for tag in raw if tag in SPECIAL}
    content = {CONTENT[tag] for tag in raw if tag in CONTENT}
    if any(tag.startswith(('christmas:', '圣诞节:')) for tag in raw):
        content.add('节庆音乐')
    support = total = ''
    ident = artist(row['artist'])
    nearby = recording.get((key(row['song_name']), ident), set()) if row['artist'] else set()
    if styles and not content & NON_MUSIC:
        method = '曲目标签中的风格'
    elif len(nearby) == 1 and not content & NON_MUSIC:
        styles = nearby
        method = '同一歌曲的现有风格'
    elif content:
        styles = content
        method = '原始内容类别'
    else:
        method = '待确认'
        ranked = sorted(votes.get(ident, {}).items(), key=lambda x: (-x[1], x[0]))
        if ranked and row['artist']:
            best, best_count = ranked[0]
            total_count = totals[ident]
            runner = ranked[1][1] if len(ranked) > 1 else 0
            if best_count >= 3 and best_count / total_count >= .65 and (best_count-runner) / total_count >= .20:
                styles = {best}
                support, total = best_count, total_count
                method = '艺人主风格推断'
    row['genres'] = '|'.join(sorted(styles)) if styles else UNKNOWN
    method_counts[method] += 1
    audit.append((row['song_id'],row['song_name'],row['artist'],row['genres'],method,original,support,total))

counts = Counter(g for row in rows for g in tags(row['genres']))
write_csv(OUT/'songs.csv', FIELDS, (tuple(r[k] for k in FIELDS) for r in rows))
write_csv(OUT/'genre_counts.csv', ('genre','count'), counts.most_common())
write_csv(OUT/'coverage_evidence.csv', ('song_id','song_name','artist','genres','method','previous_labels','support','artist_tagged_tracks'), audit)
write_csv(OUT/'genre_unconfirmed.csv', FIELDS,
          (tuple(r[k] for k in FIELDS) for r in rows if r['genres']==UNKNOWN))
report = {'tracks':len(rows),'original_unknown':len(audit),'by_method':dict(method_counts),
          'remaining_unknown':counts[UNKNOWN],
          'musical_style_count':len(rows)-len(audit)+sum(method_counts[r] for r in RULES)+method_counts['艺人主风格推断'],
          'catalog_label_coverage_pct':round(100*(len(rows)-counts[UNKNOWN])/len(rows),2)}
(OUT/'coverage_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
