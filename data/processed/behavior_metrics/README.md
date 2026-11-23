# 行为数据聚合指标（不随仓库分发逐条数据）

本目录只保存**聚合统计**，用于报告与复现核对；逐条交互/宽表/特征/相似边留在本地数据包。

| 文件 | 内容 |
| --- | --- |
| `clean_metrics.json` | k-core 参数、保留用户/歌曲/交互、密度、耗时 |
| `cf_metrics.json` | ItemCF 评估（HitRate@10、Precision、覆盖率等） |
| `data_quality.json` | 用户/歌曲度数与播放量分位数、直方图 |
| `perf_compare.json` | Spark 与 Pandas 同口径统计耗时对比 |
| `msd_meta_coverage.json` | 歌名/歌手/专辑/年份/时长覆盖率 |
| `coverage_denominators.json` | 覆盖率的分母拆解（曲目/交互/播放/用户/候选池） |
| `genre_fill_potential.json` | 用艺术家标签补风格的上限测算（99.79%，但标签宽泛） |
| `msd_features_stats.json` | 音频特征分布、不可用字段（danceability/energy 全 0） |
| `artist_similarity_stats.json` | 相似度覆盖、Top 歌手邻居、用户推荐演示 |
| `mapreduce_metrics.json` | Hadoop Streaming 作业耗时与校验值 |
| `itunes_crawl_stats.json` | iTunes 爬虫命中率、流派覆盖率、请求数 |
| `mb_tags_stats.json` | MusicBrainz Top100 样例命中与标签覆盖 |

图表见 `../behavior_charts/`；方法与局限见 `../../docs/data/behavior_pipeline.md`。

> 许可：这些指标由 MSD / Echo Nest 数据聚合而来，仅限非商业研究与课程组内使用；
> 引用时请署名 *Million Song Dataset, Echo Nest Taste Profile Subset (LabROSA / The Echo Nest)*。
