import unittest
import builtins
import csv
import tempfile
from pathlib import Path
from unittest.mock import patch
from web.app import app, mock_recommend, SAMPLE

class WebTests(unittest.TestCase):
    def test_large_artist_list_and_manual_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / 'data' / 'processed'
            base.mkdir(parents=True)
            with (base / 'songs.csv').open('w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['song_id', 'song_name', 'artist', 'genres'])
                writer.writerows((f'{i:03}', f'歌曲{i}', f'歌手{i:03}', '流行') for i in range(120))
            with patch('web.app.ROOT', Path(directory)):
                client = app.test_client()
                page = client.get('/').get_data(as_text=True)
                self.assertEqual(page.count('name="artists"'), 100)
                self.assertNotIn('value="歌手119"', page)
                selected = client.post('/', data={'artist_search': '歌手119'}).get_data(as_text=True)
                self.assertIn('歌曲119', selected)
                self.assertIn('歌手匹配', selected)
                self.assertIn('value="歌手119"', selected)

    def test_missing_recommender_uses_mock(self):
        original_import = builtins.__import__
        def importing(name, *args, **kwargs):
            if name == 'recommender.recommend':
                raise ModuleNotFoundError("No module named 'recommender'", name='recommender')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=importing):
            response = app.test_client().get('/')
        self.assertIn('模拟推荐算法', response.get_data(as_text=True))

    def test_broken_recommender_import_is_not_silenced(self):
        original_import = builtins.__import__
        for error in (ModuleNotFoundError("No module named 'dependency'", name='dependency'),
                      ImportError('cannot import recommend')):
            def importing(name, *args, **kwargs):
                if name == 'recommender.recommend':
                    raise error
                return original_import(name, *args, **kwargs)
            with self.subTest(error=error), patch('builtins.__import__', side_effect=importing), patch.dict(app.config, TESTING=True):
                with self.assertRaises(type(error)):
                    app.test_client().get('/')

    def test_mock_scoring_and_empty(self):
        result = mock_recommend(SAMPLE, {'genres': ['流行', '流行'], 'artists': ['示例歌手甲']})
        self.assertEqual(result[0]['score'], 5)
        self.assertEqual(mock_recommend(SAMPLE, {'genres': ['不存在'], 'artists': []}), [])
    def test_missing_data_page(self):
        with patch('web.app.ROOT') as root:
            root.__truediv__.return_value.__truediv__.return_value.__truediv__.side_effect = FileNotFoundError('missing')
            response = app.test_client().get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn('虚构演示样例', response.get_data(as_text=True))

if __name__ == '__main__': unittest.main()
