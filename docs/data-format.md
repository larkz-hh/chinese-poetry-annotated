# 数据格式：SQLite 表结构与 JSON 示例

[返回项目首页](../README.md) · [App 接入指南](integration.md) · [查询 SQL 与档案解码](../app-runtime/README.md)

下面区分 **App 运行包（runtime schema 1）** 和 **完整维护包（schema 3）**。字段与示例均依据当前交付文件整理；两包保存同一批作品，但存储结构不同。

## 两种数据库如何对应

| 数据内容 | App 运行包 `app-runtime/poems.db` | 完整维护包 `app-data/poems.db` |
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
| 全文搜索 | `poems_fts`，按 `rowid` 关联作品 | `poems_fts`，按 `pid` 关联作品 ID |

运行包中的视图是 SQL 读取接口，不能直接按同名普通表写入。Room 映射需区分 Entity 与 DatabaseView，具体见 [App 接入指南](integration.md#使用-sqlite-或-room)。

## App 运行包的主要字段

以下类型表示查询值的用途；视图中计算字段的 SQLite 声明类型可能为空。布尔字段在 SQLite 中使用整数 `0/1`，JSON 中使用 `false/true`。`*_json` 列是存放 JSON 文本的 `TEXT`，读取后需再解析。

### 作品阅读视图 `poems`

| 字段 | 读取类型 | 含义 |
|---|---|---|
| `rowid` | INTEGER | 当前运行包内的 FTS 关联键；不用于跨版本收藏 |
| `id` | TEXT | 作品稳定 ID，供详情、收藏及关联查询使用 |
| `title` | TEXT | 当前显示题名 |
| `source_title` | TEXT | 来源题名 |
| `author` | TEXT | 作者名称 |
| `author_id` | TEXT | 关联 `authors.id` |
| `dynasty` | TEXT | 朝代，如 `唐代` |
| `format` | TEXT | 来源标注的体裁，如 `七言绝句` |
| `genre` | TEXT | 诗、词、曲、文、赋等分类 |
| `genre_basis` | TEXT | 文体判定依据 |
| `source` | TEXT | 主要来源 URL；全部来源见 `poem_sources` |
| `body_hash` | TEXT | 当前正文的校验哈希 |
| `complete` | INTEGER | 三类注解数组是否均非空；不代表内容质量已获保证 |
| `ai_generated` | INTEGER | 是否保留 AI 生成或编辑注解的标记，含历史标记；不表示正文由 AI 创作 |
| `review_status` | TEXT | 当前作品审核状态，枚举含义见 [审核说明](review.md) |
| `text_scope` | TEXT | 正文收录范围标记 |
| `collection` | TEXT | 选集名称以 `、` 连接的显示文本；筛选使用 `collections` |
| `content` | TEXT / NULL | 主版本正文各单元用换行拼接的文本 |
| `translate` | TEXT / NULL | 译文各段用换行拼接的文本 |
| `notes` | TEXT / NULL | 注释各段用换行拼接的文本 |
| `appreciation` | TEXT / NULL | 赏析各段用换行拼接的文本 |

`poems.content` 等字段是字符串；JSON 文件中的同名字段是字符串数组。需要精确保留段落边界时读取下面的 `passages`，不要通过拆分换行来猜测原数组。

### 段落视图 `passages`

| 字段 | 读取类型 | 含义 |
|---|---|---|
| `poem_id` | TEXT | 关联作品 ID |
| `kind` | TEXT | `content`、`translate`、`notes`、`appreciation`、`original_content` |
| `ordinal` | INTEGER | 同一作品、同一种类内从 0 开始的序号 |
| `body` | TEXT | 一个完整显示单元的文本 |

按 `poem_id`、`kind` 查询并按 `ordinal` 排序。正文单元可能是一联、一段或合集中的一首。当前译注按整篇展示，**数组长度相等不代表逐句对齐**。

### 作者表 `authors`

| 字段 | SQLite 类型 | 含义 |
|---|---|---|
| `id` | TEXT | 作者主键 |
| `name` | TEXT | 作者名称 |
| `dynasty` | TEXT | 主要朝代 |
| `lifetime` | TEXT | 简介文本，包含生平信息，并非单独的生卒年字段 |
| `works` | INTEGER | 本包实际收录作品数 |
| `source_works` | INTEGER | 原资料声称的作品总数 |
| `avatar` | TEXT | 来源头像 URL，App 离线显示需自行处理 |
| `bio_status` | TEXT | 简介资料状态，与作品注解审核状态分别记录 |
| `entity_type` | TEXT | 作者实体类型，例如 `person` |
| `dynasties_json` | TEXT | 朝代数组的 JSON 文本 |
| `bio_sources_json` | TEXT | 简介来源的 JSON 文本 |

作者长文通过 `author_desc(author_id, ordinal, kind, body)` 读取，按 `ordinal` 排序。`kind` 是生平、轶事等章节类型；`body` 是该章节各段换行拼接的文本。完整章节数组保留在作者 JSON 的 `describe` 中。

### 注解信息表 `annotation_info`

| 字段 | SQLite 类型 | 含义 |
|---|---|---|
| `poem_id` | TEXT | 作品 ID；与 `kind` 组成复合主键 |
| `kind` | TEXT | `translate`、`notes` 或 `appreciation` |
| `source_type` | TEXT | 原始、生成或其他来源类型 |
| `review_status` | TEXT | 该类注解的审核状态 |
| `model` | TEXT | 相关生成模型，可为 NULL |
| `source_url` | TEXT | 来源链接，可为 NULL |
| `body_hash` | TEXT | 注解绑定的正文哈希 |
| `alignment_mode` | TEXT | 当前为 `document`，按整篇展示 |
| `alignment_verified` | INTEGER | 是否验证了对齐关系 |
| `equal_length` | INTEGER | 注解与正文数组长度是否相等；不保证逐句对应 |
| `unit_ids_json` | TEXT | 显式对应单元 ID 的 JSON 数组 |

### 分类、版本、来源与档案

下表中的列名为完整列清单，具体 SQL 见 [运行包说明](../app-runtime/README.md#普通读取)。

| 对象 | 类型 | 列 | 用途或关联 |
|---|---|---|---|
| `themes` | 视图 | `poem_id, theme` | 题材筛选 |
| `collections` | 视图 | `poem_id, collection` | 选集筛选 |
| `levels` | 视图 | `poem_id, level` | 学段筛选 |
| `poem_aliases` | 表 | `poem_id, ordinal, title` | 旧题名与别名 |
| `poem_sources` | 表 | `poem_id, ordinal, url` | 全部来源 URL |
| `poem_source_ids` | 表 | `poem_id, ordinal, source_id` | 全部来源作品 ID |
| `id_aliases` | 表 | `old_id, poem_id` | 合并前 ID、旧 ID 到当前作品的映射 |
| `editions` | 表 | `id, poem_id, ordinal, label, is_primary, source, source_id, revision, reason, variants_json, evidence_json` | `is_primary=1` 选主版本，JSON 列保留异文与校订依据 |
| `edition_passages` | 视图 | `id, poem_id, edition_id, ordinal, kind, body` | 版本的稳定单元 ID 与正文 |
| `review_cautions` | 表 | `poem_id, finding_index, field, body` | 已明确标示的解释分歧 |
| `record_archives` | 表 | `kind, id, codec, payload, sha256, raw_bytes` | 按 `(kind,id)` 定位完整档案；`payload` 为压缩 BLOB |
| `package_info` | 表 | `key, value` | 包级元信息，值为文本 |
| `poems_fts` | FTS5 虚拟表 | `pid, title, author, content`；另有 `rowid` | 仅供搜索；按 `rowid` 关联 `poems`，四个文本列不用于读取结果 |

`record_archives.kind` 支持 `poem`、`author`、`package`，作品与作者使用各自 ID，包级档案含 `source_evidence`、`source_manifest`。`codec` 为 `zlib-json-textrefs-v1`，需要按 [解码规则](../app-runtime/README.md#完整记录和审核档案) 还原；不能把 `payload` 直接当成 JSON 文本。

### 底层去重存储

普通阅读优先使用上述视图。需要了解物理表时，底层结构如下；完整约束与索引见 [建库定义](../scripts/runtime_db.py)。

| 表 | 完整列清单 | 作用 |
|---|---|---|
| `poem_records` | `rowid, id, title, source_title, author_id, dynasty, format, genre, genre_basis, source, body_hash, complete, ai_generated, review_status, text_scope, reference_json, quality_issues_json` | 作品基础字段，`rowid` 为整数主键，`id` 唯一 |
| `text_blocks` | `id, body` | 共享文本，`id` 为整数主键 |
| `poem_text` | `poem_id, kind, ordinal, text_id` | 复合主键为前三列，`text_id` 关联共享文本 |
| `poem_terms` | `poem_id, kind, ordinal, value` | 保存 `themes/collections/levels/tags` 分类与顺序 |
| `author_sections` | `author_id, ordinal, kind` | 作者长文的章节 |
| `author_section_text` | `author_id, section_ordinal, ordinal, text_id` | 章节内各段引用的文本 |
| `poem_units` | `id, edition_id, ordinal, kind, text_id` | 版本单元，`id` 为稳定单元主键 |
| `edition_originals` | `edition_id, ordinal, text_id` | 各版本未经覆盖的原始正文 |

## JSON 文件与实例

`app-data/poems.json` 和 `app-data/authors.json` 顶层都是数组，分别存放作品对象与作者对象，通过 `author_id` ↔ `id` 关联。它们是维护包的 JSON 交付格式，运行包解码完整档案可得到对应完整对象。

### 作品对象的字段分组

| 字段 | JSON 类型 | 内容 |
|---|---|---|
| `id, title, source_title, author, author_id` | string | 身份、题名与作者关联 |
| `dynasty, format, genre, genre_basis, text_scope` | string | 朝代、文体及收录范围 |
| `aliases, collections, themes, levels, tags` | string[] | 别名、选集、题材、学段和原始标签 |
| `source` / `sources, source_ids` | string / string[] | 主要来源、全部来源与来源 ID |
| `content, original_content` | string[] | 主版本显示单元与来源正文 |
| `translate, notes, appreciation` | string[] | 译文、注释、赏析，各自按数组顺序展示 |
| `editions` | object[] | 各版本、主版本标记、异文、原文与稳定单元 |
| `field_sources` | object | 三类注解各自的来源类型、链接、模型、审核与绑定哈希 |
| `alignment` | object | 三类注解各自的展示模式及对齐状态 |
| `body_hash, review_status` | string | 正文校验哈希与审核状态 |
| `complete, ai_generated, has_author_bio` | boolean | 覆盖率标记、生成标记、作者简介可用性 |
| `reference, quality_issues` | array | 参考资料与质量提示，允许空数组 |
| `catalog_review, content_review` | object | 目录决定与完整内容审核记录 |

### 作品 JSON 示例

下面取自真实记录《静夜思》，**仅选取部分字段，所展示字段的值均未截断**。完整对象还包含注释、赏析、版本、来源与详细审核等信息；省略的字段不表示原数据中没有。

```json
{
  "id": "5c22086397880d3b825c95db",
  "title": "静夜思",
  "author": "李白",
  "author_id": "au_李白",
  "dynasty": "唐代",
  "format": "五言绝句",
  "genre": "诗",
  "themes": [
    "月亮",
    "思乡"
  ],
  "levels": [
    "小学古诗"
  ],
  "content": [
    "床前明月光，疑是地上霜。",
    "举头望明月，低头思故乡。"
  ],
  "translate": [
    "明亮的月光洒在床前的窗户纸上，好像地上泛起了一层霜。",
    "我禁不住抬起头来，看那天窗外空中的一轮明月，不由得低头沉思，想起远方的家乡。"
  ],
  "alignment": {
    "translate": {
      "mode": "document",
      "equal_length": true,
      "verified": false,
      "unit_ids": []
    },
    "notes": {
      "mode": "document",
      "equal_length": true,
      "verified": false,
      "unit_ids": []
    },
    "appreciation": {
      "mode": "document",
      "equal_length": false,
      "verified": false,
      "unit_ids": []
    }
  },
  "review_status": "ai_reviewed",
  "complete": true,
  "ai_generated": false
}
```

`alignment.*.mode="document"` 表示整篇展示。即使正文、译文和注释都各有两项，也不能据此认定同下标的内容已经逐句校准。

### 作者 JSON 示例

下面是上述作品对应作者的部分字段，值来自当前 `authors.json`。简介 `lifetime`、头像 `avatar`、长文 `describe` 等仍在完整对象中。

```json
{
  "id": "au_李白",
  "name": "李白",
  "dynasty": "唐代",
  "works": 115,
  "source_works": 1310,
  "bio_status": "available_unreviewed",
  "entity_type": "person"
}
```

作者对象中的 `describe` 是章节数组，每项包含 `type`（章节名称）与 `content`（字符串数组）。简介资料状态 `bio_status` 应按原值处理，不能因为作者有简介便认定已经完成学术审核。

## 自查实际结构

以下 SQL 可在 App 运行库上查看物理表、视图、字段及外键。`table_info` 返回的 `pk` 大于 0 表示主键位置；视图没有数据库主键约束，部分计算列的声明类型为空。

```sql
SELECT type,name,sql FROM sqlite_master
WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'
ORDER BY type,name;

PRAGMA table_info(poem_records);
PRAGMA foreign_key_list(poem_records);
PRAGMA table_info(poems);
```
