# 构建与维护

[项目首页](../README.md) · [接入指南](integration.md) · [内容审核与修订](review.md)

本文面向数据维护者。构建工具需要 Python 3.10+，仅使用标准库；所有命令在仓库根目录执行。常规构建、导出、审计与测试均为离线操作。

## 选择维护操作

| 任务 | 操作 | 是否更新发布数据 |
|---|---|---|
| 检查现有完整包 | `audit_data.py` | 否，仅更新审计报告 |
| 验证素材能否重建 | `rebuild.py --app-only --check-only` | 否，仅更新检查报告 |
| 使用现有素材重建 | `rebuild.py --app-only` | 是，更新完整维护包 |
| 更新 App 运行包 | `export_app_runtime.py` | 是，更新运行包 |
| 重新导入原始转储 | `rebuild.py --source-dir ...` | 是，更新素材与完整维护包 |

内容修改、生成补注及模型审核流程见 [内容审核与修订](review.md#修订流程)。

## 常规重建

数据流为：来源素材与显式修订 → 完整维护包 → App 运行包。

仓库已包含重建所需素材。以下三步应在前一步成功后依次执行。

### 1. 检查构建结果

```powershell
python -X utf8 scripts/rebuild.py --app-only --check-only
```

在临时目录建库并验证，保留现有发布数据，结果写入 `reports/staged-audit.json`。

### 2. 发布完整维护包

```powershell
python -X utf8 scripts/rebuild.py --app-only
```

校验通过后更新 `app-data/`。`merge_annotations.py` 为此操作的兼容入口。

### 3. 导出 App 运行包

```powershell
python -X utf8 scripts/export_app_runtime.py
```

导出器核对源包哈希，在临时目录创建并验证运行库，再更新 `app-runtime/`。**完整维护包更新后，须单独执行运行包导出。**

## 从原始转储重建

原始目录默认为相邻的 `../poems-db`，须包含 `poems1.json` 至 `poems4.json`、`poems-authors.json`、`poems-cipai.json`。

```powershell
python -X utf8 scripts/rebuild.py --source-dir ../poems-db --check-only
python -X utf8 scripts/rebuild.py --source-dir ../poems-db
python -X utf8 scripts/export_app_runtime.py
```

按顺序执行，各步成功后再继续。构建通过来源 URL、作者与正文识别重复，保留稳定 ID 映射。固定选取范围记录在 `raw/selection.json`；异文合并、作者归属及文体决定记录在 `raw/content_review.json`。

## 验证与报告

```powershell
# 检查完整维护包
python -X utf8 scripts/audit_data.py

# 执行全部自动化测试
python -X utf8 -m unittest discover -s scripts -p "test_*.py" -v
```

| 检查对象 | 验证内容 | 结果位置 |
|---|---|---|
| 完整维护包 | JSON/SQLite 一致性、来源与正文绑定、ID、分类、版本、FTS、文件哈希、外键及报错文本 | [审计 JSON](../reports/app-data-audit.json) / [审计说明](../reports/app-data-audit.md) |
| 临时构建 | 上述完整包检查及当前包差异 | [构建检查](../reports/staged-audit.json) |
| App 运行包 | 完整记录、阅读段落、作者长文、版本、来源及搜索分页结果与完整包一致 | [验收 JSON](../reports/app-runtime-audit.json) / [验收说明](../reports/app-runtime-audit.md) |

当前统计以数据包 manifest、`app-data/stats.json` 及最新报告为准。`raw/data-report-v1.json`、`reports/baseline-v2-audit.md` 等仅用于历史追溯。

## 目录职责

| 目录 | 主要内容 |
|---|---|
| `app-runtime/` | App 数据库、运行包 manifest、查询文档 |
| `app-data/` | 完整数据库、作品与作者 JSON、分类、ID 映射及统计 |
| `raw/` | 来源素材、选取规则、审核意见和显式修订 |
| `scripts/` | 构建、导出、查询、审核与测试工具 |
| `docs/` | 开发与维护文档 |
| `reports/` | 构建检查、完整包审计与运行包验收 |
| `backups/` | 本机快照与工作记录，Git 忽略 |

完整包中，`review_cautions.jsonl` 保存解释分歧，`source_evidence.json` 保存古籍核对依据，`generated.jsonl` 保存历史生成记录。`todo_annotations.jsonl` 与 `todo_content_review.jsonl` 分别为补注和内容待核清单。

名句选取输入为 `raw/famous_lines.json`，模型选择日志保存在 `raw/famous_line_selections.jsonl`。维护方法及正文绑定规则见 [名句维护](famous-lines.md#维护与验证)。

## 工具索引

| 工具 | 用途 |
|---|---|
| `scripts/rebuild.py` | 临时构建、验证及发布完整维护包 |
| `scripts/export_app_runtime.py` | 从完整维护包生成 App 运行包 |
| `scripts/audit_data.py` | 检查完整包并更新报告 |
| `scripts/search.py` | 查询两种数据库，自动识别格式 |
| `scripts/read_runtime_record.py` | 还原运行包中的完整档案 |
| `scripts/prepare_review_resolutions.py` | 编译显式修订、前后值与校验哈希 |
| `scripts/merge_annotations.py` | 兼容入口，等同 `rebuild.py --app-only` |

`scripts/` 同时保留历史工具与诊断脚本，日常维护以本页入口为准。
