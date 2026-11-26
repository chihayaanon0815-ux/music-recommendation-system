"""Build a read-only SQLite index from weighted PageRank recommendations."""

import argparse
import heapq
import json
import os
import sqlite3
import tempfile
from collections import Counter, defaultdict
from contextlib import closing, suppress
from pathlib import Path

from prepare_graph import normalize, rows, stable_order


DAMPING = 0.85
ITERATIONS = 20
TOP_K = 200
FRONTIER = 500


def walk(edges, seeds):
    """Approximate personalized PageRank with a bounded frontier and restart."""
    total = sum(seeds.values())
    restart = {node: weight / total for node, weight in seeds.items()}
    scores = restart
    paths = {node: [node] for node in scores}
    examples = paths.copy()
    for _ in range(ITERATIONS):
        updated = defaultdict(float, {node: (1 - DAMPING) * p for node, p in restart.items()})
        best = {node: (p, examples[node]) for node, p in updated.items()}
        unmatched = 0.0
        for node, score in scores.items():
            neighbors = edges.get(node, ())
            if not neighbors:
                unmatched += score * DAMPING
                continue
            for target, probability in neighbors:
                contribution = score * DAMPING * probability
                updated[target] += contribution
                path = paths.get(node)
                if path and target not in path and contribution > best.get(target, (0, None))[0]:
                    best[target] = (contribution, [*path, target])
        for node, weight in restart.items():
            updated[node] += unmatched * weight
        keep = heapq.nsmallest(FRONTIER, updated, key=lambda node: (-updated[node], node))
        scores = {node: updated[node] for node in keep}
        paths = {node: best[node][1] if node in best else examples[node] for node in keep
                 if node in best or node in examples}
        examples.update(paths)
    return scores, examples


class Neo4jGraph:
    """Load an experiment graph and run Neo4j GDS on its in-memory projection."""

    def __init__(self, uri, nodes, edges, name):
        from neo4j import GraphDatabase

        self.name = name
        password = os.getenv("NEO4J_PASSWORD")
        auth = (os.getenv("NEO4J_USER", "neo4j"), password) if password else None
        self.driver = GraphDatabase.driver(uri, auth=auth)
        self.database = os.getenv("NEO4J_DATABASE", "neo4j")
        try:
            self.version = self.query("RETURN gds.version() AS version")[0]["version"]
            self.query("CREATE CONSTRAINT recommendation_key IF NOT EXISTS "
                       "FOR (n:RecommendationNode) REQUIRE (n.run, n.key) IS UNIQUE")
            for kind in ("Song", "Artist", "Genre"):
                selected = [(node, label) for node, (node_kind, label) in nodes.items() if node_kind == kind]
                for i in range(0, len(selected), 4000):
                    self.query(
                        f"UNWIND $rows AS row MERGE (n:RecommendationNode:{kind} "
                        "{run: $run, key: row[0]}) SET n.name = row[1]", rows=selected[i:i + 4000],
                    )
            chunk = []
            for source, neighbors in edges.items():
                for target, probability, relation in neighbors:
                    chunk.append([source, target, probability, relation])
                    if len(chunk) == 4000:
                        self.write_edges(chunk)
                        chunk = []
            if chunk:
                self.write_edges(chunk)
            stored = self.query("MATCH (n:RecommendationNode {run: $run}) RETURN count(n) AS count")
            if stored[0]["count"] != len(nodes):
                raise RuntimeError("Neo4j node count differs from the prepared graph")
            projection = self.query(
                "MATCH (a:RecommendationNode {run: $run}) "
                "OPTIONAL MATCH (a)-[r:RECOMMEND_STEP]->(b:RecommendationNode {run: $run}) "
                "WITH gds.graph.project($run, a, b, {relationshipProperties: "
                "CASE WHEN r IS NULL THEN {} ELSE {weight: r.weight} END}) AS g "
                "RETURN g.nodeCount AS nodes, g.relationshipCount AS edges"
            )[0]
            expected_edges = sum(len(neighbors) for neighbors in edges.values())
            if projection["nodes"] != len(nodes) or projection["edges"] != expected_edges:
                raise RuntimeError("Neo4j projection counts differ from the prepared graph")
            print(f"Neo4j GDS {self.version} | {projection['nodes']:,} nodes | "
                  f"{projection['edges']:,} projected edges", flush=True)
        except Exception:
            with suppress(Exception):
                self.close()
            raise

    def query(self, cypher, **parameters):
        result = self.driver.execute_query(cypher, parameters_={"run": self.name, **parameters},
                                           database_=self.database)
        return result.records

    def write_edges(self, chunk):
        self.query(
            "UNWIND $rows AS row "
            "MATCH (a:RecommendationNode {run: $run, key: row[0]}) "
            "MATCH (b:RecommendationNode {run: $run, key: row[1]}) "
            "MERGE (a)-[r:RECOMMEND_STEP {kind: row[3]}]->(b) SET r.weight = row[2]",
            rows=chunk,
        )

    def recommend(self, seeds):
        records = self.query(
            "UNWIND $seeds AS seed MATCH (n:RecommendationNode {run: $run, key: seed}) "
            "WITH collect(n) AS sources "
            "CALL gds.pageRank.stream($run, {sourceNodes: sources, maxIterations: $iterations, "
            "dampingFactor: $damping, relationshipWeightProperty: 'weight', "
            "concurrency: 1, logProgress: false}) "
            "YIELD nodeId, score WITH gds.util.asNode(nodeId) AS song, score "
            "WHERE song:Song AND score > 0 "
            "RETURN song.key AS key, score ORDER BY score DESC, key ASC LIMIT $limit",
            seeds=seeds, iterations=ITERATIONS, damping=DAMPING, limit=TOP_K,
        )
        return {row["key"]: row["score"] for row in records}

    def close(self):
        try:
            try:
                self.query("CALL gds.graph.drop($run, false) YIELD graphName RETURN graphName")
            finally:
                for kind in ("Song", "Artist", "Genre"):
                    while self.query(
                        f"MATCH (n:RecommendationNode:{kind} {{run: $run}}) WITH n LIMIT 5000 "
                        "DETACH DELETE n RETURN count(*) AS removed"
                    )[0]["removed"]:
                        pass
        finally:
            self.driver.close()


def build(graph, path, *, uri=None, artist_limit=120, probe=None):
    nodes = graph["nodes"]
    edges = {}
    for node, neighbors in graph["edges"].items():
        total = sum(weight for _, weight, _ in neighbors)
        if total:
            edges[node] = [(target, weight / total) for target, weight, _ in neighbors]
    artists = Counter(normalize(song["artist"]) for song in graph["tracks"]
                      if song["artist"] and song.get("recommendable", True))
    seed_nodes = [node for node, (kind, _) in nodes.items() if kind == "Genre"]
    seed_nodes.extend(f"a:{artist}" for artist, _ in sorted(artists.items(), key=lambda row: (-row[1], row[0]))[:artist_limit])
    graph_engine = None
    if uri:
        import uuid
        graph_engine = Neo4jGraph(uri, nodes, graph["edges"], f"music_{uuid.uuid4().hex}")
    try:
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("""
                CREATE TABLE info (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE tracks (id TEXT PRIMARY KEY, artist TEXT NOT NULL,
                    genres TEXT NOT NULL, weight REAL NOT NULL, duplicate_group TEXT NOT NULL);
                CREATE TABLE features (seed TEXT NOT NULL, track TEXT NOT NULL,
                    rank INTEGER NOT NULL, PRIMARY KEY (seed, rank));
                CREATE TABLE neighbors (seed TEXT NOT NULL, track TEXT NOT NULL,
                    rank INTEGER NOT NULL, score REAL NOT NULL, reason TEXT NOT NULL,
                    PRIMARY KEY (seed, rank));
                CREATE TABLE artist_routes (seed TEXT NOT NULL, target TEXT NOT NULL,
                    source_name TEXT NOT NULL, target_name TEXT NOT NULL, strength REAL NOT NULL,
                    PRIMARY KEY (seed, target));
            """)
            db.executemany("INSERT INTO info VALUES (?, ?)", (
                ("schema", "3"), ("source_sha256", graph["source_sha256"]),
                ("backend", f"Neo4j GDS {graph_engine.version}" if graph_engine else "Python PPR"),
                ("song_count", str(len(graph["tracks"]))),
            ))
            direct = defaultdict(list)
            eligible = set()
            for song in graph["tracks"]:
                if not song.get("recommendable", True):
                    continue
                eligible.add(f's:{song["id"]}')
                artist = normalize(song["artist"])
                if artist:
                    direct[f"a:{artist}"].append((song["id"], song["weight"]))
                for genre in song["genres"]:
                    direct[f"g:{genre}"].append((song["id"], song["weight"]))
            db.executemany("INSERT INTO tracks VALUES (?, ?, ?, ?, ?)", (
                (song["id"], normalize(song["artist"]) if song.get("recommendable", True) else "",
                 "|".join(song["genres"]), song["weight"], song["duplicate"])
                for song in graph["tracks"]
            ))
            db.executemany("INSERT INTO features VALUES (?, ?, ?)", (
                (seed, sid, rank) for seed, members in direct.items()
                for rank, (sid, _) in enumerate(heapq.nsmallest(
                    TOP_K, members, key=lambda row: (-row[1], stable_order(row[0]))
                ))
            ))
            db.executemany("INSERT INTO artist_routes VALUES (?, ?, ?, ?, ?)", (
                (seed, target, nodes[seed][1], nodes[target][1], strength)
                for seed, neighbors in graph["edges"].items()
                for target, strength, kind in neighbors if kind == "SIMILAR_ARTIST"
            ))
            for seed in seed_nodes:
                scores, paths = walk(edges, {seed: 1})
                if graph_engine:
                    scores = graph_engine.recommend([seed])
                top = heapq.nsmallest(TOP_K, scores.keys() & eligible,
                                      key=lambda node: (-scores[node], node))
                if not top:
                    continue
                best = scores[top[0]]
                db.executemany("INSERT INTO neighbors VALUES (?, ?, ?, ?, ?)", (
                    (seed, node[2:], rank, scores[node] / best,
                     " → ".join(nodes[p][1] for p in paths[node]) if node in paths and paths[node][0] == seed
                     else f"图传播种子：{nodes[seed][1]}")
                    for rank, node in enumerate(top)
                ))
            count = db.execute("SELECT count(*) FROM neighbors").fetchone()[0]
            print(f"{len(seed_nodes)} graph seeds | {count:,} cached candidates")
        if probe:
            playlist, output = probe
            seeds = list(dict.fromkeys(f"s:{row['song_id']}" for row in rows(playlist)))
            seeds = [seed for seed in seeds if seed in nodes]
            if len(seeds) < 2:
                raise ValueError("The probe needs at least two songs in the prepared graph")
            recommendations = graph_engine.recommend(seeds)
            output.write_text(json.dumps({
                "gds_version": graph_engine.version,
                "catalog_count": len(graph["tracks"]),
                "seed_ids": [seed[2:] for seed in seeds],
                "songs": [
                    {"song_id": key[2:], "name": nodes[key][1], "score": score}
                    for key, score in recommendations.items() if key not in seeds and key in eligible
                ][:10],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        if graph_engine:
            graph_engine.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--neo4j-uri")
    parser.add_argument("--artist-limit", type=int, default=120)
    parser.add_argument("--probe-playlist", nargs=2, type=Path, metavar=("SEED_CSV", "OUTPUT_JSON"))
    args = parser.parse_args()
    if args.artist_limit < 0:
        parser.error("--artist-limit must be nonnegative")
    if args.probe_playlist and not args.neo4j_uri:
        parser.error("--probe-playlist requires --neo4j-uri")
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as file:
        temporary = Path(file.name)
    try:
        build(graph, temporary, uri=args.neo4j_uri, artist_limit=args.artist_limit, probe=args.probe_playlist)
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
