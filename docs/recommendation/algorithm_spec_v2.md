# 推荐算法 v2 规格与实现规则

本文件描述 `recommender/recommend_v2.py` 的实现口径。与 v1 一样，它是**确定性规则打分**，不是训练模型：同一份输入永远得到同一份输出，任何一条分数都能手工复算。

## 1. 定位

| 项目 | 内容 |
| --- | --- |
| 对 v1 的关系 | 完全向后兼容：v1 的 `recommend()` 默认行为、23 项契约测试不变 |
| 新增入口 | `recommend(strategy="v2")`、`recommend_v2()`、`recommend_from_seeds()` |
| 依赖 | Python 标准库（`math`、`unicodedata`），不引入 numpy/pandas |
| 是否改契约定 | 否；v2 的输出仍是六个字段，只是分值与理由更细 |
| 适用规模 | 8.9 万首实测（见 `eval_report_v2.md`），单次数百毫秒内 |

## 2. 新增文件

| 文件 | 作用 |
| --- | --- |
| `recommender/similarity.py` | 文本归一化（NFKC + 去空格 + casefold）、标签切分、偏好覆盖度、Jaccard |
| `recommender/recommend_v2.py` | v2 主算法：软匹配 + 热度先验 + MMR 重排 + 歌单种子模式 |
| `tests/recommender/test_recommend_v2.py` | 31 项测试（策略开关、软匹配、热度、多样性、排除、边界、种子模式） |
| `tests/recommender/eval_v2.py` | 真实曲库离线评估脚本，输出三张对比表与 JSON 摘要 |
| `docs/recommendation/algorithm_spec_v2.md` | 本文件 |
| `docs/recommendation/eval_report_v2.md` | 真实数据上的评估结果与口径 |

## 3. 对外函数

| 函数 | 签名 |
| --- | --- |
| 策略开关 | `recommend(songs, preferences, limit=10, strategy="v1")` |
| v2 偏好推荐 | `recommend_v2(songs, preferences, limit=10, *, diversity=0.3, popularity_weight=0.6, exclude_ids=None, max_per_artist=2)` |
| v2 歌单续听 | `recommend_from_seeds(catalog, seeds, limit=10, *, diversity=0.3, popularity_weight=0.6, exclude_ids=None, max_per_artist=None)` |

`strategy` 只接受 `"v1"` / `"v2"`，其他值抛 `ValueError`；`limit` 非 `int` 抛 `TypeError`，`limit<=0` 返回 `[]`；`diversity` 越界抛 `ValueError`。

## 4. 评分公式

对每一首歌：

```text
score = 3.0 × coverage + 2.0 × artist_hit + popularity_weight × popularity
```

| 项 | 定义 | 取值范围 |
| --- | --- | --- |
| `coverage` | 歌曲覆盖的偏好风格数 / 请求的风格数 | 0 – 1 |
| `artist_hit` | 歌手与偏好歌手 casefold 后相同 | 0 / 1 |
| `popularity` | 曲库频次先验（见第 5 节） | 0 – 1 |
| `popularity_weight` | 默认 0.6，可传 0 关闭热度 | ≥ 0 |

要点：

1. **软匹配**：选了 2 个风格，歌曲只命中 1 个得 1.5 分而不是 0 分；
2. **归一化**：偏好与标签比较前做 NFKC、去首尾空格、casefold，所以 `Pop`/`pop`、全角空格都能命中（v1 是精确比较）；
3. **资格线**：`coverage<=0 且无歌手命中` 的歌曲直接丢弃，热度不会让无关歌曲挤进结果；
4. 风格权重 3.0 仍高于歌手 2.0，与 v1 的相对优先级一致。

## 5. 热度先验

`popularity = 0.4 × artist_part + 0.6 × genre_part`

| 分量 | 计算 |
| --- | --- |
| `artist_part` | `log1p(该歌手曲目数) / log1p(曲库最大歌手曲目数)` |
| `genre_part` | 该歌各标签中**最大**的 `log1p(标签曲目数)/log1p(最大标签曲目数)` |

- 用 `max` 而不是平均，避免“一个冷门标签 + 一个热门标签”的歌被误判为不热门；
- 风格权重高于歌手权重：否则冷启动会变成“某位高产歌手的作品列表”（复现记录见评估报告第 5 节）；
- 热度上限 0.6 分，不足 3 分的一次风格命中，排序主导权仍在标签匹配。

## 6. 多样性与单歌手配额

候选先按 `score` 降序、`song_id` 升序排好，再走 MMR：

```text
relevance_i = score_i / max(score)
penalty_i   = max over chosen j of min(1, jaccard(tags_i, tags_j) + 0.4 × same_artist(i, j))
mmr_i       = relevance_i − diversity × penalty_i
```

- 每轮取 `mmr` 最大者，平局按 `song_id` 字符串序，保证可复算；
- `diversity=0` 时退化为纯分数排序；
- **单歌手配额** `max_per_artist=2`：同一歌手最多 2 首，配额用尽且候选不足时自动放宽，绝不返回不足 `limit` 的结果；
- 候选池按“每歌手最多 `max(2, 4×配额)` 首”预筛，避免高产歌手把池子占满（89,740 首实测时曾出现 top10 全是同一歌手，这一条就是修正）。

## 7. 冷启动

未选择任何偏好时：

| 项目 | v1 | v2 |
| --- | --- | --- |
| 排序依据 | `song_id` 字典序 | 热度先验降序，`song_id` 升序兜底 |
| score | 0 | 0.0 |
| 理由 | “默认推荐：未选择偏好，按 song_id 字典序展示” | “默认推荐：未选择偏好，按曲库热度（歌手与风格出现频次）排序” |

v2 的口径是**如实说明按热度**，不把默认结果包装成个性化推荐。

## 8. 歌单种子模式 `recommend_from_seeds`

输入 `seeds`（歌单里已有的歌曲），构建画像：

| 信号 | 分值 |
| --- | --- |
| 风格：`3.0 × (该风格在种子中出现次数 / 种子内最大次数)` | 0 – 3 每标签 |
| 歌手：`2.0 × min(该歌手在种子中出现次数, 3)` | 0 – 6 |
| 热度：`0.6 × popularity` | 0 – 0.6 |

- 种子自身（按 `song_id` 与 `(歌名, 歌手)` 双重判断）不进入候选；
- 歌手项有意不做除法归一：8 首同歌手的歌单，续听应继续给该歌手，这与 C 现有 `recommender/playlist.py` 的取向一致；
- 测试与评估显示在“歌手续听”场景与 v1 持平（P@10 = 1.0），v2 额外提供 `diversity`、`exclude_ids`、更细的理由文本。

## 9. 处理流程

```text
1. 校验 limit / diversity；limit<=0 → []
2. 取偏好，strip/casefold 去重；exclude_ids 转集合
3. 规范化曲库：跳过空 id/空名、重复 id；保存原始 genres 与标签列表
4. 建立歌手/风格频次表 → 热度先验
5. 有偏好：
   a. 逐曲算 coverage、artist_hit；无任何命中 → 跳过
   b. score = 3×coverage + 2×artist_hit + w×popularity
   c. 按 (-score, song_id) 排序 → 候选池（每歌手限流）
   d. MMR 选 top-limit（含单歌手配额与放宽）
6. 无偏好：按 (-popularity, song_id) 取 top-limit，score=0
7. 输出六字段新字典，score 保留两位小数
```

## 10. 复杂度

设曲库 N、候选 C、返回 K：

| 阶段 | 复杂度 |
| --- | --- |
| 规范化 + 频次表 | O(N × 平均标签数) |
| 打分 | O(N × 请求风格数) |
| 排序 | O(C log C) |
| MMR | O(min(C, 120) × K) |

8.9 万首实测（本机）：

| 操作 | 耗时 |
| --- | --- |
| v1 单次 | 0.14 s |
| `build_index()` 一次性 | 0.31 s |
| v2 单次（不复用索引） | 0.59 s |
| v2 单次（复用索引） | 0.19 s |
| `eval_v2.py` 三组场景 | 约 14 s |

网页切 v2 时应启动时建一次索引，之后传 `index=...`，把单次请求压到 0.19 s。

## 11. 不变量

1. **确定性**：无随机数、无时间戳、无哈希序依赖；平局一律 `song_id`；
2. **不改输入**：`songs`、`preferences`、`seeds`、`exclude_ids` 都不会被修改；
3. **字段固定**：每项恰好 `song_id, song_name, artist, genres, score, reason`；
4. **不伪造**：有偏好但无命中返回 `[]`，不补齐、不混入无关热门；
5. **可解释**：每条理由都写出覆盖比例与加分，如 `风格匹配：流行（覆盖 1/2，+1.50）`。

## 12. 与 v1 的差异一览

| 维度 | v1 | v2 |
| --- | --- | --- |
| 风格匹配 | 精确、全有全无 | 覆盖比例，支持大小写/全半角归一 |
| 热度 | 无 | 有界先验（默认 0.6） |
| 多样性 | 无 | MMR + 单歌手配额 |
| 冷启动 | ID 序 | 热度序 |
| 排除已听 | 无 | `exclude_ids` |
| 歌单续听 | C 的 `playlist.py` | `recommend_from_seeds()` |
| 理由 | 命中项 | 命中项 + 覆盖比例 + 分值 |
| 输出字段 | 六字段 | 六字段（`score` 为 float） |

## 13. 接入方式

| 场景 | 调用 |
| --- | --- |
| 网页保持现状 | `recommend(songs, preferences, limit=10)`，仍走 v1 |
| 网页切 v2 | 启动时 `INDEX = build_index(songs)`，请求里 `recommend_v2(songs, preferences, limit=10, index=INDEX)`；或 `recommend(songs, preferences, limit=10, strategy="v2")`（不传索引，每次重建） |
| 歌单页切 v2 | `recommend_from_seeds(catalog, seeds, limit, diversity=0.3, index=INDEX)` |
| 排除已听 | 传 `exclude_ids=[...]` |

给 C 的建议：先加一个开关（环境变量或页面参数），默认 v1，对比两天再决定是否默认 v2；两版输出字段一致，模板不需要改。

## 14. 已知限制

- 仍是规则模型，没有学习用户真实行为；A 的行为链路（PR #4）里的原始交互数据不随仓库分发，所以本版本不训练任何参数；
- 热度先验用“曲库频次”代理真实播放量，热门歌手/风格会被系统性抬升，报告里不能把它说成“个性化程度”；
- 风格仍依赖上游标签质量，A 的 `genre_map_zh.csv` 映射不到的风格会整类缺失；
- MMR 的 `diversity` 是固定超参，没有线上反馈可以自动调；
- 未做 A/B 实验与线上点击评估。
