# App 接入指南

[项目首页](../README.md) · [字段手册](sqlite-schema.md) · [查询示例](../app-runtime/README.md)

本文面向接入现有数据包的 App 开发者，以 `app-runtime/poems.db` 为例。数据库格式为 runtime schema 2。

## 接入准备

| 项目 | 要求 |
|---|---|
| 交付文件 | `app-runtime/poems.db` 及同目录 `manifest.json` |
| 数据访问 | SQLite API，或由 App 配置的 Room 适配层 |
| SQLite 能力 | 启用 FTS5，支持本库全文搜索 |
| 内容库 | 按只读方式使用 |
| 用户数据 | 收藏、历史和背诵进度存放在独立数据库 |

本仓库提供数据文件及格式说明。App 中的数据访问代码由应用开发者实现；Python 脚本属于数据维护工具。

## 初始化与更新

### 1. 放置资源

将 `poems.db` 放入 App 资源目录。保留对应 `manifest.json`，用于文件大小、SHA-256 和内容版本校验。

### 2. 打开数据库

首次启动时，将数据库复制到应用私有目录，再按所选访问方式打开。SQLite API 可直接执行查询；Room 的预置库加载还须通过结构校验，具体要求见下节。

### 3. 读取内容

列表读取 `poems` 视图的必要字段；详情通过 `passages` 读取有序段落，再按需关联作者、分类、版本与审核提示。

| 功能 | 主要读取对象 |
|---|---|
| 列表与基本详情 | `poems` |
| 正文与译注段落 | `passages`、`annotation_info` |
| 作者简介与长文 | `authors`、`author_desc` |
| 分类筛选 | `themes`、`collections`、`levels` |
| 名句卡片 | `famous_lines`、`famous_line_units` |
| 版本选择 | `editions`、`edition_passages` |
| 全文搜索 | `poems_fts` 关联 `poems` |

字段定义见 [SQLite 字段手册](sqlite-schema.md)，可执行示例见 [运行包查询](../app-runtime/README.md#普通读取)。

### 4. 更新内容包

先根据 manifest 校验新文件，关闭旧数据库连接，再替换内容库。用户数据保留在独立数据库中，通过作品稳定 ID 关联。

更新时使用 `id_aliases` 解析旧作品 ID；JSON 接入可使用 `app-data/id_map.json`。作品标题可能重复，不适合作为收藏主键。

## 使用 SQLite 或 Room

| 访问方式 | App 端工作 |
|---|---|
| SQLite API | 打开数据库，以参数绑定方式执行 SQL，并映射查询结果 |
| Room | 编写 Entity、DatabaseView、DAO 和 RoomDatabase，配置预置库加载并验证兼容性 |

运行包中的 `poems`、`passages` 等为视图。Room 映射应区分物理表与视图，并满足预置库结构校验要求。**当前仓库未提供经过编译验证的 Room 适配层**；Room 接入还需在目标 App 中完成适配与验证。

参考：[Room 官方说明](https://developer.android.com/training/data-storage/room) · [预置数据库加载](https://developer.android.com/training/data-storage/room/prepopulate)。两种访问方式均需确认 SQLite 驱动的 FTS5 支持。

## 内容展示约定

| 对象 | 展示或存储规则 |
|---|---|
| 正文 | `content` 按原顺序展示，一个单元可能是一联、一段或合集中的一首 |
| 译文、注释、赏析 | 当前采用 `document` 模式，按整篇展示；数组等长不代表逐句对应 |
| 主版本 | 以 `editions.is_primary=1` 选择，不依赖数组首项 |
| 作者作品数 | `works` 为本包收录数，`source_works` 为来源宣称的总数 |
| 文体 | `genre` 用于诗、词、曲、文、赋分类；`format` 保留来源体裁标注 |
| 稳定标识 | 作品使用 `id`，正文版本和单元使用各自稳定 ID；`rowid` 仅用于包内关联 |

译注展示模式可从 `annotation_info.alignment_mode` 或完整 JSON 的 `alignment[field].mode` 读取。质量与来源标记见 [内容审核与修订](review.md#审核标记)。

`notes` 已整理为可直接展示的注释条目，保留读音与异文说明；无需额外拼接原文，也不与正文逐行配对。格式约定见 [注释格式](notes-format.md)。

## 格式识别

| 标识 | 含义 |
|---|---|
| `PRAGMA user_version` | 表结构版本；运行包为 `2`，完整维护包为 `4` |
| `PRAGMA application_id` | 运行包标识 `1347372372`，对应 ASCII `POET` |
| manifest：`data_version` | 当前内容包版本 |
| manifest：`source_data_version` | 运行包所依据的完整维护包版本 |

运行包与完整维护包应使用各自的查询与档案读取方式，格式对照见 [字段手册](sqlite-schema.md#格式对照)。

名句卡片的 JSON、SQL 与格式升级说明见 [名句接入](famous-lines.md)。

## 开发机验证

以下命令需要 Python 3.10+，仅使用标准库，在仓库根目录执行。

```powershell
# 按标题搜索，含别名
python -X utf8 scripts/search.py 静夜思 --column title --db app-runtime/poems.db

# 搜索标题、作者与正文
python -X utf8 scripts/search.py 明月 --db app-runtime/poems.db

# 读取完整作品档案，也支持旧作品 ID
python -X utf8 scripts/read_runtime_record.py poem 5c26e57597880d3b8265ceec
```

搜索的 `--column` 可选 `title`、`author`、`content`，省略时查询三个字段。省略 `--db` 时，搜索脚本默认使用完整维护库。档案工具支持 `poem`、`author`、`package` 三类记录，默认读取运行库。
