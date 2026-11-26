"""Replay the reviewed-track cases against a full catalog and graph index."""

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from recommender.graph_playlist import recommend_playlist_graph
from recommender.playlist import labels, recommend_playlist
from recommender.recommend import recommend
from recommender.reviewed_tracks import (CLEAN_REPLACEMENTS, CONFIRMED_MUSIC_IDS,
                                         MIXED_TRACK_IDS, SPOKEN_TRACK_IDS, UNRESOLVED_TRACK_IDS)
from recommender.track_content import is_recommendable_track
from web.catalog import connect, sync_catalog


def check_results(results, blocked, limit):
    ids = {song["song_id"] for song in results}
    assert len(ids) == len(results) <= limit
    assert ids.isdisjoint(blocked)
    assert all(is_recommendable_track(song["song_name"], song["genres"], song["song_id"])
               for song in results)
    return ids


def audit(songs_path, index_path):
    with songs_path.open(encoding="utf-8-sig", newline="") as source:
        songs = {song["song_id"]: song for song in csv.DictReader(source)}
    blocked = SPOKEN_TRACK_IDS | MIXED_TRACK_IDS
    reviewed = blocked | CONFIRMED_MUSIC_IDS | UNRESOLVED_TRACK_IDS
    assert reviewed <= songs.keys()
    assert all(is_recommendable_track(songs[sid]["song_name"], songs[sid]["genres"], sid)
               for sid in CONFIRMED_MUSIC_IDS | UNRESOLVED_TRACK_IDS)
    for target in CLEAN_REPLACEMENTS.values():
        assert is_recommendable_track(songs[target]["song_name"], songs[target]["genres"], target)
    names = defaultdict(list)
    styles = defaultdict(set)
    for song in songs.values():
        names[song["artist"]].append(song)
        for genre in labels(song["genres"]):
            styles[genre].add(song["song_id"])
    artists = sorted({songs[sid]["artist"] for sid in reviewed if songs[sid]["artist"]})
    seeds_count = 0
    graph_count = 0
    with closing(connect(Path(":memory:"))) as catalog, closing(sqlite3.connect(index_path)) as graph:
        metadata = dict(graph.execute("SELECT * FROM info"))
        assert metadata["schema"] == "3"
        assert int(metadata["song_count"]) == len(songs)
        assert graph.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        placeholders = ",".join("?" for _ in blocked)
        for table in ("features", "neighbors"):
            assert graph.execute(f"SELECT count(*) FROM {table} WHERE track IN ({placeholders})",
                                 tuple(blocked)).fetchone()[0] == 0
        sync_catalog(catalog, songs_path)
        for artist in artists:
            check_results(recommend(names[artist], {"artists": [artist]}, 10), blocked, 10)
            eligible = [song for song in names[artist] if song["genres"] and
                        not re.search(r"\b(?:commentary|interview)\b", song["song_name"], re.I) and
                        is_recommendable_track(song["song_name"], song["genres"], song["song_id"])]
            if not eligible:
                continue
            source = min(eligible, key=lambda track: track["song_id"])
            seeds = [{**source, "matched": True}]
            pool = {song["song_id"] for song in names[artist]}
            for genre in labels(source["genres"]):
                pool.update(styles[genre])
            classic = recommend_playlist((songs[sid] for sid in pool), seeds, 100)
            graph_results = recommend_playlist_graph(catalog, seeds, 100, index_path, songs_path)
            assert source["song_id"] not in check_results(classic, blocked, 100)
            assert source["song_id"] not in check_results(graph_results, blocked, 100)
            seeds_count += 1
            graph_count += bool(graph_results)
        assert graph_count > 0
    return {
        "catalog_songs": len(songs), "index_backend": metadata["backend"],
        "reviewed_tracks": len(reviewed), "blocked_tracks": len(blocked),
        "clean_recording_mappings": len(CLEAN_REPLACEMENTS),
        "home_artist_cases": len(artists),
        "playlist_cases": seeds_count, "playlist_graph_cases_with_results": graph_count,
        "blocked_tracks_in_recommendations": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("songs", type=Path)
    parser.add_argument("index", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    text = json.dumps(audit(args.songs, args.index), ensure_ascii=False, indent=2)
    args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
