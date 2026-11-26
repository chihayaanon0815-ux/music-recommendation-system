"""Export a recommendation vocabulary and a reversible mapping for every track."""
import csv
import json
import re
from collections import Counter
from pathlib import Path

from catalog import key, write_csv

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'outputs/标签补齐完整交付'
OUT = ROOT / 'outputs/全量曲库-统一标签'
OUT.mkdir(exist_ok=True)
FIELDS = ('song_id', 'song_name', 'artist', 'genres')
UNKNOWN = '风格待确认'

# Format: broad genre, followed by explicitly associated source labels.
GROUPS = '''
流行:华语流行|粤语流行|台湾流行|日语流行|韩语流行|日韩流行|独立流行|传统流行|法语流行|印度流行|泰国流行乐|国语流行乐|广东歌/香港流行乐|c-pop|德国流行|german pop|pop latino|vocal pop|美声流行乐|synth-pop|adult contemporary|成人当代|schlager|ballad|oldies|bossa nova pop|chamber pop|city pop|electropop|europop|演歌|indо pop|indo pop|brostep pop|hyperpop|fantezi|art pop|power pop|teen pop|bubblegum pop|psychedelic pop|ambient pop|arabic pop|egyptian pop|turkish pop|punjabi pop|pop in russian
摇滚:独立摇滚|另类摇滚|硬摇滚|迷幻摇滚|民谣摇滚|流行摇滚|华语摇滚|蓝调摇滚|草根摇滚|前卫摇滚/艺术摇滚|rock y alternativo|rock & roll|rock and roll|grunge|post-grunge|surf|emo|emo pop|new wave|neo-psychedelia|britpop|post-britpop|aor|mod revival|rock in russian|j-rock
电子:电子乐|浩室|深浩室|科技舞曲|出神舞曲|碎拍|回响贝斯|鼓打贝斯|氛围|idm/experimental|idm/试验性|downtempo|electro|edm|brostep|big beat|future bass|industrial|electroclash|complextro|uk garage|2-step|nightcore|jungle terror|moombahton|moombahcore|indietronica|festival trap|trap edm|hybrid trap|leftfield|drumstep|chillstep
爵士:人声爵士|当代爵士|酸爵士|柔和爵士|酷派爵士|融合爵士|自由爵士|bop|bebop|big band|swing|dixieland|ragtime|post-bop|hard bop
古典:古典跨界|歌剧|室内乐|管弦乐|国乐|中国弦乐|baroque|neoclassicism
民谣:台湾民谣|中国地方民谣|另类民谣|当代民谣|traditional folk|irish folk|german folk|indian folk|stomp and holler
乡村:蓝草|americana|contemporary bluegrass|progressive bluegrass|honky tonk
金属:重金属|鞭击金属|死亡金属|死亡金属/黑金属|grindcore|metalcore
朋克:流行朋克|hardcore punk|post-punk|post-punk revival|dance-punk
嘻哈:嘻哈/说唱|说唱|华语嘻哈|chinese hip-hop|grime|phonk|trap|boom bap|dirty south|trip hop
节奏布鲁斯与灵魂乐:节奏布鲁斯/灵魂乐|节奏布鲁斯|灵魂乐|当代节奏布鲁斯|新灵魂乐|motown|new jack swing|quiet storm|doo-wop
蓝调:chicago blues
放克:synth funk|boogie
雷鬼:斯卡|dancehall|modern dancehall|dub|ragga
舞曲:迪斯科|nu disco|italo-disco|latin disco|eurodance|twerk
世界音乐:古风/中国风|celtic|contemporary celtic|fado|flamenco|worldbeat|afrobeats|afro-beat|afrobeat|afro-pop|afro-fusion|alte|amapiano|coladeira|morna|mbalax|halk|sanat|éntekhno|ghazals|abhang|rabindra sangeet
拉丁:tango|pagode|mpb|música tropical|raíces|urbano latino|samba|música mexicana|forró|baladas y boleros|bossa nova|bolero|bolero son|sertanejo|baile funk|ranchera|reggaeton|salsa|guajira|samba-reggae|guitarrada|danzón|son cubano|descarga|regional mexicano|axé|mambo|latin pop|contemporary latin
宗教音乐:christian|devotional & spiritual|gospel|福音音乐|基督教音乐|基督教流行乐|christian rock|christian pop|christian rap|classic christian|contemporary christian|contemporary gospel|ccm|praise & worship|islamic|sufi|qawwali|chant
轻音乐:easy listening|lounge
新世纪:新原音
另类与实验:alternative|另类音乐|华语另类音乐|adult alternative|成人另类|experimental|free improvisation|sound collage
'''
GROUPS = GROUPS.replace('|bossa nova pop', '').replace('|indо pop', '').replace('|brostep pop', '')
groups = {}
for line in GROUPS.strip().splitlines():
    parent, children = line.split(':', 1)
    for child in [parent, *children.split('|')]:
        assert child not in groups
        groups[child] = parent
groups.update({'pop latino': '拉丁', 'alternative dance': '电子', 'west coast swing': '舞曲'})

OTHER = {
    '地区或语种': '中国|日本|俄罗斯|亚洲|阿拉伯|印度|巴西|华语音乐|african|tamil|telugu|bengali|malayalam|punjabi|kannada|marathi|odia|iberia|south america|france|north african|south africa|israeli|turkish|cuban|caribbean|regional indian|chanson in russian|romance in russian|arabesque',
    '场景与情绪': '派对|学习|放松|伤感|助眠|欢快|浪漫|冥想|健身运动|摇篮曲|inspirational|club|chillout',
    '媒介与用途': '影视原声|影视|acg|动画音乐|电视原声|原创配乐|音乐剧|电子游戏|disney|bollywood|filmi',
    '节庆': '节庆音乐|圣诞音乐|easter|halloween|thanksgiving',
    '声音类型': '纯音乐|人声|自然声音|器乐',
    '受众': '儿童音乐|儿童',
    '内容类型': '喜剧|单口喜剧|朗读|访谈|stories|non-music',
    '版本': '卡拉ok|翻唱致敬',
    '年代': '老歌|modern era',
    '艺人类型': '创作歌手|当代歌手/歌曲作者|contemporary singer/songwriter',
    '其他描述': '原创音乐',
    '质量状态': UNKNOWN,
}
other_dimensions = {tag: dimension for dimension, tags in OTHER.items() for tag in tags.split('|')}
RULES = [
    ('爵士', r'\bjazz\b'), ('古典', r'\bclassical\b'),
    ('金属', r'\bmetal\b'), ('朋克', r'\bpunk\b'),
    ('嘻哈', r'\b(?:hip[ -]hop|rap)\b'), ('节奏布鲁斯与灵魂乐', r'\b(?:r&b|soul)\b'),
    ('摇滚', r'\brock\b'), ('蓝调', r'\bblues\b'),
    ('乡村', r'\b(?:country|bluegrass)\b'), ('民谣', r'\bfolk\b'),
    ('雷鬼', r'\breggae\b'),
    ('电子', r'\b(?:house|techno|trance|electronic|ambient|breaks|dubstep|drum and bass)\b'),
    ('流行', r'\bpop\b'),
]


def classify(raw):
    tag = key(raw)
    if tag in other_dimensions:
        return other_dimensions[tag], '', tag
    if tag.startswith(('christmas:', '圣诞节:')):
        return '节庆', '', tag
    if tag in groups:
        return '曲风', groups[tag], tag
    for broad, pattern in RULES:
        if re.search(pattern, tag):
            return '曲风', broad, tag
    return '待复核', '', tag


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        yield from csv.DictReader(file)


before = Counter()
after = Counter()
mapping = {}
tracks = []
dimensions = []
unknown_by_reason = Counter()
for original in read(BASE/'songs.csv'):
    raw_tags = {tag.strip() for tag in original['genres'].split('|') if tag.strip()}
    before.update(raw_tags)
    broad, fine, notes = set(), set(), set()
    for raw in raw_tags:
        axis, parent, detail = mapping.setdefault(raw, classify(raw))
        if parent:
            broad.add(parent)
            if detail != parent:
                fine.add((parent, detail))
        else:
            notes.add((axis, detail))
    if not broad:
        unknown_by_reason['已有待确认标记' if UNKNOWN in raw_tags else '只有其他维度或待复核标签'] += 1
        broad.add(UNKNOWN)
    after.update(broad)
    tracks.append((original['song_id'], original['song_name'], original['artist'], '|'.join(sorted(broad))))
    dimensions.append((original['song_id'], '|'.join(sorted(raw_tags)),
                       '|'.join(f'{parent}/{detail}' for parent, detail in sorted(fine)),
                       '|'.join(f'{axis}/{detail}' for axis, detail in sorted(notes))))

write_csv(OUT/'songs.csv', FIELDS, tracks)
write_csv(OUT/'song_label_details.csv', ('song_id','original_labels','subgenres','other_labels'), dimensions)
write_csv(OUT/'genre_counts.csv', ('genre','count'), sorted(after.items(), key=lambda x: (-x[1], x[0])))
write_csv(OUT/'label_mapping.csv', ('original_label','dimension','recommendation_genre','normalized_detail','song_count'),
          [(raw,*mapping[raw],n) for raw, n in before.most_common()])
write_csv(OUT/'pending_labels.csv', ('original_label','song_count'),
          [(raw,n) for raw,n in before.most_common() if mapping[raw][0]=='待复核'])
source_mapping = []
for row in read(ROOT/'outputs/清洗与标签统一草稿/label_mapping_review.csv'):
    axis, broad, detail = classify(row['canonical_label'])
    source_mapping.append((row['raw_label'], row['canonical_label'], axis, broad, detail, row['source_record_count']))
write_csv(OUT/'source_label_mapping.csv',
          ('source_label','previous_standard_label','dimension','recommendation_genre','normalized_detail','source_record_count'),
          source_mapping)
write_csv(OUT/'recommendation_genres.csv', ('genre','count'),
          sorted(((g,n) for g,n in after.items() if g != UNKNOWN), key=lambda x:(-x[1],x[0])))
report = {'tracks_retained': len(tracks), 'input_label_spellings':len(before),
          'recommendation_genres':len(set(after)-{UNKNOWN}), 'unclassified_tracks':after[UNKNOWN],
          'unclassified_breakdown':dict(unknown_by_reason),
          'labels_pending_review':sum(axis=='待复核' for axis, _, _ in mapping.values()),
          'dimension_label_counts':dict(Counter(axis for axis, _, _ in mapping.values())),
          'before_top_labels':before.most_common(15), 'after_counts':dict(after.most_common())}
(OUT/'taxonomy_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
