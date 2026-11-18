# 个性化音乐推荐系统

三人一周课程设计：离线 Windows 本地网页，PySpark 离线清洗，Flask 展示基于偏好的推荐和统计图。音频播放不在必做范围。

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
