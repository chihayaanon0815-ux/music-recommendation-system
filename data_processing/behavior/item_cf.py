import csv, json, time, os, random
import numpy as np

BASE = r"D:\desktop\音乐推荐数据\cf_data"
POOL_N = 5000
TOP_K = 10
EVAL_USERS = 2000
SEED = 42
random.seed(SEED)
t0 = time.time()

with open(os.path.join(BASE, "id_maps.json"), encoding="utf-8") as f:
    maps = json.load(f)
song_idx = maps["songs"]
idx_song = {i: s for s, i in song_idx.items()}
NS = len(song_idx)

# 1. 统计物品度数，同时缓存用户交互
user_items = {}
deg = np.zeros(NS, dtype=np.int64)
with open(os.path.join(BASE, "train.csv"), encoding="utf-8") as f:
    rd = csv.reader(f)
    next(rd)
    for u, s, c in rd:
        si = song_idx[s]
        user_items.setdefault(u, []).append(si)
        deg[si] += 1
print(f"loaded train: {len(user_items):,} users, {time.time()-t0:.0f}s", flush=True)

# 2. 热门物品池
pool = np.sort(np.argsort(-deg)[:POOL_N])
in_pool = np.zeros(NS, dtype=bool)
in_pool[pool] = True
pos = {int(s): i for i, s in enumerate(pool)}
with open(os.path.join(BASE, "song_pool.csv"), "w", encoding="utf-8", newline="\n") as fp:
    fp.write("song_id,user_count\n")
    for s in pool:
        fp.write(f"{idx_song[int(s)]},{int(deg[s])}\n")

# 3. 共现矩阵（仅池内）
co = np.zeros((POOL_N, POOL_N), dtype=np.int32)
for u, items in user_items.items():
    pi = sorted(pos[i] for i in items if in_pool[i])
    for a in range(len(pi)):
        ia = pi[a]
        for b in range(a, len(pi)):
            ib = pi[b]
            co[ia, ib] += 1
print(f"co-occurrence done, {time.time()-t0:.0f}s", flush=True)

# 4. 余弦相似度
d = np.sqrt(deg[pool].astype(np.float64))
sim = co / np.outer(d, d)
np.fill_diagonal(sim, 0.0)
np.save(os.path.join(BASE, "similarity.npy"), sim)

# 5. 测试集
test = {}
with open(os.path.join(BASE, "test.csv"), encoding="utf-8") as f:
    rd = csv.reader(f)
    next(rd)
    for u, s in rd:
        test[u] = song_idx[s]

# 6. 抽样评估
eval_users = random.sample(list(user_items.keys()), min(EVAL_USERS, len(user_items)))
hits = 0
recall_sum = 0.0
precision_sum = 0.0
recommended = set()
test_in_pool = 0
examples = []

for u in eval_users:
    items = user_items[u]
    pi = sorted(pos[i] for i in items if in_pool[i])
    target = test[u]
    if in_pool[target]:
        test_in_pool += 1
    if pi:
        scores = sim[pi].sum(axis=0)
        scores[pi] = -1.0
        top = pool[np.argsort(-scores)[:TOP_K]]
    else:
        top = np.array([], dtype=np.int64)
    recommended.update(int(x) for x in top)
    if target in top:
        hits += 1
    precision_sum += len(set(top) & {target}) / TOP_K
    recall_sum += len(set(top) & {target})
    if len(examples) < 100:
        examples.append({"user_id": u, "recommendations": [idx_song[int(x)] for x in top]})

n = len(eval_users)
metrics = {
    "pool_size": POOL_N,
    "eval_users": n,
    "test_target_in_pool": test_in_pool,
    "test_target_in_pool_ratio": round(test_in_pool / n, 4),
    "hit_rate_at_10": round(hits / n, 4),
    "precision_at_10": round(precision_sum / n, 4),
    "recall_at_10": round(recall_sum / n, 4),
    "recommendation_coverage_in_pool": round(len(recommended) / POOL_N, 4),
    "elapsed_seconds": round(time.time() - t0, 1),
}
with open(os.path.join(BASE, "cf_metrics.json"), "w", encoding="utf-8") as m:
    json.dump(metrics, m, ensure_ascii=False, indent=2)
with open(os.path.join(BASE, "sample_recommendations.json"), "w", encoding="utf-8") as m:
    json.dump(examples, m, ensure_ascii=False, indent=2)
print(json.dumps(metrics, indent=2))
