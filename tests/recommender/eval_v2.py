"""Offline evaluation for the v2 recommender on the real catalogue.

Usage (from the repository root):

    python tests/recommender/eval_v2.py
    python tests/recommender/eval_v2.py --data data/processed/songs.csv --k 10

What it does
------------
For the ten most frequent genres in ``data/processed/songs.csv`` it builds a
deterministic pseudo-user: 30 seed tracks of that genre are removed from the
pool, and the remaining tracks of the same genre form the relevant set.

Each strategy is scored with binary relevance:

* Precision@K / Recall@K / NDCG@K / HitRate@K
* Intra-list diversity (1 - mean pairwise Jaccard of the returned genre sets)
* Catalogue coverage (unique recommended tracks / catalogue size)

The script only uses the standard library, so it runs in the same offline
environment as the algorithm. Output is a markdown table on stdout plus a
JSON summary written next to this file (``eval_v2_summary.json``).
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommender.playlist import recommend_playlist  # noqa: E402
from recommender.recommend import recommend  # noqa: E402
from recommender.recommend_v2 import recommend_from_seeds, recommend_v2  # noqa: E402
from recommender.similarity import fold, genre_labels, jaccard  # noqa: E402

FIELDS = ("song_id", "song_name", "artist", "genres")


def load_songs(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError("songs.csv 表头不符合契约")
        songs = []
        for row in reader:
            song = {key: (row.get(key) or "").strip() for key in FIELDS}
            if song["song_id"] and song["song_name"]:
                songs.append(song)
    return songs


def genre_counts(songs):
    counts = {}
    for song in songs:
        for label in genre_labels(song["genres"]):
            counts[label] = counts.get(label, 0) + 1
    return counts


def build_queries(songs, limit=10, seeds=30):
    """Deterministic pseudo-users, one per frequent genre."""
    counts = genre_counts(songs)
    eligible = sorted(
        ((count, label) for label, count in counts.items() if count >= 200),
        key=lambda pair: (-pair[0], pair[1]),
    )[:limit]
    queries = []
    for count, label in eligible:
        key = fold(label)
        members = sorted(
            (song for song in songs if key in {fold(tag) for tag in genre_labels(song["genres"])}),
            key=lambda song: song["song_id"],
        )
        step = max(1, len(members) // (seeds + 1))
        picked = [members[i * step] for i in range(seeds)]
        holdout = {song["song_id"] for song in members} - {song["song_id"] for song in picked}
        queries.append({
            "genre": label,
            "catalogue_size": count,
            "seeds": picked,
            "holdout": holdout,
        })
    return queries


def ndcg(hits, k):
    dcg = sum(1.0 / math.log2(position + 2) for position, hit in enumerate(hits) if hit)
    ideal = sum(1.0 / math.log2(position + 2) for position in range(k))
    return dcg / ideal if ideal else 0.0


def build_artist_queries(songs, limit=8, seeds=8):
    """Pseudo-users that follow one artist: holdout is the artist's other tracks."""
    counts = {}
    for song in songs:
        artist = song["artist"]
        if artist:
            counts[artist] = counts.get(artist, 0) + 1
    eligible = sorted(((count, artist) for artist, count in counts.items() if count >= 100),
                      key=lambda pair: (-pair[0], pair[1]))[:limit]
    queries = []
    for count, artist in eligible:
        members = sorted((song for song in songs if song["artist"] == artist),
                         key=lambda song: song["song_id"])
        step = max(1, len(members) // (seeds + 1))
        picked = [members[i * step] for i in range(seeds)]
        holdout = {song["song_id"] for song in members} - {song["song_id"] for song in picked}
        queries.append({"artist": artist, "pool": count, "seeds": picked, "holdout": holdout})
    return queries


def evaluate_cold_start(songs, k):
    """No preferences: relevant = the three most frequent genres combined."""
    counts = genre_counts(songs)
    top = [label for _, label in sorted(((c, l) for l, c in counts.items()),
                                        key=lambda pair: (-pair[0], pair[1]))[:3]]
    keys = {fold(label) for label in top}
    relevant = {song["song_id"] for song in songs
                if keys & {fold(tag) for tag in genre_labels(song["genres"])}}

    from recommender.recommend import recommend
    from recommender.recommend_v2 import recommend_v2

    rows = []
    for strategy in ("v1-default", "v2-default"):
        results = (recommend(songs, {}, limit=k)
                   if strategy == "v1-default"
                   else recommend_v2(songs, {}, limit=k))
        hit = sum(1 for item in results if item["song_id"] in relevant)
        rows.append({"strategy": strategy,
                     "genres": "/".join(top),
                     "precision_at_k": round(hit / k, 4),
                     "relevant_pool": len(relevant)})
    return rows


def evaluate_artist(strategy, songs, queries, k):
    def run(query):
        if strategy == "playlist-v1":
            seeds = [{**song, "matched": True} for song in query["seeds"]]
            return recommend_playlist(songs, seeds, k)
        return recommend_from_seeds(songs, query["seeds"], limit=k)

    precision, recall, ndcgs = [], [], []
    for query in queries:
        results = run(query)
        flags = [item["song_id"] in query["holdout"] for item in results]
        hit = sum(flags)
        precision.append(hit / k if k else 0.0)
        recall.append(hit / len(query["holdout"]) if query["holdout"] else 0.0)
        ndcgs.append(ndcg(flags, k))
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
    return {
        "strategy": strategy,
        "precision_at_k": round(mean(precision), 4),
        "recall_at_k": round(mean(recall), 4),
        "ndcg_at_k": round(mean(ndcgs), 4),
        "queries": len(queries),
        "k": k,
    }


def evaluate(strategy, songs, queries, k):
    def run(query):
        if strategy == "v1":
            return recommend(songs, {"genres": [query["genre"]]}, limit=k, strategy="v1")
        if strategy == "v2":
            return recommend_v2(songs, {"genres": [query["genre"]]}, limit=k)
        return recommend_v2(songs, {"genres": [query["genre"]]}, limit=k, diversity=0.0)

    precision, recall, ndcgs, hits_at_k = [], [], [], []
    recommended_ids = set()
    list_diversities, artist_counts = [], []
    for query in queries:
        results = run(query)
        flags = [item["song_id"] in query["holdout"] for item in results]
        hit = sum(flags)
        precision.append(hit / k if k else 0.0)
        recall.append(hit / len(query["holdout"]) if query["holdout"] else 0.0)
        ndcgs.append(ndcg(flags, k))
        hits_at_k.append(1.0 if hit else 0.0)
        recommended_ids.update(item["song_id"] for item in results)

        tag_sets = [set(genre_labels(item["genres"])) for item in results]
        pairs = [(a, b) for i, a in enumerate(tag_sets) for b in tag_sets[i + 1:]]
        if pairs:
            list_diversities.append(1.0 - sum(jaccard(a, b) for a, b in pairs) / len(pairs))
        artist_counts.append(len({item["artist"] for item in results if item["artist"]}))

    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
    return {
        "strategy": strategy,
        "precision_at_k": round(mean(precision), 4),
        "recall_at_k": round(mean(recall), 4),
        "ndcg_at_k": round(mean(ndcgs), 4),
        "hit_rate_at_k": round(mean(hits_at_k), 4),
        "intra_list_diversity": round(mean(list_diversities), 4),
        "coverage": round(len(recommended_ids) / len(songs), 5),
        "distinct_artists_per_query": round(mean(artist_counts), 2),
        "queries": len(queries),
        "k": k,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate v1 vs v2 on songs.csv")
    parser.add_argument("--data", default=str(ROOT / "data" / "processed" / "songs.csv"))
    parser.add_argument("--queries", type=int, default=10)
    parser.add_argument("--k", type=int, default=10)
    arguments = parser.parse_args()

    songs = load_songs(Path(arguments.data))
    queries = build_queries(songs, limit=arguments.queries)
    rows = [evaluate(strategy, songs, queries, arguments.k)
            for strategy in ("v1", "v2", "v2-div0")]

    headers = ["strategy", "precision_at_k", "recall_at_k", "ndcg_at_k",
               "hit_rate_at_k", "intra_list_diversity", "coverage",
               "distinct_artists_per_query"]
    print(f"catalogue={len(songs)} queries={len(queries)} k={arguments.k}")
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        print("| " + " | ".join(str(row[h]) for h in headers) + " |")

    artist_queries = build_artist_queries(songs)
    artist_rows = [evaluate_artist(strategy, songs, artist_queries, arguments.k)
                   for strategy in ("playlist-v1", "playlist-v2")]
    artist_headers = ["strategy", "precision_at_k", "recall_at_k", "ndcg_at_k"]
    print()
    print("歌手续听场景（seeds=该歌手 8 首，相关集=该歌手其余曲目）")
    print("| " + " | ".join(artist_headers) + " |")
    print("| " + " | ".join("---" for _ in artist_headers) + " |")
    for row in artist_rows:
        print("| " + " | ".join(str(row[h]) for h in artist_headers) + " |")

    cold_rows = evaluate_cold_start(songs, arguments.k)
    cold_headers = ["strategy", "genres", "precision_at_k", "relevant_pool"]
    print()
    print("冷启动场景（未选偏好，相关集=前三大风格的全部曲目）")
    print("| " + " | ".join(cold_headers) + " |")
    print("| " + " | ".join("---" for _ in cold_headers) + " |")
    for row in cold_rows:
        print("| " + " | ".join(str(row[h]) for h in cold_headers) + " |")

    summary = {
        "catalogue": len(songs),
        "k": arguments.k,
        "preference_queries": [
            {"genre": query["genre"], "pool": query["catalogue_size"],
             "holdout": len(query["holdout"])} for query in queries],
        "preference_results": rows,
        "artist_queries": [
            {"artist": query["artist"], "pool": query["pool"],
             "holdout": len(query["holdout"])} for query in artist_queries],
        "artist_results": artist_rows,
        "cold_start": cold_rows,
    }
    out = Path(__file__).resolve().parent / "eval_v2_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary -> {out}")


if __name__ == "__main__":
    main()
