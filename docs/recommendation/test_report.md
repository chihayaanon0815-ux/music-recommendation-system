# 算法组测试与复现说明

本文件记录 `tests/recommender/` 怎么跑、跑了什么、真实输出是什么。所有数字都来自 2026-11-21 在本机（Windows 10 / Python 3.13.18）的实际运行。

## 1. 环境与依赖

| 项目 | 值 |
| --- | --- |
| 操作系统 | Windows 10（64 位） |
| Python | 3.13.18 |
| 测试框架 | 标准库 `unittest` |
| 第三方依赖 | 无（`recommender/requirements.txt` 为空依赖说明） |
| 是否需要网络 | 不需要 |

## 2. 测试命令

在包根目录（含 `recommender/`、`tests/` 的那一层）执行：

```powershell
python -m unittest discover -s tests/recommender -v
```

单个文件运行：

```powershell
python -m unittest tests.recommender.test_recommend -v
```

演示脚本（不跑断言，只打印结果）：

```powershell
python tests/recommender/demo.py
```

## 3. 本次实际运行记录（2026-11-21，本机）

### 3.1 单元测试

```text
test_case_is_not_folded ... ok
...
test_whitespace_is_trimmed_for_matching ... ok

Ran 23 tests in 0.002s

OK
```

### 3.2 演示脚本

```text
=== 选择流行 + 测试歌手 ===
01  测试歌曲  5分  风格匹配：流行；歌手匹配：测试歌手
04  测试歌曲四  3分  风格匹配：流行
03  测试歌曲三  2分  歌手匹配：测试歌手

=== 未选择偏好（默认推荐，score=0） ===
01  测试歌曲  0分  默认推荐：未选择偏好，按 song_id 字典序展示
...
=== 选择不存在的风格 ===
（空列表，页面提示“没有匹配歌曲”）

=== 流行 + limit=2 ===
01  测试歌曲  5分  ...
04  测试歌曲四  3分  ...
```

### 3.3 解压后复跑

把交付 zip 解压到空目录再跑一次测试：`Ran 23 tests in 0.003s OK`，确认包自包含、不依赖开发机路径。

## 4. 用例清单（23 项，按测试类分组）

### 4.1 `ContractExampleTests`（契约示例，4 项）

`test_genre_and_artist_match_scores_five`、`test_multi_genre_match_adds_three_each`、`test_duplicate_genre_preference_does_not_double_score`、`test_duplicate_genre_tags_in_song_do_not_double_score`。

### 4.2 `DefaultRecommendationTests`（默认推荐，3 项）

`test_no_preferences_returns_default_sorted_by_song_id`、`test_missing_preference_keys_are_treated_as_empty`、`test_default_limit_is_ten`。

### 4.3 `NoMatchAndBoundaryTests`（无命中与边界，5 项）

`test_no_match_returns_empty_list`、`test_skips_records_without_id_or_name`、`test_limit_zero_and_negative_return_empty`、`test_limit_caps_without_padding`、`test_non_positive_scores_are_excluded`。

### 4.4 `OrderingTests`（排序，3 项）

`test_only_positive_results_are_never_padded`、`test_ties_sort_by_song_id_string_order`、`test_higher_score_sorts_before_id`。

### 4.5 `NormalisationTests`（规范化，4 项）

`test_case_is_not_folded`、`test_whitespace_is_trimmed_for_matching`、`test_empty_artist_never_matches_empty_selection`、`test_empty_song_genres_do_not_match`。

### 4.6 `ImmutabilityAndShapeTests`（不可变与返回结构，3 项）

`test_input_is_not_modified`、`test_results_are_new_objects_with_all_fields`、`test_returned_fields_keep_string_type`。

### 4.7 `SampleFileTests`（样例文件，1 项）

`test_fictional_sample_file_runs`：读取 `tests/recommender/sample_songs.json`（5 首虚构歌曲）跑通推荐，防止样例文件损坏。

## 5. 覆盖对照（任务要求）

| 任务要求 | 对应用例 |
| --- | --- |
| 风格每个 +3、歌手 +2 | 4.1 |
| 只返回正分 | 4.3、4.4 |
| 同分按 ID 字符串序 | 4.4 |
| 无偏好默认推荐、不称热门 | 4.2 |
| `limit` 非正返回空 | 4.3 |
| 不修改输入、返回固定字段 | 4.6 |
| 去空格、大小写不折叠 | 4.5 |
| 虚构样例可运行 | 4.7 |

## 6. 与网页联调记录（2026-11-19）

在 C 的 `feature/web-ui` 工作树内放入本模块，用 Flask 3.1.3 测试客户端验证：

| 动作 | 结果 |
| --- | --- |
| `GET /` | 算法标签显示“推荐算法模块”，说明走的是真算法 |
| `POST /`（流行 + 示例歌手甲） | 首条“晨光”5 分，展示两条理由 |
| 空选择提交 | 展示默认推荐，score=0 |
| 跑 C 自带的 4 个网页测试 | 仍全部 `OK` |

该次联调用 C 的虚构样例，只证明接口接通和页面展示，**不构成效果结论**。

## 7. 未做与不能声称的验证

- 未在真实数据（A 的 89,740 首 `songs.csv`）上跑冒烟，等合并后由 C 做；
- 未在 PyInstaller 打包产物内运行；
- 未做性能压测、并发测试、内存分析；
- 未做任何推荐质量评估（没有准确率、召回率、NDCG、点击率）；
- 因此报告中只能写“契约实现 + 23 项测试通过 + 页面联调通过”，不能写效果提升。
