# -*- coding: utf-8 -*-
"""Stage 6: artist_similarity.db → 行为曲库的歌手相似边表 + 歌手维表 + 统计与演示。

输入:
  D:\\DSH-Work\\msd\\artist_similarity.db（similarity: 2,201,916 条 target/similar 边）
  cf_data\\msd_song_meta.csv（song_id -> artist_id, plays, ...）

输出:
  cf_data\\artist_similarity_edges.csv      行为曲库歌手的相似边（target,similar）
  cf_data\\artist_dim.csv                  行为曲库 30,543 位歌手的维表（名称/播放/热度/地区）
  cf_data\\artist_similarity_stats.json     覆盖统计
  cf_data\\artist_similarity_demo.json      10 位高播放歌手的相似歌手与代表作 + 3 位用户的相似歌手推荐演示
"""
import csv
import json
import os
import sqlite3
import time
from collections import Counter, defaultdict

import pandas as pd

CF = r"D:\desktop\音乐推荐数据\cf_data"
DB = r"D:\DSH-Work\msd\artist_similarity.db"

t0 = time.time()
meta = pd.read_csv(
    os.path.join(CF, "msd_song_meta.csv"),
    dtype={"song_id": str, "track_id": str, "artist_id": str},
    keep_default_na=False,
    low_memory=False,
)
print("meta rows:", len(meta), flush=True)

# 歌手维表：按播放量聚合
g = meta.groupby("artist_id").agg(
    artist_name=("artist", "first"),
    songs=("song_id", "count"),
    plays=("plays", "sum"),
    users=("users", "sum"),
).reset_index()
g = g.merge(meta.groupby("artist_id").agg(
    artist_familiarity=("artist_familiarity", "first"),
    artist_hotttnesss=("artist_hotttnesss", "first"),
    artist_location=("artist_location", "first"),
).reset_index(), on="artist_id", how="left")
g = g[g["artist_id"] != ""].sort_values(["plays", "artist_id"], ascending=[False, True]).reset_index(drop=True)
g.to_csv(os.path.join(CF, "artist_dim.csv"), index=False, encoding="utf-8")
artists = set(g["artist_id"])
print("artist_dim:", len(g), flush=True)

# 相似边：只保留 target 在行为曲库里的边
con = sqlite3.connect(DB)
con.execute("PRAGMA temp_store=MEMORY")
con.execute("CREATE TEMP TABLE want(artist_id text PRIMARY KEY)")
con.executemany("INSERT OR IGNORE INTO want VALUES(?)", [(a,) for a in artists])
edges = pd.read_sql_query(
    "SELECT s.target, s.similar FROM similarity s JOIN want w ON s.target = w.artist_id",
    con,
)
con.close()
edges = edges.drop_duplicates().sort_values(["target", "similar"]).reset_index(drop=True)
edges = edges[edges["target"] != edges["similar"]]
edges.to_csv(os.path.join(CF, "artist_similarity_edges.csv"), index=False, encoding="utf-8")
print("edges:", len(edges), "targets:", edges["target"].nunique(), flush=True)

per_target = edges.groupby("target").size()
in_catalog = set(g["artist_id"])

# 演示：高播放歌手的相似歌手（按相似歌手在曲库内的播放量排序）
name_map = dict(zip(g["artist_id"], g["artist_name"]))
plays_map = dict(zip(g["artist_id"], g["plays"]))
nb = defaultdict(list)
for t, s in zip(edges["target"], edges["similar"]):
    nb[t].append(s)

top_artists = g.head(10)["artist_id"].tolist()
examples = []
for aid in top_artists:
    neighbors = [x for x in nb.get(aid, []) if x in in_catalog]
    neighbors.sort(key=lambda x: -plays_map.get(x, 0))
    examples.append({
        "artist_id": aid,
        "artist": name_map.get(aid, ""),
        "plays": int(plays_map.get(aid, 0)),
        "neighbor_count": int(len(nb.get(aid, []))),
        "top_neighbors": [
            {"artist_id": n, "artist": name_map.get(n, ""), "plays": int(plays_map.get(n, 0))}
            for n in neighbors[:5]
        ],
    })

# 演示：3 位用户的"相似歌手"推荐（无权重边，仅作可用性示例）
hist = defaultdict(list)
with open(os.path.join(CF, "sample_recommendations.json"), encoding="utf-8") as fh:
    samples = json.load(fh)[:3]
user_ids = {u["user_id"] for u in samples}
with open(os.path.join(CF, "train.csv"), encoding="utf-8") as fh:
    rd = csv.reader(fh)
    next(rd)
    for u, s, c in rd:
        if u in user_ids:
            hist[u].append(s)

song_artist = dict(zip(meta["song_id"], meta["artist_id"]))
song_title = dict(zip(meta["song_id"], meta["title"]))
song_plays = dict(zip(meta["song_id"], meta["plays"]))
artist_songs = defaultdict(list)
for _, row in meta.iterrows():
    artist_songs[row["artist_id"]].append(row["song_id"])

user_demo = []
for u in samples:
    uid = u["user_id"]
    pairs = hist.get(uid, [])
    owned_artists = Counter(song_artist.get(s) for s in pairs)
    top_owned = [a for a, _ in owned_artists.most_common(5) if a]
    cand = Counter()
    for a in top_owned:
        for n in nb.get(a, []):
            if n in in_catalog and n not in owned_artists:
                cand[n] += 1
    recs = []
    for aid, weight in cand.most_common(50):
        for sid in sorted(artist_songs.get(aid, []), key=lambda x: -song_plays.get(x, 0))[:1]:
            recs.append({"artist": name_map.get(aid, ""), "title": song_title.get(sid, ""),
                         "plays": int(song_plays.get(sid, 0)), "via_artists": weight})
    recs.sort(key=lambda r: (-r["via_artists"], -r["plays"]))
    user_demo.append({
        "user_id": uid,
        "history_songs": len(pairs),
        "top_owned_artists": [name_map.get(a, a) for a in top_owned],
        "demo_recommendations": recs[:5],
    })

stats = {
    "source": "artist_similarity.db (Echo Nest artist similarity, 2,201,916 edges, 44,460 targets)",
    "catalog_artists": int(len(artists)),
    "catalog_artists_with_neighbors": int(len(per_target)),
    "coverage_pct": round(len(per_target) / len(artists) * 100, 2),
    "edges_for_catalog": int(len(edges)),
    "neighbors_mean": round(float(per_target.mean()), 2) if len(per_target) else 0,
    "neighbors_median": int(per_target.median()) if len(per_target) else 0,
    "neighbors_max": int(per_target.max()) if len(per_target) else 0,
    "neighbors_min": int(per_target.min()) if len(per_target) else 0,
    "similar_in_catalog_pct": round(edges["similar"].isin(in_catalog).mean() * 100, 2),
    "no_distance_column": True,
    "note": ("similarity 表只有 target/similar 两列，没有相似度分数与排名；"
             "边是无权邻居集合，使用时不能把顺序当相似度"),
    "top_artist_examples": examples,
    "user_recommendation_demo": user_demo,
    "elapsed_seconds": round(time.time() - t0, 1),
}
with open(os.path.join(CF, "artist_similarity_stats.json"), "w", encoding="utf-8") as fh:
    json.dump(stats, fh, ensure_ascii=False, indent=2)
print(json.dumps({k: v for k, v in stats.items() if k not in ("top_artist_examples", "user_recommendation_demo")},
                 ensure_ascii=False, indent=2))
print("done", round(time.time() - t0, 1), "s")
