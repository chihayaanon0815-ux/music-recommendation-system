# -*- coding: utf-8 -*-
"""数据采集与清洗测试（不访问网络）。

运行：python -m unittest discover -s data_processing/tests -v
清洗测试需要 PySpark + Java 17，首次启动约需数十秒。
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "data_processing"))

import fetch_musicbrainz as fetch  # noqa: E402
import download_spotify as spotify  # noqa: E402

SAMPLE = os.path.join(REPO_ROOT, "data", "sample", "songs_sample.csv")
CLEAN = os.path.join(REPO_ROOT, "data_processing", "clean_songs.py")
VALIDATE = os.path.join(REPO_ROOT, "data_processing", "validate_outputs.py")


def read_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FetchHelpersTest(unittest.TestCase):
    def test_artist_display_joins_joinphrase(self):
        rec = {
            "artist-credit": [
                {"name": "甲", "joinphrase": " & "},
                {"name": "乙", "joinphrase": ""},
            ]
        }
        self.assertEqual(fetch.artist_display(rec), "甲 & 乙")

    def test_artist_display_handles_missing(self):
        self.assertEqual(fetch.artist_display({}), "")
        self.assertEqual(fetch.artist_display({"artist-credit": []}), "")

    def test_genre_map_unique_and_zh(self):
        english = [en for en, _ in fetch.GENRE_MAP]
        chinese = [zh for _, zh in fetch.GENRE_MAP]
        self.assertEqual(len(english), len(set(english)))
        self.assertEqual(len(chinese), len(set(chinese)))
        self.assertIn(("pop", "流行"), fetch.GENRE_MAP)

    def test_compute_quotas_sums_to_total(self):
        for total in (100, 480, 5000):
            quotas = fetch.compute_quotas(total)
            self.assertEqual(sum(quotas.values()), total)
            self.assertEqual(set(quotas), {en for en, _ in fetch.GENRE_MAP})

    def test_compute_quotas_positive_and_weighted(self):
        quotas = fetch.compute_quotas(5000)
        self.assertTrue(all(value > 0 for value in quotas.values()))
        # 权重相近的风格配额最多相差 1（最大余数法）
        ordered = sorted(quotas, key=lambda en: fetch.GENRE_WEIGHTS[en])
        for lower, higher in zip(ordered, ordered[1:]):
            if fetch.GENRE_WEIGHTS[lower] == fetch.GENRE_WEIGHTS[higher]:
                self.assertLessEqual(abs(quotas[lower] - quotas[higher]), 1)


class DownloadMappingTest(unittest.TestCase):
    def test_sanitize_quotes_and_newlines(self):
        self.assertEqual(spotify.sanitize('He said "hi"'), "He said 'hi'")
        self.assertEqual(spotify.sanitize("a\nb\tc"), "a b c")
        self.assertEqual(spotify.sanitize("  x  "), "x")

    def test_genre_map_complete_and_unique(self):
        path = os.path.join(REPO_ROOT, "data_processing", "genre_map_zh.csv")
        mapping = spotify.load_genre_map(path)
        self.assertEqual(len(mapping), 114)
        self.assertTrue(all(info["zh"] for info in mapping.values()))
        self.assertTrue(all(info["group"] for info in mapping.values()))
        self.assertEqual(len({info["zh"] for info in mapping.values()}), len(mapping))
        self.assertEqual(mapping["pop"]["zh"], "流行")
        self.assertEqual(mapping["hip-hop"]["zh"], "嘻哈")
        self.assertEqual(mapping["mandopop"]["group"], "流行|华语流行")
        groups = {group for info in mapping.values() for group in info["group"].split("|")}
        self.assertEqual(len(groups), 31)

    def test_map_rows_joins_artists_and_keeps_genre(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False) as handle:
            handle.write(
                "track_id,track_name,artists,track_genre,popularity\n"
                'id1,"Song ""Q""",A;B,pop,50\n'
                "id2,Other,,rock,0\n"
            )
            path = handle.name
        try:
            rows = list(
                spotify.map_rows(
                    path,
                    {
                        "pop": {"zh": "流行", "group": "流行"},
                        "rock": {"zh": "摇滚", "group": "摇滚"},
                    },
                )
            )
        finally:
            os.unlink(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["song_id"], "id1")
        self.assertEqual(rows[0]["song_name"], "Song 'Q'")
        self.assertEqual(rows[0]["artist"], "A & B")
        self.assertEqual(rows[0]["genres"], "流行")
        self.assertEqual(rows[0]["genres_zh"], "流行")
        self.assertEqual(rows[0]["genres_en"], "pop")
        self.assertEqual(rows[1]["artist"], "")
        self.assertEqual(rows[1]["genres"], "摇滚")


class CleanSongsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="clean-test-")
        cls.raw = os.path.join(cls.tmp, "raw.csv")
        with open(cls.raw, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["song_id", "song_name", "artist", "genres", "extra"])
            writer.writerow([" 10 ", " 歌曲甲 ", " 歌手A ", " 流行 | 民谣 ", "x"])
            writer.writerow(["11", "歌曲乙", "歌手B", "流行"])
            writer.writerow(["11", "歌曲乙重复", "歌手B", "摇滚"])       # 重复 ID，排序后保留 song_name 较小者
            writer.writerow(["12", "歌曲丙", "", "  "])                # 空歌手、空风格
            writer.writerow(["", "无 ID", "歌手C", "流行"])            # 空 ID 剔除
            writer.writerow(["13", " ", "歌手D", "流行"])              # 空歌名剔除
            writer.writerow(["14", "歌曲丁", "歌手E", "民谣|民谣|流行 |"])  # 重复标签、空格
            writer.writerow(["15", "歌名,含逗号", "歌手F", "流行"])  # 逗号字段需正确解析
        cls.out = os.path.join(cls.tmp, "out")
        cls.metrics = os.path.join(cls.tmp, "metrics.json")
        cls.result = subprocess.run(
            [sys.executable, CLEAN, "--input", cls.raw, "--out-dir", cls.out, "--metrics", cls.metrics],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        cls.songs = read_rows(os.path.join(cls.out, "songs.csv")) if os.path.exists(os.path.join(cls.out, "songs.csv")) else []
        cls.counts = read_rows(os.path.join(cls.out, "genre_counts.csv")) if os.path.exists(os.path.join(cls.out, "genre_counts.csv")) else []

    def test_exit_code_and_diagnostics(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)

    def test_header_contract(self):
        with open(os.path.join(self.out, "songs.csv"), encoding="utf-8") as handle:
            self.assertEqual(handle.readline().strip(), "song_id,song_name,artist,genres")
        with open(os.path.join(self.out, "genre_counts.csv"), encoding="utf-8") as handle:
            self.assertEqual(handle.readline().strip(), "genre,count")

    def test_dedup_and_trim(self):
        self.assertEqual([row["song_id"] for row in self.songs], ["10", "11", "12", "14", "15"])
        self.assertEqual(self.songs[0]["song_name"], "歌曲甲")
        self.assertEqual(self.songs[0]["artist"], "歌手A")
        self.assertEqual(self.songs[0]["genres"], "民谣|流行")
        self.assertEqual(self.songs[1]["song_name"], "歌曲乙")
        self.assertEqual(self.songs[1]["artist"], "歌手B")
        # 重复 ID 的标签取并集
        self.assertEqual(self.songs[1]["genres"], "摇滚|流行")

    def test_comma_field_preserved(self):
        row = next(item for item in self.songs if item["song_id"] == "15")
        self.assertEqual(row["song_name"], "歌名,含逗号")
        self.assertEqual(row["artist"], "歌手F")

    def test_empty_cases(self):
        row = next(item for item in self.songs if item["song_id"] == "12")
        self.assertEqual(row["artist"], "")
        self.assertEqual(row["genres"], "")

    def test_genre_normalization(self):
        row = next(item for item in self.songs if item["song_id"] == "14")
        self.assertEqual(row["genres"], "民谣|流行")

    def test_genre_counts(self):
        counts = {row["genre"]: int(row["count"]) for row in self.counts}
        self.assertEqual(counts, {"流行": 4, "民谣": 2, "摇滚": 1})

    def test_metrics(self):
        import json

        with open(self.metrics, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["input_rows"], 8)
        self.assertEqual(data["songs_rows"], 5)
        self.assertEqual(data["dropped_blank_id_or_name"], 2)
        self.assertEqual(data["duplicate_song_id_rows"], 1)

    def test_missing_column_rejected(self):
        bad = os.path.join(self.tmp, "bad.csv")
        with open(bad, "w", encoding="utf-8", newline="") as handle:
            handle.write("song_id,song_name\n1,只有两列\n")
        result = subprocess.run(
            [sys.executable, CLEAN, "--input", bad, "--out-dir", os.path.join(self.tmp, "bad-out")],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        self.assertEqual(result.returncode, 2)

    def test_validate_outputs_passes(self):
        result = subprocess.run(
            [sys.executable, VALIDATE, "--dir", self.out],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sample_file_contract(self):
        rows = read_rows(SAMPLE)
        self.assertGreaterEqual(len(rows), 6)
        self.assertEqual(set(rows[0].keys()), {"song_id", "song_name", "artist", "genres"})
        self.assertEqual(len({row["song_id"] for row in rows}), len(rows))
        self.assertTrue(any("|" in row["genres"] for row in rows))
        self.assertTrue(any(row["genres"] == "" for row in rows))
        self.assertTrue(any("&" in row["artist"] for row in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
