# 内容审核与修订

[返回项目首页](../README.md) · [构建维护](maintenance.md) · [完整包审计报告](../reports/app-data-audit.md)

本页说明精选包的审核状态、资料展示边界、修订记录和可选的模型调用。下面的文件路径和命令均相对项目根目录。

## 当前审核状态

当前精选包已完成全量 AI 初审、初审有疑点作品的二审，以及二审后剩余疑点的逐项编辑处理。

| 环节 | 当前结果 |
|---|---:|
| AI 初审覆盖 | 1524 条作品 |
| 初审有疑点且已二审 | 805 条作品 |
| 二审后疑点编辑处理 | 385 条作品、565 个疑点，全部处理 |
| 缺注解 / 作者简介待补 / 内容待核 | 0 / 0 / 0 |
| 已明确标示的解释分歧 | 42 条 |

疑点的处理包括据正文纠错、找到古籍依据后保留原释、删除未经证实的非必要细节，以及明确标出不同解释。待核清单为空表示本轮所列疑点均已有处理决定，不表示每一种古代训读、地望和史事都已确定唯一答案。

| 字段或状态 | 含义 |
|---|---|
| `complete=true` | 三类注解都有通过基础检查的文本 |
| `review_status=ai_reviewed` | AI 审核后没有尚未处理的疑点 |
| `review_status=editorially_reviewed` | Codex 已对本轮剩余疑点作出逐项编辑决定 |
| `review_status=needs_source_check` | 仍有待处理的来源核查问题 |
| `academic_review_complete=false` | 未标记为专家学术校勘完成 |

全包保持 `academic_review_complete=false`。本轮审核范围是精选包，未声称完成二十余万条 raw 全库的专家校勘。来源类型、模型、审核状态和正文绑定信息保存在完整记录的 `field_sources` 中，运行包的 `annotation_info` 提供常用字段；App 可据此显示 AI 辅助生成或编辑标记。

《田家词》《风流子·黄钟商芍药》《除夜自石湖归苕溪十首》另有据古籍校订的主版本，旧正文、旧题名、版本与单元 ID 均保留。具体依据与修订前后对照见 [内容审核报告](../reports/app-data-audit.md)。

## 后续抽查与修订

2026-11-11 整理数据格式示例时，发现以下问题，已通过显式修订重新构建两种数据包。初审曾指出此问题，二审却错误地将其驳回，说明自动审核完成标记不能替代内容质量检查。

| 作品 ID | 作品 | 字段 | 问题 | 状态 |
|---|---|---|---|---|
| `5c26e1cc97880d3b826103d9` | 赵孟頫《后庭花·清溪一叶舟》 | `appreciation` | 混入“网页发生错误，请联系网站管理员：service@gushiwen.org”报错文本 | 已替换为据正文撰写、参考公开资料的简要赏析；原报错、修改理由和来源保留在审核记录中 |

改写参考 [中国宋庆龄基金会署名赏析](https://www.csclf.org/jdyq/202411/t20241104_31068.htm) 与 [古诗文网正文及说明](https://www.gushiwen.cn/mingju/juv.aspx?id=f6478b646b2c)，明确标为 Codex 编辑修订，没有冒称恢复原网站赏析。维护包和 App 运行包同步更新，正文与其他作品未改。发布校验新增 `web_error_artifacts`，对作品正文、译注和作者资料中的典型网站报错文本报错，不能以 `complete=true` 或已有审核标记绕过。

## 维护记录

| 文件 | 内容 |
|---|---|
| `raw/content_review.json` | 异文合并、题名、作者归属、文体等目录决定 |
| `raw/author_overrides.json` | 作者简介修订及来源 |
| `raw/annotation_additions.jsonl` | 带正文哈希的补注记录 |
| `raw/content_reviews.jsonl` | 初审意见，包含误报，不直接当作修改依据 |
| `raw/review_triage.jsonl` | 二审决定及可续跑的失败记录 |
| `raw/approved_review_edits.json` | 显式批准的局部修订 |
| `raw/final_content_decisions.json` | 剩余疑点的逐项处理和精确变更 |
| `raw/review_resolutions.json` | 各阶段合成的修改前后数组与校验哈希 |
| `raw/editorial_fixes.json` | 早期字段修复记录 |
| `raw/source_evidence.json` | 古籍核对摘录、URL 与哈希 |

修订应进入上述维护记录，再经构建发布。应用修改时校验输入哈希、正文绑定、引用位置和出现次数，过期记录会报错，不在不同文本上静默套用修订。

### 可选的模型补注与审核

现有数据读取、构建和测试不需要模型接口。以下命令用于后续增量补注、审核或失败续跑，需主动执行并配置接口。可在本机 `.env` 中设置：

```dotenv
LLM_API_KEY=你的接口密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL_ID=你的模型标识
```

环境变量优先于 `.env`，也可通过 `--env-file` 指定配置文件。`.env` 已加入 Git 忽略规则。

```powershell
python -X utf8 scripts/complete_annotations.py --env-file .env --workers 2
python -X utf8 scripts/review_content.py --env-file .env --workers 2
python -X utf8 scripts/resolve_content_reviews.py --env-file .env --workers 2
```

这些工具保留生成结果、失败记录及已完成输入，支持续跑；模型建议不会自动成为已批准的内容修订。检查意见并写入显式修改后，依次运行：

```powershell
python -X utf8 scripts/prepare_review_resolutions.py
python -X utf8 scripts/merge_annotations.py
python -X utf8 scripts/export_app_runtime.py
```
