# recommender（角色 B：推荐算法）

两套可切换的确定性推荐：**v1**（契约版，精确风格/歌手打分，网页当前调用）与 **v2**（软覆盖率 + 热度先验 + 多样性重排 + 歌单续听）。都纯标准库、无训练、结果可复算。同一份输入永远得到同一份输出，每条结果都带中文理由。

## 文件

| 文件 | 作用 |
| --- | --- |
| `__init__.py` | 包标记，导出 `recommend` |
| `recommend.py` | 唯一对外模块，约 133 行，含权重常量与理由生成 |
| `recommend_v2.py` | v2 主算法：`recommend_v2` / `recommend_from_seeds` / `build_index` |
| `similarity.py` | 文本归一化（NFKC/casefold）、标签切分、覆盖度与 Jaccard |
| `playlist.py` | 歌单接口（C 维护，v2 未改动） |
| `README.md` | 本文件 |
| `requirements.txt` | 空依赖说明（不装任何第三方包） |

## 快速开始

```powershell
# 1) 在仓库根目录运行契约测试
python -m unittest discover -s tests/recommender -v

# 2) 打印演示结果（5 首虚构歌曲，4 组场景）
python tests/recommender/demo.py

# 3) 在代码里调用（读虚构样例，选“流行”）
python -c "import json;from recommender.recommend import recommend;s=json.load(open('tests/recommender/sample_songs.json',encoding='utf-8'))['songs'];print(recommend(s,{'genres':['流行']}))"
```

调用方式：

```python
from recommender.recommend import recommend

results = recommend(
    songs,                                   # [{song_id, song_name, artist, genres}, ...]
    {"genres": ["流行"], "artists": ["某歌手"]},
    limit=10,
)
```

每条结果固定六个字段：`song_id, song_name, artist, genres, score, reason`。

## v2（推荐算法 v2）

```python
from recommender.recommend_v2 import build_index, recommend_v2, recommend_from_seeds

INDEX = build_index(songs)                      # 启动时一次，8.9 万首约 0.31 s
results = recommend_v2(songs, {"genres": ["流行"]}, limit=10, index=INDEX,
                       diversity=0.3, popularity_weight=0.6, max_per_artist=2,
                       exclude_ids=heard_ids)   # 单次约 0.19 s
playlist = recommend_from_seeds(songs, seeds, limit=10, index=INDEX)
```

或者保持调用方式不变、只切策略：

```python
from recommender.recommend import recommend
results = recommend(songs, preferences, limit=10, strategy="v2")   # 默认仍是 "v1"
```

| 维度 | v1（默认） | v2 |
| --- | --- | --- |
| 风格 | 精确命中 +3 | 覆盖比例 3×（支持大小写/全半角归一） |
| 热度 | 无 | 有界先验 0..0.6 |
| 多样性 | 无 | MMR 重排 + 单歌手最多 2 首 |
| 冷启动 | `song_id` 序 | 热度序 |
| 排除已听 | 无 | `exclude_ids` |
| 歌单续听 | 用 `playlist.py` | `recommend_from_seeds` |

细则是 `docs/recommendation/algorithm_spec_v2.md`，真实曲库上的指标是 `docs/recommendation/eval_report_v2.md`（P@10 0.90→0.99、NDCG 0.78→0.99、ILD 0.28→0.61）。

## 边界

- 只返回正分；有偏好但无命中返回 `[]`，不补齐、不伪造；
- 未选择偏好时按 `song_id` 字符串序给默认推荐，`score=0`，理由以“默认推荐”开头，**不称“热门”**；
- `limit<=0` 返回 `[]`；`limit` 只是上限，命中不足不补；
- 输入的对象与列表都不会被修改；
- 匹配为精确字符串比较（去首尾空格，不改大小写），不做同义词归并。

细则见 `docs/recommendation/algorithm_spec.md` 与 `algorithm_spec_v2.md`，限制见 `docs/recommendation/limitations.md`。

## 测试

```bash
python3 -m unittest discover -s tests/recommender          # 54 项（v1 23 + v2 31）
python3 tests/recommender/eval_v2.py --queries 10 --k 10   # 生成三张评估表
```
