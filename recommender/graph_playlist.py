"""Recommend from a materialized graph without a running Neo4j server."""

import hashlib
import heapq
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from functools import lru_cache

from recommender.track_content import is_recommendable_track


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@lru_cache(maxsize=4)
def file_digest(path, size, modified):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def batched_rows(connection, query, values):
    values = tuple(values)
    for offset in range(0, len(values), 400):
        batch = values[offset:offset + 400]
        yield from connection.execute(query.format(",".join("?" for _ in batch)), batch)


def seed_weights(tracks):
    artists, genres = Counter(), Counter()
    for track in tracks:
        if track["artist"]:
            artists[f'a:{track["artist"]}'] += 1
        for label in filter(None, track["genres"].split("|")):
            genres[f"g:{label}"] += track["weight"]
    result = {}
    for block, share in ((artists, 0.6), (genres, 0.4)):
        strongest = sorted(block.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
        total = sum(value for _, value in strongest)
        for seed, value in strongest:
            result[seed] = share * value / total
    return result


def similar_artist_paths(db, weights):
    paths = {}
    for seed, weight in weights.items():
        if not seed.startswith("a:"):
            continue
        for row in db.execute("""
            SELECT r.source_name, r.target_name, r.strength, f.track, f.rank
            FROM (
                SELECT * FROM artist_routes WHERE seed=?
                ORDER BY strength DESC, target LIMIT 8
            ) AS r
            JOIN features AS f ON f.seed=r.target AND f.rank<12
        """, (seed,)):
            score = weight * row["strength"] / (1 + 0.03 * row["rank"])
            sid = row["track"]
            if score > paths.get(sid, (0, "", ""))[0]:
                paths[sid] = score, row["source_name"], row["target_name"]
    return paths


def score_candidates(db, weights, artist_paths):
    direct_seeds, relevance, reasons = defaultdict(set), defaultdict(float), {}
    for seed, weight in weights.items():
        for row in db.execute("SELECT track FROM features WHERE seed=? ORDER BY rank", (seed,)):
            direct_seeds[row["track"]].add(seed)
        for row in db.execute("SELECT track, score, reason FROM neighbors WHERE seed=? ORDER BY rank", (seed,)):
            score = weight * row["score"]
            relevance[row["track"]] += score
            if score > reasons.get(row["track"], (0, ""))[0]:
                reasons[row["track"]] = score, row["reason"], seed
    if not direct_seeds and not relevance and not artist_paths:
        return {}, {}, {}
    direct_max = sum(weights.values())
    graph_max = max(relevance.values(), default=1)
    path_max = max((path[0] for path in artist_paths.values()), default=1)
    genre_seeds = {seed[2:] for seed in weights if seed.startswith("g:")}
    ranked = {}
    eligible_paths = {}
    candidate_ids = direct_seeds.keys() | relevance.keys() | artist_paths.keys()
    for track in batched_rows(db, "SELECT * FROM tracks WHERE id IN ({})", candidate_ids):
        sid = track["id"]
        genres = set(filter(None, track["genres"].split("|")))
        artist_score = weights.get(f'a:{track["artist"]}', 0.0)
        genre_score = sum(weights.get(f"g:{label}", 0.0) for label in genres) * track["weight"]
        base = 0.45 * (artist_score + genre_score) / direct_max
        base += 0.40 * relevance.get(sid, 0) / graph_max
        if genres:
            base += 0.15 * track["weight"]
        if (sid in artist_paths and not artist_score and track["weight"] >= 0.5
                and (not genre_seeds or genres & genre_seeds)):
            path = artist_paths[sid]
            base += 0.12 * path[0] / path_max
            eligible_paths[sid] = path[1:]
        elif sid not in direct_seeds and sid not in relevance:
            continue
        ranked[sid] = base, track, genres
    return ranked, reasons, eligible_paths


def rerank(candidates, limit, seed_artists, routed):
    selected = []
    used_groups, used_names = set(), set()
    artist_counts = Counter()
    redundancy = defaultdict(float)
    titles = {song["song_id"]: (normalize(song["song_name"]), artist)
              for _, song, artist, _, _ in candidates}
    for position in range(limit):
        best = None
        anchored = None
        discovery = None
        for candidate in candidates:
            score, song, artist, _, group = candidate
            sid = song["song_id"]
            if titles[sid] in used_names or (group and group in used_groups):
                continue
            adjusted = score - 0.20 * redundancy[sid] - 0.06 * artist_counts[artist]
            key = -adjusted, sid
            if best is None or key < best[0]:
                best = key, candidate
            if artist in seed_artists and (anchored is None or key < anchored[0]):
                anchored = key, candidate
            if sid in routed and not artist_counts[artist] and (discovery is None or key < discovery[0]):
                discovery = key, candidate
        if position in (0, 3) and anchored:
            best = anchored
        elif position in (1, 4) and discovery:
            best = discovery
        if best is None:
            break
        score, song, artist, genres, group = best[1]
        selected.append(best[1])
        used_names.add(titles[song["song_id"]])
        if group:
            used_groups.add(group)
        if artist:
            artist_counts[artist] += 1
        for _, other_song, other_artist, other_genres, _ in candidates:
            sid = other_song["song_id"]
            similarity = 0.65 * bool(artist and artist == other_artist)
            similarity += 0.35 * len(genres & other_genres) / max(1, len(genres | other_genres))
            redundancy[sid] = max(redundancy[sid], similarity)
    return [{**song, "score": round(score * 100, 1)} for score, song, _, _, _ in selected]


def recommend_playlist_graph(catalog, seeds, limit, index_path, songs_path):
    """Return an empty result when the index or usable graph seeds are unavailable."""
    ids = {song["song_id"] for song in seeds}
    matched = {song["song_id"]: song for song in seeds
               if song["matched"] and is_recommendable_track(song["song_name"], song["genres"], song["song_id"])}
    if not matched or not index_path.is_file():
        return []
    stat = songs_path.stat()
    with closing(sqlite3.connect(index_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        info = dict(db.execute("SELECT key, value FROM info"))
        if info.get("schema") != "3" or info.get("source_sha256") != file_digest(
            songs_path, stat.st_size, stat.st_mtime_ns
        ):
            return []
        seed_features = list(batched_rows(db, "SELECT * FROM tracks WHERE id IN ({})", ids))
        weights = seed_weights(track for track in seed_features if track["id"] in matched)
        ranked, reasons, routed = score_candidates(db, weights, similar_artist_paths(db, weights))
        genre_sources = {}
        for feature in seed_features:
            if feature["id"] in matched and feature["weight"]:
                for genre in filter(None, feature["genres"].split("|")):
                    genre_sources.setdefault(genre, matched[feature["id"]]["song_name"])
        suppressed_groups = {track["duplicate_group"] for track in seed_features if track["duplicate_group"]}
        known_names = {(normalize(song["song_name"]), normalize(song["artist"])) for song in seeds}
        eligible = {sid for sid, (_, track, _) in ranked.items()
                    if sid not in ids and track["duplicate_group"] not in suppressed_groups}
        candidate_ids = heapq.nsmallest(
            max(350, limit * 8), eligible, key=lambda sid: (-ranked[sid][0], sid),
        )
        candidate_ids = set(candidate_ids) | set(heapq.nsmallest(
            max(12, limit), eligible & routed.keys(), key=lambda sid: (-ranked[sid][0], sid),
        ))
        candidates = []
        for row in batched_rows(catalog, "SELECT song_id,song_name,artist,genres FROM catalog WHERE song_id IN ({})",
                                candidate_ids):
            song = dict(row)
            sid = song["song_id"]
            score, track, genres = ranked[sid]
            if ((normalize(song["song_name"]), normalize(song["artist"])) in known_names
                    or not is_recommendable_track(song["song_name"], song["genres"], sid)):
                continue
            parts = []
            if f'a:{track["artist"]}' in weights:
                parts.append("匹配歌单艺人")
            shared = sorted(label for label in genres if f"g:{label}" in weights)
            if shared:
                parts.append("共享曲风：" + "、".join(shared))
            if sid in routed:
                source, target = routed[sid]
                parts.append(f'图关系：{source} → {target} → 《{song["song_name"]}》（相似艺人）')
            elif sid in reasons:
                _, path, seed = reasons[sid]
                if " → " in path:
                    if seed.startswith("g:") and seed[2:] in genre_sources:
                        path = f'《{genre_sources[seed[2:]]}》 → {path}'
                    parts.append("图关系：" + path)
                else:
                    parts.append(path)
            if not parts:
                continue
            song["reason"] = "；".join(parts)
            candidates.append((score, song, track["artist"], genres, track["duplicate_group"]))
    return rerank(candidates, limit, {seed[2:] for seed in weights if seed.startswith("a:")}, routed)
