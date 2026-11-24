import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from catalog import key, names_for, write_csv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/艺人扩充1000'
OUT.mkdir(exist_ok=True)
with (ROOT / 'outputs/艺人名单-扩充候选首版.csv').open(encoding='utf-8-sig', newline='') as file:
    seeds = list(csv.DictReader(file))
with (ROOT / 'work/integration-check/data/processed/songs.csv').open(encoding='utf-8-sig', newline='') as file:
    songs = list(csv.DictReader(file))
counts = Counter()
genres = defaultdict(Counter)
for song in songs:
    artist = song['artist'].strip()
    if not artist:
        continue
    counts[artist] += 1
    for genre in set(song['genres'].split('|')) - {''}:
        genres[genre][artist] += 1

selected = {}
def add(name, region, reason, evidence):
    identity = min(names_for(name))
    if identity in selected:
        return False
    selected[identity] = (region, name, reason, evidence, counts[name])
    return True

for seed in seeds:
    add(seed['候选名称'], seed['覆盖规划'], '原有种子名单', '此前人工候选名单')

extra = {
    '古典': ['Johann Sebastian Bach', 'Wolfgang Amadeus Mozart', 'Ludwig van Beethoven', 'Frédéric Chopin', 'Claude Debussy', 'Pyotr Ilyich Tchaikovsky', 'Sergei Rachmaninoff', 'Antonio Vivaldi', 'Franz Schubert', 'Gustav Mahler', '郎朗', '王羽佳', '李云迪', '谭盾', '马友友'],
    '爵士': ['Duke Ellington', 'Charlie Parker', 'Thelonious Monk', 'Bill Evans', 'Chet Baker', 'Herbie Hancock', 'Chick Corea', 'Sarah Vaughan', 'Diana Krall', 'Norah Jones'],
    '电子': ['Kraftwerk', 'Aphex Twin', 'The Chemical Brothers', 'Massive Attack', 'Portishead', 'Boards of Canada', 'Tiësto', 'Armin van Buuren', 'Skrillex', 'Martin Garrix'],
    '金属': ['Black Sabbath', 'Iron Maiden', 'Judas Priest', 'Slayer', 'Megadeth', 'Opeth', 'Nightwish', 'Rammstein'],
    '世界音乐': ['Buena Vista Social Club', 'Salif Keita', 'Angélique Kidjo', 'Oumou Sangaré', 'Ravi Shankar', 'Anoushka Shankar', 'Sezen Aksu', 'Mariza'],
    '华语补充': ['罗文', '甄妮', '汪明荃', '叶丽仪', '徐小凤', '白光', '周璇', '姚莉', '潘秀琼', '凤飞飞', '刘文正', '高凌风', '欧阳菲菲', '黄莺莺', '潘越云', '许景淳', '江蕙', '黄乙玲', '陈雷', '洪荣宏', '蔡秋凤', '萧煌奇', '林强', '林生祥', '交工乐队', '生祥乐队', '林二汶', '林一峰', '卢巧音', '卢冠廷', '黄霑', '顾嘉辉', '关淑怡', '彭羚', '刘美君', '麦浚龙', '方皓玟', '陈蕾', '郑欣宜', 'AGA', '岑宁儿', '蓝奕邦', 'RubberBand', 'Dear Jane', 'C AllStar', 'MIRROR', '郑润泽', '黄霄雲', '袁娅维', '黄绮珊', '吉克隽逸', '阿云嘎', '郑云龙', '龚琳娜', '萨顶顶', '杭盖乐队', '九连真人', '海龟先生', '声音碎片', '木马乐队', '旅行团乐队', '鹿先森乐队', '回春丹', '棱镜', '椅子乐团', '伤心欲绝', '无妄合作社', '美秀集团', '甜约翰', '李友廷', '裘德', '陈卓璇', '陈雪凝', '鞠婧祎', '许馨文', '陈立农', '黄龄', '阿肆', '金玟岐', '蒋敦豪', '刘柏辛', '万妮达', '王以太', '艾热', '法老', '杨和苏', '谢帝', 'Higher Brothers', '南征北战', '满江', '沙宝亮', '零点乐队', '郑智化', '赵传', '温兆伦', '吴奇隆', '苏有朋', '小虎队', '李翊君', '裘海正', '高胜美', '黄安'],
}
for genre, artists in extra.items():
    for artist in artists:
        add(artist, '华语' if genre == '华语补充' else '待核实地区', genre, '人工补充候选，风格及身份待核实')

# Reserve existing Chinese-tagged artists before allocating the remaining genres.
for artist, n in genres['华语流行'].most_common():
    if sum(row[0] in ('华语', '华语标签候选') for row in selected.values()) >= 400:
        break
    if any(separator in artist for separator in (' & ', ';', '、')):
        continue
    add(artist, '华语标签候选', '华语流行', f'现有曲库该标签 {n} 首，语种地区待核实')

queues = {}
for genre, artists in genres.items():
    queues[genre] = iter(sorted(artists, key=lambda a: (-artists[a], -counts[a], a)))
while len(selected) < 1000:
    before = len(selected)
    for genre in sorted(queues):
        for artist in queues[genre]:
            if any(separator in artist for separator in (' & ', ';', '、')):
                continue
            if add(artist, '待核实地区', genre, f'现有曲库该标签 {genres[genre][artist]} 首'):
                break
        if len(selected) >= 1000:
            break
    if len(selected) == before:
        raise RuntimeError('Insufficient candidates')

rows = list(selected.values())
write_csv(OUT / 'artists_1000.csv', ['覆盖规划', '候选名称', '补充流派', '选择依据', '现有精确署名歌曲数'], rows)
old_keys = {min(names_for(seed['候选名称'])) for seed in seeds}
added = [row for identity, row in selected.items() if identity not in old_keys]
write_csv(OUT / 'artists_added.csv', ['覆盖规划', '候选名称', '补充流派', '选择依据', '现有精确署名歌曲数'], added)
summary = {'total': len(rows), 'added': len(added), 'planning_groups': dict(Counter(r[0] for r in rows)), 'selection_genres': dict(Counter(r[2] for r in rows))}
(OUT / 'roster_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False))
