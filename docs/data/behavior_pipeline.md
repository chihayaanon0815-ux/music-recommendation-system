# 行为数据与大数据扩展链路（可选模块）

日期：2026-11-23　｜　归属：数据组（A）　｜　状态：代码与聚合指标已提交，逐条数据不入库

本模块是 `songs.csv` 统一契约之外的**可选大数据链路**：用 Million Song Dataset（MSD）/
Echo Nest Taste Profile 的用户行为数据，补齐“清洗 → 划分 → 评估 → 元数据 → 特征 → 对比实验”的完整过程。
`recommender/`、`web/` 与 `data/processed/songs.csv` 不依赖本模块，合并不影响主链路。

## 整合状态

本模块已与 662,939 首曲库、Neo4j 图推荐和 Windows 离线应用整合到 main。网页使用已发布的图推荐索引。下列行为实验指标保留其原始数据版本口径。

行为实验尚有已知待修项。原始 item_cf.py 只累计共现矩阵的上三角，需要修正对称性并重新评估。采用统一歌曲 ID 后，应先按用户和曲目聚合，再重新划分训练测试集，以处理来源 ID 合并造成的跨集合重叠。现有 ItemCF 指标应作为历史实验记录引用。完整原始听歌数据由课程组的数据包提供。

新版曲库与行为映射见 [合并说明](catalog-behavior-2026-11-25/README.md)。

## 1. 数据源与许可

| 数据 | 内容 | 规模 | 许可 |
| --- | --- | --- | --- |
| Taste Profile（MSD） | `user_id / song_id / play_count` | 48,373,586 行，解压 3.0 GB | 仅非商业研究，**原始与逐条派生数据不得公开再分发** |
| MSD 附加文件 | `track_metadata.db`、`unique_tracks.txt`、`artist_term.db`、`artist_similarity.db`、`msd_summary_file.h5` | 1,000,000 行级别 | 同上（Echo Nest 条款） |
| MusicBrainz | 录音检索与标签 | Top 100 样例 | 核心数据 CC0 |
| iTunes Search API | 流派/发行日期 | Top 150 样例 | 版权归 Apple/唱片方，仅课程内部使用 |

因此：**本仓库只提交代码与聚合统计**；交互表、宽表、特征、相似边等逐条数据只留在本地。

## 2. 处理链路

```text
train_triplets.txt (48,373,586 行 / 3.0 GB)
  ├─ 质量扫描：0 格式错误 / 0 非法 ID / 0 重复 (user,song) / play_count 1–9,667
  ├─ k-core 9 轮（用户≥20、歌曲≥50）
  │     → 39,326,348 条交互 / 624,984 用户 / 91,283 首歌（密度 0.069%）
  ├─ 留一法划分（种子 42）→ train 38,701,364 / test 624,984
  ├─ ItemCF（5,000 候选池，余弦相似度）→ HitRate@10 = 0.0665
  ├─ 元数据补全（song_id 直连 track_metadata）
  │     → k-core 歌名覆盖 4.87% → 100%；全量 384,546 首歌名/歌手/专辑/时长 100%
  ├─ 音频特征（msd_summary_file.h5）
  │     → 384,546/384,546 命中；danceability/energy 源文件全 0，已排除
  ├─ 歌手相似度（artist_similarity.db）
  │     → 30,493/30,543 位歌手（99.84%）、1,669,104 条无权边
  ├─ 宽表（Spark local）→ train 38,701,364 行 / test 624,984 行（Parquet）
  └─ MapReduce 对比（Hadoop 3.3.6 Streaming，LocalJobRunner）139 秒
```

## 3. 关键结果

| 指标 | 值 |
| --- | --- |
| 原始交互 / 用户 / 歌曲 / 播放 | 48,373,586 / 1,019,318 / 384,546 / 138,680,243 |
| k-core 保留 | 39,326,348 条、624,984 用户、91,283 歌、111,745,239 次播放 |
| 歌名覆盖率（k-core） | 4,441/91,283（4.87%）→ **91,283/91,283（100%）** |
| 歌名覆盖（按交互计） | 14.51% → **100%** |
| 音频特征 | 384,546 首（100%）；tempo/loudness/key/mode/time_signature 可用 |
| 歌手相似度 | 30,493/30,543（99.84%），平均 54.74 邻居/歌手 |
| ItemCF | HitRate@10 = 0.0665（池内条件命中 0.1391） |
| MapReduce vs Spark vs Pandas | 139s / 31.9s / 41.4s（同口径统计） |
| iTunes 爬虫（Top150） | 命中 134（89.33%）、流派 123（82.0%） |
| 31 类中文风格覆盖 | 4,441/91,283（4.87%，未补齐） |

## 4. 仓库内产物（只含聚合）

| 路径 | 内容 |
| --- | --- |
| `data/processed/behavior_metrics/*.json` | 清洗/评估/覆盖率/特征/相似度/MapReduce/爬虫的聚合指标 |
| `data/processed/behavior_charts/*.png` | 7 张数据质量与用户兴趣图 |
| `data_processing/behavior/*.py` | 全部可复现脚本（见该目录 README） |

## 5. 复现

1. 按许可自行获取 MSD 原始数据，放到本机目录（脚本顶部常量，如 `D:\DSH-Work\msd`）；
2. 安装依赖：`pandas`、`numpy`；音频特征需 `h5py`；宽表需 JDK17 + PySpark；
3. 按 `data_processing/behavior/README.md` 的顺序执行；
4. 逐条产物写入本地数据包目录，**不要 commit**；仓库只更新 `behavior_metrics/` 与 `behavior_charts/`。

## 6. 局限（写报告照实写）

1. 行为数据**无时间戳**，只能随机划分，不能做时间序列推荐；
2. Spark 为 `local[*]`、MapReduce 为 LocalJobRunner，**单机执行，不代表集群性能**；未部署 HDFS/YARN，未引入 Hive；
3. 31 类中文风格仍只有 4.87%；iTunes 的 82% 只代表 150 首抽样；
4. 音频特征缺 `danceability`/`energy`（源文件全 0），且为 2011 年前 Echo Nest 估计值；
5. 歌手相似边无分数/排名，只能当二值邻居集合；
6. 与 `songs.csv` 仍是两套 ID 体系，靠 `msd_spotify_map.csv`（7,678 首）交叉映射。

## 7. 与统一契约的关系

- 本模块**不修改** `data/processed/songs.csv`、`recommender/`、`web/`、`packaging/`；
- 若后续要把行为数据用于推荐，需要单独设计接口（当前 `recommend()` 契约只接受 `songs.csv` 字段）；
- 合并本分支不会改变主链路的任何行为。
