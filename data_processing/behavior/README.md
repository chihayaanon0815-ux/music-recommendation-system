# 行为数据 / 大数据扩展链路（可选模块）

本目录是**可选**的大数据扩展：基于 Million Song Dataset / Echo Nest Taste Profile 的用户行为数据，
做清洗、划分、协同过滤评估、元数据补全、音频特征、歌手相似度、MapReduce 对比与合规爬虫演示。

> 不影响统一契约：`data/processed/songs.csv`、`recommender/`、`web/` 均不依赖本目录。
> 行为数据与 MSD 派生数据**不得公开再分发**，本仓库只提交代码与**聚合指标**；
> 逐条数据（交互表、宽表、特征、相似边）不进入 Git，详见 `docs/data/behavior_pipeline.md`。

## 目录内容

| 文件 | 用途 |
| --- | --- |
| `clean_kcore.py` | 9 轮 k-core 清洗（用户 ≥20、歌曲 ≥50）→ `interactions.csv` |
| `split_data.py` | 留一法划分 → `train.csv` / `test.csv` / `id_maps.json` |
| `item_cf.py` | ItemCF 相似度 + 评估 → `similarity.npy` / `cf_metrics.json` |
| `degree_distribution_save.py` | 度数/播放分布 → `data_quality.json` |
| `pair_scale.py` / `stats_triplets.py` | 共现规模测算 / 原始数据统计 |
| `build_msd_meta.py` | 曲目元数据 + k-core 维表 + 候选池补名 + 宽表样例 |
| `build_wide_parquet.py` | Spark 生成交互宽表（Parquet） |
| `build_audio_features.py` | 从 `msd_summary_file.h5` 抽音频特征（需 h5py） |
| `build_artist_similarity.py` | 歌手相似边 + 歌手维表 + 推荐演示 |
| `spark_kcore_aggregate.py` | Spark 两轮阈值过滤聚合 |
| `mb_enrich.py` / `crawl_mb_enrich.py` | MusicBrainz 采集（Top100 样例 / 可扩量版） |
| `crawl_itunes_genre.py` | iTunes 流派采集（Top150，限速 2.5 秒） |
| `mr_mapper.py` / `mr_reducer.py` / `run_mapreduce.sh` | Hadoop Streaming 作业（WSL） |
| `verify_hashes.py` / `regen_manifest.py` | 数据文件哈希核对 / 清单生成 |
| `make_quality_charts.py` / `make_interest_charts.py` / `user_interest_tags.py` | 数据质量与用户兴趣图表 |

## 运行前提

1. 原始数据（不随仓库分发）：
   - `train_triplets.txt`（Taste Profile，48,373,586 行）
   - `track_metadata.db`、`unique_tracks.txt`、`artist_term.db`、`similarity.db`、`msd_summary_file.h5`（MSD 附加文件）
2. Python 3.10+，依赖 `pandas`、`numpy`；音频特征需 `h5py`；宽表需 JDK17 + PySpark。
3. **路径常量**：脚本顶部使用作者机器的绝对路径（`D:\DSH-Work\msd`、数据包目录等），
   换机器时请统一修改，或改为环境变量。建议先改 `build_*` 系列脚本顶部的 `CF` / `MSD` 常量。

## 复现顺序（本机，约 20 分钟）

```text
python clean_kcore.py       # 9 轮 k-core
python split_data.py        # 留一法划分
python item_cf.py           # ItemCF + 评估
python build_msd_meta.py    # 元数据 / 维表 / 候选池
python build_audio_features.py
python build_artist_similarity.py
spark-submit build_wide_parquet.py
bash run_mapreduce.sh       # WSL + Hadoop 3.3.6（可选）
python crawl_itunes_genre.py --limit 150
```

完整数据与逐条产物留在本地数据包（不入库），仓库内的 `data/processed/behavior_metrics/`
只保存聚合指标，`data/processed/behavior_charts/` 保存图表。

## 关键结果（详见 `docs/data/behavior_pipeline.md`）

- 原始 48,373,586 行 / 3.0 GB；k-core 后 39,326,348 条、624,984 用户、91,283 首歌；
- k-core 歌名覆盖 4.87% → 100%（MSD 元数据按 song_id 直连）；
- 音频特征 384,546/384,546（danceability/energy 源文件全 0，已排除）；
- 歌手相似度覆盖 99.84%（1,669,104 条无权边）；
- MapReduce（LocalJobRunner）139 秒 vs Spark local 31.9 秒；iTunes 爬虫 150 首命中 134、流派覆盖 82%。

## 许可

MSD / Echo Nest 数据仅限非商业研究，原始与逐条派生数据不得公开再分发；
MusicBrainz 核心数据 CC0；iTunes 数据版权归 Apple/唱片方，仅课程内部使用。
