"""Tests for the v2 recommender and the strategy switch in recommend()."""

import json
import unittest

from recommender.recommend import recommend
from recommender.recommend_v2 import recommend_from_seeds, recommend_v2

SONGS = [
    {"song_id": "01", "song_name": "晴天", "artist": "周杰伦", "genres": "流行|华语"},
    {"song_id": "02", "song_name": "夜曲", "artist": "周杰伦", "genres": "流行"},
    {"song_id": "03", "song_name": "七里香", "artist": "周杰伦", "genres": "华语"},
    {"song_id": "04", "song_name": "稻香", "artist": "周杰伦", "genres": "民谣|流行"},
    {"song_id": "05", "song_name": "平凡之路", "artist": "朴树", "genres": "民谣"},
    {"song_id": "06", "song_name": "蓝莲花", "artist": "许巍", "genres": "摇滚|民谣"},
    {"song_id": "07", "song_name": "夜空中最亮的星", "artist": "逃跑计划", "genres": "摇滚"},
    {"song_id": "08", "song_name": "无题", "artist": "", "genres": ""},
]


def ids(results):
    return [item["song_id"] for item in results]


class StrategySwitchTests(unittest.TestCase):
    def test_default_strategy_is_still_v1(self):
        result = recommend(SONGS, {"genres": ["流行"]})
        self.assertEqual(ids(result), ["01", "02", "04"])
        self.assertEqual([item["score"] for item in result], [3, 3, 3])

    def test_explicit_v1_is_unchanged(self):
        self.assertEqual(ids(recommend(SONGS, {"genres": ["流行"]}, strategy="v1")), ["01", "02", "04"])

    def test_unknown_strategy_is_rejected(self):
        with self.assertRaises(ValueError):
            recommend(SONGS, {"genres": ["流行"]}, strategy="v3")

    def test_v2_reason_mentions_numbers(self):
        result = recommend(SONGS, {"genres": ["流行", "华语"]}, limit=1, strategy="v2")
        self.assertEqual(result[0]["song_id"], "01")
        self.assertIn("覆盖 2/2", result[0]["reason"])
        self.assertIn("+3.00", result[0]["reason"])

    def test_v2_partial_reason_shows_fraction(self):
        result = recommend_v2(SONGS, {"genres": ["流行", "华语"]}, limit=10)
        item = [row for row in result if row["song_id"] == "03"][0]
        self.assertIn("覆盖 1/2", item["reason"])


class SoftGenreCoverageTests(unittest.TestCase):
    def test_full_coverage_beats_partial(self):
        result = recommend_v2(SONGS, {"genres": ["流行", "华语"]}, limit=3)
        self.assertEqual(result[0]["song_id"], "01")
        self.assertGreater(result[0]["score"], result[1]["score"])

    def test_partial_coverage_scores_between_zero_and_full(self):
        partial = [item for item in recommend_v2(SONGS, {"genres": ["流行", "华语"]}, limit=10)
                   if item["song_id"] == "03"][0]
        # 1.50 from the single covered genre plus a bounded popularity bonus.
        self.assertGreaterEqual(partial["score"], 1.5)
        self.assertLess(partial["score"], 2.5)

    def test_case_insensitive_matching(self):
        songs = [
            {"song_id": "01", "song_name": "A", "artist": "X", "genres": "Pop"},
            {"song_id": "02", "song_name": "B", "artist": "Y", "genres": "Rock"},
        ]
        self.assertEqual(ids(recommend_v2(songs, {"genres": ["pop"]})), ["01"])

    def test_fullwidth_and_spacing_are_normalised(self):
        songs = [
            {"song_id": "01", "song_name": "A", "artist": "X", "genres": " 流行 "},
            {"song_id": "02", "song_name": "B", "artist": "Y", "genres": "摇滚"},
        ]
        self.assertEqual(ids(recommend_v2(songs, {"genres": ["流行"]})), ["01"])

    def test_unmatched_preference_returns_empty(self):
        self.assertEqual(recommend_v2(SONGS, {"genres": ["电子"]}), [])


class ArtistAndPopularityTests(unittest.TestCase):
    def test_artist_hit_adds_two_points(self):
        result = recommend_v2(SONGS, {"genres": ["民谣"], "artists": ["周杰伦"]}, limit=10)
        top = result[0]
        self.assertEqual(top["song_id"], "04")
        self.assertIn("歌手匹配：周杰伦（+2.00）", top["reason"])

    def test_popularity_breaks_ties_deterministically(self):
        songs = [
            {"song_id": "01", "song_name": "A", "artist": "热门歌手", "genres": "流行"},
            {"song_id": "02", "song_name": "B", "artist": "热门歌手", "genres": "流行"},
            {"song_id": "03", "song_name": "C", "artist": "冷门歌手", "genres": "流行"},
        ]
        result = recommend_v2(songs, {"genres": ["流行"]}, limit=3)
        self.assertEqual(ids(result), ["01", "02", "03"])
        self.assertGreater(result[0]["score"], result[2]["score"])

    def test_blank_preference_falls_back_to_default(self):
        result = recommend_v2(SONGS, {"artists": [""]})
        self.assertEqual(len(result), len(SONGS))
        self.assertTrue(all(item["score"] == 0 for item in result))

    def test_bare_string_preferences_are_accepted(self):
        result = recommend_v2(SONGS, {"genres": "流行"})
        self.assertEqual(set(ids(result)), {"01", "02", "04"})


class DefaultAndBoundaryTests(unittest.TestCase):
    def test_default_follows_popularity_then_id(self):
        result = recommend_v2(SONGS, {})
        self.assertEqual(len(result), len(SONGS))
        self.assertTrue(all(item["score"] == 0 for item in result))
        self.assertTrue(all(item["reason"].startswith("默认推荐") for item in result))

    def test_non_positive_limit_returns_empty(self):
        self.assertEqual(recommend_v2(SONGS, {"genres": ["流行"]}, limit=0), [])
        self.assertEqual(recommend_v2(SONGS, {"genres": ["流行"]}, limit=-3), [])

    def test_limit_caps_result_without_backfilling(self):
        self.assertEqual(len(recommend_v2(SONGS, {"genres": ["流行"]}, limit=2)), 2)

    def test_invalid_limit_type_is_rejected(self):
        with self.assertRaises(TypeError):
            recommend_v2(SONGS, {"genres": ["流行"]}, limit="10")

    def test_diversity_out_of_range_is_rejected(self):
        with self.assertRaises(ValueError):
            recommend_v2(SONGS, {"genres": ["流行"]}, diversity=1.5)


class ExclusionAndShapeTests(unittest.TestCase):
    def test_exclude_ids_removes_tracks(self):
        result = recommend_v2(SONGS, {"genres": ["流行"]}, exclude_ids=["01"])
        self.assertNotIn("01", ids(result))
        self.assertEqual(set(ids(result)), {"02", "04"})

    def test_duplicate_ids_are_skipped(self):
        songs = SONGS + [dict(SONGS[0])]
        result = recommend_v2(songs, {"genres": ["流行"]}, limit=10)
        self.assertEqual(len(result), len({item["song_id"] for item in result}))

    def test_missing_name_is_skipped(self):
        songs = [{"song_id": "01", "song_name": "", "artist": "X", "genres": "流行"},
                 {"song_id": "02", "song_name": "B", "artist": "Y", "genres": "流行"}]
        self.assertEqual(ids(recommend_v2(songs, {"genres": ["流行"]})), ["02"])

    def test_inputs_are_not_mutated(self):
        songs = [dict(song) for song in SONGS] + [dict(SONGS[0])]
        snapshot = json.loads(json.dumps(songs))
        preferences = {"genres": ["流行"], "artists": ["周杰伦"]}
        recommend_v2(songs, preferences)
        self.assertEqual(songs, snapshot)
        self.assertEqual(preferences, {"genres": ["流行"], "artists": ["周杰伦"]})

    def test_every_result_has_the_six_contract_fields(self):
        result = recommend_v2(SONGS, {"genres": ["流行"]})
        for item in result:
            self.assertEqual(set(item), {"song_id", "song_name", "artist", "genres", "score", "reason"})
            self.assertIsInstance(item["score"], float)

    def test_same_input_gives_same_output(self):
        first = recommend_v2(SONGS, {"genres": ["流行", "民谣"]}, limit=5)
        second = recommend_v2(SONGS, {"genres": ["流行", "民谣"]}, limit=5)
        self.assertEqual(first, second)


class DiversityTests(unittest.TestCase):
    def test_high_diversity_spreads_genres(self):
        songs = [
            {"song_id": "A1", "song_name": "双修", "artist": "歌手A", "genres": "流行|摇滚"},
            {"song_id": "B1", "song_name": "流行一", "artist": "歌手B", "genres": "流行"},
            {"song_id": "B2", "song_name": "流行二", "artist": "歌手C", "genres": "流行"},
            {"song_id": "B3", "song_name": "流行三", "artist": "歌手D", "genres": "流行"},
            {"song_id": "C1", "song_name": "摇滚一", "artist": "歌手E", "genres": "摇滚"},
            {"song_id": "C2", "song_name": "摇滚二", "artist": "歌手F", "genres": "摇滚"},
        ]
        plain = recommend_v2(songs, {"genres": ["流行", "摇滚"]}, limit=3, diversity=0.0)
        spread = recommend_v2(songs, {"genres": ["流行", "摇滚"]}, limit=3, diversity=1.0)
        self.assertEqual(ids(plain)[0], "A1")
        self.assertEqual(ids(plain)[1:3], ["B1", "B2"])
        self.assertEqual(ids(spread)[0], "A1")
        self.assertIn("C1", ids(spread))

    def test_diversity_zero_keeps_pure_score_order(self):
        result = recommend_v2(SONGS, {"genres": ["流行"]}, limit=3, diversity=0.0)
        scores = [item["score"] for item in result]
        self.assertEqual(scores, sorted(scores, reverse=True))


class SeedRecommendationTests(unittest.TestCase):
    def test_seeds_are_excluded_from_results(self):
        seeds = [SONGS[0]]
        result = recommend_from_seeds(SONGS, seeds, limit=5)
        self.assertNotIn("01", ids(result))

    def test_profile_follows_genre_counts(self):
        seeds = [SONGS[0], {"song_id": "10", "song_name": "双料", "artist": "某人", "genres": "民谣"}]
        result = recommend_from_seeds(SONGS, seeds, limit=3)
        self.assertTrue(result)
        self.assertTrue(all(item["reason"].startswith("来自原歌单") for item in result))

    def test_empty_seeds_return_empty(self):
        self.assertEqual(recommend_from_seeds(SONGS, [], limit=5), [])

    def test_seed_results_keep_six_fields(self):
        result = recommend_from_seeds(SONGS, [SONGS[0]], limit=3)
        for item in result:
            self.assertEqual(set(item), {"song_id", "song_name", "artist", "genres", "score", "reason"})


if __name__ == "__main__":
    unittest.main()
