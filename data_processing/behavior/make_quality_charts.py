# -*- coding: utf-8 -*-
"""生成数据质量图：用户/歌曲度数分布、播放量长尾、CF 指标。"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = r"D:\desktop\音乐推荐数据\cf_data"
OUT = r"D:\desktop\音乐推荐数据\cf_data\charts"
os.makedirs(OUT, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

with open(r"D:\DSH-Work\data_quality.json", encoding="utf-8") as fh:
    dq = json.load(fh)
with open(os.path.join(BASE, "cf_metrics.json"), encoding="utf-8") as fh:
    cf = json.load(fh)


def loglog(xs, ys, title, xlabel, ylabel, path):
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    ax.loglog(xs, ys, ".", markersize=2.5, alpha=0.7)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, which="both", ls="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print("saved", path)


loglog(dq["user_degree_hist"]["x"], dq["user_degree_hist"]["y"],
       "用户交互数分布（log-log）", "每个用户的交互歌曲数", "用户数",
       os.path.join(OUT, "user_degree_loglog.png"))
loglog(dq["song_degree_hist"]["x"], dq["song_degree_hist"]["y"],
       "歌曲被交互数分布（log-log）", "每首歌的交互用户数", "歌曲数",
       os.path.join(OUT, "song_degree_loglog.png"))
loglog(dq["play_count_hist"]["x"], dq["play_count_hist"]["y"],
       "播放次数分布（log-log）", "单条交互的 play_count", "交互条数",
       os.path.join(OUT, "play_count_loglog.png"))

labels = ["HitRate@10", "Precision@10", "覆盖率(池内)", "池内条件命中率"]
values = [cf["hit_rate_at_10"], cf["precision_at_10"],
          cf["recommendation_coverage_in_pool"], cf["conditional_hit_rate_in_pool"]]
fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
bars = ax.bar(labels, values, color=["#3b6e8f", "#5c9ead", "#8fb8c9", "#b7c9d3"])
for bar, value in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.004,
            f"{value:.4f}", ha="center", fontsize=9)
ax.set_ylim(0, max(values) * 1.25)
ax.set_title("ItemCF 留一法评估指标")
ax.grid(axis="y", ls="--", alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "cf_metrics_bar.png"))
plt.close(fig)
print("saved", os.path.join(OUT, "cf_metrics_bar.png"))
