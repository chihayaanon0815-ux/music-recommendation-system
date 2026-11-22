# data/processed

本目录包含角色 A 用 PySpark 清洗生成的成品数据，供 B、C 直接拉取联调（项目负责人 2026-11-22 决定提交）。

| 文件 | 内容 |
| --- | --- |
| `songs.csv` | 89,740 首，表头 `song_id,song_name,artist,genres`，UTF-8 无 BOM、LF，约 6.4 MB |
| `genre_counts.csv` | 31 个中文大类计数，表头 `genre,count` |
| `run_metrics.json` | 输入/输出/去重行数 |

## 校验

```powershell
python data_processing/validate_outputs.py
```

预期：89,740 首、唯一 ID 89,740、31 个大类、合计 110,166 次标签计数、校验通过。

## 来源、许可与再分发状态

- 来源：Spotify Tracks Dataset（Kaggle/HuggingFace 公开再分发），底层由作者经 Spotify Web API 采集；
- 许可：Kaggle 标注 ODbL（数据库）+ 内容版权归原作者，HuggingFace 另标 BSD，两者冲突；
- **再分发权限尚未确认**：本次提交是项目负责人为组内联调作出的决定，不代表已取得公开发布授权；如后续需要公开传播或按更严格要求处理，应移除本目录数据并改为本地生成。

详见 `docs/data/sources_and_licenses.md`。

## 重新生成

```powershell
python data_processing/build_dataset.py --from-file <dataset.csv>
```

生成结果与当前提交一致（SHA-256 `c36ad601f429bc2852f86137b50d705f7dc5f2f32e176969cc871770e866f358`），可用 `validate_outputs.py` 复核。
