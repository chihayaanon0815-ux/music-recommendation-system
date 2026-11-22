#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一条命令生成 data/processed 成品（下载 -> 映射 -> Spark 清洗 -> 契约校验）。

仓库**不提交**任何 Spotify 衍生数据；使用者（B/C/评审）在本地运行本脚本自行生成，
生成结果位于 data/processed/，已被 .gitignore 忽略。

用法（仓库根目录）：
    python data_processing/build_dataset.py
    python data_processing/build_dataset.py --from-file D:\\path\\to\\dataset.csv
    python data_processing/build_dataset.py --reuse-raw      # 已有 data/raw/spotify_tracks_raw.csv，跳过下载
    python data_processing/build_dataset.py --skip-validate

依赖：Python 3.9+、Java 17、PySpark 4（见 data_processing/requirements.txt）。
首次运行需联网从 hf-mirror 下载 19.2 MB 原始 CSV；之后可用 --reuse-raw 离线重跑。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD = os.path.join(ROOT, "data_processing", "download_spotify.py")
CLEAN = os.path.join(ROOT, "data_processing", "clean_songs.py")
VALIDATE = os.path.join(ROOT, "data_processing", "validate_outputs.py")
RAW = os.path.join(ROOT, "data", "raw", "spotify_tracks_raw.csv")
OUT_DIR = os.path.join(ROOT, "data", "processed")
METRICS = os.path.join(OUT_DIR, "run_metrics.json")


def run(step: str, command: list[str]) -> None:
    print(f"\n=== {step} ===", flush=True)
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 data/processed 成品")
    parser.add_argument("--from-file", default="", help="已有的原始 dataset.csv（跳过下载）")
    parser.add_argument("--reuse-raw", action="store_true", help="已有 spotify_tracks_raw.csv 时跳过下载与映射")
    parser.add_argument("--skip-validate", action="store_true", help="跳过最后的契约校验")
    args = parser.parse_args(argv)

    os.makedirs(OUT_DIR, exist_ok=True)
    python = sys.executable

    if args.reuse_raw:
        if not os.path.isfile(RAW):
            parser.error(f"--reuse-raw 需要已有文件：{RAW}")
        print(f"复用已有原始表：{RAW}")
    else:
        command = [python, DOWNLOAD, "--out", RAW]
        if args.from_file:
            command += ["--from-file", args.from_file]
        run("下载并映射字段", command)

    run(
        "PySpark 清洗",
        [python, CLEAN, "--input", RAW, "--out-dir", OUT_DIR, "--metrics", METRICS],
    )

    if not args.skip_validate:
        run("契约校验", [python, VALIDATE, "--dir", OUT_DIR])

    print("\n完成：")
    print(f"  {os.path.join(OUT_DIR, 'songs.csv')}")
    print(f"  {os.path.join(OUT_DIR, 'genre_counts.csv')}")
    print(f"  {METRICS}")
    print("注意：这些文件不提交到 Git（见 data/.gitignore），只在本机/打包机保留。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
