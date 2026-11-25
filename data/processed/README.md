# 曲库数据

本分支的 [CSV 分片](catalog-parts) 共 662,939 首，保留项目的四列表头。网页和歌单搜索可直接读取分片。需要单个 CSV 时，在仓库根目录运行 `python -m web.catalog_snapshot`。

`genre_counts.csv` 为当前曲风计数，`catalog_snapshot.json` 记录文件校验值。`behavior/` 提供来源 ID 映射与标签补齐记录。`run_metrics.json` 为早期 Spotify 清洗实验的历史统计。详见 [用户行为曲库处理说明](../../docs/data/catalog-behavior-2026-11-25/README.md)。
