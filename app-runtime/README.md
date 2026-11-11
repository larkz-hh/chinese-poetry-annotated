# App 用 SQLite 数据包

本目录是单独生成的 App 数据包，完整维护库仍在 `app-data/`。当前数据库约 **18.7 MiB**，相比完整库约 **38.2 MiB** 减少 **51.1%**。gzip 实测约 **7.5 MiB**，这是传输压缩尺寸，解压后仍占 18.7 MiB。

没有删减作品、译注、作者长文、异文、来源或完整版已有的审核资料。常用内容以普通 SQLite 表、视图提供；重复文本集中存放，完整记录通过文本引用和 zlib 压缩保存。构建时逐条还原并与完整版比较，不用内容截断换取体积。

## 文件及版本

- `poems.db`：App 所用数据库；无须同时打包完整库或 `poems.json`。
- `manifest.json`：文件大小、SHA-256、数据来源版本和记录数。
- `PRAGMA application_id` 为 `1347372372`（ASCII `POET`），`PRAGMA user_version=1`。
- 本格式是 **runtime schema 1**，与完整维护库的 schema 3 区别使用。不能把旧代码读取 `metadata_json` 的方式直接套到新库。
- `source_data_version` 标识所用完整数据版本，`data_version` 标识本运行包。运行时按只读方式打开，收藏、进度等放 App 自己的用户库。

## 普通读取

`poems` 是阅读视图，提供标题、作者、朝代、文体、正文、译文、注释、赏析、审核状态等。列表只选择需要的字段即可。

```sql
-- 列表
SELECT id,title,author,dynasty,genre FROM poems ORDER BY id LIMIT ? OFFSET ?;

-- 旧 ID 定位
SELECT p.* FROM id_aliases a JOIN poems p ON p.id=a.poem_id WHERE a.old_id=?;

-- 按段落读取；kind 可为 content / translate / notes / appreciation / original_content
SELECT ordinal,body FROM passages WHERE poem_id=? AND kind=? ORDER BY ordinal;

-- 注解来源与展示模式
SELECT kind,source_type,review_status,model,source_url,alignment_mode
FROM annotation_info WHERE poem_id=?;

-- 当前正文版本及其稳定单元 ID
SELECT u.id,u.ordinal,u.body
FROM editions e JOIN edition_passages u ON u.edition_id=e.id
WHERE e.poem_id=? AND e.is_primary=1 ORDER BY u.ordinal;

-- 全部版本、异文提示及版本来源
SELECT * FROM editions WHERE poem_id=? ORDER BY ordinal;

-- 作者简介及长文：生平、轶事等均保留
SELECT * FROM authors WHERE id=?;
SELECT ordinal,kind,body FROM author_desc WHERE author_id=? ORDER BY ordinal;

-- 阅读时可显示的解释分歧
SELECT field,body FROM review_cautions WHERE poem_id=? ORDER BY finding_index;

-- 分类组合查询
SELECT p.id,p.title FROM poems p WHERE p.dynasty=?
AND EXISTS(SELECT 1 FROM themes t WHERE t.poem_id=p.id AND t.theme=?);
```

`passages` 的段落序号保留原数组顺序，但不表示译注与正文逐行对应。使用 `annotation_info.alignment_mode`，当前按整篇展示。`poem_sources`、`poem_source_ids`、`poem_aliases` 分别保留作品的全部来源 URL、来源 ID 和别名；`poem_terms` 保留原始标签以及题材、选集、学段的分类与顺序。

## 搜索

使用 FTS5，标题含别名，支持作者和正文。与完整库相同，查询按 Unicode 字符分词、保留标点边界，不能把用户输入直接当 FTS 语法。

```powershell
python -X utf8 scripts/search.py 明月 --db app-runtime/poems.db
python -X utf8 scripts/search.py 静夜思 --column title --db app-runtime/poems.db
```

```sql
-- ? 绑定 data_utils.match_query() 生成的查询；权重为标题 10、作者 5、正文 1
SELECT p.id,p.title,p.author,p.dynasty,p.genre
FROM poems_fts JOIN poems p ON p.rowid=poems_fts.rowid
WHERE poems_fts MATCH ?
ORDER BY bm25(poems_fts,0,10,5,1),p.id LIMIT ? OFFSET ?;
```

本库使用不保存文本副本的 contentless FTS，**通过 rowid 关联作品**。FTS 自己的 `pid/title/author/content` 列返回 NULL，标题和正文从 `poems` 视图读取。目标 SQLite 需启用 FTS5。

## 完整记录和审核档案

所有作品、作者的完整 JSON 字段均在 `record_archives` 中无损保留，包括完整审核决定、理由、历史来源元数据、校订哈希等。古籍证据摘录作为 `package/source_evidence` 保存。维护库 `raw/` 中独立的模型原始日志继续保留在项目中。

```powershell
# 从项目根目录读取完整作品记录，也接受旧作品 ID
python -X utf8 scripts/read_runtime_record.py poem 5c26e57597880d3b8265ceec

# 核查古籍证据摘录
python -X utf8 scripts/read_runtime_record.py package source_evidence
```

Python 可调用 `runtime_db.connect_readonly()` 和 `runtime_db.read_archive(con, "poem", id)`。普通阅读不需要解压完整档案。

跨语言解码规则：`payload` 使用标准 zlib 解压为 UTF-8 JSON 树。每个节点是 `[tag,value]`：`s` 代表字符串，value 是 `text_blocks.id`；`l` 代表数组节点列表；`d` 代表对象，键名保留、值递归解码；`v` 代表数字、布尔值或 null。解码器对各类型分别处理，不会把原数据中相似形状的数组、字典误作引用。Python 参考实现还校验还原后的 JSON 长度与 SHA-256。

## 重新生成

```powershell
# 先更新完整维护库，再单独生成此包；不调用模型、不改 app-data
python -X utf8 scripts/export_app_runtime.py

# 包含原管线测试和新运行包测试
python -X utf8 -m unittest discover -s scripts -p "test_*.py" -v
```

导出器先校验完整包的文件哈希，在临时目录创建运行包，逐项比对所有记录与段落，再替换此目录内的数据库。输出禁止位于源包内部，也不覆盖无运行包标识的数据库。复生成结果可重现，检查结果见 `reports/app-runtime-audit.json`。
