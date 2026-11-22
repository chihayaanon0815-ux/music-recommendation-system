#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""下载 Spotify Tracks Dataset 并映射为课程统一字段。

来源：
    数据集名：maharshipandya/spotify-tracks-dataset
    HuggingFace 页面：https://huggingface.co/datasets/maharshipandya/spotify-tracks-dataset
    Kaggle 原始页面：https://www.kaggle.com/datasets/maharshipandya/-spotify-tracks-dataset
    说明：原数据由作者用 Spotify Web API 采集整理；本脚本只下载公开再分发的 CSV，
    不访问 Spotify 接口，也不下载音频。

字段映射（写入 data/raw/spotify_tracks_raw.csv，保留 popularity 以便报告统计）：
    track_id    -> song_id
    track_name  -> song_name
    artists     -> artist（多个艺术家用 ";" 分隔，统一替换为 " & "）
    track_genre -> genres
    popularity  -> popularity（附加列，不进入统一契约）

用法（仓库根目录）：
    python data_processing/download_spotify.py
    python data_processing/download_spotify.py --out data/raw/spotify_tracks_raw.csv

注意：中国大陆网络通常无法直连 huggingface.co，脚本默认使用镜像 hf-mirror.com；
如镜像不可用，可自行从 Kaggle 下载 dataset.csv 后用 --from-file 指定本地文件。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import urllib.error
import urllib.request

MIRROR_URL = (
    "https://hf-mirror.com/datasets/maharshipandya/spotify-tracks-dataset/resolve/main/dataset.csv"
)
EXPECTED_ROWS = 114000
USER_AGENT = "DSH-CourseProject-DataCollector/1.0 (student project; 3378625648@qq.com)"


def download(url: str, target: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    temp = target + ".part"
    print(f"[下载] {url}", file=sys.stderr, flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as resp, open(temp, "wb") as handle:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
    os.replace(temp, target)


def sanitize(text: str) -> str:
    """把字段内会被 CSV 转义规则误解析的字符规范化。

    Spark 的 CSV reader 默认转义符是反斜杠，与 RFC4180 的双引号加倍写法冲突，
    含英文双引号的歌名会被解析错位。因此在写入原始表前把双引号统一为单引号，
    换行/制表符替换为空格；字段内容其余部分保持不变。
    """
    return text.replace('"', "'").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def load_genre_map(path: str) -> dict[str, dict[str, str]]:
    """读取 genre -> {中文展示名, 大类} 映射。未收录的风格保留原文。"""
    mapping: dict[str, dict[str, str]] = {}
    if not os.path.isfile(path):
        return mapping
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("genre") or "").strip()
            value = (row.get("genre_zh") or "").strip()
            group = (row.get("group_zh") or "").strip()
            if not key:
                continue
            if key in mapping:
                raise ValueError(f"风格映射重复：{key}")
            if value:
                mapping[key] = {"zh": value, "group": group or value}
    return mapping


def map_rows(source: str, genre_map: dict[str, dict[str, str]] | None = None):
    genre_map = genre_map or {}
    with open(source, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            track_id = sanitize(row.get("track_id") or "")
            name = sanitize(row.get("track_name") or "")
            artists = sanitize(row.get("artists") or "")
            genre = sanitize(row.get("track_genre") or "")
            artist = " & ".join(part.strip() for part in artists.split(";") if part.strip())
            info = genre_map.get(genre, {"zh": genre, "group": genre})
            yield {
                "song_id": track_id,
                "song_name": name,
                "artist": artist,
                "genres": info["group"],
                "genres_zh": info["zh"],
                "genres_en": genre,
                "popularity": sanitize(row.get("popularity") or ""),
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载 Spotify Tracks Dataset 并映射字段")
    parser.add_argument("--out", default=os.path.join("data", "raw", "spotify_tracks_raw.csv"))
    parser.add_argument("--from-file", default="", help="使用本地已下载的 dataset.csv，跳过网络")
    parser.add_argument(
        "--genre-map",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "genre_map_zh.csv"),
        help="风格英文 -> 中文映射 CSV",
    )
    args = parser.parse_args(argv)

    source = args.from_file
    if source:
        if not os.path.isfile(source):
            parser.error(f"本地文件不存在：{source}")
    else:
        source = os.path.join("data", "raw", "dataset.csv")
        download(MIRROR_URL, source)

    genre_map = load_genre_map(args.genre_map)
    rows = list(map_rows(source, genre_map))
    if len(rows) != EXPECTED_ROWS:
        print(
            f"警告：行数 {len(rows)} 与预期 {EXPECTED_ROWS} 不一致，请确认数据集版本",
            file=sys.stderr,
            flush=True,
        )

    unmapped = {row["genres_en"] for row in rows} - set(genre_map)
    if unmapped:
        print(f"提示：{len(unmapped)} 个风格未收录映射，保留英文：{sorted(unmapped)[:10]}", file=sys.stderr)

    fields = ["song_id", "song_name", "artist", "genres", "genres_zh", "genres_en", "popularity"]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(open(source, "rb").read()).hexdigest()
    print(f"下载文件 SHA-256：{digest}")
    print(f"风格映射 {len(genre_map)} 条，映射 {len(rows)} 行 -> {args.out}")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
