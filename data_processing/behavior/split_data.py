import csv, json, random, os, time

IN = r"D:\desktop\音乐推荐数据\cf_data\interactions.csv"
OUT_DIR = r"D:\desktop\音乐推荐数据\cf_data"
SEED = 42

random.seed(SEED)
t0 = time.time()
user_items = {}
song_set = set()

with open(IN, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        user_items.setdefault(row["user_id"], []).append((row["song_id"], int(row["play_count"])))
        song_set.add(row["song_id"])

user_idx = {u: i for i, u in enumerate(sorted(user_items))}
song_idx = {s: i for i, s in enumerate(sorted(song_set))}

with open(os.path.join(OUT_DIR, "id_maps.json"), "w", encoding="utf-8") as m:
    json.dump({"users": user_idx, "songs": song_idx}, m)

n_train = n_test = 0
with open(os.path.join(OUT_DIR, "train.csv"), "w", encoding="utf-8", newline="\n") as tr, \
     open(os.path.join(OUT_DIR, "test.csv"), "w", encoding="utf-8", newline="\n") as te:
    tr.write("user_id,song_id,play_count\n")
    te.write("user_id,song_id\n")
    for u, items in user_items.items():
        if len(items) < 2:
            for s, c in items:
                tr.write(f"{u},{s},{c}\n")
                n_train += 1
            continue
        pick = random.randrange(len(items))
        for i, (s, c) in enumerate(items):
            if i == pick:
                te.write(f"{u},{s}\n")
                n_test += 1
            else:
                tr.write(f"{u},{s},{c}\n")
                n_train += 1

print(json.dumps({
    "users": len(user_items),
    "songs": len(song_set),
    "train_rows": n_train,
    "test_rows": n_test,
    "elapsed": round(time.time() - t0, 1),
}, indent=2))
