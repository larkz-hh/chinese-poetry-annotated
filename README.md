# 古诗词 App 数据源

面向古诗词阅读、检索和背诵 App 的离线数据仓库。从 [yxcs/poems-db](https://github.com/yxcs/poems-db) 原始转储整理而来，提供作品、译文、注释、赏析、作者资料、分类、正文版本和来源信息，以及可复现的构建与审核工具。

**开发 App，优先使用 [app-runtime/poems.db](app-runtime/poems.db)。** 当前约 **18.7 MiB**，完整维护库约 **38.2 MiB**。运行包通过文本去重、引用和压缩减少重复存储，保留全部作品、译注、作者长文、异文、来源及完整记录中的审核资料。

当前精选包包含 **1524 条作品、372 条作者记录**，每条作品都有译文、注释和赏析。收录文体包括诗、词、曲、文、赋。完整目录与字段说明见下文，App 的详细 SQL 和档案解码方法见 [运行包接入说明](app-runtime/README.md)。

## 目录

- [选择数据包](#选择数据包)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [App 接入约定](#app-接入约定)
- [构建与更新](#构建与更新)
- [内容审核与质量状态](#内容审核与质量状态)
- [维护工具与审核记录](#维护工具与审核记录)
- [数据来源与使用说明](#数据来源与使用说明)

## 选择数据包

| 文件 | 用途 | 存储方式 |
|---|---|---|
| [app-runtime/poems.db](app-runtime/poems.db) | App 离线阅读、筛选、搜索 | runtime schema 1；常用内容直接 SQL 查询，完整记录按需解压 |
| [app-data/poems.db](app-data/poems.db) | 维护、核查及完整数据导入 | schema 3；关系表与完整 `metadata_json` 同时保留 |
| [app-data/poems.json](app-data/poems.json) | 脚本处理或 JSON 接入 | 完整作品记录，作者资料另见 `authors.json` |

两种数据库来自同一份精选数据，**表结构不同，内容无损保留**。运行包逐条还原作品、作者完整记录，与维护版进行比较后才发布。

| 当前交付指标 | 数量 |
|---|---:|
| 作品 / 作者记录 | 1524 / 372 |
| 有译文、注释、赏析的作品 | 各 1524 |
| 正文版本 / 显示单元 | 1594 / 6874 |
| 当前及旧 ID 映射 | 1988 |
| 作者生平、轶事等长文栏目 | 1157 |
| 已标明的解释、版本或地望分歧 | 42 |
| App 数据库 / 完整数据库 | 18.7 / 38.2 MiB |

体积以 MiB（1024² 字节）计。运行库 gzip 压缩实测约 7.5 MiB，仅代表传输压缩尺寸，解压后仍占约 18.7 MiB；仓库未额外存放一份 gzip 运行包。

App 通常打包 `app-runtime/poems.db`，并用同目录的 `manifest.json` 校验文件即可，无须再携带完整库和作品 JSON。`raw/poems_all.jsonl.gz` 中的 **214526 条全库素材**是另一层构建输入，不能与当前 1524 条精选包的覆盖率混用。

## 快速开始

已有数据库可直接读取。运行仓库工具需要 **Python 3.10+**，仅使用标准库，无须安装第三方 Python 依赖。搜索需要目标 SQLite 启用 **FTS5**。下面的命令均在项目根目录执行。

### 搜索作品

```powershell
# 按标题搜索，包含旧题名和别名
python -X utf8 scripts/search.py 静夜思 --column title --db app-runtime/poems.db

# 搜索标题、作者和正文
python -X utf8 scripts/search.py 明月 --db app-runtime/poems.db
```

`--column` 可选 `title`、`author`、`content`。省略时搜索三个字段；省略 `--db` 时，脚本默认读取完整维护库 `app-data/poems.db`。

### 读取一条完整记录

```powershell
# 包括正文、译注、版本、来源和详细审核信息；也接受旧作品 ID
python -X utf8 scripts/read_runtime_record.py poem 5c26e57597880d3b8265ceec
```

普通阅读使用 SQL 表和视图即可，这个命令主要用于核查完整资料。它支持 `poem`、`author`、`package` 三种档案。

### 运行测试

```powershell
python -X utf8 -m unittest discover -s scripts -p "test_*.py" -v
```

当前 35 项测试通过，运行包另外完成 41 组真实搜索及分页对照。普通测试、构建和导出不调用模型接口，也不要求配置 API 密钥。

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
├─ scripts/                      构建、导出、搜索、补注、审核和测试工具
├─ reports/                      数据审计与运行包验收结果
├─ backups/                      本机历史快照、工作记录；不纳入 Git
├─ .gitattributes                文本换行与二进制文件规则
├─ .gitignore
└─ README.md
```

`app-data/todo_annotations.jsonl` 和 `app-data/todo_content_review.jsonl` 分别记录缺注解、内容待核任务，当前均为空。`raw/data-report-v1.json`、`reports/baseline-v2-audit.md` 等是历史记录，当前统计以各数据包的 manifest、`app-data/stats.json` 和最新审计报告为准。

## App 接入约定

### 数据库格式与版本

| 项目 | App 运行包 | 完整维护包 |
|---|---|---|
| 路径 | `app-runtime/poems.db` | `app-data/poems.db` |
| `PRAGMA user_version` | `1` | `3` |
| `PRAGMA application_id` | `1347372372`，即 `POET` | 不用该标识识别运行包 |
| 常用作品读取 | `poems` 视图、`passages` 等 | `poems` 表及 `metadata_json` |
| 完整作品、作者 JSON | 解码 `record_archives` | 读取对应表的 `metadata_json` |
| FTS 关联作品 | `p.rowid = poems_fts.rowid` | `p.id = poems_fts.pid` |

schema 版本用于识别表结构；manifest 的 `data_version` 用于识别内容包。运行包另用 `source_data_version` 标明其完整维护包来源。应按格式选择读取逻辑，不能仅替换文件后继续读取旧格式的 `metadata_json` 列。

### 阅读、筛选与作者资料

以下 SQL **针对 App 运行包**，参数使用绑定值：

```sql
-- 列表与分页
SELECT id,title,author,dynasty,genre
FROM poems ORDER BY id LIMIT ? OFFSET ?;

-- 正文、译文、注释、赏析的有序段落
-- kind：content / translate / notes / appreciation / original_content
SELECT ordinal,body FROM passages
WHERE poem_id=? AND kind=? ORDER BY ordinal;

-- 朝代、题材、学段组合筛选
SELECT p.id,p.title,p.author FROM poems p
WHERE p.dynasty=?
  AND EXISTS(SELECT 1 FROM themes t WHERE t.poem_id=p.id AND t.theme=?)
  AND EXISTS(SELECT 1 FROM levels l WHERE l.poem_id=p.id AND l.level=?)
ORDER BY p.id LIMIT ? OFFSET ?;

-- 作者简介和生平、轶事等长文
SELECT * FROM authors WHERE id=?;
SELECT ordinal,kind,body FROM author_desc WHERE author_id=? ORDER BY ordinal;

-- 阅读时可显示的解释分歧
SELECT field,body FROM review_cautions WHERE poem_id=? ORDER BY finding_index;
```

`authors.works` 是当前包实际收录数，`source_works` 是原资料宣称的总数。文体使用 `genre` 区分诗、词、曲、文、赋；`format` 保留来源标注，不宜单独作为文体分类依据。

### 段落、版本与稳定 ID

- `content` 是当前主版本的显示单元，可能是一联、一段、序言或合集中的一首。
- `translate`、`notes`、`appreciation` 当前按**整篇**展示。数组长度相等不代表逐句对应，不能直接把 `content[i]` 与 `translate[i]`、`notes[i]` 配对。运行包读取 `annotation_info.alignment_mode`，完整记录读取 `alignment[field].mode`。
- 通过 `editions.is_primary=1` 选择主版本，不能假设版本数组的第一项始终是主版本。其他版本、异文提示、原始正文与稳定单元 ID 均保留。
- 同名作品用不同 ID 区分；来源 ID、合并前 ID 通过 `id_aliases` 或 `app-data/id_map.json` 解析。收藏和进度应保存作品 ID，更新时先解析映射，不以标题作为唯一标识。

```sql
-- 用旧 ID 查找当前作品
SELECT p.* FROM id_aliases a JOIN poems p ON p.id=a.poem_id WHERE a.old_id=?;

-- 当前主版本与稳定单元 ID
SELECT u.id,u.ordinal,u.body
FROM editions e JOIN edition_passages u ON u.edition_id=e.id
WHERE e.poem_id=? AND e.is_primary=1 ORDER BY u.ordinal;
```

数据包作为只读内容库使用。收藏、历史、背诵进度等保存在 App 自己的用户库；替换内容包前关闭旧连接，替换后按 manifest 校验文件。

### 搜索与完整审核档案

搜索覆盖标题及别名、作者、正文，权重分别为 10、5、1。查询按 Unicode 字符归一化分词，保留标点和段落边界；用户输入作为普通文字处理，避免把引号、星号等当成 FTS 运算符。可复用 `scripts/search.py` 与 `data_utils.match_query()`。

运行包使用 contentless FTS，索引不保存一份额外的可读文本。按 `rowid` 关联 `poems` 后读取结果；FTS 自身的文本列返回 NULL。详细 SQL、跨语言查询规则及档案解码见 [运行包接入说明](app-runtime/README.md)。

完整审核记录没有因运行包优化而删除：`record_archives` 保留每条作品和作者的完整记录，古籍证据摘录保存为 `package/source_evidence`。日常阅读不需要解压这些档案。`raw/` 中独立的模型原始回复、修改决定和前后对照继续保留在项目中。

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

验收记录：[完整包审计](reports/app-data-audit.md) · [运行包验收](reports/app-runtime-audit.md)。

## 内容审核与质量状态

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

《田家词》《风流子·黄钟商芍药》《除夜自石湖归苕溪十首》另有据古籍校订的主版本，旧正文、旧题名、版本与单元 ID 均保留。具体依据与修订前后对照见 [内容审核报告](reports/app-data-audit.md)。

## 维护工具与审核记录

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

主要维护记录：

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

## 数据来源与使用说明

原始素材来自 [yxcs/poems-db](https://github.com/yxcs/poems-db) 转储，其中保留了古诗文网等来源链接。作品详情、原始内容、来源 URL、来源 ID 以及校订证据继续保留，便于核查。

古代作品原文、现代译注、作者资料及生成内容的使用依据应分别核实。本项目不把“抓取内容”或“AI 内容”当作已确认授权的标记。数据更新与使用时，应保留对应来源及审核说明。
