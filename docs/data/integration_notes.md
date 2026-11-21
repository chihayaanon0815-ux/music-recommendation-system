# 联调说明（给 B 推荐算法 / C 网页打包）

本文件补充 `docs/data/data_dictionary.md`，只讲“接入时要注意什么”。数据契约仍以仓库 README 为准。

## 0. 先本地生成数据（仓库不含数据文件）

```powershell
python data_processing/build_dataset.py
```

首次运行约 1–3 分钟（下载 19.2 MB + PySpark 清洗），生成 `data/processed/songs.csv` 等文件；这些文件不提交 Git。
之后可 `--reuse-raw` 离线重跑。C 打包前务必先执行一次，否则程序目录里没有数据。

## 1. 契约速查

```
data/processed/songs.csv        89,740 行；表头 song_id,song_name,artist,genres
data/processed/genre_counts.csv 31 行；表头 genre,count
```

- 四个字段都是字符串；`song_id` 唯一、按字符串升序；`song_name` 非空；**本数据 `artist` 也全部非空**（0 条空歌手）。
- `genres` 为 31 个中文大类，多个用 `|` 分隔、按字符序升序；没有空 `genres`。
- 文件 UTF-8 无 BOM、LF 行尾；仓库用 `data/.gitattributes` 强制 LF，若你的客户端仍检出 CRLF，`csv`/`pandas` 均可正常读取。

## 2. 实测开销（本机，89,740 首）

| 操作 | 耗时 |
| --- | --- |
| `csv.DictReader` 一次性读入内存 | 约 0.12 秒 |
| 朴素实现遍历全部曲目做打分并取前 10 | 约 0.05 秒 |

结论：**每次请求重新读 CSV 也不慢，但建议进程内缓存一份**，避免重复 IO。不需要数据库。

加载示例（只用标准库，便于打包）：

```python
import csv
from functools import lru_cache

@lru_cache(maxsize=1)
def load_songs(path="data/processed/songs.csv"):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
```

## 3. 给 B（推荐算法）

- `genres` 现在是 **31 个中文大类**（`流行`、`摇滚`、`电子`、`华语流行`、`伤感`…），不是 114 个细分类；偏好里的字符串按**精确匹配**（去空格、区分大小写），不要做同义词/模糊匹配。
- 一首歌可能有多个大类（18.9%），按契约“每个匹配风格 +3”；用户同时勾选 `流行` 和 `华语流行` 时，一首华语流行歌会命中两个标签、加 6 分——这是契约行为，不是 bug。
- `artist` 是整串，可能含 `&`、空格、非拉丁字符（如 `Pink Sweat$ & Kirby`、`Håkan Hellström`）。**不要按空格或 `&` 拆分歌手**，整串精确比较。
- 其余按任务包：同分按 `song_id` 字符串升序；`limit<=0` 返回空列表；无偏好返回默认排序（score=0，理由写明“默认推荐”）；不修改传入对象。

## 4. 给 C（网页与打包）

- **风格下拉**：31 个大类，直接全列可接受。
- **歌手下拉要小心**：非空歌手共 **31,430 个**，其中 20,144 个只有 1 首歌。普通 `<select>` 会有 3 万项、体验极差。建议：
  - 用 `<input list="artists">` + `<datalist>` 做可搜索输入；或
  - 只列出现次数 Top 50–100 的歌手，并在说明里写明“其余歌手可手动输入”。
  两种做法都符合“选项来自非空 artist”，但要在文档里写清楚实际做法。
- **图表口径**：
  - 图 1：`genre_counts.csv`，31 根柱子、计数 996–15,556；这是“均衡抽样 + 大类归并”的结果，**不能写成“最受欢迎风格”**；
  - 图 2：`songs.csv` 按非空 `artist` 聚合，Top 10–15 即可（最多的是 George Jones 260 首、my little airport 171、The Beatles 149），不要试图渲染 3 万个歌手。
- **转义**：24,436 首歌名或歌手含 `&`、`<`、`>` 等字符。Jinja 模板会自动转义；如果在前端拼 JS 数组，用 `{{ data|tojson }}` 或 `json.dumps(..., ensure_ascii=False)`，**不要手工拼字符串**，否则中文和引号会坏。
- **文件缺失**：`songs.csv` 或 `genre_counts.csv` 不存在时按任务包显示明确状态，不要回退到“看起来像真数据”的假数据；可以保留 mock 但标注“演示数据”。
- 打包时把 `data/processed/` 两个 CSV 放到程序可读位置，路径用同一套启动逻辑（源码运行 vs PyInstaller 目录）解析，说明里写清。

## 5. 常见坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 第一行变成 `\ufeffsong_id` | 用 Excel/记事本另存加了 BOM | 别用 Excel 重存；用仓库原文件 |
| 风格匹配全不中 | 页面写死了“流行/民谣”，数据里是 31 类中文名 | 选项从数据生成 |
| 歌手偏好永远不命中 | 把 `A & B` 拆成 `A`、`B` 两个值 | 整串精确匹配 |
| 图表数字对不上 | 多标签计数被当成占比 | 说明“同一首歌可计入多个大类” |

## 6. 联调自检

```powershell
python data_processing/validate_outputs.py
python -c "import csv; rows=list(csv.DictReader(open('data/processed/songs.csv',encoding='utf-8'))); print(len(rows), len({r['song_id'] for r in rows}))"
```

预期：`89740 89740`，且校验通过。
