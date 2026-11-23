# -*- coding: utf-8 -*-
"""用户兴趣标签分析：CF 历史 × MSD 艺术家标签（artist_term.db）→ 用户风格画像。

输出：
  D:\\DSH-Work\\user_interest_tags.json
  D:\\DSH-Work\\user_profiles.csv
"""
import csv
import json
import random
import sqlite3
import time
from collections import Counter, defaultdict

import pandas as pd

TRAIN = r"D:\desktop\音乐推荐数据\cf_data\train.csv"
TRACK_DB = r"D:\DSH-Work\msd\track_metadata.db"
TERM_DB = r"D:\DSH-Work\msd\artist_term.db"
GENRE_MAP = r"D:\desktop\音乐推荐数据\音乐推荐\data_processing\genre_map_zh.csv"
OUT_JSON = r"D:\desktop\音乐推荐数据\cf_data\user_interest_tags.json"
OUT_CSV = r"D:\desktop\音乐推荐数据\cf_data\user_profiles.csv"

SAMPLE_USERS = 1000
SEED = 42
NOISE = {
    "seen live", "favorite", "favorites", "favourite", "favourites", "awesome", "love",
    "loved", "beautiful", "cool", "great", "good", "best", "spotify", "lastfm",
    "albums i own", "under 2000 listeners", "male vocalists", "female vocalists",
    "usa", "uk", "american", "british", "english", "singer-songwriter",
}

t0 = time.time()

# 1) 英文标签 -> 中文大类（与项目的 31 类一致）
genre_map = {}
for row in csv.DictReader(open(GENRE_MAP, encoding="utf-8")):
    en = (row.get("genre") or "").strip().lower()
    group = (row.get("group_zh") or row.get("genre_zh") or "").strip()
    if en and group:
        genre_map[en] = group
print("genre_map", len(genre_map), flush=True)

# 2) song_id -> artist_id（100 万行）
conn = sqlite3.connect(TRACK_DB)
song_artist = {song: artist for song, artist in conn.execute("select song_id, artist_id from songs")}
conn.close()
print("song_artist", len(song_artist), flush=True)

# 3) artist_id -> terms
conn = sqlite3.connect(TERM_DB)
artist_terms = defaultdict(list)
for artist, term in conn.execute("select artist_id, term from artist_term"):
    artist_terms[artist].append(term.lower())
conn.close()
print("artists_with_terms", len(artist_terms), flush=True)

# 全局标签基线（用于计算“相对兴趣” lift，抵消 rock 这类高频通用标签）
global_group = Counter()
for terms in artist_terms.values():
    for term in terms:
        group = genre_map.get(term)
        if group:
            global_group[group] += 1
total_global = sum(global_group.values())
global_share = {g: v / total_global for g, v in global_group.items()}
print("global_group", len(global_group), "total", total_global, flush=True)

# 4) 抽样用户，扫描 train.csv 收集其历史
user_ids = set()
with open(r"D:\desktop\音乐推荐数据\cf_data\id_maps.json", encoding="utf-8") as fh:
    maps = json.load(fh)
all_users = list(maps["users"].keys())
random.seed(SEED)
sample_users = set(random.sample(all_users, SAMPLE_USERS))

history = defaultdict(list)
scanned = 0
with open(TRAIN, encoding="utf-8") as fh:
    rd = csv.reader(fh)
    next(rd)
    for user, song, play in rd:
        scanned += 1
        if user in sample_users:
            history[user].append((song, int(play)))
print(f"scanned={scanned:,} sampled_users={len(history)} elapsed={time.time()-t0:.0f}s", flush=True)

# 5) 聚合每个用户的中文大类与原始标签
top_groups = Counter()
raw_tags = Counter()
group_play_weight = Counter()
top1_counter = Counter()
top1_lift_counter = Counter()
lift_accum = defaultdict(float)
lift_users = Counter()
distinct_groups = []
profiles = []
users_with_group = users_with_tag = 0
for user in sorted(sample_users):
    rows = history.get(user, [])
    group_score = Counter()
    tag_score = Counter()
    for song, play in rows:
        artist = song_artist.get(song)
        terms = artist_terms.get(artist, [])
        for term in terms:
            if term in NOISE or len(term) < 3:
                continue
            tag_score[term] += play
            group = genre_map.get(term)
            if group:
                group_score[group] += play
    if tag_score:
        users_with_tag += 1
    lifts = {}
    if group_score:
        users_with_group += 1
        top1_counter[group_score.most_common(1)[0][0]] += 1
        distinct_groups.append(len(group_score))
        group_play_weight.update(group_score)
        user_total = sum(group_score.values())
        for g, s in group_score.items():
            if s >= 2 and global_share.get(g):
                lifts[g] = (s / user_total) / global_share[g]
        if lifts:
            top_g = max(lifts, key=lifts.get)
            top1_lift_counter[top_g] += 1
            for g, v in lifts.items():
                lift_accum[g] += v
                lift_users[g] += 1
    top_groups.update({g: 1 for g in group_score})
    raw_tags.update(tag_score)
    profiles.append({
        "user_id": user,
        "history_songs": len(rows),
        "top_groups": "|".join(f"{g}:{s}" for g, s in group_score.most_common(5)),
        "top_groups_lift": "|".join(
            f"{g}:{v:.2f}" for g, v in sorted(lifts.items(), key=lambda kv: -kv[1])[:5]
        ),
        "top_terms": "|".join(f"{t}:{s}" for t, s in tag_score.most_common(5)),
    })

with open(OUT_CSV, "w", encoding="utf-8", newline="\n") as fh:
    writer = csv.DictWriter(fh, fieldnames=[
        "user_id", "history_songs", "top_groups", "top_groups_lift", "top_terms",
    ], lineterminator="\n")
    writer.writeheader()
    writer.writerows(profiles)

stats = {
    "sample_users": len(sample_users),
    "users_with_history": len(history),
    "users_with_terms": users_with_tag,
    "users_with_mapped_group": users_with_group,
    "group_coverage_pct": round(users_with_group / len(sample_users) * 100, 2),
    "avg_distinct_groups_per_user": round(sum(distinct_groups) / len(distinct_groups), 2) if distinct_groups else 0,
    "group_play_weight_share": [
        {"group": g, "weight": int(w), "share_pct": round(w / sum(group_play_weight.values()) * 100, 2)}
        for g, w in group_play_weight.most_common(15)
    ],
    "top1_group_distribution": [
        {"group": g, "users": int(c), "share_pct": round(c / users_with_group * 100, 2)}
        for g, c in top1_counter.most_common(15)
    ] if users_with_group else [],
    "top1_group_by_lift": [
        {"group": g, "users": int(c), "share_pct": round(c / sum(top1_lift_counter.values()) * 100, 2)}
        for g, c in top1_lift_counter.most_common(15)
    ] if top1_lift_counter else [],
    "avg_lift_by_group": [
        {"group": g, "avg_lift": round(lift_accum[g] / lift_users[g], 2), "users": int(lift_users[g])}
        for g in sorted(lift_accum, key=lambda x: -lift_accum[x] / lift_users[x])[:15]
    ],
    "top_terms": raw_tags.most_common(20),
    "sample_profiles": profiles[:5],
    "elapsed_seconds": round(time.time() - t0, 1),
}
with open(OUT_JSON, "w", encoding="utf-8") as fh:
    json.dump(stats, fh, ensure_ascii=False, indent=2)
print(json.dumps({k: v for k, v in stats.items() if k not in ("sample_profiles",)}, ensure_ascii=False, indent=2)[:2500])
