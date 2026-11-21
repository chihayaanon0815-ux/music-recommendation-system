# 数据来源与许可

本目录记录角色 A（数据处理）实际使用的数据来源与许可状态。所有结论以可核对的原始页面为准；不确定的地方明确标注，不代替法律判断。

## 1. 主数据源：Spotify Tracks Dataset

| 项目 | 内容 |
| --- | --- |
| 数据集 | `maharshipandya/spotify-tracks-dataset`（"Spotify Tracks Dataset"，114,000 行） |
| HuggingFace 页面 | https://huggingface.co/datasets/maharshipandya/spotify-tracks-dataset |
| Kaggle 原始页面 | https://www.kaggle.com/datasets/maharshipandya/-spotify-tracks-dataset |
| 数据内容 | Spotify 曲目元数据与音频特征：track_id、artists、track_name、track_genre、popularity、danceability、energy 等 21 列；114 个风格，每个风格 1000 行 |
| 采集方式 | 数据集作者用 Spotify Web API 采集整理后公开；本项目只下载公开 CSV，不访问 Spotify 接口 |
| 本次获取 | 2026-11-19 通过镜像 `hf-mirror.com` 下载 `dataset.csv`（huggingface.co 在本机不可达） |
| 文件校验 | 原始 `dataset.csv` SHA-256：`b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`，19.2 MB |
| 是否含歌名/歌手/风格 | 含；另有真实 popularity（0–100，Spotify 算法值） |
| 是否与本课程相关 | 是。真实音乐曲目元数据，不是景点/旅游等参考项目的数据 |
| 音频 | **不下载、不包含任何音频文件** |

### 许可状态（务必如实理解）

- **Kaggle 原页标注**：`Database: Open Database, Contents: © Original Authors`。即数据库部分适用 **ODbL 1.0**（开放数据库许可，要求署名、衍生数据库同许可、不得用技术手段限制他人使用），而歌曲/条目内容版权仍归原作者。
- **HuggingFace 数据卡标注**：`license: bsd`。这与 Kaggle 的 ODbL 标注**不一致**，属于上传者自行选择，不能视为权利人的正式授权。
- **底层数据来源**：数据集由作者通过 **Spotify Web API** 采集。Spotify 开发者条款限制对 Spotify 内容的存储与再分发；第三方再上传不能替代 Spotify 的授权。
- **本项目结论**：这是**公开可获取、但许可链并不干净**的数据集。我们按 ODbL 的要求做署名与同许可声明，并在文档中如实披露上述矛盾与风险；不宣称它是 CC0，也不把原始 `dataset.csv` 再分发到仓库。
- 原始 `dataset.csv` 不提交（`data/raw/` 被忽略），只是体积与可复现考虑；成品 `data/processed/*.csv` 提交，按 ODbL 作为衍生数据库公开，署名：Maharshi Pandya（数据集作者）、Kaggle、Spotify（原始数据来源）。
- **若课程或评审要求“许可必须完全干净”**，应改用 CC0 的 MusicBrainz 方案（见第 3 节），本仓库保留了对应脚本。

## 2. 字段映射与规范化

下载脚本 `data_processing/download_spotify.py` 把原始列映射为课程统一字段，写入 `data/raw/spotify_tracks_raw.csv`（不提交）：

| 原始列 | 成品列 | 处理 |
| --- | --- | --- |
| `track_id` | song_id | 去空格；Spotify 曲目 ID（22 位字符串），用于唯一标识 |
| `track_name` | song_name | 去空格；**字段内英文双引号替换为单引号**、换行/制表符替换为空格 |
| `artists` | artist | 多个艺术家以 `;` 分隔，统一替换为 ` & `（如 `A; B` → `A & B`） |
| `track_genre` | genres | 经 `genre_map_zh.csv` 两级映射：先得中文细分（`genres_zh`），再归并为 31 个大类写入 `genres`；英文原文另存 `genres_en`；重复曲目的标签在清洗阶段取并集 |
| `popularity` | popularity（附加列） | 保留在原始表用于报告统计，**不进入**统一契约 CSV |

### 为什么替换双引号

Spark CSV reader 默认转义符是反斜杠 `\`，与 RFC4180 的“双引号加倍”写法冲突：真实数据里有 1,762 个歌名含英文双引号，未处理时会把整行解析错位（实测风格数从 114 膨胀到 198）。因此在生成原始表前统一把 `"` 换成 `'`、把换行/制表符换成空格。这是**有记录的数据规范化**，不是丢字段；歌曲名其余内容保持不变。

### 两级分类与中文标签

数据集提供 114 个英文风格（`acoustic`、`mandopop`、`black-metal` 等）。成品用 `data_processing/genre_map_zh.csv` 做**人工映射**：英文原文 -> 中文细分 -> 31 个大类（酷狗式曲风 + 场景/人群）。

- 114 个标签全部有中文细分名，且中文细分名互不重复；大类允许重叠（`华语流行/粤语流行` 同时属于「流行」与「华语流行」），这是把酷狗的“语种 + 曲风”两个维度压进一列 `genres` 的近似做法；
- 场景/心情标签（伤感、助眠、学习等）保留为独立大类，对应酷狗的“心情/场景”轴；语言类非流行标签归「世界音乐」；
- 映射是人工整理，**不是官方译名**；区域风格（`mpb`、`pagode`、`sertanejo`、`forro`）用音译/描述性译名，答辩以英文原文为准；
- 细分与英文原文都保留在 `data/raw/spotify_tracks_raw.csv`（`genres_zh`、`genres_en` 列），随时可核对或改回细粒度口径；
- 映射表变更后需重跑下载与清洗，`genre_counts.csv` 的大类也会随之变化。


## 3. 备选数据源：MusicBrainz（CC0，许可最干净）

为应对“必须完全合规”的要求，仓库保留了 MusicBrainz 采集方案：

- 接口：https://musicbrainz.org/ws/2/recording （Web Service v2，JSON）
- 许可：核心数据 **CC0 1.0**，原文见 https://musicbrainz.org/doc/About/Data_License 的 “MusicBrainz Database → Core data” 一节
- 抓取要求：可识别 User-Agent、平均 ≤1 请求/秒；脚本内置 1.1 s 间隔与 503 退避
- 生成命令：`python data_processing/fetch_musicbrainz.py --total 5000`

### 实测规模与标签覆盖（2026-11-19，本机实际抓取）

| 指标 | 实测值 |
| --- | --- |
| 抓取配置 | 12 个受控风格（pop/rock/jazz/folk/hip hop/electronic/classical/metal/country/blues/reggae/soul）× 40 条 |
| 去重后曲目 | **480 首**（480 个唯一 MBID） |
| 风格分布 | 流行 47、摇滚 42，其余 10 个风格各 40；合计 489 次标签计数 |
| 多标签曲目 | 仅 **9 首**（1.9%），其余 471 首单标签 |
| 歌手 | 全部非空 |
| 耗时 | 约 4 分钟检索 + 约 25 分钟逐首标签回查（含 503 退避） |

**华语覆盖（MusicBrainz 全库检索命中数）**：`mandopop` 52 条、`cantopop` 63 条、`c-pop` 27 条，
合计约 140 条录音——按此覆盖率，扩到 5000 首也无法得到有统计意义的华语样本。

**结论**：MusicBrainz 许可最干净（CC0），但**欧美为主、多标签稀少、华语几乎不可用**；
若完全以合规为先，可接受“约 5000 首、12–21 个英文风格、中文展示名”的方案（采集约 2–3 小时），
但中文歌比例极低，需要向评审如实说明。当前仓库不提交任何 Spotify 衍生成品（见第 4 节）。

## 4. 再分发策略（按集成审核意见执行）

集成审核指出：“仅对衍生 CSV 标注 ODbL 不能确认有权在公开仓库再分发”。因此本仓库采取**不分发数据**的策略：

- **不提交**任何 Spotify 衍生文件：`data/processed/songs.csv`、`genre_counts.csv`、`run_metrics.json` 均被 `data/.gitignore` 忽略；
- 仓库只提交**生成脚本 + 字段/许可文档 + 虚构样例**（`data/sample/songs_sample.csv`，8 行、明确标注虚构）；
- 使用者（B/C/评审）在本地运行 `python data_processing/build_dataset.py` 自行下载与清洗，生成结果仅存在于本地，打包时打进程序目录；
- 原始 `dataset.csv`（19.2 MB）与中间表 `spotify_tracks_raw.csv` 同样不提交；
- 文档中不把“许可问题”表述为“已解决”，只陈述事实与风险，并给出 CC0 替代方案（MusicBrainz）。

`ODbL` 署名仅用于说明生成结果的许可意图（数据库部分），不代表已获得 Spotify 内容的再分发授权；公开分发前应取得权利方许可或改用 CC0 数据源。

## 5. 其他合规红线

- 不包含音频、不含播放量之外的平台内部数据；popularity 只用于课程统计，不对外宣称“实时热度”。
- 不再分发 Spotify 的封面、歌词、试听地址等受限内容。
- 报告与答辩中引用本数据集时，需同时写明“数据集许可为 ODbL + 内容版权归原作者，原始数据经 Spotify API 采集，本仓库不分发数据”这一事实。

