# 用户行为曲库处理说明

本版用于非商业课程研究。曲库包含 662,939 首，沿用项目的四列格式 `song_id,song_name,artist,genres`。曲风覆盖率为 98.399%。

## 1. 从来源表提取与合并

处理时以本地校验过的 293,867 首为基线，其中包含上一版正式复核的 293,864 首。输入为课程组的 `音乐推荐数据_20261123.zip`，其中的 Spotify 曲目表有 89,740 条，可全部通过来源 ID 或旧曲目映射归入曲库。MSD 曲目表使用 `msd_song_meta.csv`，它提供曲名、艺人、发行资料和录音 ID。原始三元组、训练集、测试集、宽表及其它曲目引用用来找出必须纳入的 MSD 曲目。

1. 优先采用通过曲名和艺人双重核对的精确 Spotify 对应，其次匹配标准化后唯一的同名同艺人歌曲。Unicode、大小写、空白以及已知艺人别名一并规范化。
2. 对可识别的现场版、重制版等后缀，仅在去掉后缀后仍能唯一匹配时合并版本。模糊匹配或身份不明的曲目保留独立 ID，新增曲目使用 `msd:<MSD song_id>`。
3. 原始行为始终通过来源 ID 映射到最终曲目。384,546 个 MSD ID 映射到 378,499 个曲库 ID。相对处理基线新增 369,072 首，原有非空曲风保持原值。源表中缺歌名的 4 条记录以“待确认歌名”和源 ID 显示，对应 65 条原始播放记录。

## 2. 补齐曲风与细分标签

- **曲目证据优先。** 以 MSD 录音 ID 接入 AllMusic MAGD/MASD、tagtraum CD2/CD2C 和其 Last.fm、beaTunes 标注。tagtraum 共识与所用的 Last.fm、beaTunes 有来源重叠，按同一组计权。对 Apple、Spotify 及附件提供的 MusicBrainz 录音标注，核对曲名及艺人后再纳入。AllMusic 部分标注来源于发行资料，采用项目的中文推荐曲风词表统一大类。更细的曲风、情绪和声音类型独立记录。 [维也纳工业大学 MSD Benchmarks](https://www.ifs.tuwien.ac.at/mir/msd/download.html) · [tagtraum 标注与研究用途条款](https://www.tagtraum.com/msd_genre_datasets.html)
- **艺人证据补漏。** 无可用曲目曲风时，使用同一艺人有可靠来源的曲目统计代表曲风，要求至少两首支持且超过投票样本的一半。仍缺证据时，再参考 MSD 中同一艺人的其它录音，以及通过稳定艺人 ID 对齐的 MusicBrainz / Wikidata。曲目证据和艺人推断分别标记。 [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API) · [Wikidata 曲风属性](https://www.wikidata.org/wiki/Property:P136)
- 补齐的 357,168 首中，310,717 首采用曲目资料，46,451 首采用艺人证据。仍有 9,171 首主曲风待确认，另有 1,442 条标为喜剧或口语内容。这两类记录均保留在曲库。

## 3. 数据文件与关联方式

网页和歌单搜索可直接读取分片。若需单个 CSV（例如用于 Spark 或 Windows 打包），在仓库根目录运行 `python -m web.catalog_snapshot`，即可按清单顺序生成并校验 `data/processed/songs.csv`。压缩映射和标签文件解压后即可作为普通 CSV 使用。

| 文件 | 用途 |
| --- | --- |
| [曲库 CSV 分片](../../../data/processed/catalog-parts)、[genre_counts.csv](../../../data/processed/genre_counts.csv) | 正式曲库和各曲风的曲目数 |
| [msd_song_id_map.csv.gz](../../../data/processed/behavior/msd_song_id_map.csv.gz) | MSD 来源 ID 到最终曲库 ID，附行为表中的分曲目记录数 |
| [spotify_song_id_map.csv](../../../data/processed/behavior/spotify_song_id_map.csv) | 附件内 Spotify 来源 ID 到最终曲库 ID |
| [genre_annotations.csv.gz](../../../data/processed/behavior/genre_annotations.csv.gz) | 处理方式、细分标签、存在分歧的曲风及艺人投票统计 |
| [pending_titles.csv](../../../data/processed/behavior/pending_titles.csv) | 源表缺少真实歌名的 4 条记录 |
| [曲库快照清单](../../../data/processed/catalog_snapshot.json) | 文件路径、SHA-256、曲库记录数 |

```sql
SELECT e.*, s.song_id AS catalog_song_id, s.song_name, s.artist, s.genres
FROM events AS e
JOIN msd_song_id_map AS m ON e.song_id = m.msd_song_id
JOIN songs AS s ON m.catalog_song_id = s.song_id;
```

一首最终曲目可以对应多个来源 ID。训练或评估若以最终曲目为单位，应先完成映射，再按用户及最终曲目汇总。原始播放数据及附带原始来源表由课程组提供。发布内容为课程衍生曲库、曲目映射、归一化标签与汇总统计，各来源适用各自的条款。 [MSD 项目与引文](https://millionsongdataset.com/) · [MSD 数据许可说明](https://github.com/tbertinmahieux/MSongsDB/blob/master/LICENSE)

## 4. 复核结果

| 数据 | 记录数 | 未关联记录 |
| --- | ---: | ---: |
| 原始播放日志 | 48,373,586 | 0 |
| 训练集 CSV / Parquet | 38,701,364 | 0 |
| 测试集 CSV / Parquet | 624,984 | 0 |
| 宽表样本 | 100,000 | 0 |

训练、测试的 CSV 和 Parquet 按曲目重新计数一致。推荐输出、候选曲池、音频特征、曲目维表与统计表的曲目引用也均能关联。原数据包中的 8 条虚构测试样例独立记录。详见 [覆盖核验](behavior_coverage.json) 和 [曲风补齐统计](genre_report.json)。
