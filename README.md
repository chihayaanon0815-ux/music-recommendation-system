# 个性化音乐推荐系统

## 下载并运行

Windows x64 用户可下载本分支的完整 ZIP，解压后双击 `Start-MusicRecommendation.cmd`。首次启动会核验并还原程序、曲库和推荐索引，随后打开浏览器。运行所需的 Python 已随程序打包。

详细步骤见 [离线使用说明](docs/recommendation/neo4j/offline-download.md)。

三人一周课程设计：离线 Windows 本地网页，PySpark 离线清洗，Flask 展示基于偏好的推荐和统计图。音频播放不在必做范围。

## 歌单功能

在首页创建歌单，搜索添加歌曲或导入 UTF-8 CSV。歌单详情页会统计歌曲风格和歌手，并按指定的 1–100 首生成新的推荐歌单。普通搜索优先查询本地曲库，本地无匹配时联网查询 MusicBrainz，也可以点击「搜索 MusicBrainz」查找其他版本。

运行、打包和本地存储说明见 [歌单版使用说明](歌单版使用说明.txt)。

## 并行协作
- 数据：feature/data-processing，负责 data_processing/、data/sample/、docs/data/
- 算法：feature/recommendation，负责 recommender/、tests/recommender/
- 网页与打包：feature/web-ui，负责 web/、packaging/、tests/web/

每人从 main 创建分支，阶段性提交并 push，完成后向 main 创建 PR；合并前检查接口与测试。不要强推 main，不要提交凭据、未经许可的数据、虚构实验结果或大型二进制。仓库为公开仓库。

## 统一契约 v1
CSV 为 UTF-8，表头 song_id,song_name,artist,genres；song_id 非空且唯一，genres 多标签用 | 分隔，空值为空字符串。示例 song_id=1,song_name=示例,artist=示例歌手,genres=流行|民谣。样例数据为虚构测试数据，须标明。
算法提供 recommender/recommend.py 的 recommend(songs, preferences, limit=10)：songs 为字典列表，preferences 为 {"genres":["流行"],"artists":[]}，返回字典列表，包含 song_id,song_name,artist,genres,score,reason。无偏好按 song_id 稳定排序并说明为默认推荐，不虚称热门。风格每命中一个加3分，歌手精确匹配加2分；只推荐正分结果，不足不补齐；无偏好返回默认列表。相同分数按 song_id 字符串排序。输入不修改；limit 非正返回空列表。若实际数据不足或契约需更改，先在 PR 提出并通知各组。
前端先用本地 mock，算法先用样例，数据组先提供样例，再接入真实数据。默认读取 data/processed/songs.csv；无真实数据时明确标记演示样例。
统计输出 data/processed/genre_counts.csv，列为 genre,count；按单首歌每个不同标签计数。若缺失可提示尚未生成。

## 验收
用户选偏好后看到前10条歌曲和真实匹配理由；未选择显示默认推荐；图表离线显示；清洗统计使用 PySpark 本地模式；打包后的 Windows 程序在无 Python、Java、网络的目标电脑运行。用户行为、音频、协同过滤非必做。真实数据来源、许可、清洗结果与实验如实记录。


## 并行开发补充细则
字段均为字符串，去掉首尾空格；genres 按 | 分割，去空、去重，按精确字符串比较，不转换大小写；preferences 缺键为空列表，重复选择去重。song_id 和 song_name 不可为空，artist 和 genres 可为空。无偏好结果 score=0，reason 标明默认推荐；有偏好但无匹配返回空列表。ID 按字符串字典序排序。
示例：歌曲 01，歌手“测试歌手”，风格“流行|民谣”；选择流行及测试歌手得 5 分，理由包含两个匹配项。
图一使用 genre_counts.csv；图二由 songs.csv 聚合非空歌手的歌曲数。数据不存在时说明状态，不虚构数据。A 提供可分发测试样例，B 和 C 的 mock 位于各自目录，不创建其他组的同名占位模块。
A 额外负责 docs/data/；B 负责 docs/recommendation/；C 负责 docs/web/。各组仅修改各自目录，共享文件和依赖由团队指定的集成人协调，契约变更通过 PR 与各负责人协商。各分支阶段性 push 并提交 PR，不能强推 main 或自动合并他人工作。合并和目标 Windows 设备验证由团队负责。

## 新版曲库与 Neo4j 图推荐

- [662,939 首曲库的新增数据处理与行为覆盖复核](docs/data/catalog-behavior-2026-11-25/README.md)
- [曲库扩充、采集脚本及交接](docs/data/catalog-pipeline/README.md)
- [图推荐构建、复现和对照](docs/recommendation/neo4j/README.md)
- [推荐内容策略与 Windows 验收](docs/recommendation/neo4j/发布验收.md)

## 已整合的交付

main 包含 662,939 首曲库、名称修复、来源 ID 映射、改进后的 Neo4j 图推荐索引与 Windows 离线程序。下载本仓库 main 的完整 ZIP，解压后双击 Start-MusicRecommendation.cmd。

用户行为数据清洗、Spark/Parquet、MapReduce、ItemCF 实验及图表见 [行为数据处理说明](docs/data/behavior_pipeline.md)。其中的 ItemCF 和训练测试划分已知待修项在该文档中记录。原始听歌日志用于重新训练时由组内数据包提供。
