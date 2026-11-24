# 歌单图推荐试玩

本目录基于 GitHub `main` 的 `9566ec1` 快照和 `2026-11-24-reviewed` 曲库。打开同一个歌单，在「推荐算法」选择「经典推荐」或「图推荐」，分别生成歌单查看前 10 首与推荐理由。也可以创建并导入自己的歌单作为种子。试玩数据放在 `test-user-data/`。

有 Flask 的 Python 环境下运行 `python start.py`，然后访问 [本地页面](http://127.0.0.1:5076/)。按 Ctrl+C 退出。`start.py --port` 可指定别的端口。

## 构建索引

先把组内交接包的 `songs.csv` 和 `genre_counts.csv` 放到仓库的 `data/processed/`。详细交接见 [新版曲库交接](../../data/catalog-pipeline/README.md)。

以下命令从试玩目录运行。先建全量图，首次实验可在第一条末尾追加 `--sample-size 40000`，并给样本使用独立输出和索引路径。

```powershell
$archive = 'C:/path/to/组内交接包/outputs'
python graph_recommendation/prepare_graph.py "$archive/新版曲库-复核版" "$archive/全量曲库-统一标签/recommendation_genres.csv" graph-data --label-details "$archive/全量曲库-统一标签/song_label_details.csv"
python graph_recommendation/build_index.py graph-data/graph.json data/processed/graph_index.sqlite3
python graph_recommendation/evaluate.py data/processed/graph_index.sqlite3 data/processed/songs.csv evaluation.json demo-playlist.csv
python tests/test_graph_playlist.py
```

第二条默认走 Python 的有限前沿加权 PageRank。使用 Neo4j 时，在图计算主机安装与数据库版本相容的 GDS 插件及 Python 驱动 `pip install -r graph_recommendation/requirements.txt`，确认 `RETURN gds.version()` 可用，然后执行：

```powershell
python graph_recommendation/build_index.py graph-data/graph.json data/processed/graph_index.sqlite3 --neo4j-uri bolt://127.0.0.1:7687
```

启用认证时由环境变量 `NEO4J_USER`、`NEO4J_PASSWORD` 提供账号和口令，`NEO4J_DATABASE` 默认 `neo4j`。建议连接本机专用实验库。工具用独立的运行 ID 写入与清理节点及图投影，数据库保留索引约束以便下次运行。离线生成的 SQLite 记录后端版本与原始歌曲 CSV 哈希，网页使用索引前会检查版本。索引缺失、不可读或不匹配时，页面给出提示并使用经典推荐。 [Neo4j GDS 兼容矩阵](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/)

可追加 `--probe-playlist demo-playlist.csv playlist-probe.json`，让 GDS 在同一张投影上直接以歌单歌曲为多起点运行，导出过滤种子后的前 10 首。探针所用 CSV 至少要有两首歌曲出现在当前投影里。网页仍通过预计算候选合并取得结果，便于比较在线近似与原生多种子结果。

## 算法和验收口径

- 保留全部曲目。曲风用复核建议权重，权重为 0 的曲目不建立曲风边。已有标签支持时保留华语、粤语和日韩等流行子类，避免在建图时全部折叠为「流行」。合作署名继续作为整体，已有别名表中的艺人按已知名称归并。
- 艺人相似度采用可信曲风 TF-IDF 余弦相似度、共享样本数降权以及最多 20 条近邻。图传播使用有向加权边，按艺人和曲风节点预计算最多 200 个候选。首版为所有录入曲风和曲目数最多的 120 个艺人预计算 PageRank，其他艺人仍有直接的歌曲索引。
- 在线融合直接偏好、图相关性及标签证据，并做歌单内去重和多样性重排。优先保留两个歌单艺人位置，剩余位置允许跨艺人探索。图关系显示已验证的可连通路径，路径用于说明候选如何与种子相关。
- 测试覆盖推荐切换、排除歌单种子、疑似版本组限流、无曲风证据的曲目、索引与曲库不匹配时的回退。对照工具使用华语流行、摇滚、爵士三组实库曲目，记录结果重合度、艺人数和耗时。相关性指标需要留出真实歌单或用户反馈。

## 本轮实测

使用 Neo4j Community 5.26.32 和 GDS 2.13.12。4 万首样本投影包含 50,353 个节点、162,541 条有向关系。全量投影包含 **293,864 首曲目、336,812 个节点和 1,006,310 条有向关系**，离线导出 29,200 条候选，试玩页使用该索引。样本中还运行了一次以三首歌曲为起点的原生 PageRank。

| 测试歌单 | 经典推荐前 10 的艺人数 | 图推荐前 10 的艺人数 | 经典推荐中位耗时 | 图推荐中位耗时 |
| --- | ---: | ---: | ---: | ---: |
| 华语流行 | 1 | 10 | 1.541 秒 | 0.027 秒 |
| 摇滚 | 2 | 10 | 1.327 秒 | 0.026 秒 |
| 爵士 | 8 | 9 | 1.276 秒 | 0.026 秒 |

每组在已初始化的 SQLite 曲库中运行三次，经典推荐全库扫描，图推荐查询预生成索引。耗时不含曲库导入、离线构建或浏览器渲染。上表记录初版结果，具体曲目见工作区 `outputs/Neo4j-GDS-全量对照.json`。

## 推荐内容与路径修复

经典和图推荐共用讲解及访谈过滤规则，保留原曲库和本地搜索。图索引第二版在建图时跳过明确的讲解和访谈关系，运行时再次检查歌曲标签和结构化标题。已知的喜剧歌曲、同名作品和模糊标题继续按音乐曲目处理。

图推荐会为同时具备相似艺人边和歌单风格证据的候选留出探索位置。理由显示「歌单艺人 → 相似艺人 → 推荐曲目」。曲风候选可以显示「种子曲目 → 共享曲风 → 推荐曲目」，每一段都对应已有的图关系。相同三组歌单的复测报告见 `outputs/Neo4j-GDS-修复后回归.json`。

[发布验收](发布验收.md) · [分阶段对照汇总](graph-regression-metrics.json)
