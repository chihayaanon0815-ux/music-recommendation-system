import csv, json, time, sys

t0 = time.time()
with open(r"D:\desktop\音乐推荐数据\cf_data\id_maps.json", encoding="utf-8") as f:
    maps = json.load(f)
song_idx = maps["songs"]
NS = len(song_idx)

pairs = set()
cur_user = None
items = []
def flush(items):
    items.sort()
    for a in range(len(items)):
        ia = items[a]
        base = ia * NS
        for b in range(a + 1, len(items)):
            pairs.add(base + items[b])

with open(r"D:\desktop\音乐推荐数据\cf_data\train.csv", encoding="utf-8") as f:
    rd = csv.reader(f)
    next(rd)
    for u, s, c in rd:
        if u != cur_user:
            if items:
                flush(items)
            cur_user = u
            items = []
        items.append(song_idx[s])
    if items:
        flush(items)

print("unique co-occurrence pairs:", f"{len(pairs):,}")
print("elapsed:", round(time.time() - t0, 1), "s")
print("rough set memory MB:", round(sys.getsizeof(next(iter(pairs))) * len(pairs) / 1e6, 1))
