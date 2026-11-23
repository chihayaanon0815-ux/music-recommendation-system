import json, time

users = set()
songs = set()
n = 0
total_plays = 0
play_hist = {}
t0 = time.time()

with open(r"D:\desktop\音乐推荐数据\train_triplets.txt", encoding="utf-8") as f:
    for line in f:
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 3:
            continue
        u, s, c = parts
        c = int(c)
        users.add(u)
        songs.add(s)
        total_plays += c
        play_hist[c] = play_hist.get(c, 0) + 1
        n += 1
        if n % 5_000_000 == 0:
            print(f"scanned {n:,} lines, elapsed {time.time()-t0:.0f}s", flush=True)

result = {
    "records": n,
    "unique_users": len(users),
    "unique_songs": len(songs),
    "total_play_count": total_plays,
    "play_count_histogram": dict(sorted(play_hist.items())),
}
with open(r"D:\desktop\音乐推荐数据\triplets_stats.json", "w", encoding="utf-8") as out:
    json.dump(result, out, ensure_ascii=False, indent=2)
print(json.dumps({k: v for k, v in result.items() if k != "play_count_histogram"}, indent=2))
print("elapsed", round(time.time() - t0, 1), "s")
