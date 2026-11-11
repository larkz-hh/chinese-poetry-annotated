# App 接入指南

[返回项目首页](../README.md) · [运行包表结构与 SQL](../app-runtime/README.md) · [构建维护](maintenance.md)

本项目交付数据库文件和数据说明。App 开发者在自己的项目里编写读取代码，无需把本仓库作为 App 依赖导入。

## 交付与初始化

1. 将 `app-runtime/poems.db` 放入 App 资源目录，`manifest.json` 用于文件校验和内容版本识别。
2. 首次启动将数据库复制到应用私有目录，再以只读方式打开；搜索使用的 SQLite 驱动须支持 FTS5。
3. 通过 SQL 查询作品、译注、作者、分类和版本。收藏、历史、背诵进度保存在 App 自己的用户库中。
4. 更新内容包前关闭旧连接，校验新包后替换内容数据库，保留独立的用户数据。

## 使用 SQLite 或 Room

可以直接使用 SQLite API 查询，也可以由 App 开发者按现有结构编写 Room 的 Entity、DatabaseView、DAO 和 RoomDatabase，再加载预置数据库。`poems` 在运行包中是视图，映射时应区分表和视图。Room 会校验预置库结构，当前仓库未提供经过编译验证的 Room 适配层。

参考：[Room 官方说明](https://developer.android.com/training/data-storage/room) · [预置数据库](https://developer.android.com/training/data-storage/room/prepopulate)。使用 Room 时也应选择支持本库 FTS5 的驱动。

## 数据库格式与版本

| 项目 | App 运行包 | 完整维护包 |
|---|---|---|
| 路径 | `app-runtime/poems.db` | `app-data/poems.db` |
| `PRAGMA user_version` | `1` | `3` |
| `PRAGMA application_id` | `1347372372`，即 `POET` | 不用该标识识别运行包 |
| 常用作品读取 | `poems` 视图、`passages` 等 | `poems` 表及 `metadata_json` |
| 完整作品、作者 JSON | 解码 `record_archives` | 读取对应表的 `metadata_json` |
| FTS 关联作品 | `p.rowid = poems_fts.rowid` | `p.id = poems_fts.pid` |

schema 版本用于识别表结构；manifest 的 `data_version` 用于识别内容包。运行包另用 `source_data_version` 标明其完整维护包来源。应按格式选择读取逻辑，不能仅替换文件后继续读取旧格式的 `metadata_json` 列。

## 阅读与展示

列表、段落读取、组合筛选、作者资料、版本、来源和分歧提示的 SQL 见 [运行包接入说明](../app-runtime/README.md#普通读取)。所有示例中的路径以项目根目录为基准，SQL 参数使用绑定值。

`authors.works` 是当前包实际收录数，`source_works` 是原资料宣称的总数。文体使用 `genre` 区分诗、词、曲、文、赋；`format` 保留来源标注，不宜单独作为文体分类依据。

- `content` 是当前主版本的显示单元，可能是一联、一段、序言或合集中的一首。
- `translate`、`notes`、`appreciation` 当前按**整篇**展示。数组长度相等不代表逐句对应，不能直接把 `content[i]` 与 `translate[i]`、`notes[i]` 配对。运行包读取 `annotation_info.alignment_mode`，完整记录读取 `alignment[field].mode`。
- 通过 `editions.is_primary=1` 选择主版本，不能假设版本数组的第一项始终是主版本。其他版本、异文提示、原始正文与稳定单元 ID 均保留。
- 同名作品用不同 ID 区分；来源 ID、合并前 ID 通过 `id_aliases` 或 `app-data/id_map.json` 解析。收藏和进度应保存作品 ID，更新时先解析映射，不以标题作为唯一标识。

## 搜索与完整档案

搜索覆盖标题及别名、作者、正文，权重分别为 10、5、1。查询按 Unicode 字符归一化分词，保留标点和段落边界；用户输入作为普通文字处理，避免把引号、星号等当成 FTS 运算符。可复用 `scripts/search.py` 与 `data_utils.match_query()`。

运行包使用 contentless FTS，索引不保存一份额外的可读文本。按 `rowid` 关联 `poems` 后读取结果；FTS 自身的文本列返回 NULL。详细 SQL、跨语言查询规则及档案解码见 [运行包接入说明](../app-runtime/README.md)。

完整审核记录没有因运行包优化而删除：`record_archives` 保留每条作品和作者的完整记录，古籍证据摘录保存为 `package/source_evidence`。日常阅读不需要解压这些档案。`raw/` 中独立的模型原始回复、修改决定和前后对照继续保留在项目中。

## 在开发机上试读

下列 Python 工具仅用于开发和核查，不是 App 的运行依赖。需要 Python 3.10+，仅使用标准库；命令在项目根目录执行。

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
