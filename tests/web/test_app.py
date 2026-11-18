import unittest
from unittest.mock import patch
from web.app import app, mock_recommend, SAMPLE

class WebTests(unittest.TestCase):
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
