# data/processed（本目录的 CSV 不在仓库里）

仓库**不提交** Spotify 衍生数据（许可链说明见 `docs/data/sources_and_licenses.md`）。
本目录只保留这份说明；`songs.csv`、`genre_counts.csv`、`run_metrics.json` 由脚本在本地生成，并被 `data/.gitignore` 忽略。

## 生成方式

```powershell
python data_processing/build_dataset.py
```

- 首次运行：联网下载 19.2 MB 原始 CSV → 字段映射 → PySpark 清洗 → 契约校验，约 1–3 分钟；
- 已有 `data/raw/spotify_tracks_raw.csv` 时：`python data_processing/build_dataset.py --reuse-raw`（可离线）；
- 已有 Kaggle 下载的 `dataset.csv` 时：`python data_processing/build_dataset.py --from-file D:\path\to\dataset.csv`。

## 生成后的契约

| 文件 | 内容 |
| --- | --- |
| `songs.csv` | 89,740 首，表头 `song_id,song_name,artist,genres`，UTF-8 无 BOM、LF |
| `genre_counts.csv` | 31 个中文大类计数，表头 `genre,count` |
| `run_metrics.json` | 输入/输出/去重行数 |

生成后可用 `python data_processing/validate_outputs.py` 复核。

## 为什么不提交

数据集原始内容涉及版权与 Spotify API 条款，许可标注存在冲突（ODbL 数据库 + 内容版权归原作者；HuggingFace 另标 BSD）。
为避免在公开仓库再分发，只提交生成脚本与虚构样例（`data/sample/`）。
