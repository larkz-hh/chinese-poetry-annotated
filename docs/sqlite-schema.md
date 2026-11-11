# SQLite 字段手册

[项目首页](../README.md) · [接入指南](integration.md) · [数据结构与 JSON](data-format.md) · [查询示例](../app-runtime/README.md)

本手册以 App 运行包 **runtime schema 2** 为主，字段按实际交付数据库整理。常用读取接口在前，底层去重存储在末尾折叠区。

## 对象导航

| 用途 | 对象 |
|---|---|
| 作品与段落 | [poems](#poems)、[passages](#passages) |
| 作者 | [authors](#authors)、[author_desc](#author_desc) |
| 注解来源 | [annotation_info](#annotation_info) |
| 分类 | [themes](#themes)、[collections](#collections)、[levels](#levels) |
| 来源与 ID | [poem_aliases](#poem_aliases)、[poem_sources](#poem_sources)、[poem_source_ids](#poem_source_ids)、[id_aliases](#id_aliases) |
| 版本 | [editions](#editions)、[edition_passages](#edition_passages) |
| 审核与包信息 | [review_cautions](#review_cautions)、[record_archives](#record_archives)、[package_info](#package_info) |
| 搜索 | [poems_fts](#poems_fts) |
| 名句卡片 | [famous_lines](#famous_lines)、[famous_line_units](#famous_line_units) |

## 字段约定

- SQLite 布尔值采用整数 `0/1`；JSON 使用 `false/true`。
- `*_json` 列为 JSON 文本，读取后需解析。
- 视图没有物理主键约束；计算列的声明类型可能为空，下表以“未声明”标示。
- 约束栏记录字段主键位置、显式非空与外键；唯一约束、索引及完整 DDL 以 [建库定义](../scripts/runtime_db.py) 为准。

## 格式对照

运行包与完整维护包收录范围相同，存储结构分别采用 runtime schema 2 与 schema 4。

| 数据内容 | App 运行包 | 完整维护包 |
|---|---|---|
| 作品列表与详情 | `poems` 视图，底层为 `poem_records` | `poems` 表 |
| 正文、译文、注释、赏析 | `passages` 视图，逐段读取 | `poems` 的换行拼接文本；完整数组在 `metadata_json` |
| 注解来源与对齐方式 | `annotation_info` 表 | `annotations` 表，含 `body_json`、`mode`、`metadata_json` |
| 作者基本资料 | `authors` 表 | `authors` 表 |
| 作者长文 | `author_desc` 视图 | `author_desc` 表；完整数组在作者 `metadata_json` |
| 版本与正文单元 | `editions` 表、`edition_passages` 视图 | `editions`、`poem_units` 表 |
| 题材、选集、学段 | `themes`、`collections`、`levels` 视图 | 三个同名表 |
| 旧作品 ID | `id_aliases` 表 | `id_aliases` 表 |
| 完整作品与作者 JSON | `record_archives` 解码后获得 | `poems.metadata_json`、`authors.metadata_json` |
| 名句与正文定位 | `famous_lines`、`famous_line_units` 表 | 同名两张表 |
| 全文搜索 | `poems_fts`，按 `rowid` 关联作品 | `poems_fts`，按 `pid` 关联作品 ID |

运行包中的完整档案经解码获得 JSON；完整维护包从 `metadata_json` 读取。格式切换时应同时调整查询方式。

## 常用读取接口

### poems

视图 · 作品阅读视图。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `rowid` | INTEGER | — | 包内 FTS 关联键；跨包收藏使用 id |
| `id` | TEXT | — | 作品稳定 ID |
| `title` | TEXT | — | 题名 |
| `source_title` | TEXT | — | 来源题名 |
| `author` | TEXT | — | 作者名称 |
| `author_id` | TEXT | — | 作者 ID |
| `dynasty` | TEXT | — | 主要朝代 |
| `format` | TEXT | — | 来源体裁标注 |
| `genre` | TEXT | — | 文体分类 |
| `genre_basis` | TEXT | — | 文体判定依据 |
| `source` | TEXT | — | 主要来源 URL |
| `body_hash` | TEXT | — | 绑定正文的校验哈希 |
| `complete` | INTEGER | — | 三类注解数组是否均非空 |
| `ai_generated` | INTEGER | — | AI 生成或编辑标记，含历史标记 |
| `review_status` | TEXT | — | 审核状态 |
| `text_scope` | TEXT | — | 正文收录范围 |
| `collection` | 未声明 | — | 选集名称，以“、”连接 |
| `content` | 未声明 | — | 主版本正文，按换行拼接 |
| `translate` | 未声明 | — | 译文，按换行拼接 |
| `notes` | 未声明 | — | 注释，按换行拼接 |
| `appreciation` | 未声明 | — | 赏析，按换行拼接 |

列表按需读取字段。精确段落边界使用 `passages`，跨版本关联使用作品 `id`。

### passages

视图 · 正文与译注段落。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | — | 作品 ID |
| `kind` | TEXT | — | content / translate / notes / appreciation / original_content |
| `ordinal` | INTEGER | — | 同一分组内从 0 开始的序号 |
| `body` | TEXT | — | 一个完整显示单元 |

按 `poem_id`、`kind` 过滤，再按 `ordinal` 排序。正文与译注数组长度相等不代表逐句对应。

### authors

表 · 作者基本资料。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | 主键 1 | 作者稳定 ID |
| `name` | TEXT | 非空 | 作者名称 |
| `dynasty` | TEXT | — | 主要朝代 |
| `lifetime` | TEXT | — | 简介文本，包含生平信息 |
| `works` | INTEGER | — | 本包收录作品数 |
| `source_works` | INTEGER | — | 来源宣称的作品总数 |
| `avatar` | TEXT | — | 来源头像 URL |
| `bio_status` | TEXT | — | 作者简介资料状态 |
| `entity_type` | TEXT | — | 作者实体类型，如 person |
| `dynasties_json` | TEXT | 非空 | 朝代数组的 JSON 文本 |
| `bio_sources_json` | TEXT | 非空 | 简介来源的 JSON 文本 |

`works` 为本包收录数，`source_works` 为来源宣称的总数；`lifetime` 为简介文本。

### author_desc

视图 · 作者长文章节。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `author_id` | TEXT | — | 作者 ID |
| `ordinal` | INTEGER | — | 同一分组内从 0 开始的序号 |
| `kind` | TEXT | — | 章节类型，如生平、轶事 |
| `body` | 未声明 | — | 章节各段按换行拼接的文本 |

### annotation_info

表 · 注解来源与展示模式。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | 主键 1；非空；→ `poem_records.id` | 作品 ID |
| `kind` | TEXT | 主键 2；非空 | translate / notes / appreciation |
| `source_type` | TEXT | — | 注解来源类型 |
| `review_status` | TEXT | — | 审核状态 |
| `model` | TEXT | — | 相关生成模型 |
| `source_url` | TEXT | — | 来源 URL |
| `body_hash` | TEXT | — | 绑定正文的校验哈希 |
| `alignment_mode` | TEXT | — | 展示模式，当前为 document |
| `alignment_verified` | INTEGER | — | 是否验证对齐关系 |
| `equal_length` | INTEGER | — | 注解与正文数组长度是否相等 |
| `unit_ids_json` | TEXT | 非空 | 对应单元 ID 的 JSON 数组 |

`equal_length` 仅表示长度相等。当前展示模式为 `document`，按整篇展示。

## 分类与来源

### themes

视图 · 题材。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | — | 作品 ID |
| `theme` | TEXT | — | 题材名称 |

### collections

视图 · 选集。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | — | 作品 ID |
| `collection` | TEXT | — | 选集名称 |

### levels

视图 · 学段。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | — | 作品 ID |
| `level` | TEXT | — | 学段名称 |

### poem_aliases

表 · 题名别名。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | 主键 1；非空；→ `poem_records.id` | 作品 ID |
| `ordinal` | INTEGER | 主键 2；非空 | 同一分组内从 0 开始的序号 |
| `title` | TEXT | — | 题名 |

### poem_sources

表 · 来源链接。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | 主键 1；非空；→ `poem_records.id` | 作品 ID |
| `ordinal` | INTEGER | 主键 2；非空 | 同一分组内从 0 开始的序号 |
| `url` | TEXT | — | 来源 URL |

### poem_source_ids

表 · 来源作品 ID。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | 主键 1；非空；→ `poem_records.id` | 作品 ID |
| `ordinal` | INTEGER | 主键 2；非空 | 同一分组内从 0 开始的序号 |
| `source_id` | TEXT | — | 来源记录 ID |

### id_aliases

表 · 旧作品 ID 映射。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `old_id` | TEXT | 主键 1；非空 | 来源或合并前作品 ID |
| `poem_id` | TEXT | 非空；→ `poem_records.id` | 作品 ID |

## 版本与审核

### editions

表 · 正文版本。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | 主键 1 | 版本稳定 ID |
| `poem_id` | TEXT | → `poem_records.id` | 作品 ID |
| `ordinal` | INTEGER | — | 同一分组内从 0 开始的序号 |
| `label` | TEXT | — | 版本显示名称 |
| `is_primary` | INTEGER | — | 是否为主版本 |
| `source` | TEXT | — | 主要来源 URL |
| `source_id` | TEXT | — | 来源记录 ID |
| `revision` | TEXT | — | 修订标识 |
| `reason` | TEXT | — | 修订理由 |
| `variants_json` | TEXT | 非空 | 异文的 JSON 文本 |
| `evidence_json` | TEXT | 非空 | 校订依据的 JSON 文本 |

每个作品以 `is_primary=1` 选择主版本。版本顺序由 `ordinal` 表示。

### edition_passages

视图 · 版本正文单元。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | — | 单元稳定 ID |
| `poem_id` | TEXT | — | 作品 ID |
| `edition_id` | TEXT | — | 版本 ID |
| `ordinal` | INTEGER | — | 同一分组内从 0 开始的序号 |
| `kind` | TEXT | — | 单元类型，如 passage |
| `body` | TEXT | — | 文本内容 |

### review_cautions

表 · 解释分歧提示。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | 主键 1；非空；→ `poem_records.id` | 作品 ID |
| `finding_index` | INTEGER | 主键 2；非空 | 原审核疑点序号 |
| `field` | TEXT | — | 涉及的注解字段 |
| `body` | TEXT | 非空 | 文本内容 |

### record_archives

表 · 完整压缩档案。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `kind` | TEXT | 主键 1 | poem / author / package |
| `id` | TEXT | 主键 2 | 作品、作者或包级档案标识 |
| `codec` | TEXT | 非空 | 编码标识：zlib-json-textrefs-v1 |
| `payload` | BLOB | 非空 | 压缩后的带标签节点树 |
| `sha256` | TEXT | 非空 | 还原 JSON 的 SHA-256 |
| `raw_bytes` | INTEGER | 非空 | 还原 JSON 的 UTF-8 字节数 |

以 `(kind,id)` 定位记录。包级档案包括 `source_evidence` 与 `source_manifest`，解码步骤见 [运行包说明](../app-runtime/README.md#完整记录和审核档案)。

### package_info

表 · 包级信息。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `key` | TEXT | 主键 1；非空 | 元信息名称 |
| `value` | TEXT | 非空 | 值 |

### poems_fts

FTS5 虚拟表 · 全文检索索引。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `pid` | 未声明 | — | 索引字段，运行包读取值为 NULL |
| `title` | 未声明 | — | 索引字段，运行包读取值为 NULL |
| `author` | 未声明 | — | 索引字段，运行包读取值为 NULL |
| `content` | 未声明 | — | 索引字段，运行包读取值为 NULL |

采用 contentless FTS5，查询结果以 `rowid` 关联 `poems.rowid`。索引自身文本列不用于展示。

## 名句卡片

JSON 格式、收录范围及使用示例见 [名句指南](famous-lines.md)。

### famous_lines

表 · 名句文本与来源。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | 主键 1 | 名句稳定 ID |
| `poem_id` | TEXT | 非空；→ `poem_records.id` | 所属作品 ID |
| `ordinal` | INTEGER | 非空 | 从 0 开始的顺序 |
| `text` | TEXT | 非空 | 卡片展示文本 |
| `source_url` | TEXT | 非空 | 名句页或正文来源 URL |

### famous_line_units

表 · 名句到正文单元的有序关联。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `quote_id` | TEXT | 主键 1；非空；→ `famous_lines.id` | 名句 ID |
| `ordinal` | INTEGER | 主键 2；非空 | 从 0 开始的顺序 |
| `unit_id` | TEXT | 非空；→ `poem_units.id` | 当前主版本内的正文单元 ID |

## 底层存储

以下为共享文本与引用关系的物理表。应用常规阅读优先使用上文视图。

<details>
<summary>展开底层存储字段（8 张表）</summary>

### poem_records

表 · 作品基础存储。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `rowid` | INTEGER | 主键 1 | 包内整数标识，用于 FTS 关联 |
| `id` | TEXT | 非空 | 记录标识 |
| `title` | TEXT | 非空 | 题名 |
| `source_title` | TEXT | — | 来源题名 |
| `author_id` | TEXT | 非空；→ `authors.id` | 作者 ID |
| `dynasty` | TEXT | — | 主要朝代 |
| `format` | TEXT | — | 来源体裁标注 |
| `genre` | TEXT | — | 文体分类 |
| `genre_basis` | TEXT | — | 文体判定依据 |
| `source` | TEXT | 非空 | 主要来源 URL |
| `body_hash` | TEXT | 非空 | 绑定正文的校验哈希 |
| `complete` | INTEGER | 非空 | 三类注解数组是否均非空 |
| `ai_generated` | INTEGER | 非空 | AI 生成或编辑标记，含历史标记 |
| `review_status` | TEXT | 非空 | 审核状态 |
| `text_scope` | TEXT | — | 正文收录范围 |
| `reference_json` | TEXT | 非空 | 参考资料的 JSON 文本 |
| `quality_issues_json` | TEXT | 非空 | 质量提示的 JSON 文本 |

### text_blocks

表 · 共享文本。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | 主键 1 | 记录标识 |
| `body` | TEXT | 非空 | 文本内容 |

### poem_text

表 · 作品段落引用。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | 主键 1；非空；→ `poem_records.id` | 作品 ID |
| `kind` | TEXT | 主键 2；非空 | content / translate / notes / appreciation / original_content |
| `ordinal` | INTEGER | 主键 3；非空 | 同一分组内从 0 开始的序号 |
| `text_id` | INTEGER | → `text_blocks.id` | 共享文本 ID |

### poem_terms

表 · 分类与标签存储。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `poem_id` | TEXT | 主键 1；非空；→ `poem_records.id` | 作品 ID |
| `kind` | TEXT | 主键 2；非空 | themes / collections / levels / tags |
| `ordinal` | INTEGER | 主键 3；非空 | 同一分组内从 0 开始的序号 |
| `value` | TEXT | — | 分类名称或原始标签 |

### author_sections

表 · 作者章节。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `author_id` | TEXT | 主键 1；非空；→ `authors.id` | 作者 ID |
| `ordinal` | INTEGER | 主键 2；非空 | 同一分组内从 0 开始的序号 |
| `kind` | TEXT | — | 内容种类 |

### author_section_text

表 · 作者章节段落引用。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `author_id` | TEXT | 主键 1；非空；→ `author_sections.author_id` | 作者 ID |
| `section_ordinal` | INTEGER | 主键 2；非空；→ `author_sections.ordinal` | 所属作者章节序号 |
| `ordinal` | INTEGER | 主键 3；非空 | 同一分组内从 0 开始的序号 |
| `text_id` | INTEGER | → `text_blocks.id` | 共享文本 ID |

### poem_units

表 · 版本单元存储。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | 主键 1 | 单元稳定 ID |
| `edition_id` | TEXT | → `editions.id` | 版本 ID |
| `ordinal` | INTEGER | — | 同一分组内从 0 开始的序号 |
| `kind` | TEXT | — | 单元类型，如 passage |
| `text_id` | INTEGER | → `text_blocks.id` | 共享文本 ID |

### edition_originals

表 · 版本原始正文。

| 字段 | 声明类型 | 约束 | 说明 |
|---|---|---|---|
| `edition_id` | TEXT | 主键 1；非空；→ `editions.id` | 版本 ID |
| `ordinal` | INTEGER | 主键 2；非空 | 同一分组内从 0 开始的序号 |
| `text_id` | INTEGER | → `text_blocks.id` | 共享文本 ID |

</details>

## 检查实际结构

以下 SQL 适用于 App 运行库。`table_info` 中 `pk` 大于 0 表示主键位置。

```sql
SELECT type, name, sql
FROM sqlite_master
WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
ORDER BY type, name;

PRAGMA table_info(poems);
PRAGMA table_info(poem_records);
PRAGMA foreign_key_list(poem_records);
```
