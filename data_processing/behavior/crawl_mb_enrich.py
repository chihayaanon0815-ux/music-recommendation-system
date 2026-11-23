# -*- coding: utf-8 -*-
"""MusicBrainz 补标签爬虫（合规、限速 1 请求/秒）。

目标：对 k-core 播放量 Top N 的歌曲，按“歌名 + 歌手”检索 MusicBrainz 录音，
命中后回查标签/流派，输出可复核的采集表与统计。

数据源：MusicBrainz Web Service v2（CC0 1.0），要求 User-Agent 可识别且 ≤1 req/s。
输出：
  cf_data/mb_crawl_top500.csv     逐首采集结果
  cf_data/mb_crawl_stats.json     请求数、命中率、标签覆盖率、耗时
  cf_data/mb_crawl_cache.jsonl    断点续传缓存（每首一行）

用法：
  python crawl_mb_enrich.py [--limit 500]
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
OUT_CSV = os.path.join(CF, "mb_crawl_top150.csv")
OUT_STATS = os.path.join(CF, "mb_crawl_stats.json")
CACHE = os.path.join(CF, "mb_crawl_cache.jsonl")
API = "https://musicbrainz.org/ws/2"
UA = "MusicRecommendCourse/1.0 (student project; contact: https://github.com/chihayaanon0815-ux/music-recommendation-system)"
RATE = 2.5


def norm(text):
    text = (text or "").lower()
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def artist_matches(a, b, threshold=0.6):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= threshold


def api_get(path, params, retries=4):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < retries - 1:
                wait = 15 * (attempt + 1)
                print(f"  503/429，等待 {wait}s 后重试", flush=True)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def load_cache():
    cache = {}
    if os.path.isfile(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    item = json.loads(line)
                    cache[item["song_id"]] = item
    return cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    import pandas as pd

    dim = pd.read_csv(os.path.join(CF, "song_dim_kcore.csv"), dtype={"song_id": str}, keep_default_na=False)
    rows = dim.sort_values("kcore_users", ascending=False).head(args.limit)
    print("target songs:", len(rows), flush=True)

    cache = load_cache()
    t0 = time.time()
    requests_made = 0
    hits = 0
    tag_hits = 0
    genre_hits = 0
    results = []

    with open(CACHE, "a", encoding="utf-8") as cache_fh:
        for i, row in enumerate(rows.itertuples(index=False), start=1):
            sid = row.song_id
            title = (row.title or "").strip()
            artist = (row.artist or "").strip()
            if sid in cache:
                results.append(cache[sid])
                if cache[sid].get("mb_recording_id"):
                    hits += 1
                if cache[sid].get("tags"):
                    tag_hits += 1
                if cache[sid].get("genres"):
                    genre_hits += 1
                continue

            rec_id = ""
            score = ""
            match_title = ""
            match_artist = ""
            tags = ""
            genres = ""
            first_release = ""
            try:
                search_title = re.sub(r"[\(\[].*?[\)\]]", "", title).strip() or title
                query = f'recording:"{search_title}" AND artist:"{artist}"'
                payload = api_get("recording", {"query": query, "fmt": "json", "limit": 3})
                requests_made += 1
                time.sleep(RATE)
                best = None
                for rec in payload.get("recordings") or []:
                    if rec.get("video"):
                        continue
                    credit = "".join(
                        (c.get("name") or "") + (c.get("joinphrase") or "")
                        for c in rec.get("artist-credit") or [] if isinstance(c, dict)
                    ).strip()
                    if not artist_matches(artist, credit):
                        continue
                    if best is None or (rec.get("score") or 0) > (best.get("score") or 0):
                        best = rec
                        best_credit = credit
                if best and (best.get("score") or 0) >= 80:
                    rec_id = best.get("id") or ""
                    score = best.get("score") or ""
                    match_title = (best.get("title") or "").strip()
                    match_artist = best_credit
                    if rec_id:
                        # 注意：inc=tags+genres 组合会被 API 拒绝（503），这里只取 tags；
                        # genres 需要单独一个请求，为控制请求数不取。
                        detail = api_get(f"recording/{rec_id}", {"inc": "tags", "fmt": "json"})
                        requests_made += 1
                        time.sleep(RATE)
                        tag_list = [t.get("name") or "" for t in detail.get("tags") or [] if t.get("name")]
                        tags = "|".join(sorted(tag_list)[:10])
                        first_release = detail.get("first-release-date") or ""
            except Exception as exc:
                print(f"  song {sid} failed: {exc}", flush=True)

            item = {
                "song_id": sid,
                "title": title,
                "artist": artist,
                "kcore_users": int(row.kcore_users),
                "mb_recording_id": rec_id,
                "match_score": score,
                "match_title": match_title,
                "match_artist": match_artist,
                "tags": tags,
                "genres": genres,
                "first_release_date": first_release,
            }
            cache[sid] = item
            cache_fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            cache_fh.flush()
            results.append(item)
            if rec_id:
                hits += 1
            if tags:
                tag_hits += 1
            if genres:
                genre_hits += 1
            if i % 25 == 0:
                print(f"  {i}/{len(rows)} hits={hits} tags={tag_hits} elapsed={time.time()-t0:.0f}s", flush=True)

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        fields = ["song_id", "title", "artist", "kcore_users", "mb_recording_id", "match_score",
                  "match_title", "match_artist", "tags", "genres", "first_release_date"]
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)

    elapsed = round(time.time() - t0, 1)
    stats = {
        "target_songs": len(rows),
        "matched_recordings": hits,
        "match_rate_pct": round(hits / len(rows) * 100, 2),
        "with_tags": tag_hits,
        "tag_rate_pct": round(tag_hits / len(rows) * 100, 2),
        "with_genres": genre_hits,
        "genre_rate_pct": round(genre_hits / len(rows) * 100, 2),
        "api_requests": requests_made,
        "elapsed_seconds": elapsed,
        "rate_limit_seconds": RATE,
        "source": "MusicBrainz Web Service v2 (CC0 1.0)",
        "user_agent": UA,
        "note": "检索 score>=80 才接受；未命中/低分保留空值，不做编造。",
    }
    with open(OUT_STATS, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


