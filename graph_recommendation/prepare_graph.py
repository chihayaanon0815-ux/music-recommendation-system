"""Prepare the reviewed catalog as a weighted, directed recommendation graph."""

import argparse
import csv
import hashlib
import heapq
import json
import math
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recommender.track_content import is_recommendable_track


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


ALIASES = {
    normalize(alias): names[0]
    for names in (
        ("周杰伦", "周杰倫", "Jay Chou"), ("陈奕迅", "陳奕迅", "Eason Chan"),
        ("邓丽君", "鄧麗君", "Teresa Teng"), ("王菲", "Faye Wong"),
        ("邓紫棋", "鄧紫棋", "G.E.M.", "G.E.M. 鄧紫棋"),
        ("林俊杰", "林俊傑", "JJ Lin"), ("张学友", "張學友", "Jacky Cheung"),
        ("张惠妹", "張惠妹", "A-Mei", "aMEI"), ("蔡依林", "Jolin Tsai"),
        ("孙燕姿", "孫燕姿", "Stefanie Sun"), ("刘德华", "劉德華", "Andy Lau"),
        ("五月天", "Mayday"), ("梁静茹", "梁靜茹", "Fish Leong"),
        ("宇多田ヒカル", "宇多田光", "Hikaru Utada"), ("苏打绿", "蘇打綠", "Sodagreen"),
    )
    for alias in names
}


def artist_name(value):
    return ALIASES.get(normalize(value), value.strip())


def stable_order(song_id):
    return hashlib.blake2b(song_id.encode(), digest_size=8).digest()


def load_tracks(directory, genres_file, sample_size=None, label_details=None):
    weights = {
        row["song_id"]: float(row["suggested_genre_weight"])
        for row in rows(directory / "genre_ranking_policy.csv")
    }
    excluded = {row["song_id"] for row in rows(directory / "exclude_from_genre_ranking.csv")}
    duplicates = {
        row["song_id"]: row["group_id"] for row in rows(directory / "duplicate_review.csv")
    }
    styles = {row["genre"] for row in rows(genres_file) if row["genre"] != "风格待确认"}
    regional_pop = {"华语流行", "粤语流行", "日韩流行", "日语流行", "韩语流行", "台语流行"}
    detail_styles = {}
    if label_details:
        for row in rows(label_details):
            labels = regional_pop & set(row["original_labels"].split("|"))
            if labels:
                detail_styles[row["song_id"]] = labels
    tracks = []
    seen = set()
    for row in rows(directory / "songs.csv"):
        sid = row["song_id"]
        if not sid or not row["song_name"] or sid in seen:
            raise ValueError(f"Invalid or repeated song ID: {sid}")
        seen.add(sid)
        weight = 0.0 if sid in excluded else weights.get(sid, 1.0)
        genres = set(row["genres"].split("|")) & styles if weight else set()
        if "流行" in genres and weight == 1.0:
            genres |= detail_styles.get(sid, set())
        tracks.append({
            "id": sid, "name": row["song_name"], "artist": artist_name(row["artist"]),
            "genres": sorted(genres), "weight": weight, "duplicate": duplicates.get(sid, ""),
            "recommendable": is_recommendable_track(row["song_name"], row["genres"], sid),
        })
    if sample_size and sample_size < len(tracks):
        strata = defaultdict(list)
        for song in tracks:
            strata[tuple(song["genres"][:1])].append(song)
        ordered = {
            genre: sorted(group, key=lambda song: stable_order(song["id"]))
            for genre, group in strata.items()
        }
        selected = [
            ((position + 0.5) / len(group), stable_order(song["id"]), song)
            for group in ordered.values() for position, song in enumerate(group)
        ]
        tracks = [song for _, _, song in heapq.nsmallest(sample_size, selected, key=lambda row: row[:2])]
    return tracks


def artist_neighbors(groups, tracks, limit=20):
    raw = {}
    by_genre = defaultdict(set)
    for artist, ids in groups.items():
        counts = Counter(genre for sid in ids if tracks[sid]["weight"] == 1
                         for genre in tracks[sid]["genres"])
        if sum(counts.values()) >= 3:
            raw[artist] = counts
            for genre in counts:
                by_genre[genre].add(artist)
    vectors = {}
    for artist, counts in raw.items():
        vector = {genre: math.log1p(count) * (1 + math.log((len(raw) + 1) / (len(by_genre[genre]) + 1)))
                  for genre, count in counts.items()}
        norm = math.sqrt(sum(value * value for value in vector.values()))
        vectors[artist] = {genre: value / norm for genre, value in vector.items()}
    # Restrict comparisons to artists that share a genre beyond their dominant broad category.
    strongest = {
        artist: sorted(vector, key=lambda genre: (-vector[genre], genre))[:3]
        for artist, vector in vectors.items()
    }
    inverted = defaultdict(list)
    for artist, genres in strongest.items():
        for genre in genres:
            inverted[genre].append(artist)
    # Cap the comparison pool per style using evidence count and stable ordering.
    for candidates in inverted.values():
        candidates.sort(key=lambda artist: (-sum(raw[artist].values()), stable_order(artist)))
        del candidates[350:]
    for artist, vector in sorted(vectors.items()):
        candidates = set().union(*(inverted[genre] for genre in strongest[artist])) - {artist}
        scores = []
        for other in candidates:
            shared = vector.keys() & vectors[other].keys()
            # Sharing only a coarse label does not establish an artist relationship.
            if not (shared - {"流行", "摇滚", "世界音乐"}):
                continue
            evidence = sum(min(raw[artist][genre], raw[other][genre]) for genre in shared)
            score = math.fsum(vector[genre] * vectors[other][genre] for genre in sorted(shared))
            score *= evidence / (evidence + 5)
            if score >= 0.15:
                scores.append((other, score))
        yield artist, heapq.nsmallest(limit, scores, key=lambda pair: (-pair[1], pair[0]))


def prepare(tracks):
    tracks = {song["id"]: song for song in tracks}
    artists, genres = defaultdict(list), defaultdict(list)
    nodes = {f"s:{sid}": ("Song", song["name"]) for sid, song in tracks.items()}
    edges = defaultdict(list)
    for sid, song in tracks.items():
        if not song.get("recommendable", True):
            continue
        if song["artist"]:
            artists[normalize(song["artist"])].append(sid)
        for genre in song["genres"]:
            genres[genre].append(sid)
    for artist, ids in artists.items():
        node = f"a:{artist}"
        nodes[node] = ("Artist", tracks[ids[0]]["artist"])
        for sid in ids:
            edges[f"s:{sid}"].append((node, 0.65, "ARTIST"))
        representatives = heapq.nsmallest(180, ids, key=stable_order)
        edges[node].extend((f"s:{sid}", 0.55 / len(representatives), "TRACK") for sid in representatives)
    for genre, ids in genres.items():
        node = f"g:{genre}"
        nodes[node] = ("Genre", genre)
        broadness = 1 + math.log(len(tracks) / len(ids))
        for sid in ids:
            song = tracks[sid]
            weight = 0.12 * broadness * song["weight"] / len(song["genres"])
            edges[f"s:{sid}"].append((node, weight, "GENRE"))
        representatives = heapq.nsmallest(
            180, ids, key=lambda sid: (-tracks[sid]["weight"], stable_order(sid))
        )
        edges[node].extend((f"s:{sid}", tracks[sid]["weight"], "TRACK") for sid in representatives)
    for artist, neighbors in artist_neighbors(artists, tracks):
        total = sum(score for _, score in neighbors)
        edges[f"a:{artist}"].extend(
            (f"a:{other}", 0.45 * score / total, "SIMILAR_ARTIST") for other, score in neighbors
        )
    return nodes, edges, artists, genres


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("genres", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sample-size", default=0, type=int)
    parser.add_argument("--label-details", type=Path)
    args = parser.parse_args()
    if args.sample_size < 0:
        parser.error("--sample-size must be nonnegative")
    tracks = load_tracks(args.catalog, args.genres, args.sample_size, args.label_details)
    nodes, edges, _, _ = prepare(tracks)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.catalog / "songs.csv").open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    graph = {"source_sha256": digest, "tracks": tracks, "nodes": nodes, "edges": edges}
    with (args.output / "graph.json").open("w", encoding="utf-8") as file:
        json.dump(graph, file, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(tracks):,} songs | {len(nodes):,} nodes | {sum(map(len, edges.values())):,} directed edges")


if __name__ == "__main__":
    main()
