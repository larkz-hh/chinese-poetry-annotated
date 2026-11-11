# App 运行包：查询与档案读取

[项目首页](../README.md) · [接入指南](../docs/integration.md) · [字段手册](../docs/sqlite-schema.md)

本页面向已完成数据库初始化的开发者，所有 SQL 均适用于 **runtime schema 1**。命令在仓库根目录执行；SQL 中的 `?` 使用参数绑定。

本页内容：[普通读取](#普通读取) · [搜索](#搜索) · [完整记录和审核档案](#完整记录和审核档案) · [数据包更新](#数据包更新)。

## 文件与版本

| 项目 | 值或用途 |
|---|---|
| `poems.db` | 运行数据库，约 18.7 MiB |
| `manifest.json` | 文件大小、SHA-256、版本及记录数 |
| `PRAGMA user_version` | `1` |
| `PRAGMA application_id` | `1347372372`，即 ASCII `POET` |
| `data_version` | 当前运行包版本 |
| `source_data_version` | 对应完整维护包版本 |

运行包通过共享文本与压缩档案保留完整资料。gzip 传输压缩实测约 7.5 MiB，解压后的数据库约 18.7 MiB。体积与无损比对结果见 [验收报告](../reports/app-runtime-audit.md)。

## 普通读取

### 列表与详情

`poems` 为作品阅读视图。列表按需选择字段，参数依次为每页条数、偏移量。

```sql
SELECT id, title, author, dynasty, genre
FROM poems
ORDER BY id
LIMIT ? OFFSET ?;
```

`passages` 提供保留数组顺序的段落。参数为作品 ID、内容种类；`kind` 可选 `content`、`translate`、`notes`、`appreciation`、`original_content`。

```sql
SELECT ordinal, body
FROM passages
WHERE poem_id = ? AND kind = ?
ORDER BY ordinal;
```

译注的来源与展示方式按作品 ID 查询。当前采用 `document` 模式，整篇展示。

```sql
SELECT kind, source_type, review_status, model, source_url, alignment_mode
FROM annotation_info
WHERE poem_id = ?;
```

### 作者资料

两条查询均以作者 ID 为参数。`authors` 提供基本资料，`author_desc` 按章节顺序提供生平、轶事等长文。

```sql
SELECT * FROM authors WHERE id = ?;

SELECT ordinal, kind, body
FROM author_desc
WHERE author_id = ?
ORDER BY ordinal;
```

### 分类筛选

以下查询组合朝代、题材与学段，参数依次为朝代、题材、学段、每页条数、偏移量。选集筛选可按同样方式使用 `collections`。

```sql
SELECT p.id, p.title, p.author
FROM poems p
WHERE p.dynasty = ?
  AND EXISTS (
    SELECT 1 FROM themes t
    WHERE t.poem_id = p.id AND t.theme = ?
  )
  AND EXISTS (
    SELECT 1 FROM levels l
    WHERE l.poem_id = p.id AND l.level = ?
  )
ORDER BY p.id
LIMIT ? OFFSET ?;
```

### 正文版本

通过 `is_primary=1` 选择主版本，并按单元序号读取。参数为作品 ID。

```sql
SELECT u.id, u.ordinal, u.body
FROM editions e
JOIN edition_passages u ON u.edition_id = e.id
WHERE e.poem_id = ? AND e.is_primary = 1
ORDER BY u.ordinal;
```

全部版本包含异文提示与版本来源，同样按作品 ID 查询。

```sql
SELECT * FROM editions WHERE poem_id = ? ORDER BY ordinal;
```

### 旧 ID 与解释分歧

旧作品 ID 通过 `id_aliases` 定位当前作品。

```sql
SELECT p.*
FROM id_aliases a
JOIN poems p ON p.id = a.poem_id
WHERE a.old_id = ?;
```

详情页可按作品 ID 读取已标示的解释分歧。

```sql
SELECT field, body
FROM review_cautions
WHERE poem_id = ?
ORDER BY finding_index;
```

全部来源链接、来源 ID 和别名分别保存在 `poem_sources`、`poem_source_ids`、`poem_aliases`；字段见 [SQLite 手册](../docs/sqlite-schema.md)。

## 搜索

全文搜索使用 FTS5，覆盖标题与别名、作者、正文，权重分别为 10、5、1。

### 查询文本处理

以 `scripts/data_utils.py` 中的 `match_query()` 为参考，将输入按 Unicode 字符归一化分词，保留标点和段落边界，并作为普通文字转义。App 端需复现相同规则。

### 搜索 SQL

参数依次为处理后的 FTS 查询、每页条数、偏移量。

```sql
SELECT p.id, p.title, p.author, p.dynasty, p.genre
FROM poems_fts
JOIN poems p ON p.rowid = poems_fts.rowid
WHERE poems_fts MATCH ?
ORDER BY bm25(poems_fts, 0, 10, 5, 1), p.id
LIMIT ? OFFSET ?;
```

运行包采用 contentless FTS，搜索结果通过 `rowid` 关联 `poems`。FTS 的 `pid`、`title`、`author`、`content` 列返回 NULL，可读文本从作品视图获取。

### 开发机查询

```powershell
python -X utf8 scripts/search.py 明月 --db app-runtime/poems.db
python -X utf8 scripts/search.py 静夜思 --column title --db app-runtime/poems.db
```

## 完整记录和审核档案

日常阅读使用表与视图。需要完整作品、作者 JSON 或详细审核记录时，按 `(kind, id)` 读取 `record_archives`。

| `kind` | `id` | 内容 |
|---|---|---|
| `poem` | 作品 ID | 完整作品记录 |
| `author` | 作者 ID | 完整作者记录 |
| `package` | `source_evidence` | 古籍证据摘录 |
| `package` | `source_manifest` | 来源完整包清单 |

独立的模型原始日志、修订输入及历史前后值继续保留在仓库 `raw/` 中。

### Python 读取

```powershell
python -X utf8 scripts/read_runtime_record.py poem 5c26e57597880d3b8265ceec
python -X utf8 scripts/read_runtime_record.py package source_evidence
```

代码可调用 `runtime_db.connect_readonly()` 与 `runtime_db.read_archive(con, "poem", id)`，参考实现见 [runtime_db.py](../scripts/runtime_db.py)。

### 跨语言解码

`codec` 为 `zlib-json-textrefs-v1`。将 `payload` 以标准 zlib 解压，再按 UTF-8 解析为 JSON 节点树；每个节点采用 `[tag, value]` 结构。

| tag | value | 还原方式 |
|---|---|---|
| `s` | `text_blocks.id` | 查询共享文本，得到字符串 |
| `l` | 节点数组 | 递归解码各项，得到数组 |
| `d` | 对象 | 保留键名，递归解码值 |
| `v` | 数字、布尔或 null | 直接使用该值 |

节点标签与原始内容分开编码，原 JSON 中形状相似的数组或对象按其自身结构还原。Python 参考实现还核对还原 JSON 的字节长度与 SHA-256。

## 数据包更新

由完整维护包导出运行包：

```powershell
python -X utf8 scripts/export_app_runtime.py
```

导出器先核对源包哈希，在临时目录建库并验证完整记录、阅读文本及搜索结果，成功后替换运行包。完整流程及测试命令见 [构建与维护](../docs/maintenance.md)。
