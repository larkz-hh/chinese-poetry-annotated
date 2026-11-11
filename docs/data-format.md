# 数据结构与 JSON 示例

[项目首页](../README.md) · [接入指南](integration.md) · [SQLite 字段手册](sqlite-schema.md)

本文介绍作品、作者及其关联方式，并提供真实 JSON 示例。SQL 表与视图的完整字段定义见 [字段手册](sqlite-schema.md)。

## 数据组织

以作品为核心，关联作者、分类、正文版本和审核资料。作品正文与译注均保留有序显示单元。

| 数据对象 | 内容 | 关联标识 |
|---|---|---|
| 作品 | 题名、朝代、文体、正文与译注 | `id` |
| 作者 | 简介、生平及其他长文 | 作品的 `author_id` → 作者的 `id` |
| 分类 | 题材、选集、学段与原始标签 | 作品 ID |
| 版本 | 主版本、其他版本、异文与原始正文 | 作品 ID、版本 ID |
| 正文单元 | 版本内的一联、一段或一首 | 版本 ID、单元 ID |
| 名句 | 适合卡片展示的独立摘录，可有多组 | 作品 ID、名句 ID、正文单元 ID |
| 审核资料 | 来源、生成标记、处理决定与分歧提示 | 作品 ID、注解种类 |

## SQLite 与 JSON 的表示差异

| 内容 | SQLite 运行包 | JSON 文件 |
|---|---|---|
| 作品基本信息 | `poems` 视图 | 作品对象的直接字段 |
| 正文与译注 | `passages` 中的有序行 | `content`、`translate` 等字符串数组 |
| 作者资料 | `authors`、`author_desc` | 独立作者对象 |
| 版本与单元 | `editions`、`edition_passages` | `editions` 对象数组 |
| 完整记录 | 解码 `record_archives` | 作品或作者完整对象 |

`poems.content` 等 SQL 视图字段是换行拼接的字符串。精确读取段落边界应使用 `passages`；JSON 则直接保留数组。译注按整篇展示，数组下标不表示经过验证的逐句对应关系。

名句使用 `famous_lines` 对象数组，格式与查询见 [名句与诗词卡片](famous-lines.md)。

注释使用可直接展示的词义、读音、异文或说明条目，规则与真实示例见 [注释格式](notes-format.md)。

## JSON 文件

| 文件 | 顶层类型 | 每项内容 |
|---|---|---|
| [poems.json](../app-data/poems.json) | array | 一条作品对象 |
| [authors.json](../app-data/authors.json) | array | 一条作者对象 |

两个文件通过 `author_id` 与 `id` 关联。运行包中的完整档案解码后可获得相应对象。

### 作品示例

以下选取《静夜思》的部分字段，所有展示值均保持原样。注释、赏析、版本、来源与详细审核记录保留在完整对象中。

```json
{
  "id": "5c22086397880d3b825c95db",
  "title": "静夜思",
  "author": "李白",
  "author_id": "au_李白",
  "dynasty": "唐代",
  "format": "五言绝句",
  "genre": "诗",
  "themes": ["月亮", "思乡"],
  "levels": ["小学古诗"],
  "content": [
    "床前明月光，疑是地上霜。",
    "举头望明月，低头思故乡。"
  ],
  "translate": [
    "明亮的月光洒在床前的窗户纸上，好像地上泛起了一层霜。",
    "我禁不住抬起头来，看那天窗外空中的一轮明月，不由得低头沉思，想起远方的家乡。"
  ],
  "review_status": "ai_reviewed",
  "complete": true,
  "ai_generated": false
}
```

### 作者示例

以下为对应作者的部分字段。完整作者对象还包含简介 `lifetime`、头像 `avatar`、长文章节 `describe` 及来源资料。

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

`works` 为本包实际收录数，`source_works` 为来源宣称的总数。`describe` 是章节数组，每项含 `type`（章节名称）和 `content`（字符串数组）。

### 译注对齐信息

下面是同一作品的完整 `alignment` 字段。当前三类注解均采用 `document` 模式，即整篇展示。

```json
{
  "alignment": {
    "translate": {
      "mode": "document",
      "equal_length": true,
      "verified": false,
      "unit_ids": []
    },
    "notes": {
      "mode": "document",
      "equal_length": false,
      "verified": false,
      "unit_ids": []
    },
    "appreciation": {
      "mode": "document",
      "equal_length": false,
      "verified": false,
      "unit_ids": []
    }
  }
}
```

`equal_length` 仅记录数组长度是否相等；逐句对应关系由 `verified` 与 `unit_ids` 表示。应用应依据 `mode` 组织展示。

## 作品字段索引

下表按用途分组。`string[]` 表示字符串数组，`object[]` 表示对象数组。

| 用途 | 字段 | JSON 类型 |
|---|---|---|
| 身份与关联 | `id`、`author_id` | string |
| 题名与作者 | `title`、`source_title`、`author` | string |
| 朝代与文体 | `dynasty`、`format`、`genre`、`genre_basis` | string |
| 收录范围 | `text_scope` | string |
| 别名与分类 | `aliases`、`collections`、`themes`、`levels`、`tags` | string[] |
| 来源链接 | `source` | string |
| 来源集合 | `sources`、`source_ids` | string[] |
| 正文 | `content`、`original_content` | string[] |
| 译注 | `translate`、`notes`、`appreciation` | string[] |
| 版本 | `editions` | object[] |
| 名句卡片 | `famous_lines` | object[] |
| 字段来源 | `field_sources` | object |
| 展示与对齐 | `alignment` | object |
| 校验与审核 | `body_hash`、`review_status` | string |
| 内容标记 | `complete`、`ai_generated`、`has_author_bio` | boolean |
| 参考与问题 | `reference`、`quality_issues` | array |
| 目录与审核决定 | `catalog_review`、`content_review` | object |

审核标记的含义见 [内容审核与修订](review.md#审核标记)。SQLite 中的同名字段可能采用不同表示方式，具体以 [字段手册](sqlite-schema.md) 为准。
