# -*- coding: utf-8 -*-
"""用 MusicBrainz 官方 API 给 MSD 热门歌曲补充流派/标签（CC0 核心数据，1 请求/秒）。

输入：D:\\DSH-Work\\msd_linked_tmp\\part-*.csv（song_id, plays, artist, title）
输出：D:\\DSH-Work\\mb_tags_topN.csv、D:\\DSH-Work\\mb_tags_stats.json
缓存：D:\\DSH-Work\\mb_tags_cache.jsonl（可续跑）
"""
import csv
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

UA = "DSH-CourseProject-DataCollector/1.0 (student project; https://github.com/chihayaanon0815-ux/music-recommendation-system)"
API = "https://musicbrainz.org/ws/2"
RATE = 1.1
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
OUT_CSV = r"D:\desktop\音乐推荐数据\cf_data\mb_tags_topN.csv"
OUT_STATS = r"D:\desktop\音乐推荐数据\cf_data\mb_tags_stats.json"
CACHE = r"D:\desktop\音乐推荐数据\cf_data\mb_tags_cache.jsonl"


def api_get(path: str, params: dict) -> dict:
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 503 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


cache = {}
if os.path.isfile(CACHE):
    for line in open(CACHE, encoding="utf-8"):
        line = line.strip()
        if line:
            item = json.loads(line)
            cache[item["song_id"]] = item

msd = pd.read_csv(glob.glob(r"D:\DSH-Work\msd_linked_tmp\part-*.csv")[0], dtype=str)
msd["plays"] = pd.to_numeric(msd["plays"], errors="coerce").fillna(0).astype("int64")
msd = msd.sort_values("plays", ascending=False).drop_duplicates("song_id").head(N)

rows = []
fetched = cached = 0
t0 = time.time()
with open(CACHE, "a", encoding="utf-8") as cache_fh:
    for i, row in enumerate(msd.itertuples(), 1):
        song_id = row.song_id
        if song_id in cache:
            item = cache[song_id]
            cached += 1
        else:
            query = f'recording:"{row.title}" AND artist:"{row.artist}"'
            try:
                search = api_get("recording", {"query": query, "fmt": "json", "limit": 3})
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}] search failed {row.title[:30]} {exc}", file=sys.stderr)
                search = {}
            time.sleep(RATE)
            rec = None
            for cand in search.get("recordings") or []:
                credits = cand.get("artist-credit") or []
                name = "".join((c.get("name") or "") for c in credits if isinstance(c, dict))
                if name.strip().lower() == str(row.artist).strip().lower():
                    rec = cand
                    break
            if rec is None and (search.get("recordings") or []):
                rec = search["recordings"][0]
            tags, genres, mb_id = [], [], ""
            if rec:
                mb_id = rec.get("id", "")
                try:
                    detail = api_get(f"recording/{mb_id}", {"inc": "tags+genres", "fmt": "json"})
                except Exception:  # noqa: BLE001
                    detail = {}
                time.sleep(RATE)
                tags = [t.get("name", "") for t in detail.get("tags") or [] if t.get("name")]
                genres = [g.get("name", "") for g in detail.get("genres") or [] if g.get("name")]
            item = {
                "song_id": song_id, "title": row.title, "artist": row.artist,
                "mb_recording_id": mb_id, "tags": tags, "genres": genres,
            }
            cache[song_id] = item
            cache_fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            cache_fh.flush()
            fetched += 1
            if fetched % 25 == 0:
                print(f"  fetched {fetched} ({i}/{N}) elapsed={time.time()-t0:.0f}s", file=sys.stderr)
        rows.append(item)

with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
    writer = csv.writer(fh, lineterminator="\n")
    writer.writerow(["song_id", "title", "artist", "mb_recording_id", "tags", "genres"])
    for item in rows:
        writer.writerow([item["song_id"], item["title"], item["artist"],
                         item["mb_recording_id"], "|".join(item["tags"]), "|".join(item["genres"])])

matched = sum(1 for r in rows if r["mb_recording_id"])
with_tags = sum(1 for r in rows if r["tags"])
stats = {
    "requested": len(rows),
    "matched_recording": matched,
    "with_tags": with_tags,
    "with_genres": sum(1 for r in rows if r["genres"]),
    "fetched": fetched,
    "from_cache": cached,
    "elapsed_seconds": round(time.time() - t0, 1),
    "sample": rows[:5],
}
with open(OUT_STATS, "w", encoding="utf-8") as fh:
    json.dump(stats, fh, ensure_ascii=False, indent=2)
print(json.dumps({k: v for k, v in stats.items() if k != "sample"}, ensure_ascii=False, indent=2))
