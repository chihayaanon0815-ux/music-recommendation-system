"""Assign one provisional musical style when direct catalog evidence is missing."""
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from catalog import key, names_for, write_csv

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'outputs/风格复查-扩大搜索'
TAX = ROOT/'outputs/全量曲库-统一标签'
OUT = ROOT/'outputs/全曲库-曲风补全'
OUT.mkdir(exist_ok=True)
FIELDS = ('song_id', 'song_name', 'artist', 'genres')
UNKNOWN = '风格待确认'
NON_MUSIC = {'喜剧与单口', '朗读与访谈', '环境声音', '非音乐音频'}
FEATURED = re.compile(r'\s+(?:feat\.?|ft\.?|featuring)\s+', re.I)
CREDIT_SPLIT = re.compile(r'\s+(?:&|×)\s+|、|\s*,\s*')
WORD = re.compile(r'[^\W\d_]+', re.UNICODE)
CJK = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+')


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        yield from csv.DictReader(file)


def artist_key(value):
    return min(names_for(value))


def genre_set(row):
    return set(filter(None, row['genres'].split('|')))


def features(row, contexts):
    title = key(row['song_name'])
    credit = key(row['artist'])
    terms = {'title:' + word for word in WORD.findall(title) if len(word) > 2 and not CJK.search(word)}
    for sequence in CJK.findall(title):
        terms.update('title2:' + sequence[i:i+2] for i in range(len(sequence)-1))
    for prefix, value in [('title', title), ('artist', credit)]:
        if CJK.search(value):
            terms.add(prefix + ':east_asian_script')
        if re.search('[а-яё]', value):
            terms.add(prefix + ':cyrillic')
        if re.search('[ぁ-ヿ]', value):
            terms.add(prefix + ':kana')
    terms.update('context:' + tag for tag in contexts.get(row['song_id'], ()))
    return terms


def is_eval(artist):
    return hashlib.sha256(artist.encode()).digest()[0] < 13


styles = {r['genre'] for r in read(TAX/'recommendation_genres.csv')}
rows = list(read(BASE/'songs.csv'))
contexts = {}
for r in read(TAX/'song_label_details.csv'):
    keep = [tag for tag in r['other_labels'].split('|') if tag and not tag.startswith(('质量状态/', '待复核/'))]
    if keep:
        contexts[r['song_id']] = keep

# Avoid training a new estimate on earlier artist-based guesses.
inferred = set()
for relative in ('缺失标签补齐-扩大检索/tag_evidence.csv',
                 '标签补齐完整交付/final_fill_evidence.csv',
                 '全量曲库-风格覆盖/coverage_evidence.csv'):
    for r in read(ROOT/'outputs'/relative):
        if r['method'] in ('artist_style', 'lead_artist_style', 'performers_agree', '艺人主风格推断'):
            inferred.add(r['song_id'])

class_docs = Counter()
feature_docs = Counter()
feature_class = defaultdict(Counter)
artist_votes = defaultdict(Counter)
artist_totals = Counter()
holdout = []
for row in rows:
    labels = genre_set(row) & styles
    if not labels or row['song_id'] in inferred:
        continue
    artist = artist_key(row['artist'])
    if artist:
        artist_votes[artist].update(labels)
        artist_totals[artist] += 1
    tokens = features(row, contexts)
    if is_eval(artist):
        holdout.append((tokens, labels))
        continue
    class_docs.update(labels)
    feature_docs.update(tokens)
    for token in tokens:
        feature_class[token].update(labels)


def estimate(tokens):
    active = [t for t in sorted(tokens) if feature_docs[t] >= 5]
    scores = {}
    total = sum(class_docs.values())
    for genre, count in class_docs.items():
        prior = count / total
        # Smooth label associations toward the observed global prior.
        score = .55 * math.log(prior)
        for token in active:
            distribution = feature_class[token]
            conditional = (distribution[genre] + 16*prior) / (distribution.total()+16)
            weight = .65 if token.startswith('context:') else .32
            score += weight * math.log(conditional/prior)
        scores[genre] = score
    best = sorted(scores, key=lambda g: (-scores[g],g))
    return best[0], len(active), scores[best[0]]-scores[best[1]]


def artist_choice(ident, minimum=2):
    ranked = artist_votes.get(ident, {}).most_common() if ident in artist_votes else []
    if not ranked:
        return None
    label, supporting = ranked[0]
    total = artist_totals[ident]
    runner = ranked[1][1] if len(ranked) > 1 else 0
    if supporting >= minimum and supporting > runner and supporting/total >= .55:
        return label, supporting, total
    return None


baseline = class_docs.most_common(1)[0][0]
correct = baseline_correct = 0
for tokens, labels in holdout:
    correct += estimate(tokens)[0] in labels
    baseline_correct += baseline in labels

audit = []
method_counts = Counter()
counts = Counter()
non_music = 0
for row in rows:
    current = genre_set(row)
    if current & NON_MUSIC and not current & styles:
        non_music += 1
    elif not current & styles:
        identity = artist_key(row['artist'])
        choice = artist_choice(identity)
        method = '同艺人主风格'
        if not choice and FEATURED.search(row['artist']):
            choice = artist_choice(artist_key(FEATURED.split(row['artist'],maxsplit=1)[0]))
            method = '主艺人风格'
        if not choice:
            credits = [artist_key(x) for x in CREDIT_SPLIT.split(row['artist']) if x]
            choices = [artist_choice(name) for name in dict.fromkeys(credits)]
            if len(choices) >= 2 and all(choices) and len({c[0] for c in choices}) == 1:
                choice = min(choices,key=lambda c:c[1]/c[2])
                method = '合作艺人风格一致'
        support = observed = used_features = margin = ''
        if choice:
            genre, support, observed = choice
            confidence = '中' if support >= 5 and support/observed >= .7 else '低'
        else:
            genre, used_features, difference = estimate(features(row,contexts))
            margin = round(difference,4)
            method = '曲名与标签模型' if used_features else '全库风格分布兜底'
            confidence = '低' if used_features else '极低'
        previous = row['genres']
        current.discard(UNKNOWN)
        current.add(genre)
        row['genres'] = '|'.join(sorted(current))
        method_counts[method] += 1
        audit.append((row['song_id'],row['song_name'],row['artist'],previous,genre,method,confidence,
                      support,observed,used_features,margin))
    counts.update(genre_set(row))

assert all(genre_set(r) & (styles | NON_MUSIC) and UNKNOWN not in genre_set(r) for r in rows)
write_csv(OUT/'songs.csv', FIELDS, (tuple(r[k] for k in FIELDS) for r in rows))
write_csv(OUT/'genre_counts.csv', ('genre','count'), counts.most_common())
write_csv(OUT/'genre_estimates.csv', ('song_id','song_name','artist','previous_labels','assigned_genre','method',
          'confidence','artist_support','artist_labeled_tracks','matched_features','model_score_margin'), audit)
write_csv(OUT/'non_music.csv', FIELDS, (tuple(r[k] for k in FIELDS) for r in rows
                                      if genre_set(r) & NON_MUSIC and not genre_set(r) & styles))
report = {'retained_tracks':len(rows),'songs_with_musical_genre':len(rows)-non_music,
          'identified_non_music_entries':non_music, 'new_estimates':len(audit),
          'by_method':dict(method_counts),'holdout_rows':len(holdout),
          'holdout_match_percent':round(100*correct/len(holdout),2),
          'holdout_popularity_baseline_percent':round(100*baseline_correct/len(holdout),2),
          'interpretation':'留出艺人测试仅衡量标签复现，不能验证未标注歌曲的实际风格。模型分差不是概率。'}
(OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
