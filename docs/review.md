# 内容审核与修订

[项目首页](../README.md) · [构建与维护](maintenance.md) · [完整包审计](../reports/app-data-audit.md)

本文说明精选包的审核范围、状态字段与修订流程。审核决定、原始意见和内容来源分别保留，供应用展示与后续追溯。

## 审核范围与结果

| 环节 | 当前结果 |
|---|---:|
| AI 初审 | 1524 条作品 |
| 初审有疑点且已二审 | 805 条作品 |
| 二审后逐项编辑处理 | 385 条作品、565 个疑点，全部处理 |
| 缺注解 / 作者简介待补 / 内容待核 | 0 / 0 / 0 |
| 已标示的解释分歧 | 42 条 |

本轮覆盖精选包。待核清单为空，表示已列疑点均有处理决定；原始全库素材及所有古代训读、地望和史事不因此获得完整审定。全包保持 `academic_review_complete=false`。

## 审核标记

| 字段或状态 | 含义 |
|---|---|
| `complete=true` | 译文、注释、赏析三个数组均非空 |
| `review_status=ai_reviewed` | 已完成 AI 审核，当前记录没有待处理疑点 |
| `review_status=editorially_reviewed` | 本轮剩余疑点已由 Codex 逐项作出编辑决定 |
| `review_status=needs_source_check` | 存在待处理的来源核查问题 |
| `academic_review_complete=false` | 未完成专家学术校勘 |

这些标记记录覆盖率与流程状态。它们不能单独证明内容准确，也不能替代来源核查。

App 可通过完整 JSON 的 `field_sources`，或运行库的 `annotation_info`，展示注解来源、生成模型与审核状态。作者简介的 `bio_status` 独立于作品注解审核。

## 修订原则

修订依据包括正文、上下文和可追溯文献。处理方式包括纠正文义、保留有据旧释、删除未经证实的非必要细节，以及标示不同解释。

每项修改绑定原输入哈希、段落位置和原值。编译时检查正文绑定、引用位置与出现次数；文本已变化时中止处理。修改前后值与依据保留在修订记录中。

《田家词》《风流子·黄钟商芍药》《除夜自石湖归苕溪十首》新增据古籍校订的主版本，同时保留原始正文、旧版本及稳定单元 ID。详细依据见 [审计报告](../reports/app-data-audit.md#三处正文校订)。

### 后续修订记录

**2026-11-11：《后庭花·清溪一叶舟》赏析报错修复**

| 项目 | 记录 |
|---|---|
| 作品 | 赵孟頫《后庭花·清溪一叶舟》 |
| ID | `5c26e1cc97880d3b826103d9` |
| 字段 | `appreciation` |
| 问题 | 混入网站错误提示；初审曾指出，二审误作驳回 |
| 处理 | 以据正文撰写、参考公开资料的简要赏析替换，标记为 Codex 编辑修订 |
| 发布 | 完整维护包与 App 运行包同步更新 |
| 追溯 | 原报错、原始模型意见、修改理由及参考链接保留 |

参考资料为 [中国宋庆龄基金会署名赏析](https://www.csclf.org/jdyq/202411/t20241104_31068.htm) 与 [古诗文网正文及说明](https://www.gushiwen.cn/mingju/juv.aspx?id=f6478b646b2c)。本次为编辑改写，区别于恢复来源网站原赏析。

发布校验新增 `web_error_artifacts`，检查作品正文、译注与作者资料中的典型网站报错文本。现有审核标记不会豁免该检查。

## 修订流程

在相应维护记录中明确修改范围与依据，然后依次执行：

```powershell
# 编译显式修改与前后值
python -X utf8 scripts/prepare_review_resolutions.py

# 重建完整维护包
python -X utf8 scripts/merge_annotations.py

# 同步 App 运行包
python -X utf8 scripts/export_app_runtime.py
```

命令在仓库根目录执行，各步成功后再继续。构建与验证细节见 [维护指南](maintenance.md)。

### 维护记录索引

下列文件均位于 `raw/`。

| 文件 | 职责 |
|---|---|
| `content_review.json` | 异文合并、题名、作者归属与文体决定 |
| `author_overrides.json` | 作者简介修订及来源 |
| `annotation_additions.jsonl` | 绑定正文哈希的补注 |
| `content_reviews.jsonl` | 初审原始意见 |
| `review_triage.jsonl` | 二审决定及失败记录 |
| `approved_review_edits.json` | 显式批准的局部修订 |
| `final_content_decisions.json` | 二审剩余疑点的逐项处理 |
| `review_resolutions.json` | 各阶段合成的前后值与校验哈希 |
| `editorial_fixes.json` | 早期字段修复 |
| `source_evidence.json` | 古籍摘录、来源 URL 与哈希 |

## 可选模型审核

以下流程用于增量补注、内容审核或失败续跑，需主动执行并配置接口。读取现有数据、构建及测试均无需模型接口。

### 配置

在本机 `.env` 设置接口信息：

```dotenv
LLM_API_KEY=<API_KEY>
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL_ID=<MODEL_ID>
```

环境变量优先于 `.env`，`--env-file` 可指定其他配置文件。`.env` 已加入 Git 忽略规则。

### 执行

```powershell
python -X utf8 scripts/complete_annotations.py --env-file .env --workers 2
python -X utf8 scripts/review_content.py --env-file .env --workers 2
python -X utf8 scripts/resolve_content_reviews.py --env-file .env --workers 2
```

工具保留已完成输入、生成结果和失败记录，支持续跑。模型建议须经显式批准并写入维护记录，再按 [修订流程](#修订流程) 编译与发布。
