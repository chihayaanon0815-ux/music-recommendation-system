# 离线运行 Neo4j 图推荐

1. 在 GitHub 的 `main` 分支选择 **Code → Download ZIP**，并完整解压到可写目录。
2. 在 Windows x64 上双击 `Start-MusicRecommendation.cmd`。首次启动会校验并还原程序、曲库和推荐索引，随后打开本地网页。
3. 在网页新建歌单，添加曲目或导入[示例歌单 CSV](offline-sample-playlist.csv)，然后选择「图推荐」生成推荐歌单。
4. 在启动窗口按 Ctrl+C 或关闭窗口退出。

本包包含应用运行时和已计算的 Neo4j GDS 推荐索引。下载完成后，曲库搜索、歌单和图推荐均可在本机离线运行。索引来自 662,939 首曲目版本，包含 30,800 条预计算候选。

[索引校验清单](../../../data/processed/graph_index_snapshot.json) · [完整建图与验收](catalog-662939.md)

使用源码时，可在已安装 Flask 的 Python 3.11 或更新环境执行 `python start.py`。该入口也会自动还原曲库和推荐索引。
