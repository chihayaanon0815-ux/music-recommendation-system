#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 MusicBrainz 公共 API 采集带风格标签的录音数据。

数据源：MusicBrainz Web Service v2（https://musicbrainz.org/doc/MusicBrainz_API）。
许可：核心数据为 CC0 1.0（公有领域），见 https://musicbrainz.org/doc/About/Data_License。
API 要求：请求必须带可识别的 User-Agent，且平均不超过 1 请求/秒。

用法（在仓库根目录）：
    python data_processing/fetch_musicbrainz.py --out data/raw/musicbrainz_raw.csv
    python data_processing/fetch_musicbrainz.py --per-genre 60 --out data/raw/musicbrainz_raw.csv

输出为原始采集表 data/raw/musicbrainz_raw.csv，列为：
    song_id,song_name,artist,genres_en,genres,first_release_date,source_url
清洗与统计由 clean_songs.py（PySpark local）完成。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_ROOT = "https://musicbrainz.org/ws/2"
USER_AGENT = "DSH-CourseProject-DataCollector/1.0 (student project; 3378625648@qq.com)"
RATE_LIMIT_SECONDS = 1.1

# 课程展示使用中文风格名；此处为显式的英文标签 -> 中文展示名映射，
# 只采集该表中的标签，避免把无法映射的自由标签混入成品。
GENRE_MAP = [
    ("pop", "流行"),
    ("rock", "摇滚"),
    ("jazz", "爵士"),
    ("electronic", "电子"),
    ("folk", "民谣"),
    ("classical", "古典"),
    ("metal", "金属"),
    ("hip hop", "嘻哈"),
    ("country", "乡村"),
    ("blues", "布鲁斯"),
    ("soul", "灵魂乐"),
    ("rhythm and blues", "节奏布鲁斯"),
    ("reggae", "雷鬼"),
    ("punk", "朋克"),
    ("indie rock", "独立摇滚"),
    ("alternative rock", "另类摇滚"),
    ("funk", "放克"),
    ("disco", "迪斯科"),
    ("house", "浩室"),
    ("techno", "科技舞曲"),
    ("gospel", "福音"),
]

# 抽样权重：决定各风格进入成品的比例。这是抽样设计，不代表流行度；
# 权重起伏让风格统计图可读，也避免每个风格数量完全一致。
GENRE_WEIGHTS = {
    "pop": 12,
    "rock": 12,
    "jazz": 9,
    "electronic": 9,
    "folk": 8,
    "classical": 8,
    "metal": 8,
    "hip hop": 8,
    "country": 7,
    "blues": 7,
    "soul": 7,
    "rhythm and blues": 5,
    "reggae": 5,
    "punk": 5,
    "indie rock": 5,
    "alternative rock": 5,
    "funk": 4,
    "disco": 3,
    "house": 3,
    "techno": 3,
    "gospel": 2,
}


def compute_quotas(total: int) -> dict[str, int]:
    """按权重把总量分配到各风格，最大余数法保证总和等于 total。"""
    ordered = [en for en, _ in GENRE_MAP]
    weight_sum = sum(GENRE_WEIGHTS[en] for en in ordered)
    exact = {en: total * GENRE_WEIGHTS[en] / weight_sum for en in ordered}
    quotas = {en: int(exact[en]) for en in ordered}
    remainder = total - sum(quotas.values())
    ranked = sorted(ordered, key=lambda en: (exact[en] - quotas[en], GENRE_WEIGHTS[en]), reverse=True)
    for en in ranked[:remainder]:
        quotas[en] += 1
    return quotas



def api_get(path: str, params: dict) -> dict:
    url = f"{API_ROOT}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 503 and attempt < 2:
                wait = 2 * (attempt + 1)
                print(f"  503 限流，{wait}s 后重试：{url}", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 2:
                print(f"  网络错误重试（{exc}）：{url}", file=sys.stderr, flush=True)
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def artist_display(recording: dict) -> str:
    parts = []
    for credit in recording.get("artist-credit") or []:
        if not isinstance(credit, dict):
            continue
        parts.append(credit.get("name") or "")
        parts.append(credit.get("joinphrase") or "")
    return "".join(parts).strip()


def collect(quotas: dict[str, int]) -> list[dict]:
    songs: dict[str, dict] = {}
    for en_tag, zh_tag in GENRE_MAP:
        quota = quotas.get(en_tag, 0)
        if quota <= 0:
            continue
        query = f'tag:"{en_tag}" AND status:official'
        print(f"[采集] 风格 {en_tag} -> {zh_tag}，目标 {quota} 条", file=sys.stderr, flush=True)
        fetched = 0
        offset = 0
        while fetched < quota:
            page = min(100, quota - fetched)
            payload = api_get(
                "recording",
                {"query": query, "fmt": "json", "limit": page, "offset": offset},
            )
            time.sleep(RATE_LIMIT_SECONDS)
            recordings = payload.get("recordings") or []
            if not recordings:
                print(f"  偏移 {offset} 无更多结果，提前结束", file=sys.stderr, flush=True)
                break
            for rec in recordings:
                rec_id = (rec.get("id") or "").strip()
                title = (rec.get("title") or "").strip()
                artist = artist_display(rec)
                if not rec_id or not title or not artist:
                    continue
                if rec.get("video"):
                    continue
                entry = songs.get(rec_id)
                if entry is None:
                    entry = {
                        "song_id": rec_id,
                        "song_name": title,
                        "artist": artist,
                        "genres": set(),
                        "first_release_date": (rec.get("first-release-date") or "").strip(),
                        "source_url": f"https://musicbrainz.org/recording/{rec_id}",
                    }
                    songs[rec_id] = entry
                entry["genres"].add(zh_tag)
            fetched += len(recordings)
            offset += len(recordings)
            print(
                f"  已取 {fetched}/{quota}（总命中 {payload.get('count')}），累计唯一 {len(songs)}",
                file=sys.stderr,
                flush=True,
            )

    rows = []
    for rec_id in sorted(songs):
        entry = songs[rec_id]
        rows.append(
            {
                "song_id": entry["song_id"],
                "song_name": entry["song_name"],
                "artist": entry["artist"],
                "genres_en": "",
                "genres": "|".join(sorted(entry["genres"])),
                "first_release_date": entry["first_release_date"],
                "source_url": entry["source_url"],
            }
        )
    return rows


def load_cache(path: str) -> dict[str, list[str]]:
    cache: dict[str, list[str]] = {}
    if not os.path.isfile(path):
        return cache
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            cache[item["id"]] = item["tags"]
    return cache


def enrich_tags(rows: list[dict], cache_path: str) -> None:
    """逐首回查录音标签（1 请求/首），把映射表中的标签并入 genres。

    结果按行追加到 JSONL 缓存，中断后重跑可续传，避免重复请求。
    """
    cache = load_cache(cache_path)
    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    fetched = skipped = 0
    with open(cache_path, "a", encoding="utf-8") as cache_handle:
        for index, row in enumerate(rows, start=1):
            rec_id = row["song_id"]
            tags = cache.get(rec_id)
            if tags is None:
                payload = api_get(f"recording/{rec_id}", {"inc": "tags", "fmt": "json"})
                tags = [t.get("name") or "" for t in payload.get("tags") or [] if t.get("name")]
                cache[rec_id] = tags
                cache_handle.write(json.dumps({"id": rec_id, "tags": tags}, ensure_ascii=False) + "\n")
                cache_handle.flush()
                fetched += 1
                if index % 20 == 0:
                    print(f"  标签回查 {index}/{len(rows)}", file=sys.stderr, flush=True)
                time.sleep(RATE_LIMIT_SECONDS)
            else:
                skipped += 1

            lower = {tag.lower() for tag in tags}
            mapped = {zh for en, zh in GENRE_MAP if en in lower}
            merged = set(filter(None, row.get("genres", "").split("|"))) | mapped
            row["genres"] = "|".join(sorted(merged))
            row["genres_en"] = "|".join(tags)
    print(f"  标签回查完成：新请求 {fetched}，命中缓存 {skipped}", file=sys.stderr, flush=True)


def read_raw(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_raw(rows: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fields = ["song_id", "song_name", "artist", "genres_en", "genres", "first_release_date", "source_url"]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="采集 MusicBrainz 带风格标签的录音")
    parser.add_argument("--out", default=os.path.join("data", "raw", "musicbrainz_raw.csv"))
    parser.add_argument("--total", type=int, default=5000, help="目标总条数，按风格权重分配（默认 5000）")
    parser.add_argument(
        "--per-genre",
        type=int,
        default=0,
        help="可选：每个风格固定条数，覆盖 --total 的加权分配（用于小样本验证）",
    )
    parser.add_argument(
        "--enrich-only",
        metavar="RAW_CSV",
        default="",
        help="跳过检索，仅对已有原始 CSV 逐首回查标签并重写 genres",
    )
    parser.add_argument(
        "--cache",
        default=os.path.join("data", "raw", "tags_cache.jsonl"),
        help="标签回查缓存（JSONL），可用于断点续传",
    )
    parser.add_argument(
        "--genres",
        default="",
        help="可选：只采这些英文风格标签（逗号分隔），用于小范围验证",
    )
    parser.add_argument("--skip-en-tags", action="store_true", help="跳过英文原始标签回查（更快，但无多标签）")
    args = parser.parse_args(argv)

    if args.per_genre:
        if not 1 <= args.per_genre <= 100:
            parser.error("--per-genre 必须在 1..100 之间")
        quotas = {en: args.per_genre for en, _ in GENRE_MAP}
    else:
        if not 1 <= args.total <= 50000:
            parser.error("--total 必须在 1..50000 之间")
        quotas = compute_quotas(args.total)

    if args.genres:
        selected = {item.strip().lower() for item in args.genres.split(",") if item.strip()}
        unknown = selected - {en for en, _ in GENRE_MAP}
        if unknown:
            parser.error(f"--genres 含未知标签：{sorted(unknown)}")
        quotas = {en: (quota if en in selected else 0) for en, quota in quotas.items()}
    print(
        "风格配额：" + "，".join(f"{en}={quotas[en]}" for en, _ in GENRE_MAP),
        file=sys.stderr,
        flush=True,
    )

    if args.enrich_only:
        rows = read_raw(args.enrich_only)
        enrich_tags(rows, args.cache)
        write_raw(rows, args.out)
        print(f"写入 {len(rows)} 条 -> {args.out}")
        return 0

    rows = collect(quotas)
    if not args.skip_en_tags:
        enrich_tags(rows, args.cache)
    write_raw(rows, args.out)
    print(f"写入 {len(rows)} 条 -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
