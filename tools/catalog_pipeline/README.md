# MusicBrainz 自动采集（候选数据）

解压后在程序目录运行（构建或采集电脑需要 Python 和网络）：

```powershell
python collect.py --input artists_prioritized.csv --work state --max-artists 100 --max-records 120000
```

输入 CSV 须有 `artist_credit`、`artist` 或 `候选名称` 列；脚本按输入顺序取前 N 条，默认 20。附带的 `artists_prioritized.csv` 是现有 31,430 个完整署名，按现有“华语流行”标签歌曲数、歌曲总数排序；这只是查询优先级，不代表语种或身份认证。扩大范围时增大 `--max-artists` 并保持相同的 `--work`。查询仅接受唯一精确标准名称作为候选，仍标记未核对；没有精确结果或有多个同名结果不会自动选取，记录在 artist_status.csv，别名与合作署名需要后续人工或可靠映射。不要把名字精确匹配视为身份已确认。

脚本分页查询正式发行，排除明确标注现场、精选、混音等发行组，对每组选择一条发行，获取录音与歌手；SQLite 按页和发行保存原始结果及进度，重复运行可继续，自动限速并对失败退避重试。`--max-releases-per-artist` 可限制试运行工作量，默认不限制；`--max-records` 仅限制候选录音数，不保证最终合并后净增数量。中断后重跑并在相同目录生成 CSV。

输出 `songs_candidates.csv` 使用现有四列格式，录音 MBID 加 `mbid:` 前缀；`genres` 留空，尚未做标签映射。`provenance.csv` 保留目标艺人、发行、发行组和录音的对应关系；`artist_status.csv` 保留候选身份与未匹配项。数据仅按录音 ID 去重，未完成不同版本、跨来源、合作艺人的作品级归并，不应直接加入成品库。返回无曲目的发行标记 `empty_review`；接口总数是实时值，分页期间可能变化，不能单靠脚本输出证明艺人目录完整。注意 MusicBrainz 原始字段与派生标签的许可不同，按数据类型核对使用许可。

演示：`python collect.py --input demo_artists.csv --work demo_state --max-artists 2 --max-releases-per-artist 1`。
