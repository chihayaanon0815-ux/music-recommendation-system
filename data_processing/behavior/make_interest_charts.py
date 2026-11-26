# -*- coding: utf-8 -*-
"""用户兴趣标签图：全局标签权重、大类播放权重、用户第一兴趣（lift）。"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA = r"D:\desktop\音乐推荐数据\cf_data\user_interest_tags.json"
OUT = r"D:\desktop\音乐推荐数据\cf_data\charts"
os.makedirs(OUT, exist_ok=True)
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

d = json.load(open(DATA, encoding="utf-8"))


def bar(labels, values, title, xlabel, path, color="#3b6e8f", rotate=30):
    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=150)
    bars = ax.bar(labels, values, color=color)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:,}", ha="center",
                va="bottom", fontsize=7)
    ax.set_title(title)
    ax.set_ylabel(xlabel)
    plt.setp(ax.get_xticklabels(), rotation=rotate, ha="right", fontsize=8)
    ax.grid(axis="y", ls="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print("saved", path)


terms = d["top_terms"][:15]
bar([t for t, _ in terms], [v for _, v in terms],
    "用户兴趣标签 Top15（按播放权重）", "播放权重", os.path.join(OUT, "user_top_terms.png"))

groups = d["group_play_weight_share"][:12]
bar([g["group"] for g in groups], [g["share_pct"] for g in groups],
    "用户兴趣大类占比（播放权重）", "占比 %", os.path.join(OUT, "user_group_share.png"), color="#8fb8c9")

lift = d["top1_group_by_lift"][:10]
bar([g["group"] for g in lift], [g["share_pct"] for g in lift],
    "用户第一兴趣（lift 归一化，含稀有标签放大效应）", "用户占比 %",
    os.path.join(OUT, "user_top1_lift.png"), color="#b7c9d3", rotate=0)
