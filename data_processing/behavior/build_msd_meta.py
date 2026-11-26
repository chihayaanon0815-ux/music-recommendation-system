# -*- coding: utf-8 -*-
"""Stage 1-3: 用本机 MSD 元数据补全行为数据曲目信息。

输入:
  D:\\DSH-Work\\msd\\train_triplets.txt        用户-歌曲-播放
  D:\\DSH-Work\\msd\\unique_tracks.txt         track_id<SEP>song_id<SEP>artist<SEP>title
  D:\\DSH-Work\\msd\\track_metadata.db         songs(track_id,title,song_id,release,artist_id,artist_name,duration,year,...)
  D:\\desktop\\音乐推荐数据\\cf_data\\{id_maps.json,train.csv,test.csv,song_pool.csv,msd_spotify_map.csv}

输出:
  cf_data\\msd_song_meta.csv        384,546 首全量元数据 + 全量播放/用户数
  cf_data\\song_dim_kcore.csv       91,283 首 k-core 曲目维表 + 交叉引用
  cf_data\\song_pool_named.csv      5,000 首候选池补名
  cf_data\\wide_sample.csv          10 万条交互宽表样例
  cf_data\\msd_meta_coverage.json   覆盖率指标
"""
import json
import os
import sqlite3
import time
import zipfile

import pandas as pd

BASE = r"D:\desktop\音乐推荐数据"
CF = os.path.join(BASE, "cf_data")
MSD = r"D:\DSH-Work\msd"
TRIPLETS = os.path.join(MSD, "train_triplets.txt")
UNIQUE = os.path.join(MSD, "unique_tracks.txt")
DB = os.path.join(MSD, "track_metadata.db")

t0 = time.time()
print("[1/6] 聚合全量播放/用户数 ...", flush=True)
plays, users = {}, {}
n = 0
with open(TRIPLETS, encoding="utf-8") as fh:
    for line in fh:
        u, s, c = line.rstrip("\n").split("\t")
        plays[s] = plays.get(s, 0) + int(c)
        users[s] = users.get(s, 0) + 1
        n += 1
print(f"  rows={n:,} songs={len(plays):,} elapsed={time.time()-t0:.0f}s", flush=True)

print("[2/6] unique_tracks 兜底表 ...", flush=True)
tracks = {}
with open(UNIQUE, encoding="utf-8") as fh:
    for line in fh:
        tr, s, a, t = line.rstrip("\n").split("<SEP>")
        tracks.setdefault(s, (tr, a, t))
print(f"  unique_tracks songs={len(tracks):,} elapsed={time.time()-t0:.0f}s", flush=True)

print("[3/6] track_metadata.db 查询 ...", flush=True)
ids = list(plays.keys())
con = sqlite3.connect(DB)


def best_key(row):
    song_id, track_id, title, release, artist_id, artist_name, duration, year = row
    return (
        1 if (year or 0) > 0 else 0,
        1 if release else 0,
        1 if (duration or 0) > 0 else 0,
        1 if artist_name else 0,
        track_id or "",
    )


meta = {}
con.execute("PRAGMA temp_store=MEMORY")
con.execute("CREATE TEMP TABLE want(song_id text PRIMARY KEY)")
con.executemany("INSERT OR IGNORE INTO want VALUES(?)", [(x,) for x in ids])
sql = ("SELECT s.song_id, s.track_id, s.title, s.release, s.artist_id, s.artist_name, s.duration, s.year "
       "FROM songs s JOIN want w ON s.song_id = w.song_id")
for row in con.execute(sql):
    sid = row[0]
    old = meta.get(sid)
    if old is None or best_key(row) > best_key(old):
        meta[sid] = row
print(f"  query done rows={len(meta):,} elapsed={time.time()-t0:.0f}s", flush=True)
con.close()
print(f"  metadata songs={len(meta):,} elapsed={time.time()-t0:.0f}s", flush=True)

print("[4/6] 组装全量元数据表 ...", flush=True)
rows = []
for sid in ids:
    m = meta.get(sid)
    fallback = tracks.get(sid, ("", "", ""))
    if m:
        track_id, title, release, artist_id, artist_name, duration, year = \
            m[1], m[2], m[3], m[4], m[5], m[6], m[7]
    else:
        track_id, title, release, artist_id, artist_name, duration, year = \
            fallback[0], fallback[2], "", "", fallback[1], None, None
    rows.append({
        "song_id": sid,
        "track_id": track_id or "",
        "title": ((title or "").strip() or fallback[2].strip()),
        "artist": ((artist_name or "").strip() or fallback[1].strip()),
        "artist_id": artist_id or "",
        "release": (release or "").strip(),
        "year": int(year) if year else "",
        "duration_sec": round(float(duration), 2) if duration else "",
        "plays": int(plays[sid]),
        "users": int(users[sid]),
    })
meta_df = pd.DataFrame(rows).sort_values(["plays", "song_id"], ascending=[False, True]).reset_index(drop=True)
meta_df.to_csv(os.path.join(CF, "msd_song_meta.csv"), index=False, encoding="utf-8")
print(f"  msd_song_meta.csv rows={len(meta_df):,} elapsed={time.time()-t0:.0f}s", flush=True)

print("[5/6] k-core 曲目维表 ...", flush=True)
idm = json.load(open(os.path.join(CF, "id_maps.json"), encoding="utf-8"))
kcore_ids = list(idm["songs"].keys())

kusers, kplays = {}, {}
alive_users = set(idm["users"])
alive_songs = set(idm["songs"])
with open(TRIPLETS, encoding="utf-8") as fh:
    for line in fh:
        u, s, c = line.rstrip("\n").split("\t")
        if u in alive_users and s in alive_songs:
            kusers[s] = kusers.get(s, 0) + 1
            kplays[s] = kplays.get(s, 0) + int(c)
print(f"  kcore interactions={sum(kusers.values()):,} plays={sum(kplays.values()):,} "
      f"songs={len(kusers):,} elapsed={time.time()-t0:.0f}s", flush=True)

import csv

sp_map = {}
with open(os.path.join(CF, "msd_spotify_map.csv"), encoding="utf-8", newline="") as fh:
    for p in csv.reader(fh):
        if p[0] == "msd_song_id":
            continue
        sp_map[p[0]] = (p[1], p[7], p[8])

meta_by_sid = meta_df.set_index("song_id")[["title", "artist", "release", "year", "duration_sec", "plays", "users"]]
meta_lookup = meta_by_sid.to_dict("index")
dim_rows = []
for sid in kcore_ids:
    m = meta_lookup.get(sid)
    sp = sp_map.get(sid)
    dim_rows.append({
        "song_id": sid,
        "title": m["title"] if m else "",
        "artist": m["artist"] if m else "",
        "release": m["release"] if m else "",
        "year": m["year"] if m else "",
        "duration_sec": m["duration_sec"] if m else "",
        "kcore_users": int(kusers.get(sid, 0)),
        "kcore_plays": int(kplays.get(sid, 0)),
        "total_plays": int(m["plays"]) if m else 0,
        "total_users": int(m["users"]) if m else 0,
        "spotify_song_id": sp[0] if sp else "",
        "spotify_genres": sp[1] if sp else "",
        "spotify_match_type": sp[2] if sp else "",
    })
dim_df = pd.DataFrame(dim_rows).sort_values(["kcore_users", "song_id"], ascending=[False, True]).reset_index(drop=True)
dim_df.to_csv(os.path.join(CF, "song_dim_kcore.csv"), index=False, encoding="utf-8")
print(f"  song_dim_kcore.csv rows={len(dim_df):,} elapsed={time.time()-t0:.0f}s", flush=True)

pool = pd.read_csv(os.path.join(CF, "song_pool.csv"), dtype=str)
pool["user_count"] = pool["user_count"].astype(int)
named = pool.merge(
    dim_df[["song_id", "title", "artist", "release", "year", "duration_sec", "spotify_genres", "spotify_match_type"]],
    on="song_id", how="left",
)
named.to_csv(os.path.join(CF, "song_pool_named.csv"), index=False, encoding="utf-8")
print(f"  song_pool_named.csv rows={len(named):,} named={int(named['title'].notna().sum()):,}", flush=True)

print("[6/6] 宽表样例（train 前 10 万行）+ 覆盖率 ...", flush=True)
sample = pd.read_csv(os.path.join(CF, "train.csv"), nrows=100000, dtype=str)
sample = sample.merge(
    meta_df[["song_id", "title", "artist", "release", "year", "duration_sec"]],
    on="song_id", how="left",
)
sample.to_csv(os.path.join(CF, "wide_sample.csv"), index=False, encoding="utf-8")

def pct(x, total):
    return round(x / total * 100, 2) if total else 0.0

def present(series):
    return int(series.fillna("").astype(str).str.strip().ne("").sum())


total = len(meta_df)
nonempty = lambda col: present(meta_df[col])
year_ok = int((meta_df["year"].astype(str) != "").sum())
dur_ok = int((meta_df["duration_sec"].astype(str) != "").sum())
rel_ok = nonempty("release")
title_ok = nonempty("title")
artist_ok = nonempty("artist")
title_mask = meta_df["title"].fillna("").astype(str).str.strip().ne("")

kdim_total = len(dim_df)
kdim_named = present(dim_df["title"])
kdim_genre = present(dim_df["spotify_genres"])
pool_named = present(named["title"])
pool_genre = present(named["spotify_genres"])

coverage = {
    "msd_songs": total,
    "total_plays": int(meta_df["plays"].sum()),
    "title_present": {"count": title_ok, "pct": pct(title_ok, total)},
    "artist_present": {"count": artist_ok, "pct": pct(artist_ok, total)},
    "release_present": {"count": rel_ok, "pct": pct(rel_ok, total)},
    "year_present": {"count": year_ok, "pct": pct(year_ok, total)},
    "duration_present": {"count": dur_ok, "pct": pct(dur_ok, total)},
    "played_pct_covered_by_title": pct(int(meta_df.loc[title_mask, "plays"].sum()), int(meta_df["plays"].sum())),
    "kcore": {
        "songs": kdim_total,
        "title_present": kdim_named,
        "title_pct": pct(kdim_named, kdim_total),
        "spotify_genres_present": kdim_genre,
        "spotify_genres_pct": pct(kdim_genre, kdim_total),
        "kcore_interactions": int(sum(kusers.values())),
        "kcore_plays_total": int(sum(kplays.values())),
    },
    "song_pool": {
        "songs": len(named),
        "title_present": pool_named,
        "spotify_genres_present": pool_genre,
    },
    "before": {"kcore_named_from_spotify_map": 4441, "kcore_named_pct": 4.87,
               "spotify_map_songs": 7678, "spotify_map_play_coverage_pct": 14.26},
    "elapsed_seconds": round(time.time() - t0, 1),
}
with open(os.path.join(CF, "msd_meta_coverage.json"), "w", encoding="utf-8") as fh:
    json.dump(coverage, fh, ensure_ascii=False, indent=2)
print(json.dumps(coverage, ensure_ascii=False, indent=2))
print("done", round(time.time() - t0, 1), "s", flush=True)
