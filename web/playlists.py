import csv
import hashlib
import io
import os
import secrets
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from recommender.playlist import profile, recommend_playlist
from web import catalog


bp = Blueprint('playlists', __name__, url_prefix='/playlists')


def register(app, root, assets):
    user_dir = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local' / 'share')
    app.config.update(
        PLAYLIST_DB=user_dir / 'MusicRecommendation' / 'catalog.sqlite3',
        SONG_CSV=root / 'data' / 'processed' / 'songs.csv',
        GENRE_MAP=assets.parent / 'data_processing' / 'genre_map_zh.csv',
        MAX_CONTENT_LENGTH=1024 * 1024 + 8192,
    )
    app.secret_key = secrets.token_bytes(32)
    app.register_blueprint(bp)


@bp.before_request
def protect_posts():
    token = csrf_token()
    if request.method == 'POST' and not secrets.compare_digest(token, request.form.get('csrf', '')):
        abort(400, '请刷新页面后重新提交。')


@bp.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return 'CSV 文件过大，最大支持 1 MiB。', 413


def csrf_token():
    if 'playlist_csrf' not in session:
        session['playlist_csrf'] = secrets.token_urlsafe(32)
    return session['playlist_csrf']


def db():
    if 'playlist_db' not in g:
        g.playlist_db = catalog.connect(Path(current_app.config['PLAYLIST_DB']))
    return g.playlist_db


@bp.teardown_request
def close_db(_error):
    connection = g.pop('playlist_db', None)
    if connection:
        connection.close()


def load_local():
    connection = db()
    try:
        catalog.sync_catalog(connection, Path(current_app.config['SONG_CSV']))
    except (OSError, ValueError, csv.Error):
        flash('预置曲库无法读取。已保存的歌曲仍可使用。')
    return connection


def get_playlist(playlist_id):
    row = db().execute('SELECT * FROM playlists WHERE id = ?', (playlist_id,)).fetchone()
    if row is None:
        abort(404)
    return row


def insert_item(connection, playlist_id, song, matched=True):
    fields = tuple(song[key] for key in catalog.FIELDS)
    return connection.execute("""
        INSERT OR IGNORE INTO items
        (playlist_id, song_id, song_name, artist, genres, matched, score, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (playlist_id, *fields, int(matched), song.get('score'), song.get('reason'))).rowcount


@bp.route('/', methods=['GET', 'POST'])
def index():
    connection = db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not 1 <= len(name) <= 80:
            flash('请输入 1～80 个字符的歌单名称。')
        else:
            with connection:
                playlist_id = connection.execute(
                    'INSERT INTO playlists(name) VALUES (?)', (name,)
                ).lastrowid
            return redirect(url_for('playlists.detail', playlist_id=playlist_id))
    playlists = connection.execute("""
        SELECT p.*, count(i.id) AS song_count FROM playlists p
        LEFT JOIN items i ON i.playlist_id = p.id GROUP BY p.id ORDER BY p.id DESC
    """).fetchall()
    return render_template('playlists.html', playlists=playlists)


@bp.get('/<int:playlist_id>')
def detail(playlist_id):
    playlist = get_playlist(playlist_id)
    songs = db().execute('SELECT * FROM items WHERE playlist_id=? ORDER BY id', (playlist_id,)).fetchall()
    query = request.args.get('q', '').strip()
    candidates = []
    online_candidates = []
    lookup_state = ''
    online_state = ''
    if query:
        if len(query) > 100:
            lookup_state = '请输入不超过 100 个字符的关键词。'
        else:
            connection = load_local()
            candidates = catalog.local_search(connection, query)
            lookup_state = '本地曲库结果' if candidates else '本地曲库没有找到符合条件的歌曲。'
            if request.args.get('search_online') == '1' or not candidates:
                try:
                    matches = catalog.online_search(query, Path(current_app.config['GENRE_MAP']))
                    local_ids = {song['song_id'] for song in candidates}
                    online_candidates = [song for song in matches if song['song_id'] not in local_ids]
                    if online_candidates:
                        online_state = 'MusicBrainz 在线结果'
                    elif matches:
                        online_state = 'MusicBrainz 未找到更多版本。'
                    else:
                        online_state = 'MusicBrainz 没有找到符合条件的歌曲。'
                except (OSError, ValueError):
                    online_state = 'MusicBrainz 暂时不可用，可以稍后重试。'
    genres, artists = profile(songs)
    return render_template('playlist_detail.html', playlist=playlist, songs=songs, query=query,
                           candidates=candidates, lookup_state=lookup_state,
                           online_candidates=online_candidates, online_state=online_state,
                           genres=genres.most_common(8), artists=artists.most_common(5),
                           tagged=sum(bool(song['matched'] and song['genres']) for song in songs))


@bp.post('/<int:playlist_id>/add')
def add(playlist_id):
    get_playlist(playlist_id)
    connection = load_local()
    song_id = request.form.get('song_id', '')
    row = connection.execute('SELECT * FROM catalog WHERE song_id = ?', (song_id,)).fetchone()
    song = dict(row) if row else None
    if not song and song_id.startswith('mb:'):
        try:
            song = catalog.online_recording(song_id[3:], Path(current_app.config['GENRE_MAP']))
        except (OSError, ValueError):
            flash('暂时无法取得录音详情，可以稍后重试。')
    if song:
        with connection:
            connection.execute('INSERT OR IGNORE INTO catalog VALUES (?, ?, ?, ?, ?, ?, ?)', (
                *(song[key] for key in catalog.FIELDS), catalog.normalize(song['song_name']),
                catalog.normalize(song['artist']), song['source'],
            ))
            added = insert_item(connection, playlist_id, song)
        flash('已添加歌曲。' if added else '这首歌已在歌单中。')
    else:
        flash('未能添加该歌曲。')
    return redirect(url_for('playlists.detail', playlist_id=playlist_id))


@bp.post('/<int:playlist_id>/import')
def import_csv(playlist_id):
    get_playlist(playlist_id)
    file = request.files.get('playlist')
    try:
        if not file or not file.filename:
            raise ValueError('请选择 CSV 文件。')
        data = file.stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError('CSV 文件最大支持 1 MiB。')
        reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''), strict=True)
        if not {'song_name', 'artist'}.issubset(reader.fieldnames or ()):
            raise ValueError('CSV 必须包含 song_name 和 artist 两列。')
        rows = []
        for row in reader:
            if len(rows) >= 1000:
                raise ValueError('一次最多导入 1,000 行。')
            title, artist = (row.get(key, '') or '' for key in ('song_name', 'artist'))
            if title.strip():
                rows.append(((row.get('song_id') or '').strip(), title.strip(), artist.strip()))
    except (UnicodeError, csv.Error):
        flash('无法读取 CSV，请检查 UTF-8 编码和文件格式。')
        return redirect(url_for('playlists.detail', playlist_id=playlist_id))
    except ValueError as error:
        flash(str(error))
        return redirect(url_for('playlists.detail', playlist_id=playlist_id))
    connection = load_local()
    matched_count = unresolved = duplicate = 0
    with connection:
        for song_id, title, artist in rows:
            match = catalog.normalize(title), catalog.normalize(artist)
            exact = connection.execute('SELECT * FROM catalog WHERE song_id=?', (song_id,)).fetchone()
            if not exact and match[1]:
                candidates = connection.execute("""
                    SELECT * FROM catalog WHERE name_key=? AND artist_key=? LIMIT 2
                """, match).fetchall()
                exact = candidates[0] if len(candidates) == 1 else None
            fingerprint = hashlib.sha256(repr(match).encode('utf-8')).hexdigest()
            song = dict(exact) if exact else dict(
                song_id='pending:' + fingerprint, song_name=title, artist=artist, genres='')
            if not insert_item(connection, playlist_id, song, bool(exact)):
                duplicate += 1
            elif exact:
                matched_count += 1
            else:
                unresolved += 1
    flash(f'导入完成：匹配 {matched_count} 首，待匹配 {unresolved} 首，重复跳过 {duplicate} 首。')
    return redirect(url_for('playlists.detail', playlist_id=playlist_id))


@bp.post('/<int:playlist_id>/items/<int:item_id>/remove')
def remove(playlist_id, item_id):
    get_playlist(playlist_id)
    connection = db()
    with connection:
        connection.execute('DELETE FROM items WHERE playlist_id=? AND id=?', (playlist_id, item_id))
    return redirect(url_for('playlists.detail', playlist_id=playlist_id))


@bp.post('/<int:playlist_id>/generate')
def generate(playlist_id):
    playlist = get_playlist(playlist_id)
    raw_limit = request.form.get('limit', '')
    if raw_limit not in {str(value) for value in range(1, 101)}:
        flash('推荐数量请输入 1～100 的整数。')
        return redirect(url_for('playlists.detail', playlist_id=playlist_id))
    limit = int(raw_limit)
    connection = load_local()
    seeds = connection.execute('SELECT * FROM items WHERE playlist_id=?', (playlist_id,)).fetchall()
    candidates = connection.execute('SELECT song_id,song_name,artist,genres FROM catalog')
    results = recommend_playlist((dict(song) for song in candidates), seeds, limit)
    if not results:
        flash('没有可推荐的歌曲。请先添加能匹配风格或歌手的歌曲，再试一次。')
        return redirect(url_for('playlists.detail', playlist_id=playlist_id))
    with connection:
        generated = connection.execute('INSERT INTO playlists(name, requested) VALUES (?, ?)',
                                       (playlist['name'] + ' · 推荐', limit)).lastrowid
        for song in results:
            insert_item(connection, generated, song)
    return redirect(url_for('playlists.detail', playlist_id=generated))
