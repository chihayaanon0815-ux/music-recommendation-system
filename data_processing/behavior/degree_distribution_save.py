# -*- coding: utf-8 -*-
"""统计行为数据的度数分布与播放量分布，落盘为绘图用的 JSON。"""
import json
import time
from collections import Counter

PATH = r"D:\DSH-Work\msd\train_triplets.txt"
OUT = r"D:\desktop\音乐推荐数据\cf_data\data_quality.json"

t0 = time.time()
user_deg = Counter()
song_deg = Counter()
play_hist = Counter()
total_plays = 0
rows = 0

with open(PATH, encoding="utf-8") as fh:
    for line in fh:
        user, song, play = line.rstrip("\n").split("\t")
        user_deg[user] += 1
        song_deg[song] += 1
        play_hist[int(play)] += 1
        total_plays += int(play)
        rows += 1

def quantiles(counter, qs):
    vals = sorted(counter.values())
    n = len(vals)
    return {str(q): vals[min(n - 1, int(q * n))] for q in qs}

def hist_arrays(counter):
    hist = Counter(counter.values())
    xs = sorted(hist)
    return {"x": xs, "y": [hist[x] for x in xs]}

result = {
    "rows": rows,
    "total_plays": total_plays,
    "users": len(user_deg),
    "songs": len(song_deg),
    "user_degree_quantiles": quantiles(user_deg, [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]),
    "song_degree_quantiles": quantiles(song_deg, [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]),
    "users_ge_20": sum(1 for v in user_deg.values() if v >= 20),
    "users_ge_50": sum(1 for v in user_deg.values() if v >= 50),
    "songs_ge_50": sum(1 for v in song_deg.values() if v >= 50),
    "songs_ge_100": sum(1 for v in song_deg.values() if v >= 100),
    "user_degree_hist": hist_arrays(user_deg),
    "song_degree_hist": hist_arrays(song_deg),
    "play_count_hist": {"x": sorted(play_hist), "y": [play_hist[x] for x in sorted(play_hist)]},
    "elapsed_seconds": round(time.time() - t0, 1),
}
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2)
print(json.dumps({k: v for k, v in result.items() if "hist" not in k}, ensure_ascii=False, indent=2))

