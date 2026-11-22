# 数据组复现说明

> 仓库已提交 `data/processed/` 成品（负责人 2026-11-22 决定，供 B/C 联调），可直接使用；
> 如需从头复现或核对版本，运行 `python data_processing/build_dataset.py`（约 1–3 分钟，首次需联网）。
> 再分发权限尚未确认，见 `docs/data/sources_and_licenses.md`。

环境：Windows 11 x64；Java 17（Temurin 17.0.19）；Python 3.12；PySpark 4.0.1（本地模式 `local[*]`）。
所有命令在仓库根目录执行。

## 1. 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r data_processing/requirements.txt
```

> 演示机不需要 Python / Java / 网络，因为打包后的 Flask 程序只读取已生成的 CSV；PySpark 只在本机清洗阶段使用。

## 2. 一键生成数据（推荐）

```powershell
.\.venv\Scripts\python.exe data_processing/build_dataset.py
```

依次执行：下载并映射（19.2 MB，来自 `hf-mirror.com`，中国大陆通常无法直连 `huggingface.co`）→ PySpark 清洗 → 契约校验，约 1–3 分钟。

常用变体：

```powershell
# 已有 data/raw/spotify_tracks_raw.csv，跳过下载，可离线重跑
.\.venv\Scripts\python.exe data_processing/build_dataset.py --reuse-raw

# 已从 Kaggle 手动下载 dataset.csv
.\.venv\Scripts\python.exe data_processing/build_dataset.py --from-file "D:\path\to\dataset.csv"
```

原始文件 `data/raw/*` 与生成结果 `data/processed/*.csv` **都不提交仓库**（见 `data/.gitignore`），脚本会打印 `dataset.csv` 的 SHA-256：
`b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`。

### 手动分步（与脚本等价）

```powershell
python data_processing/download_spotify.py
.\.venv\Scripts\python.exe data_processing/clean_songs.py `
  --input data/raw/spotify_tracks_raw.csv `
  --out-dir data/processed `
  --metrics data/processed/run_metrics.json
```

输出：

- `data/processed/songs.csv`（契约表头，普通 UTF-8 CSV，89,740 行，约 6.4 MB，行尾 LF、无 BOM）
- `data/processed/genre_counts.csv`（31 个大类）
- `run_metrics.json`：输入/输出行数、剔除与合并数量

Spark 原生 `write.csv` 会生成目录，脚本内部用 `coalesce(1)` 写临时目录后移动为单文件，最终产物是普通文件，不是目录。

## 3. 用样例验证流水线（不需要网络）

```powershell
.\.venv\Scripts\python.exe data_processing/clean_songs.py --input data/sample/songs_sample.csv --out-dir dist/sample_out
```

## 4. 测试与成品校验

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s data_processing/tests -v
.\.venv\Scripts\python.exe data_processing/validate_outputs.py
```

- 单元/流水线测试覆盖：表头契约、去空格、重复 ID 标签并集合并、空风格/空歌手、重复标签、逗号字段解析、风格计数、缺列报错、虚构样例契约、下载映射与引号规范化、大类映射完整性。首次运行需启动 Spark，单次约 15–60 秒。
- `validate_outputs.py` 不依赖 Spark，几秒内校验成品：UTF-8 无 BOM、LF 行尾、表头、唯一性、排序、空值、标签规范、`genre_counts.csv` 与 `songs.csv` 交叉核对。

## 5. 本次实际运行记录（2026-11-19，本机）

### 5.1 下载与映射

- 命令：`python data_processing/download_spotify.py --from-file <本地 dataset.csv>`
- 原始行数 114,000，映射后 114,000 行；`dataset.csv` 19.2 MB，SHA-256 见上；114 个英文风格先映射为中文细分，再归并为 31 个大类（`data_processing/genre_map_zh.csv`），英文原文与中文细分分别保留在 `genres_en`、`genres_zh` 列。

### 5.2 清洗

```
输入 114000 行，删除空 ID/歌名 1 行，重复 ID 合并 24259 行，成品 89740 首，风格统计 31 行
```

`data/processed/run_metrics.json`：

```json
{
  "input_rows": 114000,
  "songs_rows": 89740,
  "dropped_blank_id_or_name": 1,
  "duplicate_song_id_rows": 24259,
  "genre_rows": 31,
  "total_genre_assignments": 110166
}
```

大类计数范围 996–15,556（电子最多，喜剧最少；均衡抽样 + 大类归并导致，不代表市场分布）；16,981 首有 2 个及以上大类；2,900 首标题含中文。计数合计 110,166 大于曲目数，是因为 `华语流行` 等标签同时挂在「流行」和地区流行两个大类下。

### 5.3 测试

```
Ran 17 tests in 16.371s
OK
```

## 6. 已知环境注意点

- `JAVA_HOME` 必须指向 JDK/JRE 17；Java 8 无法启动 Spark 4。
- Windows 上 Spark 读写 CSV 需要 Hadoop 的 `winutils.exe`：把 `winutils.exe`、`hadoop.dll` 放到 `%HADOOP_HOME%\bin`，设置 `HADOOP_HOME` 并把该 `bin` 加入 `PATH`。缺少时会报 `HADOOP_HOME and hadoop.home.dir are unset`。
- 本机 `%TEMP%` 下 cmd 重定向被拒绝时，Spark 启动会报 `Access is denied` 且找不到 `spark-class-launcher-output-*.txt`；把 `TEMP`、`TMP` 指到工作区可写目录即可。
- 若 Windows 控制台中文乱码，运行前设置 `$env:PYTHONUTF8="1"`；生成的 CSV 始终为 UTF-8。
- 首次运行 Spark 需要写临时目录，磁盘空间约 1 GB。
- Spark 输出目录中的 `_SUCCESS`、`.crc` 文件不会进入 `data/processed/`。

## 7. 备选数据源：MusicBrainz（CC0）

若课程要求使用许可最干净的数据源，可改用 MusicBrainz 方案（脚本已保留）：

```powershell
python data_processing/fetch_musicbrainz.py --total 5000
.\.venv\Scripts\python.exe data_processing/clean_songs.py --input data/raw/musicbrainz_raw.csv --out-dir data/processed
```

该方案核心数据为 CC0，但华语覆盖极弱、多标签需逐首回查、约需 2–3 小时网络时间；详见 `docs/data/sources_and_licenses.md`。
