# 构建与维护

[返回项目首页](../README.md) · [App 接入](integration.md) · [审核流程与记录](review.md)

本页供维护数据的人使用。只接入现有数据包的 App 开发者可直接阅读 [App 接入指南](integration.md)。下面的路径和命令均相对项目根目录。

构建工具需要 Python 3.10+，仅使用标准库。普通重建、导出、审计和自动化测试不调用模型接口，也不要求 API 密钥。

## 项目结构

```text
poems-clean/
├─ app-runtime/                  App 交付包
│  ├─ poems.db                   运行数据库
│  ├─ manifest.json              文件哈希、格式与来源版本、记录数
│  └─ README.md                  运行包表结构、SQL 与档案解码说明
├─ app-data/                     完整维护包
│  ├─ poems.db / poems.json       同一批作品的 SQLite 与 JSON 表示
│  ├─ authors.json               作者简介与长文
│  ├─ categories.json            题材、选集、学段字典
│  ├─ id_map.json                来源及旧作品 ID → 当前作品 ID
│  ├─ review_cautions.jsonl       已处理但仍有解释分歧的提示
│  ├─ source_evidence.json        古籍核对摘录及依据
│  ├─ generated.jsonl            历史生成记录
│  └─ manifest.json / stats.json  完整包清单与覆盖率
├─ raw/                          构建素材、审核意见、显式修订决定
├─ docs/                         接入、构建、审核专题文档
├─ scripts/                      构建、导出、搜索、补注、审核和测试工具
├─ reports/                      数据审计与运行包验收结果
├─ backups/                      本机历史快照、工作记录；不纳入 Git
├─ .gitattributes                文本换行与二进制文件规则
├─ .gitignore
└─ README.md
```

`app-data/todo_annotations.jsonl` 和 `app-data/todo_content_review.jsonl` 分别记录缺注解、内容待核任务，当前均为空。`raw/data-report-v1.json`、`reports/baseline-v2-audit.md` 等是历史记录，当前统计以各数据包的 manifest、`app-data/stats.json` 和最新审计报告为准。

## 构建与更新

```text
原始 poems-db 转储 + 固定选取范围
                  ↓
raw/ 素材 + 补注记录 + 显式修订决定
                  ↓
app-data/ 完整维护包
                  ↓
app-runtime/ App 运行包
```

### 使用已有素材重建

仓库已包含所需 raw 素材和历史注解。只复用这些文件时，无需相邻的原始转储目录。

```powershell
# 临时重建并检查，不替换完整数据包；会更新检查报告
python -X utf8 scripts/rebuild.py --app-only --check-only

# 检查通过后，生成完整维护包
python -X utf8 scripts/rebuild.py --app-only

# 再由完整维护包生成 App 运行包
python -X utf8 scripts/export_app_runtime.py
```

每步成功后再执行下一步。`rebuild.py` 和 `merge_annotations.py` 更新的是完整维护包，**不会自动更新运行包**；随后须运行 `export_app_runtime.py`。导出器先核对源包哈希，在临时目录生成并检查新库，校验通过才替换运行包，同时确认完整源包未变化。

### 从原始转储全量重建

默认原始目录为相邻的 `../poems-db`，需包含 `poems1.json` 至 `poems4.json`、`poems-authors.json`、`poems-cipai.json`。

```powershell
# 也可通过 --source-dir 指定其他位置
python -X utf8 scripts/rebuild.py --source-dir ../poems-db --check-only
python -X utf8 scripts/rebuild.py --source-dir ../poems-db
python -X utf8 scripts/export_app_runtime.py
```

构建以来源 URL、作者、正文等识别重复，不按标题直接合并。固定选取范围保存在 `raw/selection.json`；额外的异文合并、作者归属和文体决定保存在 `raw/content_review.json`。原 1470 个作品 ID、中间版本全部 1579 个作品 ID 仍有解析映射。

### 验证结果

```powershell
# 只读检查完整数据包，将结果写入 reports/
python -X utf8 scripts/audit_data.py

# 全部自动化测试
python -X utf8 -m unittest discover -s scripts -p "test_*.py" -v
```

完整包校验覆盖 JSON/SQLite 一致性、字段来源、正文哈希、ID 映射、版本、分类、FTS、外键与文件清单。运行包导出还逐项核对全部作品与作者完整记录、段落、长文、原始正文、版本、单元 ID、来源、分类和审核提示，并对照搜索及分页结果。

验收记录：[完整包审计](../reports/app-data-audit.md) · [运行包验收](../reports/app-runtime-audit.md)。

## 工具入口

日常维护建议从下列入口开始；`scripts/` 中同时保留了历史生成、排查和诊断工具。

| 工具 | 用途 |
|---|---|
| `scripts/rebuild.py` | 临时构建、校验并发布完整维护包 |
| `scripts/export_app_runtime.py` | 从完整包导出独立的 App 运行包 |
| `scripts/search.py` | 查询两种数据库，自动识别格式 |
| `scripts/read_runtime_record.py` | 读取并还原运行包中的完整档案 |
| `scripts/audit_data.py` | 核验完整包并写审计报告 |
| `scripts/prepare_review_resolutions.py` | 离线编译显式修改、前后值与哈希 |
| `scripts/merge_annotations.py` | 复用 raw 重建完整包，相当于 `rebuild.py --app-only` |

补注、内容核查、显式修订及模型接口配置单独见 [审核流程与记录](review.md)。
