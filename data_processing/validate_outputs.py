#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""校验 data/processed 下的成品是否满足统一契约与清洗规则。

不依赖 PySpark，只读 CSV，几秒内完成；B、C 在联调/打包前可直接运行：
    python data_processing/validate_outputs.py
    python data_processing/validate_outputs.py --dir data/processed

检查项：
1. 两个文件 UTF-8、无 BOM、无非 LF 行尾；
2. 表头严格等于契约；
3. songs.csv 按 song_id 字符串升序、song_id 非空唯一、song_name 非空；
4. 字段无首尾空格、无换行/制表符；
5. genres 用 | 分隔、无空项、无重复、按字符序升序；
6. genre_counts.csv 与 songs.csv 交叉核对：风格集合一致、每行计数一致、总计一致。
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

SONG_HEADER = ["song_id", "song_name", "artist", "genres"]
COUNT_HEADER = ["genre", "count"]


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def read_rows(path: str, header: list[str], problems: list[str], warnings: list[str]) -> list[dict]:
    with open(path, "rb") as handle:
        data = handle.read()
    if data.startswith(b"\xef\xbb\xbf"):
        fail(problems, f"{os.path.basename(path)} 含 BOM")
    if b"\r\n" in data:
        # 仓库用 data/.gitattributes 强制 LF，但个别 Git 客户端仍可能检出 CRLF；
        # CRLF 是合法 CSV，只提示不判失败。
        warnings.append(f"{os.path.basename(path)} 使用 CRLF 行尾（可正常解析，仓库规范为 LF）")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(problems, f"{os.path.basename(path)} 不是合法 UTF-8：{exc}")
        return []
    rows = list(csv.DictReader(text.splitlines()))
    if csv.DictReader(text.splitlines()).fieldnames != header:
        fail(problems, f"{os.path.basename(path)} 表头不是 {','.join(header)}")
        return []
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验数据成品契约")
    parser.add_argument("--dir", default=os.path.join("data", "processed"))
    args = parser.parse_args(argv)
    base = os.path.abspath(args.dir)
    songs_path = os.path.join(base, "songs.csv")
    counts_path = os.path.join(base, "genre_counts.csv")
    problems: list[str] = []
    warnings: list[str] = []

    for path in (songs_path, counts_path):
        if not os.path.isfile(path):
            print(f"缺少文件：{path}", file=sys.stderr)
            return 2

    songs = read_rows(songs_path, SONG_HEADER, problems, warnings)
    counts = read_rows(counts_path, COUNT_HEADER, problems, warnings)

    ids = [row["song_id"] for row in songs]
    if len(ids) != len(set(ids)):
        fail(problems, f"song_id 不唯一：{len(ids) - len(set(ids))} 个重复")
    if ids != sorted(ids):
        fail(problems, "songs.csv 未按 song_id 字符串升序")
    if any(not row["song_id"] for row in songs):
        fail(problems, "存在空 song_id")
    if any(not row["song_name"] for row in songs):
        fail(problems, "存在空 song_name")

    for row in songs:
        for field in ("song_id", "song_name", "artist", "genres"):
            value = row[field] or ""
            if value != value.strip():
                fail(problems, f"{row['song_id']} 的 {field} 有首尾空格")
                break
            if "\n" in value or "\t" in value:
                fail(problems, f"{row['song_id']} 的 {field} 含换行/制表符")
                break
        genres = row["genres"] or ""
        if genres:
            parts = genres.split("|")
            if any(part == "" for part in parts):
                fail(problems, f"{row['song_id']} 的 genres 有空项")
            elif len(parts) != len(set(parts)):
                fail(problems, f"{row['song_id']} 的 genres 有重复项")
            elif parts != sorted(parts):
                fail(problems, f"{row['song_id']} 的 genres 未按字符序排序")

    computed: dict[str, int] = {}
    for row in songs:
        for genre in (row["genres"] or "").split("|"):
            if genre:
                computed[genre] = computed.get(genre, 0) + 1

    listed = {row["genre"]: int(row["count"]) for row in counts}
    if set(listed) != set(computed):
        fail(
            problems,
            f"风格集合不一致：仅计数文件有 {sorted(set(listed) - set(computed))[:5]}，"
            f"仅歌曲文件有 {sorted(set(computed) - set(listed))[:5]}",
        )
    for genre, count in listed.items():
        if computed.get(genre) != count:
            fail(problems, f"{genre} 计数不符：文件 {count}，实际 {computed.get(genre)}")
    if sum(listed.values()) != sum(computed.values()):
        fail(problems, "风格计数合计不符")

    print(f"songs.csv：{len(songs)} 首，唯一 song_id {len(set(ids))} 个")
    print(f"genre_counts.csv：{len(counts)} 个风格，合计 {sum(listed.values())} 次标签计数")
    print(f"多标签曲目：{sum(1 for row in songs if '|' in (row['genres'] or ''))} 首")
    for item in warnings:
        print(f"提示：{item}")

    if problems:
        print(f"\n发现 {len(problems)} 个问题：")
        for item in problems[:50]:
            print(" -", item)
        return 1
    print("\n校验通过：表头、唯一性、排序、空值、标签规范、风格计数均符合契约。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
