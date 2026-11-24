import hashlib
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "graph_recommendation"))

from build_index import build
from prepare_graph import prepare
from recommender.recommend import recommend
from recommender.reviewed_tracks import (CLEAN_REPLACEMENTS, CONFIRMED_MUSIC_IDS,
                                         MIXED_TRACK_IDS, SPOKEN_TRACK_IDS, UNRESOLVED_TRACK_IDS)
from recommender.track_content import is_recommendable_track
from web.app import app
from web.catalog import connect, sync_catalog


class GraphPlaylistTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.songs = root / "songs.csv"
        self.index = root / "index.sqlite3"
        self.user_db = root / "playlists.sqlite3"
        records = [
            ("seed", "Seed", "First artist", ["爵士"], 1, "seed-version"),
            ("variant", "Seed remix", "First artist", ["爵士"], 1, "seed-version"),
            ("b1", "Song B1", "Second artist", ["爵士"], 1, "duplicate"),
            ("b2", "Song B2", "Second artist", ["爵士"], 1, "duplicate"),
            ("c", "Song C", "Third artist", ["爵士"], 1, ""),
            ("zero", "No style evidence", "Unrelated", [], 0, ""),
            ("spoken-title", "Commentary: Wayne Shorter", "First artist", ["爵士"], 1, ""),
            ("spoken-label", "A Conversation", "First artist", ["爵士", "朗读与访谈"], 1, ""),
        ]
        lines = ["song_id,song_name,artist,genres"]
        lines.extend(f'{sid},{name},{artist},{"|".join(genres)}' for sid, name, artist, genres, _, _ in records)
        self.songs.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tracks = [dict(id=sid, name=name, artist=artist, genres=genres, weight=weight, duplicate=group,
                       recommendable=is_recommendable_track(name, genres))
                  for sid, name, artist, genres, weight, group in records]
        nodes, edges, _, _ = prepare(tracks)
        self.assertNotIn("s:spoken-title", edges)
        self.assertNotIn("s:spoken-label", edges)
        edges["a:first artist"].append(("a:second artist", 0.4, "SIMILAR_ARTIST"))
        self.assertFalse(any(kind == "GENRE" for _, _, kind in edges["s:zero"]))
        build(dict(tracks=tracks, nodes=nodes, edges=edges,
                   source_sha256=hashlib.sha256(self.songs.read_bytes()).hexdigest()), self.index)

        original = app.config.copy()
        self.addCleanup(app.config.update, original)
        app.config.update(TESTING=True, SONG_CSV=self.songs, GRAPH_INDEX=self.index, PLAYLIST_DB=self.user_db)
        with closing(connect(self.user_db)) as db, db:
            sync_catalog(db, self.songs)
            db.execute("INSERT INTO playlists(id,name) VALUES (1,'种子歌单')")
            db.execute("INSERT INTO items(playlist_id,song_id,song_name,artist,genres,matched) "
                       "VALUES (1,'seed','Seed','First artist','爵士',1)")
        self.client = app.test_client()
        self.assertEqual(self.client.get("/playlists/1").status_code, 200)
        with self.client.session_transaction() as session:
            self.token = session["playlist_csrf"]

    def generate(self, algorithm):
        return self.client.post("/playlists/1/generate", data={
            "csrf": self.token, "limit": 10, "algorithm": algorithm,
        }, follow_redirects=True).get_data(as_text=True)

    def test_web_comparison_and_duplicate_groups(self):
        classic = self.generate("classic")
        graph = self.generate("graph")
        self.assertIn("Seed remix", classic)
        self.assertIn("种子歌单 · 图推荐", graph)
        self.assertIn("First artist → Second artist → 《Song B", graph)
        self.assertIn("《Seed》 → 爵士 → Song C", graph)
        for page in (classic, graph):
            self.assertNotIn("Commentary: Wayne Shorter", page)
            self.assertNotIn("A Conversation", page)
        with closing(sqlite3.connect(self.user_db)) as db:
            ids = {row[0] for row in db.execute("SELECT song_id FROM items WHERE playlist_id=3")}
        self.assertEqual(len(ids & {"b1", "b2"}), 1)
        self.assertEqual(ids - {"b1", "b2"}, {"c"})

    def test_catalog_mismatch_falls_back(self):
        with self.songs.open("a", encoding="utf-8") as file:
            file.write("new,New,First artist,爵士\n")
        page = self.generate("graph")
        self.assertIn("本次使用经典推荐", page)
        self.assertIn("种子歌单 · 推荐", page)
        self.assertNotIn("Commentary: Wayne Shorter", page)

    def test_speech_markers_do_not_filter_musical_titles(self):
        self.assertTrue(is_recommendable_track("Interview with the Vampire", "摇滚"))
        self.assertTrue(is_recommendable_track("Amish Paradise", "喜剧与单口"))
        self.assertFalse(is_recommendable_track("Take Five (Track Commentary)", "爵士"))
        self.assertFalse(is_recommendable_track("[Interview 2]", "摇滚"))
        self.assertFalse(is_recommendable_track("AC/DC London Interview 1976 & 1977", "摇滚"))
        self.assertFalse(is_recommendable_track("无题", "古典|非音乐音频"))

    def test_reviewed_policy_applies_to_home_ranker(self):
        self.assertEqual((len(SPOKEN_TRACK_IDS), len(MIXED_TRACK_IDS), len(CONFIRMED_MUSIC_IDS),
                          len(UNRESOLVED_TRACK_IDS)), (47, 25, 4, 9))
        cases = [
            {"song_id": track, "song_name": "Generic title", "artist": "Test artist", "genres": "摇滚"}
            for track in sorted(SPOKEN_TRACK_IDS | MIXED_TRACK_IDS | CONFIRMED_MUSIC_IDS | UNRESOLVED_TRACK_IDS)
        ]
        result = recommend(cases, {"artists": ["Test artist"]}, limit=len(cases))
        self.assertEqual({item["song_id"] for item in result}, CONFIRMED_MUSIC_IDS | UNRESOLVED_TRACK_IDS)

    def test_verified_clean_seed_replaces_commentary_for_recommendations_only(self):
        source, clean = next(iter(CLEAN_REPLACEMENTS.items()))
        with self.songs.open("a", encoding="utf-8") as file:
            file.write(f"{source},Mixed recording,Other artist,流行\n{clean},Clean recording,First artist,爵士\n")
        with closing(connect(self.user_db)) as db, db:
            sync_catalog(db, self.songs)
            db.execute("DELETE FROM items WHERE playlist_id=1")
            db.execute("INSERT INTO items(playlist_id,song_id,song_name,artist,genres,matched) "
                       "VALUES (1,?,'Mixed recording','Other artist','流行',1)", (source,))
        page = self.generate("classic")
        self.assertIn("种子歌单 · 推荐", page)
        self.assertIn("Seed remix", page)
        self.assertNotIn("Clean recording", page)
        self.assertNotIn("Mixed recording", page)
        self.assertIn("Mixed recording", self.client.get("/playlists/1").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
