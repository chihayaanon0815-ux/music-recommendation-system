import csv
import sys
from collections import Counter
from pathlib import Path
from flask import Flask, render_template, request

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
ASSETS = Path(getattr(sys, '_MEIPASS', ROOT)) / 'web'
app = Flask(__name__, template_folder=str(ASSETS / 'templates'), static_folder=str(ASSETS / 'static'))
SAMPLE = [dict(song_id=f'{i:02}', song_name=n, artist=a, genres=g) for i, n, a, g in [
    (1, '晨光', '示例歌手甲', '流行|民谣'), (2, '远方', '示例歌手乙', '摇滚'),
    (3, '小路', '示例歌手甲', '民谣'), (4, '夜空', '示例歌手丙', '电子|流行'),
    (5, '海风', '示例歌手乙', '流行'), (6, '无题', '示例歌手丁', '')]]

def load_csv(path, fields):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(fields).issubset(reader.fieldnames):
            raise ValueError('表头不符合约定')
        return [{k: (row.get(k) or '').strip() for k in fields} for row in reader]

def mock_recommend(songs, preferences, limit=10):
    genres, artists = set(preferences['genres']), set(preferences['artists'])
    out = []
    for song in songs:
        matched = sorted(genres & set(x.strip() for x in song['genres'].split('|') if x.strip()))
        artist = song['artist'] in artists and bool(song['artist'])
        score = 3 * len(matched) + 2 * int(artist)
        if genres or artists:
            if not score: continue
            reason = '；'.join(([f"风格匹配：{'、'.join(matched)}"] if matched else []) + ([f"歌手匹配：{song['artist']}"] if artist else []))
        else: reason = '未选择偏好，按歌曲 ID 默认推荐'
        out.append({**song, 'score': score, 'reason': reason})
    return sorted(out, key=lambda x: (-x['score'], x['song_id']))[:limit]

@app.route('/', methods=['GET', 'POST'])
def index():
    base = ROOT / 'data' / 'processed'
    messages = []
    try:
        songs = load_csv(base / 'songs.csv', ['song_id', 'song_name', 'artist', 'genres'])
        ids = [s['song_id'] for s in songs]
        if not songs or any(not s['song_id'] or not s['song_name'] for s in songs) or len(ids) != len(set(ids)):
            raise ValueError('歌曲为空、必填字段缺失或 ID 重复')
        source = '已加载处理后的歌曲数据'
    except (OSError, ValueError, UnicodeError, csv.Error) as e:
        songs = SAMPLE
        source = '虚构演示样例'
        messages.append(f'歌曲文件缺失或损坏（{e}），当前使用虚构演示样例。')
    genres = sorted({g.strip() for s in songs for g in s['genres'].split('|') if g.strip()})
    artists = sorted({s['artist'] for s in songs if s['artist']})
    artist_set = set(artists)
    selected_artists = request.form.getlist('artists') + [request.form.get('artist_search', '').strip()]
    preferences = {'genres': [x for x in request.form.getlist('genres') if x in genres], 'artists': list(dict.fromkeys(x for x in selected_artists if x))}
    try:
        from recommender.recommend import recommend
        algorithm = '推荐算法模块'
    except ModuleNotFoundError as e:
        if e.name not in ('recommender', 'recommender.recommend'):
            raise
        recommend = mock_recommend
        algorithm = '模拟推荐算法（待接入 B 模块）'
    results = recommend(songs, preferences, limit=10)
    counts = []
    if songs is not SAMPLE:
        try:
            rows = load_csv(base / 'genre_counts.csv', ['genre', 'count'])
            counts = [(r['genre'], int(r['count'])) for r in rows]
            if any(not g or n < 0 for g, n in counts): raise ValueError('无效统计值')
        except (OSError, ValueError, UnicodeError, csv.Error) as e:
            messages.append(f'风格统计尚未生成或文件损坏：{e}')
    else:
        counts = sorted(Counter(g.strip() for s in songs for g in set(s['genres'].split('|')) if g.strip()).items())
        messages.append('风格统计为虚构演示样例的统计；真实风格统计尚未加载。')
    artist_counts = sorted(Counter(s['artist'] for s in songs if s['artist']).items(), key=lambda x: (-x[1], x[0]))
    featured_artists = list(dict.fromkeys([a for a, _ in artist_counts[:100]] + [a for a in preferences['artists'] if a in artist_set]))
    return render_template('index.html', songs=songs, source=source, messages=messages, genres=genres, artists=featured_artists, p=preferences, results=results, counts=counts, artist_counts=artist_counts[:15], algorithm=algorithm)
