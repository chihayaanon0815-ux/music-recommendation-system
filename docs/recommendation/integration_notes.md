# 联调说明（给 C 网页 / 集成人）

B 的模块与 C 的网页之间只走 `recommend()` 一个函数，不共享全局状态，也没有网络调用。

## 1. 契约速查

```python
from recommender.recommend import recommend
results = recommend(songs, preferences, limit=10)
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `song_id` | string | 唯一，同分排序依据（字符串序） |
| `song_name` | string | 展示名 |
| `artist` | string | 展示名 |
| `genres` | string | `\|` 分隔原样透传 |
| `score` | int | 3 × 命中风格数 + 2（歌手命中） |
| `reason` | string | 中文，非空 |

无偏好：`score=0`、理由以“默认推荐”开头；有偏好但无命中：返回 `[]`。

## 2. 实测开销（本机，5 首样例）

| 场景 | 耗时 |
| --- | --- |
| 23 项测试全跑 | 0.002 s |
| 演示脚本（4 组场景） | 小于 0.1 s |
| 单次 `recommend`（5 首） | 微秒级，可忽略 |

扫描与排序都在内存里完成；8.9 万首规模仍是毫秒级，页面每次请求重算即可，不需要缓存或预热。

## 3. 给 C（网页）

1. **保留 try/except 回退**：导入失败时页面会退回自带的模拟算法，所以 `recommender/` 一旦被误删或改名，页面不会报错但结果会变假。请在页面算法标签上保留“推荐算法模块”这个可核对标志。
2. **空结果要单独处理**：`[]` 表示“有偏好但没命中”，不是出错。显示“没有匹配歌曲，试试调整偏好”，不要自动改回默认推荐，也不要显示 0 条结果的表格。
3. **不要改字段名**：模板里取 `song.score`、`song.reason` 即可；`genres` 是原始字符串，页面要拆分请自己 `split("|")`。
4. **不要传 `None` 给 `songs`**：`songs=None` 会抛 `TypeError`；数据没加载好时先跳过调用。
5. **`limit` 保持正整数**：传 0 或负数会得到空列表，页面看起来像“没有推荐”。

## 4. 给打包与集成

- 合并只覆盖 `recommender/`、`tests/recommender/`、`docs/recommendation/`，不要动根 `README.md` 和 A、C 的目录；
- PyInstaller 要显式收集包：`pyinstaller --collect-submodules recommender ...`，否则打包后导入失败、页面静默回退；
- 打出来的 exe 在**离线**环境试一次：本模块无网络、无 Java、无 Spark，离线应完全可用；
- 合并后跑 `python -m unittest discover -s tests/recommender -v`，确认 `Ran 23 tests ... OK`。

## 5. 常见坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 页面还能出结果，但算法标签是“模拟算法” | `recommender` 未导入成功 | 检查目录名、`__init__.py`、打包收集参数 |
| 选了偏好却一条都没有 | 偏好与标签字符串不完全一致（大小写、空格、别名） | 对照 A 的标签表；本模块不做同义词归并 |
| 结果少于 10 条 | `limit` 是上限，命中不足不补齐 | 正常行为，不要当 bug |
| 默认推荐被标成“热门” | 文案写错 | 默认推荐不代表热度，改文案 |
| 同样输入两次结果不同 | 不应该发生 | 本模块确定性；若出现请检查是否混入了随机模拟算法 |
| 测试在别的目录跑失败 | 工作目录不对 | 在含 `recommender/` 的包根目录执行 `-s tests/recommender` |

## 6. 联调自检

```powershell
# 1) 模块可导入
python -c "from recommender.recommend import recommend; print('ok')"

# 2) 契约测试
python -m unittest discover -s tests/recommender -v

# 3) 演示
python tests/recommender/demo.py

# 4) 页面自检（在 C 的目录）
python -m pytest tests/web -q
```

四项都通过，且页面算法标签显示“推荐算法模块”，才算联调完成。只通过 1–3 而页面仍显示模拟算法，问题在导入路径或打包收集，不在算法本身。

## 7. v2 接入（可选，默认关闭）

v2 不是替换，而是**并列的第二套策略**。v1 的函数签名、默认行为、六字段输出全部保留，C 的页面不改也能继续跑。

### 7.1 最小改法（不动模板）

```python
from recommender.recommend import recommend
results = recommend(songs, preferences, limit=10, strategy="v2")
```

只把这一行的 `strategy` 换成 `"v2"` 即可；返回字段仍是 `song_id, song_name, artist, genres, score, reason`，只是 `score` 变成两位小数。

### 7.2 推荐改法（启动时建索引）

```python
from recommender.recommend_v2 import build_index, recommend_v2

INDEX = build_index(songs)          # 8.9 万首约 0.31 s，放在 app 启动处
...
results = recommend_v2(songs, preferences, limit=10, index=INDEX, exclude_ids=heard_ids)
```

单次请求从 0.59 s 降到 0.19 s。`songs` 每次传入同一份即可；若曲库被重载，需要重建 `INDEX`。

### 7.3 歌单页

```python
from recommender.recommend_v2 import recommend_from_seeds
results = recommend_from_seeds(catalog, seeds, limit=10, index=INDEX)
```

与 `playlist.py` 的 `recommend_playlist` 口径一致（优先同歌手），并额外支持 `diversity` 与 `exclude_ids`。

### 7.4 注意

| 事项 | 说明 |
| --- | --- |
| `score` 类型 | v2 是 float（两位小数），模板若格式化成整数需改 `"{:.1f}"` |
| 空结果 | v2 同样返回 `[]`，语义不变，页面仍要显示“没有匹配”，不要回退默认 |
| 多样性 | `diversity=0` 即纯分数排序，与 v2-div0 评估一致；上线默认 0.3 |
| 打包 | 新增 `recommend_v2.py`、`similarity.py` 都在 `recommender/` 内，`--collect-submodules recommender` 已能覆盖 |
| 回退 | 若 v2 导入失败，`strategy="v2"` 会抛异常；页面应 try/except 后回落 v1，而不是显示空结果 |

### 7.5 建议的上线顺序

1. 先用环境变量切 v2（如 `RECOMMENDER_STRATEGY=v2`），默认仍是 v1；
2. 页面上标注当前策略，方便验收时核对；
3. 对照 `docs/recommendation/eval_report_v2.md` 的三张表确认数字一致；
4. 稳定后再决定是否把默认改成 v2。
