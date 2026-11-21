"""Contract tests for recommender.recommend.

Self-contained: fictional fixtures only, standard library only.
Run from the package root:
    python -m unittest discover -s tests/recommender -v
"""

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from recommender.recommend import recommend  # noqa: E402


SAMPLE = [
    {"song_id": "01", "song_name": "测试歌曲", "artist": "测试歌手", "genres": "流行|民谣"},
    {"song_id": "02", "song_name": "另一首", "artist": "另一位歌手", "genres": "摇滚"},
    {"song_id": "03", "song_name": "第三首", "artist": "测试歌手", "genres": "民谣"},
    {"song_id": "04", "song_name": "第四首", "artist": "第三位歌手", "genres": "电子|流行"},
    {"song_id": "05", "song_name": "第五首", "artist": "", "genres": ""},
]


def by_id(results):
    return {item["song_id"]: item for item in results}


class ContractExampleTests(unittest.TestCase):
    def test_genre_and_artist_match_scores_five(self):
        results = recommend(SAMPLE, {"genres": ["流行"], "artists": ["测试歌手"]})
        top = results[0]
        self.assertEqual(top["song_id"], "01")
        self.assertEqual(top["score"], 5)
        self.assertIn("风格匹配：流行", top["reason"])
        self.assertIn("歌手匹配：测试歌手", top["reason"])

    def test_duplicate_genre_preference_does_not_double_score(self):
        results = recommend(SAMPLE, {"genres": ["流行", "流行"]})
        self.assertEqual(by_id(results)["01"]["score"], 3)

    def test_duplicate_genre_tags_in_song_do_not_double_score(self):
        songs = [{"song_id": "01", "song_name": "重复标签", "artist": "", "genres": "流行|流行| 流行 "}]
        results = recommend(songs, {"genres": ["流行"]})
        self.assertEqual(results[0]["score"], 3)

    def test_multi_genre_match_adds_three_each(self):
        results = recommend(SAMPLE, {"genres": ["流行", "民谣"]})
        self.assertEqual(by_id(results)["01"]["score"], 6)
        self.assertIn("风格匹配：民谣、流行", by_id(results)["01"]["reason"])


class DefaultRecommendationTests(unittest.TestCase):
    def test_no_preferences_returns_default_sorted_by_song_id(self):
        results = recommend(SAMPLE, {"genres": [], "artists": []})
        self.assertEqual([r["song_id"] for r in results], ["01", "02", "03", "04", "05"])
        for item in results:
            self.assertEqual(item["score"], 0)
            self.assertIn("默认推荐", item["reason"])

    def test_missing_preference_keys_are_treated_as_empty(self):
        self.assertEqual(recommend(SAMPLE, {}), recommend(SAMPLE, {"genres": [], "artists": []}))

    def test_default_limit_is_ten(self):
        songs = [
            {"song_id": f"{i:02}", "song_name": f"歌曲{i}", "artist": "", "genres": ""}
            for i in range(1, 13)
        ]
        results = recommend(songs, {"genres": [], "artists": []})
        self.assertEqual(len(results), 10)
        self.assertEqual(results[0]["song_id"], "01")
        self.assertEqual(results[-1]["song_id"], "10")
        self.assertIn("默认推荐", results[0]["reason"])


class NoMatchAndBoundaryTests(unittest.TestCase):
    def test_no_match_returns_empty_list(self):
        self.assertEqual(recommend(SAMPLE, {"genres": ["不存在的风格"]}), [])
        self.assertEqual(recommend(SAMPLE, {"artists": ["不存在的歌手"]}), [])

    def test_skips_records_without_id_or_name(self):
        songs = [
            {"song_id": "", "song_name": "无ID", "artist": "测试歌手", "genres": "流行"},
            {"song_id": "01", "song_name": "", "artist": "测试歌手", "genres": "流行"},
            {"song_id": "02", "song_name": "合法", "artist": "测试歌手", "genres": "流行"},
        ]
        self.assertEqual([r["song_id"] for r in recommend(songs, {"genres": ["流行"]})], ["02"])

    def test_limit_zero_and_negative_return_empty(self):
        self.assertEqual(recommend(SAMPLE, {"genres": ["流行"]}, limit=0), [])
        self.assertEqual(recommend(SAMPLE, {"genres": ["流行"]}, limit=-3), [])

    def test_limit_caps_without_padding(self):
        results = recommend(SAMPLE, {"genres": ["流行"]}, limit=1)
        self.assertEqual(len(results), 1)
        results = recommend(SAMPLE, {"genres": ["流行"]}, limit=99)
        self.assertEqual(len(results), 2)

    def test_non_positive_scores_are_excluded(self):
        results = recommend(SAMPLE, {"genres": ["流行"]})
        self.assertTrue(all(item["score"] > 0 for item in results))

    def test_only_positive_results_are_never_padded(self):
        self.assertEqual(len(recommend(SAMPLE, {"artists": ["测试歌手"]}, limit=10)), 2)


class OrderingTests(unittest.TestCase):
    def test_ties_sort_by_song_id_string_order(self):
        songs = [
            {"song_id": "10", "song_name": "十", "artist": "同一歌手", "genres": "流行"},
            {"song_id": "2", "song_name": "二", "artist": "同一歌手", "genres": "流行"},
            {"song_id": "01", "song_name": "一", "artist": "同一歌手", "genres": "流行"},
        ]
        results = recommend(songs, {"genres": ["流行", "民谣"]})
        self.assertEqual([r["song_id"] for r in results], ["01", "10", "2"])
        self.assertEqual({r["score"] for r in results}, {3})

    def test_higher_score_sorts_before_id(self):
        songs = [
            {"song_id": "01", "song_name": "低分", "artist": "", "genres": "流行"},
            {"song_id": "99", "song_name": "高分", "artist": "目标歌手", "genres": "流行|民谣"},
        ]
        results = recommend(songs, {"genres": ["流行", "民谣"], "artists": ["目标歌手"]})
        self.assertEqual([r["song_id"] for r in results], ["99", "01"])
        self.assertEqual(results[0]["score"], 8)


class NormalisationTests(unittest.TestCase):
    def test_case_is_not_folded(self):
        songs = [{"song_id": "01", "song_name": "大小写", "artist": "Pop", "genres": "Pop"}]
        self.assertEqual(recommend(songs, {"genres": ["pop"]}), [])
        self.assertEqual(recommend(songs, {"artists": ["pop"]}), [])

    def test_whitespace_is_trimmed_for_matching(self):
        songs = [{"song_id": "01", "song_name": "空格", "artist": " 测试歌手 ", "genres": " 流行 | 民谣 "}]
        results = recommend(songs, {"genres": [" 流行 "], "artists": ["测试歌手 "]})
        self.assertEqual(results[0]["score"], 5)

    def test_empty_artist_never_matches_empty_selection(self):
        songs = [{"song_id": "01", "song_name": "空歌手", "artist": "", "genres": ""}]
        self.assertEqual(recommend(songs, {"genres": [], "artists": [""]}), recommend(songs, {}))

    def test_empty_song_genres_do_not_match(self):
        songs = [{"song_id": "01", "song_name": "无风格", "artist": "", "genres": ""}]
        self.assertEqual(recommend(songs, {"genres": ["流行", ""]}), [])


class ImmutabilityAndShapeTests(unittest.TestCase):
    def test_input_is_not_modified(self):
        songs = copy.deepcopy(SAMPLE)
        before = copy.deepcopy(songs)
        preferences = {"genres": ["流行"], "artists": ["测试歌手"]}
        prefs_before = copy.deepcopy(preferences)
        recommend(songs, preferences)
        self.assertEqual(songs, before)
        self.assertEqual(preferences, prefs_before)
        self.assertNotIn("score", songs[0])

    def test_results_are_new_objects_with_all_fields(self):
        results = recommend(SAMPLE, {"genres": ["流行"]})
        for item in results:
            self.assertEqual(
                set(item.keys()),
                {"song_id", "song_name", "artist", "genres", "score", "reason"},
            )
            self.assertIsInstance(item["score"], int)
            self.assertTrue(item["reason"])

    def test_returned_fields_keep_string_type(self):
        songs = [{"song_id": "01", "song_name": "类型", "artist": None, "genres": "流行"}]
        results = recommend(songs, {"genres": ["流行"]})
        self.assertEqual(results[0]["artist"], "")


class SampleFileTests(unittest.TestCase):
    def test_fictional_sample_file_runs(self):
        path = Path(__file__).with_name("sample_songs.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("虚构", data["notice"])
        results = recommend(data["songs"], {"genres": ["流行"], "artists": ["测试歌手"]})
        self.assertEqual(results[0]["song_id"], "01")
        self.assertEqual(results[0]["score"], 5)


if __name__ == "__main__":
    unittest.main()
