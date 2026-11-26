# -*- coding: utf-8 -*-
"""Spark 行为数据聚合：阈值过滤（近似 k-core）+ 用户/歌曲统计，输出可交付文件。

说明：Spark local 单机内存有限，这里采用“广播小表 + 两轮阈值过滤”的方式，
避免对 4,837 万行做多轮大 shuffle；完整 9 轮迭代结果由 Python 版 clean_kcore 提供。
"""
import json
import os
import shutil
import time

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

TRIPLETS = r"D:\DSH-Work\msd\train_triplets.txt"
OUT = r"D:\desktop\音乐推荐数据\cf_data\spark"
USER_K = 20
SONG_K = 50
MAX_ROUNDS = 2

os.makedirs(OUT, exist_ok=True)

spark = (
    SparkSession.builder.master("local[*]")
    .appName("msd-kcore-spark")
    .config("spark.ui.enabled", "false")
    .config("spark.sql.shuffle.partitions", "32")
    .config("spark.driver.memory", "5g")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")

t0 = time.time()
df = spark.read.option("delimiter", "\t").csv(
    TRIPLETS, schema="user_id string, song_id string, play_count int"
)
input_rows = df.count()
print(f"input_rows={input_rows:,}", flush=True)

rounds = []
for rnd in range(1, MAX_ROUNDS + 1):
    user_deg = df.groupBy("user_id").agg(F.count(F.lit(1)).alias("n"))
    songs_deg = df.groupBy("song_id").agg(F.count(F.lit(1)).alias("n"))
    keep_users = user_deg.filter(F.col("n") >= USER_K).select("user_id")
    df = df.join(F.broadcast(keep_users), "user_id", "inner")
    df = df.persist()
    song_deg = df.groupBy("song_id").agg(F.count(F.lit(1)).alias("n"))
    keep_songs = song_deg.filter(F.col("n") >= SONG_K).select("song_id")
    df = df.join(F.broadcast(keep_songs), "song_id", "inner")
    n = df.count()
    rounds.append({"round": rnd, "interactions": n, "elapsed_seconds": round(time.time() - t0, 1)})
    print(f"round {rnd}: {n:,}", flush=True)

out_rows = df.count()
out_users = df.select("user_id").distinct().count()
out_songs = df.select("song_id").distinct().count()
out_plays = df.agg(F.sum("play_count")).first()[0]
density = out_rows / (out_users * out_songs) if out_users and out_songs else 0

df.repartition(8).write.mode("overwrite").parquet(os.path.join(OUT, "interactions.parquet"))

song_stats = (
    df.groupBy("song_id")
    .agg(F.count(F.lit(1)).alias("users"), F.sum("play_count").alias("plays"))
    .orderBy(F.desc("plays"))
)
song_stats.coalesce(1).write.mode("overwrite").option("header", True).csv(
    os.path.join(OUT, "song_stats_tmp")
)

user_stats = (
    df.groupBy("user_id")
    .agg(F.count(F.lit(1)).alias("songs"), F.sum("play_count").alias("plays"))
    .orderBy(F.desc("songs"))
)
user_stats.coalesce(1).write.mode("overwrite").option("header", True).csv(
    os.path.join(OUT, "user_stats_tmp")
)

for name in ("song_stats", "user_stats"):
    tmp = os.path.join(OUT, name + "_tmp")
    parts = [f for f in os.listdir(tmp) if f.startswith("part-") and f.endswith(".csv")]
    shutil.move(os.path.join(tmp, parts[0]), os.path.join(OUT, name + ".csv"))
    shutil.rmtree(tmp, ignore_errors=True)

metrics = {
    "input_rows": input_rows,
    "kcore_user_k": USER_K,
    "kcore_song_k": SONG_K,
    "strategy": "broadcast small degree tables + threshold filtering (2 rounds)",
    "rounds": rounds,
    "kept_interactions": out_rows,
    "kept_users": out_users,
    "kept_songs": out_songs,
    "kept_total_play_count": int(out_plays or 0),
    "density": round(density, 8),
    "elapsed_seconds": round(time.time() - t0, 1),
    "outputs": {
        "interactions_parquet": "interactions.parquet",
        "song_stats_csv": "song_stats.csv",
        "user_stats_csv": "user_stats.csv",
    },
}
with open(os.path.join(OUT, "kcore_metrics.json"), "w", encoding="utf-8") as fh:
    json.dump(metrics, fh, ensure_ascii=False, indent=2)
print(json.dumps(metrics, ensure_ascii=False, indent=2)[:1500])
spark.stop()
