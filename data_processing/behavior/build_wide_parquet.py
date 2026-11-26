# -*- coding: utf-8 -*-
"""Stage 4: Spark 生成带元数据的交互宽表（Parquet）。

输入: cf_data/train.csv, test.csv, song_dim_kcore.csv
输出: cf_data/wide/train_named.parquet, test_named.parquet, wide_metrics.json

Windows 运行前提（本机已验证）:
  JAVA_HOME   = JDK 17
  HADOOP_HOME = D:\\DSH-Work\\hadoop（含 bin\\winutils.exe，否则 Spark 写本地文件报
                "HADOOP_HOME and hadoop.home.dir are unset"）
  TEMP        = 可写目录（默认 %TEMP% 偶发 spark-class 启动失败，指向 D:\\DSH-Work\\tmp\\spark-temp 即可）
"""
import json
import os
import time

from pyspark.sql import SparkSession, functions as F

CF = r"D:\desktop\音乐推荐数据\cf_data"
OUT = os.path.join(CF, "wide")
os.makedirs(OUT, exist_ok=True)

t0 = time.time()
spark = (
    SparkSession.builder.master("local[8]")
    .appName("msd-wide")
    .config("spark.ui.enabled", "false")
    .config("spark.sql.shuffle.partitions", "16")
    .config("spark.driver.memory", "4g")
    .config("spark.sql.autoBroadcastJoinThreshold", "268435456")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")

dim = spark.read.option("header", True).csv(os.path.join(CF, "song_dim_kcore.csv"))
dim = dim.select(
    "song_id", "title", "artist", "release",
    F.when(F.trim(F.col("year")) != "", F.col("year").cast("int")).alias("year"),
    F.when(F.trim(F.col("duration_sec")) != "", F.col("duration_sec").cast("double")).alias("duration_sec"),
    F.col("spotify_genres"),
)
print("dim rows:", dim.count(), "elapsed", round(time.time() - t0, 1), flush=True)

train = spark.read.option("header", True).csv(os.path.join(CF, "train.csv")) \
    .select("user_id", "song_id", F.col("play_count").cast("int").alias("play_count"))
wide = train.join(F.broadcast(dim), "song_id", "left")
wide.write.mode("overwrite").option("compression", "snappy") \
    .parquet(os.path.join(OUT, "train_named.parquet"))
print("train wide written, elapsed", round(time.time() - t0, 1), flush=True)

test = spark.read.option("header", True).csv(os.path.join(CF, "test.csv")).select("user_id", "song_id")
test_wide = test.join(F.broadcast(dim), "song_id", "left")
test_wide.write.mode("overwrite").option("compression", "snappy") \
    .parquet(os.path.join(OUT, "test_named.parquet"))
print("test wide written, elapsed", round(time.time() - t0, 1), flush=True)

chk = spark.read.parquet(os.path.join(OUT, "train_named.parquet"))
rows = chk.count()
named = chk.filter(F.col("title").isNotNull() & (F.trim(F.col("title")) != "")).count()
with_genre = chk.filter(F.col("spotify_genres").isNotNull() & (F.trim(F.col("spotify_genres")) != "")).count()
metrics = {
    "wide_train_rows": rows,
    "wide_test_rows": spark.read.parquet(os.path.join(OUT, "test_named.parquet")).count(),
    "title_present": named,
    "title_pct": round(named / rows * 100, 2),
    "spotify_genres_present": with_genre,
    "spotify_genres_pct": round(with_genre / rows * 100, 2),
    "columns": chk.columns,
    "sample": [r.asDict() for r in chk.limit(3).collect()],
    "elapsed_seconds": round(time.time() - t0, 1),
}
with open(os.path.join(OUT, "wide_metrics.json"), "w", encoding="utf-8") as fh:
    json.dump(metrics, fh, ensure_ascii=False, indent=2)
print(json.dumps(metrics, ensure_ascii=False, indent=2)[:1500])
spark.stop()
