#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PySpark 本地模式清洗音乐数据，输出课程统一契约的 CSV。

输入：任意含 song_id,song_name,artist,genres 四列的 UTF-8 CSV
（下载脚本产出 data/raw/spotify_tracks_raw.csv，额外列会被忽略）。
输出：
    <out-dir>/songs.csv        表头 song_id,song_name,artist,genres
    <out-dir>/genre_counts.csv 表头 genre,count

清洗规则（与 docs/data/data_dictionary.md 一致）：
1. 四个字段均去首尾空格；song_id 或 song_name 为空的记录剔除。
2. genres 以 | 切分，逐项去空格、去掉空项、去重后按字符序排序，再以 | 连接；
   artist 允许为空；genres 允许为空字符串。
3. song_id 重复时合并为一条：所有行的风格取并集，song_name 取最小非空值，
   artist 取最小非空值（没有则空字符串）。规则确定，与输入行序和分区无关。
4. genre_counts 中每首歌的每个不同标签计一次。

运行（仓库根目录，需 Java 17 + PySpark 4）：
    python data_processing/download_spotify.py
    python data_processing/clean_songs.py --input data/raw/spotify_tracks_raw.csv --out-dir data/processed
    python data_processing/clean_songs.py --input data/sample/songs_sample.csv --out-dir dist/sample_out
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

SONG_COLUMNS = ["song_id", "song_name", "artist", "genres"]



def build_spark(app_name: str = "music-clean") -> SparkSession:
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.extraJavaOptions", "-Dfile.encoding=UTF-8")
        .getOrCreate()
    )


def normalize(df):
    """裁剪字段、规范 genres、按 song_id 归并，返回清洗后的 DataFrame。"""
    for column in SONG_COLUMNS:
        df = df.withColumn(column, F.trim(F.col(column).cast("string")))
    df = df.where(F.col("song_id").isNotNull() & (F.col("song_id") != ""))
    df = df.where(F.col("song_name").isNotNull() & (F.col("song_name") != ""))

    pieces = F.split(F.col("genres"), "\\|")
    pieces = F.transform(pieces, lambda item: F.trim(item))
    pieces = F.filter(pieces, lambda item: item.isNotNull() & (item != ""))
    df = df.withColumn("genre_parts", pieces)

    grouped = df.groupBy("song_id").agg(
        F.min("song_name").alias("song_name"),
        F.coalesce(F.min(F.when(F.col("artist") != "", F.col("artist"))), F.lit("")).alias("artist"),
        F.collect_set("genre_parts").alias("genre_parts"),
    )
    grouped = grouped.withColumn(
        "genres",
        F.array_join(F.array_sort(F.array_distinct(F.flatten(F.col("genre_parts")))), "|"),
    )
    return grouped.select(*SONG_COLUMNS)


def write_single_csv(df, target: str) -> None:
    """Spark 原生 write 产出目录；此处转换为单文件 UTF-8 CSV。"""
    target = os.path.abspath(target)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".spark-csv-", dir=os.path.dirname(target))
    try:
        df.coalesce(1).write.option("header", True).option("encoding", "UTF-8").option(
            "lineSep", "\n"
        ).mode("overwrite").csv(tmp)
        parts = [name for name in os.listdir(tmp) if name.startswith("part-") and name.endswith(".csv")]
        if len(parts) != 1:
            raise RuntimeError(f"期望 1 个 part 文件，实际 {parts}")
        shutil.move(os.path.join(tmp, parts[0]), target)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PySpark 本地清洗音乐数据")
    parser.add_argument("--input", required=True, help="输入 CSV 路径")
    parser.add_argument("--out-dir", default=os.path.join("data", "processed"))
    parser.add_argument("--metrics", default="", help="可选：把行数统计写入 JSON 文件")
    args = parser.parse_args(argv)

    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        parser.error(f"输入文件不存在：{input_path}")

    spark = build_spark()
    spark.sparkContext.setLogLevel("ERROR")
    try:
        raw = (
            spark.read.option("header", True)
            .option("encoding", "UTF-8")
            .option("multiLine", True)
            .option("quote", '"')
            .option("escape", '"')
            .csv(input_path)
        )
        missing = [column for column in SONG_COLUMNS if column not in raw.columns]
        if missing:
            print(f"输入缺少必需列：{missing}", file=sys.stderr)
            return 2

        raw_count = raw.count()
        trimmed = raw.select([F.trim(F.col(column).cast("string")).alias(column) for column in SONG_COLUMNS])
        dropped_blank = raw_count - trimmed.where(
            (F.col("song_id") != "") & (F.col("song_id").isNotNull())
            & (F.col("song_name") != "") & (F.col("song_name").isNotNull())
        ).count()
        songs = normalize(raw)
        songs = songs.select(*SONG_COLUMNS).orderBy(F.col("song_id").asc())
        song_count = songs.count()

        genre_counts = (
            songs.withColumn("genre", F.explode(F.split(F.col("genres"), "\\|")))
            .where(F.col("genre") != "")
            .groupBy("genre")
            .agg(F.count(F.lit(1)).alias("count"))
            .orderBy(F.col("count").desc(), F.col("genre").asc())
        )
        genre_rows = genre_counts.collect()

        out_dir = os.path.abspath(args.out_dir)
        write_single_csv(songs, os.path.join(out_dir, "songs.csv"))
        write_single_csv(genre_counts, os.path.join(out_dir, "genre_counts.csv"))

        metrics = {
            "input": input_path,
            "input_rows": raw_count,
            "songs_rows": song_count,
            "dropped_blank_id_or_name": dropped_blank,
            "duplicate_song_id_rows": raw_count - dropped_blank - song_count,
            "genre_rows": len(genre_rows),
            "total_genre_assignments": int(sum(row["count"] for row in genre_rows)),
        }
        print(
            f"输入 {raw_count} 行，删除空 ID/歌名 {dropped_blank} 行，"
            f"重复 ID 合并 {metrics['duplicate_song_id_rows']} 行，成品 {song_count} 首，"
            f"风格统计 {len(genre_rows)} 行 -> {out_dir}",
            file=sys.stderr,
        )
        for row in genre_rows:
            print(f"  {row['genre']}: {row['count']}", file=sys.stderr)
        if args.metrics:
            os.makedirs(os.path.dirname(os.path.abspath(args.metrics)), exist_ok=True)
            with open(args.metrics, "w", encoding="utf-8") as handle:
                json.dump(metrics, handle, ensure_ascii=False, indent=2)
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
