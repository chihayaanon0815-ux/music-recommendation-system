"""Fill the outstanding genre field with traceable evidence or an unknown marker."""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from catalog import key, names_for, write_csv

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'outputs/缺失标签补齐-扩大检索'
DRAFT = ROOT / 'outputs/清洗与标签统一草稿'
OUT = ROOT / 'outputs/标签补齐完整交付'
OUT.mkdir(exist_ok=True)
FIELDS = ('song_id', 'song_name', 'artist', 'genres')
UNKNOWN = '风格待确认'
SPLIT_CREDIT = re.compile(r'\s+(?:feat\.?|ft\.?|featuring|with|&|and|×)\s+|、|\s*,\s*', re.I)
FEATURED = re.compile(r'\s+(?:feat\.?|ft\.?|featuring)\s+', re.I)


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        yield from csv.DictReader(file)


def artist_key(artist):
    return min(names_for(artist))


def genres(value):
    return set(filter(None, (tag.strip() for tag in value.split('|'))))


def split_credit(artist):
    return [artist_key(part.strip()) for part in SPLIT_CREDIT.split(artist) if part.strip()]


families = {
    '摇滚': ('独立摇滚','另类摇滚','硬摇滚','迷幻摇滚','民谣摇滚','蓝调摇滚','流行摇滚'),
    '流行': ('独立流行','传统流行'),
    '爵士': ('酸爵士','酷派爵士','融合爵士','自由爵士','柔和爵士','人声爵士','当代爵士'),
    '古典': ('古典跨界','歌剧','室内乐','管弦乐'),
    '电子': ('电子乐','浩室','深浩室','科技舞曲','出神舞曲','鼓打贝斯','回响贝斯','碎拍','氛围'),
    '嘻哈': ('嘻哈/说唱','说唱'),
    '灵魂乐': ('新灵魂乐',),
    '节奏布鲁斯': ('当代节奏布鲁斯',),
    '金属': ('重金属','死亡金属','鞭击金属'),
    '民谣': ('另类民谣','当代民谣'),
    '乡村': ('蓝草',),
    '朋克': ('流行朋克',),
}
parent = {child: family for family, children in families.items() for child in children}
mapping = list(read(DRAFT/'label_mapping_review.csv'))
genre_labels = {r['canonical_label'] for r in mapping if r['dimension'] in ('曲风', '地区曲风')}
genre_labels.update('蓝调|雷鬼|朋克|乡村|世界音乐|拉丁|节奏布鲁斯|轻音乐'.split('|'))
genre_labels.discard('世界音乐')  # Too broad to serve as a dominant-artist inference.


def musical_tags(value):
    return {parent.get(g, g) for g in genres(value) & genre_labels}


rows = list(read(BASE/'songs.csv'))
previous = list(read(BASE/'tag_evidence.csv'))
inferred = {r['song_id'] for r in previous if r['method'] == 'artist_style'}
pending = [r for r in rows if not r['genres']]
artist_votes = defaultdict(Counter)
artist_totals = Counter()
performers = defaultdict(set)
known = {artist_key(r['artist']) for r in rows if r['artist'] and r['genres'] and r['song_id'] not in inferred}

for row in rows:
    if not row['genres'] or row['song_id'] in inferred or not row['artist']:
        continue
    name = artist_key(row['artist'])
    song_tags = musical_tags(row['genres'])
    if not song_tags:
        continue
    artist_totals[name] += 1
    artist_votes[name].update(song_tags)
    parts = split_credit(row['artist'])
    if len(parts) > 1 and all(part in known for part in parts):
        performers[key(row['song_name']), frozenset(parts)].update(song_tags)


def main_style(name):
    votes = sorted(artist_votes.get(name, {}).items(), key=lambda item: (-item[1], item[0]))
    total = artist_totals[name]
    if not votes:
        return None
    label, support = votes[0]
    margin = support - (votes[1][1] if len(votes) > 1 else 0)
    if support >= 2 and support * 2 >= total and margin >= max(1, total * 0.1):
        return label, support, total
    return None


audit = []
method_counts = Counter()
for row in pending:
    artist = row['artist']
    parts = split_credit(artist)
    label = UNKNOWN
    method = 'unknown'
    support = total = ''
    basis = artist
    same_track = performers.get((key(row['song_name']), frozenset(parts)), set()) if len(parts) > 1 else set()
    if len(same_track) == 1:
        label = next(iter(same_track))
        method = 'track_credit_order'
    elif style := main_style(artist_key(artist)):
        label, support, total = style
        method = 'artist_style'
    elif len(parts) > 1 and all(part in known for part in parts):
        styles = [main_style(part) for part in dict.fromkeys(parts)]
        if all(styles) and len({s[0] for s in styles}) == 1:
            label = styles[0][0]
            support, total = min((s[1:] for s in styles), key=lambda v: v[0] / v[1])
            method = 'performers_agree'
    if method == 'unknown' and FEATURED.search(artist):
        basis = FEATURED.split(artist, maxsplit=1)[0].strip()
        if style := main_style(artist_key(basis)):
            label, support, total = style
            method = 'lead_artist_style'
    row['genres'] = label
    method_counts[method] += 1
    audit.append((row['song_id'], row['song_name'], artist, label, method, basis, support, total))

counts = Counter(g for row in rows for g in genres(row['genres']))
assert len(rows) == len({r['song_id'] for r in rows}) and all(r['genres'] for r in rows)
assert sum(method_counts.values()) == len(pending)
write_csv(OUT/'songs.csv', FIELDS, (tuple(r[k] for k in FIELDS) for r in rows))
write_csv(OUT/'genre_counts.csv', ('genre','count'), counts.most_common())
write_csv(OUT/'final_fill_evidence.csv', ('song_id','song_name','artist','genre','method','basis','support','artist_tagged_tracks'), audit)
write_csv(OUT/'previous_fill_evidence.csv', tuple(previous[0]), (tuple(r.values()) for r in previous))
write_csv(OUT/'genre_unconfirmed.csv', FIELDS,
          (tuple(r[k] for k in FIELDS) for r in rows if UNKNOWN in genres(r['genres'])))
report = {'songs':len(rows),'processed_missing':len(pending),'by_method':dict(method_counts),
          'nonempty_genre_fields':len(rows),'songs_with_assigned_genre':len(rows)-counts[UNKNOWN],
          'songs_with_unconfirmed_genre':counts[UNKNOWN],
          'assigned_coverage_percent':round(100 * (1-counts[UNKNOWN]/len(rows)),2)}
(OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
