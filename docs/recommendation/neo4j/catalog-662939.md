# 662,939 首曲库的 Neo4j 图推荐

图索引使用名称编码修复版曲库。全量投影包含 743,878 个节点和 2,212,466 条有向关系。Neo4j GDS 2.13.12 为 154 个曲风和艺人种子计算并导出 30,800 条候选。网页读取生成的 SQLite 索引。

曲目共识的曲风权重为 1，单一曲目来源为 0.8，来源冲突为 0.45，同艺人曲目多数为 0.5，扩展录音或外部艺人证据为 0.35。若已有复核给予更低权重，按更低值。缺少主曲风证据的曲目仍可参与同艺人关联。口语或喜剧内容及待确认歌名保留在曲库中，图推荐过滤这些条目。

## 从本分支重建

以下命令从仓库根目录运行。准备项目的 Python 依赖和 `graph_recommendation/requirements.txt` 中的 Neo4j 驱动，并启动启用了 GDS 的 Neo4j 实例。根据实际配置替换 URI。认证由 `NEO4J_USER`、`NEO4J_PASSWORD` 提供。

```powershell
python -m web.catalog_snapshot
python graph_recommendation/prepare_graph.py data/processed data/processed/genre_counts.csv graph-data --genre-evidence data/processed/behavior/genre_annotations.csv.gz --review-policies graph_recommendation/catalog_review --label-details graph_recommendation/catalog_review/regional_pop_labels.csv
python graph_recommendation/build_index.py graph-data/graph.json data/processed/graph_index.sqlite3 --neo4j-uri bolt://127.0.0.1:17687 --probe-playlist docs/recommendation/neo4j/catalog-662939-probe-seeds.csv graph-data/gds-probe.json
python start.py --port 5081
```

第一条命令将 GitHub 的曲库分片还原为单个 CSV 并校验。图索引在本地生成。生成后网页可离线使用，在歌单里选择「图推荐」。

## 验收

同一组华语流行、摇滚和爵士种子各返回 10 首，计算中位耗时分别为 35.8、24.1、34.7 毫秒。计时从已初始化的本地曲库请求推荐开始。原生 GDS 的两首新曲目种子探针也返回 10 首，并排除种子。38 项自动化测试通过，实际网页生成歌单入口已核验。

[三组对照明细](catalog-662939-evaluation.json) · [索引与网页核验](catalog-662939-verification.json) · [原生 GDS 探针](catalog-662939-native-probe.json)
