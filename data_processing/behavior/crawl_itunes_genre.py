# -*- coding: utf-8 -*-
"""iTunes Search API 爬虫：为 k-core Top N 歌曲补“流派 + 发行日期”。

背景：MusicBrainz 公共 API 对当前网络持续返回 503（限流），先用 Apple iTunes
Search API 做补充采集演示（公开接口、无需 key，单条查询）。许可注意：iTunes
数据版权归 Apple/唱片方，仅供课程内部分析，不随仓库公开分发。

输出：
  cf_data/itunes_crawl_top150.csv    song_id, title, artist, itunes_track, genre_en, genre_zh, release_date, ...
  cf_data/itunes_crawl_stats.json    请求数、命中率、流派覆盖率、耗时、限速
  cf_data/itunes_crawl_cache.jsonl   断点续传缓存
"""
import argparse
import csv
import difflib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

CF = r"D:\desktop\音乐推荐数据\cf_data"
OUT_CSV = os.path.join(CF, "itunes_crawl_top150.csv")
OUT_STATS = os.path.join(CF, "itunes_crawl_stats.json")
CACHE = os.path.join(CF, "itunes_crawl_cache.jsonl")
RATE = 2.5
UA = {"User-Agent": "MusicRecommendCourse/1.0 (student project; contact: https://github.com/chihayaanon0815-ux/music-recommendation-system)"}

# iTunes 流派 -> 项目 31 类
GENRE_MAP = {
    "pop": "流行", "rock": "摇滚", "alternative": "摇滚", "metal": "金属",
    "punk": "朋克", "electronic": "电子", "dance": "舞曲", "house": "电子",
    "techno": "电子", "hip-hop/rap": "嘻哈", "r&b/soul": "节奏布鲁斯",
    "soul": "灵魂乐", "jazz": "爵士", "classical": "古典", "country": "乡村",
    "blues": "蓝调", "folk": "民谣", "singer/songwriter": "民谣",
    "reggae": "雷鬼", "latin": "拉丁", "world": "世界音乐", "new age": "轻音乐",
    "easy listening": "轻音乐", "vocal": "轻音乐", "soundtrack": "影视",
    "anime": "ACG", "children's music": "儿童", "comedy": "喜剧",
    "holiday": "流行",
}


def norm(text):
    text = (text or "").lower()
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similar(a, b, threshold=0.6):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= threshold


def query(term):
    params = urllib.parse.urlencode({"term": term, "entity": "song", "limit": 5, "country": "US"})
    url = "https://itunes.apple.com/search?" + params
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429, 503) and attempt < 2:
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except Exception:
            if attempt < 2:
                time.sleep(5)
                continue
            raise
    raise RuntimeError("unreachable")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=150)
    args = parser.parse_args()

    import pandas as pd

    dim = pd.read_csv(os.path.join(CF, "song_dim_kcore.csv"), dtype={"song_id": str},
                      keep_default_na=False, low_memory=False)
    rows = dim.sort_values("kcore_users", ascending=False).head(args.limit)
    print("target songs:", len(rows), flush=True)

    cache = {}
    if os.path.isfile(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    item = json.loads(line)
                    cache[item["song_id"]] = item

    t0 = time.time()
    requests_made = 0
    hits = genre_hits = 0
    results = []
    with open(CACHE, "a", encoding="utf-8") as cache_fh:
        for i, row in enumerate(rows.itertuples(index=False), start=1):
            sid = row.song_id
            if sid in cache:
                results.append(cache[sid])
                if cache[sid].get("itunes_track"):
                    hits += 1
                if cache[sid].get("genre_zh"):
                    genre_hits += 1
                continue
            title = (row.title or "").strip()
            artist = (row.artist or "").strip()
            best = None
            try:
                payload = query(f"{title} {artist}")
                requests_made += 1
                for item in payload.get("results") or []:
                    tn = item.get("trackName") or ""
                    an = item.get("artistName") or ""
                    if not similar(title, tn) or not similar(artist, an, 0.5):
                        continue
                    if best is None:
                        best = item
                time.sleep(RATE)
            except Exception as exc:
                print(f"  {sid} failed: {exc}", flush=True)

            genre_en = (best.get("primaryGenreName") or "").strip() if best else ""
            genre_zh = GENRE_MAP.get(genre_en.lower(), "")
            item = {
                "song_id": sid,
                "title": title,
                "artist": artist,
                "kcore_users": int(row.kcore_users),
                "itunes_track_id": best.get("trackId") if best else "",
                "itunes_track": (best.get("trackName") or "").strip() if best else "",
                "itunes_artist": (best.get("artistName") or "").strip() if best else "",
                "genre_en": genre_en,
                "genre_zh": genre_zh,
                "release_date": (best.get("releaseDate") or "")[:10] if best else "",
                "collection": (best.get("collectionName") or "").strip() if best else "",
            }
            cache[sid] = item
            cache_fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            cache_fh.flush()
            results.append(item)
            if item["itunes_track"]:
                hits += 1
            if genre_zh:
                genre_hits += 1
            if i % 25 == 0:
                print(f"  {i}/{len(rows)} hits={hits} genres={genre_hits} elapsed={time.time()-t0:.0f}s", flush=True)

    fields = ["song_id", "title", "artist", "kcore_users", "itunes_track_id", "itunes_track",
              "itunes_artist", "genre_en", "genre_zh", "release_date", "collection"]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)

    stats = {
        "source": "Apple iTunes Search API",
        "target_songs": len(rows),
        "matched_tracks": hits,
        "match_rate_pct": round(hits / len(rows) * 100, 2),
        "with_genre": genre_hits,
        "genre_coverage_pct": round(genre_hits / len(rows) * 100, 2),
        "api_requests": requests_made,
        "elapsed_seconds": round(time.time() - t0, 1),
        "rate_limit_seconds": RATE,
        "note": "只做单条查询；按歌名+歌手相似度校验，避免错配；流派按 iTunes 主流派映射到项目 31 类。",
    }
    with open(OUT_STATS, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
