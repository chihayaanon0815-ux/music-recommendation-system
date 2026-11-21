"""Runnable demo of recommender.recommend using the fictional sample file.

Usage (from the package root):
    python tests/recommender/demo.py

The output only proves the interface works on fictional data; it is not a
statement about recommendation quality on real music.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from recommender.recommend import recommend  # noqa: E402

HERE = Path(__file__).resolve().parent


def show(title, songs, preferences, limit=10):
    print(f"\n=== {title} ===")
    results = recommend(songs, preferences, limit=limit)
    if not results:
        print("（无结果：已选择偏好但没有歌曲命中，页面应显示无匹配提示）")
        return
    for item in results:
        print(f"{item['song_id']}  {item['song_name']}  {item['score']}分  {item['reason']}")


def main():
    data = json.loads((HERE / "sample_songs.json").read_text(encoding="utf-8"))
    songs = data["songs"]
    print(data["notice"])

    show("选择流行 + 测试歌手", songs, {"genres": ["流行"], "artists": ["测试歌手"]})
    show("未选择偏好（默认推荐）", songs, {"genres": [], "artists": []})
    show("选择不存在的风格", songs, {"genres": ["不存在的风格"], "artists": []})
    show("limit=2", songs, {"genres": ["流行"], "artists": []}, limit=2)


if __name__ == "__main__":
    main()
