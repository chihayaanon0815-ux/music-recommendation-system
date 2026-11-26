"""Measure and compare the two playlist algorithms on fixed artist scenarios."""

import argparse
import csv
import json
import sqlite3
import statistics
import sys
from contextlib import closing
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from recommender.graph_playlist import recommend_playlist_graph
from recommender.playlist import recommend_playlist
from recommender.track_content import is_recommendable_track
from web.catalog import connect, sync_catalog


def evaluate(index, songs, report, demo, reference=None):
    scenarios = (
        ("华语流行", ("周杰伦", "蔡依林", "孙燕姿")),
        ("摇滚", ("The Beatles", "Queen", "Pink Floyd")),
        ("爵士", ("Miles Davis", "John Coltrane", "Bill Evans")),
    )
    fixed_seeds = {} if reference is None else {
        case["scenario"]: case["seeds"]
        for case in json.loads(reference.read_text(encoding="utf-8"))["scenarios"]
    }
    outputs = []
    with closing(connect(Path(":memory:"))) as db, closing(sqlite3.connect(index)) as graph:
        started = perf_counter()
        sync_catalog(db, songs)
        sync_seconds = perf_counter() - started
        metadata = dict(graph.execute("SELECT key, value FROM info"))
        full_count = db.execute("SELECT count(*) FROM catalog").fetchone()[0]
        group_for = dict(graph.execute("SELECT id, duplicate_group FROM tracks WHERE duplicate_group != ''"))
        for name, artists in scenarios:
            seeds = fixed_seeds.get(name, []).copy()
            if name not in fixed_seeds:
                for artist in artists:
                    row = graph.execute(
                        "SELECT id FROM tracks WHERE artist=? AND genres!='' AND weight=1 "
                        "ORDER BY CASE WHEN genres LIKE '%华语流行%' THEN 0 ELSE 1 END, "
                        "length(id), id LIMIT 1", (artist.casefold(),),
                    ).fetchone()
                    if row:
                        seed = db.execute("SELECT * FROM catalog WHERE song_id=?", row).fetchone()
                        seeds.append({**dict(seed), "matched": True})
            if len(seeds) < 2:
                raise RuntimeError(f"Not enough seed tracks for {name}")
            if not outputs:
                with demo.open("w", encoding="utf-8-sig", newline="") as file:
                    writer = csv.DictWriter(file, fieldnames=("song_id", "song_name", "artist"), extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(seeds)
            times = {}
            outcomes = {}
            for algorithm in ("classic", "graph"):
                elapsed = []
                for _ in range(3):
                    started = perf_counter()
                    if algorithm == "classic":
                        catalog = db.execute("SELECT song_id,song_name,artist,genres FROM catalog")
                        results = recommend_playlist((dict(row) for row in catalog), seeds, 10)
                    else:
                        results = recommend_playlist_graph(db, seeds, 10, index, songs)
                    elapsed.append(perf_counter() - started)
                assert len(results) == 10, (name, algorithm)
                assert {song["song_id"] for song in results}.isdisjoint(song["song_id"] for song in seeds)
                assert all(song["reason"] for song in results)
                assert all(is_recommendable_track(song["song_name"], song["genres"], song["song_id"])
                           for song in results)
                if algorithm == "graph":
                    groups = [group_for[song["song_id"]] for song in results if song["song_id"] in group_for]
                    assert len(groups) == len(set(groups))
                    assert set(groups).isdisjoint(group_for.get(song["song_id"]) for song in seeds)
                times[algorithm] = round(statistics.median(elapsed), 4)
                outcomes[algorithm] = {
                    "distinct_artists": len({song["artist"] for song in results}),
                    "graph_paths": sum("图关系：" in song["reason"] for song in results),
                    "multi_hop_paths": sum(
                        song["reason"].partition("图关系：")[2].count("→") >= 2 for song in results
                    ),
                    "similar_artist_paths": sum("（相似艺人）" in song["reason"] for song in results),
                    "songs": results,
                }
            overlap = {song["song_id"] for song in outcomes["classic"]["songs"]} & {
                song["song_id"] for song in outcomes["graph"]["songs"]
            }
            outputs.append({
                "scenario": name, "seeds": seeds, "median_seconds": times,
                "top10_overlap": len(overlap), "algorithms": outcomes,
            })
    report.write_text(json.dumps({
        "metadata": metadata, "full_catalog_count": full_count, "sqlite_sync_seconds": round(sync_seconds, 3),
        "evaluation": "Fixed real-catalog probe tracks, no listening or preference labels",
        "scenarios": outputs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in outputs:
        print(item["scenario"], item["median_seconds"], "overlap", item["top10_overlap"],
              "artists", [data["distinct_artists"] for data in item["algorithms"].values()],
              "multi-hop", item["algorithms"]["graph"]["multi_hop_paths"],
              "similar artist", item["algorithms"]["graph"]["similar_artist_paths"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("songs", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("demo", type=Path)
    parser.add_argument("--reference", type=Path, help="reuse the seed tracks from a prior evaluation")
    args = parser.parse_args()
    evaluate(args.index, args.songs, args.report, args.demo, args.reference)
