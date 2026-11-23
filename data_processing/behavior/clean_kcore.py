import json, time, os

SRC = r"D:\desktop\音乐推荐数据\train_triplets.txt"
OUT_DIR = r"D:\desktop\音乐推荐数据\cf_data"
USER_K = 20
SONG_K = 50

os.makedirs(OUT_DIR, exist_ok=True)
t0 = time.time()

alive_users, alive_songs = None, None
round_id = 0
while True:
    round_id += 1
    user_deg, song_deg = {}, {}
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            u, s, c = line.rstrip("\n").split("\t")
            if alive_users is not None and (u not in alive_users or s not in alive_songs):
                continue
            user_deg[u] = user_deg.get(u, 0) + 1
            song_deg[s] = song_deg.get(s, 0) + 1
    new_users = {u for u, d in user_deg.items() if d >= USER_K}
    new_songs = {s for s, d in song_deg.items() if d >= SONG_K}
    print(f"round {round_id}: users={len(new_users):,} songs={len(new_songs):,} elapsed={time.time()-t0:.0f}s", flush=True)
    if new_users == alive_users and new_songs == alive_songs:
        break
    alive_users, alive_songs = new_users, new_songs

n_rows = 0
total_plays = 0
out_path = os.path.join(OUT_DIR, "interactions.csv")
with open(SRC, encoding="utf-8") as f, open(out_path, "w", encoding="utf-8", newline="\n") as out:
    out.write("user_id,song_id,play_count\n")
    for line in f:
        u, s, c = line.rstrip("\n").split("\t")
        if u in alive_users and s in alive_songs:
            c = int(c)
            out.write(f"{u},{s},{c}\n")
            n_rows += 1
            total_plays += c

metrics = {
    "kcore_user_k": USER_K,
    "kcore_song_k": SONG_K,
    "rounds": round_id,
    "kept_users": len(alive_users),
    "kept_songs": len(alive_songs),
    "kept_interactions": n_rows,
    "kept_total_play_count": total_plays,
    "density": n_rows / (len(alive_users) * len(alive_songs)),
    "elapsed_seconds": round(time.time() - t0, 1),
}
with open(os.path.join(OUT_DIR, "clean_metrics.json"), "w", encoding="utf-8") as m:
    json.dump(metrics, m, ensure_ascii=False, indent=2)
print(json.dumps(metrics, indent=2))
