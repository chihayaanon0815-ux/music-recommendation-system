# recommender（角色 B：推荐算法）

按契约 v1 实现的确定性风格/歌手打分推荐，纯标准库、无训练、结果可复算。同一份输入永远得到同一份输出，每条结果都带中文理由。

## 文件

| 文件 | 作用 |
| --- | --- |
| `__init__.py` | 包标记，导出 `recommend` |
| `recommend.py` | 唯一对外模块，约 133 行，含权重常量与理由生成 |
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

## 边界

- 只返回正分；有偏好但无命中返回 `[]`，不补齐、不伪造；
- 未选择偏好时按 `song_id` 字符串序给默认推荐，`score=0`，理由以“默认推荐”开头，**不称“热门”**；
- `limit<=0` 返回 `[]`；`limit` 只是上限，命中不足不补；
- 输入的对象与列表都不会被修改；
- 匹配为精确字符串比较（去首尾空格，不改大小写），不做同义词归并。

细则见 `docs/recommendation/algorithm_spec.md`，限制见 `docs/recommendation/limitations.md`。
