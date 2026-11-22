# data_processing（角色 A：数据处理）

负责音乐数据的获取、PySpark 本地清洗与统计，产出统一契约的 CSV。

## 文件

| 文件 | 用途 |
| --- | --- |
| `download_spotify.py` | 下载 Spotify Tracks Dataset（HF 镜像），映射为统一字段并应用中文风格映射 |
| `genre_map_zh.csv` | 114 个英文风格 -> 中文细分 -> 31 个大类的人工映射表（三列，未收录的保留原文） |
| `clean_songs.py` | PySpark local 清洗 CLI：去空格、去重合并、标签规范化，输出 `songs.csv` / `genre_counts.csv` |
| `build_dataset.py` | 一键生成：下载 → 映射 → 清洗 → 契约校验 |
| `validate_outputs.py` | 不依赖 Spark 的成品校验：表头、唯一性、排序、空值、标签规范、计数交叉核对 |
| `fetch_musicbrainz.py` | 备选数据源：从 MusicBrainz（CC0）采集带风格标签的录音 |
| `requirements.txt` | `pyspark==4.0.1` |
| `tests/test_data_pipeline.py` | 下载映射、采集辅助函数与清洗流水线测试（不访问网络） |

产物与文档：

- **成品数据已提交**（项目负责人 2026-11-22 决定，供 B/C 联调）：`data/processed/*.csv` 与 `run_metrics.json`；再分发权限未确认，见 `docs/data/sources_and_licenses.md`；
- `data/processed/songs.csv`：89,740 首真实曲目（4 列契约），约 6.4 MB，UTF-8 无 BOM、LF 行尾；
- `data/processed/genre_counts.csv`：31 个中文大类计数；
- `data/processed/run_metrics.json`：本次运行的行数与去重指标；
- `data/sample/songs_sample.csv`：**虚构**测试样例（8 行），供 B、C 并行开发；
- `docs/data/sources_and_licenses.md`：来源、许可状态（含 ODbL 与 Spotify 条款说明）、再分发策略、MusicBrainz 实测规模；
- `docs/data/data_dictionary.md`：数据字典与清洗规则；
- `docs/data/reproduction.md`：复现命令、环境与实际运行记录；
- `docs/data/integration_notes.md`：给 B、C 的接入注意点（31 类风格、3.1 万歌手、转义、图表口径）。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r data_processing/requirements.txt

# 1) 成品数据已在仓库 data/processed/，可直接校验（不需要 Spark）
.\.venv\Scripts\python.exe data_processing/validate_outputs.py

# 2) 如需从头复现：下载 + 清洗 + 校验（约 1–3 分钟）
.\.venv\Scripts\python.exe data_processing/build_dataset.py

# 3) 测试
.\.venv\Scripts\python.exe -m unittest discover -s data_processing/tests -v
```

## 边界

- 只使用元数据，不下载音频；不包含播放量之外的平台内部数据。
- 风格采用两级分类：114 个英文标签 -> 中文细分 -> 31 个中文大类（酷狗式曲风 + 场景/人群），人工整理、非官方译名；细分与英文原文保留在 `data/raw/spotify_tracks_raw.csv` 的 `genres_zh`、`genres_en` 列。
- 不修改 `recommender/`、`web/`、`packaging/` 等他人目录。
- 数据集许可为 ODbL + 内容版权归原作者，且底层经 Spotify API 采集，**不是 CC0**；如需完全干净的许可，改用 `fetch_musicbrainz.py`（CC0）。
