import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web.app import app


class PlaylistTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        songs = root / 'songs.csv'
        songs.write_text('song_id,song_name,artist,genres\n'
                         '01,晴天,Jay Chou,流行|华语流行\n'
                         '02,稻香,Jay Chou,流行\n'
                         '03,另一首,另一位歌手,摇滚\n', encoding='utf-8')
        config = patch.dict(app.config, TESTING=True, PLAYLIST_DB=root / 'test.db', SONG_CSV=songs)
        config.start()
        self.addCleanup(config.stop)
        self.client = app.test_client()
        self.client.get('/playlists/')
        with self.client.session_transaction() as session:
            self.token = session['playlist_csrf']
        self.original = self.post('/playlists/', name='我的收藏').headers['Location']

    def post(self, route, **data):
        return self.client.post(route, data={'csrf': self.token, **data})

    def test_local_search_and_short_recommendation_playlist(self):
        with patch('web.catalog.online_search') as online:
            page = self.client.get(self.original + '?q=晴天').get_data(as_text=True)
        online.assert_not_called()
        self.assertIn('本地曲库结果', page)
        self.post(self.original + '/add', song_id='01')
        self.post(self.original + '/add', song_id='01')
        result = self.post(self.original + '/generate', limit='3')
        self.assertNotEqual(self.original, result.headers['Location'])
        page = self.client.get(result.headers['Location']).get_data(as_text=True)
        self.assertIn('请求 3 首 · 当前 1 首', page)
        self.assertIn('稻香', page)
        self.assertNotIn('晴天', page)
        self.assertIn('晴天', self.client.get(self.original).get_data(as_text=True))

    def test_csv_retains_unmatched_songs(self):
        data = ('song_name,artist\n晴天,Jay Chou\n未知歌曲,未知歌手\n晴天,Jay Chou\n')
        response = self.post(self.original + '/import', playlist=(io.BytesIO(data.encode()), 'list.csv'))
        page = self.client.get(response.headers['Location']).get_data(as_text=True)
        self.assertIn('匹配 1 首，待匹配 1 首，重复跳过 1 首', page)
        self.assertIn('风格分析覆盖 1 / 2', page)
        self.assertIn('未知歌曲', page)

    def test_confirmed_online_result_becomes_searchable_locally(self):
        song = dict(song_id='mb:00000000-0000-0000-0000-000000000001', song_name='补充录音',
                    artist='外部歌手', genres='', source='musicbrainz')
        with patch('web.catalog.online_search', return_value=[song]) as online:
            page = self.client.get(self.original + '?q=补充录音').get_data(as_text=True)
            self.assertIn('MusicBrainz 在线结果', page)
            self.assertIn('补充录音', page)
            online.assert_called_once()
        with patch('web.catalog.online_recording', return_value=song):
            self.assertEqual(302, self.post(self.original + '/add', song_id=song['song_id']).status_code)
        with patch('web.catalog.online_search') as online:
            page = self.client.get(self.original + '?q=补充录音').get_data(as_text=True)
            online.assert_not_called()
        self.assertIn('本地曲库结果', page)
        self.assertIn('暂无风格', page)

    def test_explicit_online_search_keeps_local_and_other_versions(self):
        other = dict(song_id='mb:00000000-0000-0000-0000-000000000001', song_name='晴天',
                     artist='另一位歌手', genres='', source='musicbrainz', release='另一张专辑')
        with patch('web.catalog.online_search', return_value=[other]) as online:
            page = self.client.get(self.original + '?q=晴天&search_online=1').get_data(as_text=True)
        online.assert_called_once()
        self.assertIn('本地曲库结果', page)
        self.assertIn('Jay Chou', page)
        self.assertIn('MusicBrainz 在线结果', page)
        self.assertIn('另一位歌手', page)
        self.assertIn('另一张专辑', page)


if __name__ == '__main__':
    unittest.main()
