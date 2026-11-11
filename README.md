# 古诗词 App 数据源

面向古诗词阅读、检索与背诵应用的离线数据仓库，提供 SQLite 数据库、JSON 文件及数据维护工具。

当前精选数据包含 **1524 条作品、372 条作者记录**，覆盖诗、词、曲、文、赋，包含正文、译文、注释、赏析、作者资料、分类、版本及来源信息。

## 数据包选择

**App 离线接入建议使用运行包 `app-runtime/poems.db`。**

| 数据包 | 用途 | 体积 |
|---|---|---:|
| [App 运行包](app-runtime/poems.db) | 应用内阅读、分类筛选与全文搜索 | 18.7 MiB |
| [完整维护包](app-data/poems.db) | 数据核查、加工与维护 | 38.3 MiB |
| [作品 JSON](app-data/poems.json) / [作者 JSON](app-data/authors.json) | 自定义导入或脚本处理 | 按文件获取 |

两种数据库收录范围一致。运行包采用文本去重与档案压缩，保留完整维护包中的作品、作者及审核资料。两者表结构不同，接入时应采用对应的读取方式。

App 通常只需携带运行包及其 [manifest.json](app-runtime/manifest.json)。体积单位 MiB 为 1024² 字节。

名句卡片数据首批覆盖 **8 篇作品、9 组名句**，未整理作品保留空数组，详见 [名句与卡片接入](docs/famous-lines.md)。

## 接入概览

1. 将运行数据库放入 App 资源目录，首次启动时复制到应用私有目录。
2. 使用 SQLite API 查询；使用 Room 时，由 App 开发者配置实体、视图映射与 DAO。
3. 将诗词库作为只读内容库，收藏、历史和背诵进度保存在独立用户库中。

运行环境的 SQLite 驱动须支持 FTS5。Python 工具用于数据生产与维护，App 接入只需数据库文件和相应读取代码。

完整步骤见 [App 接入指南](docs/integration.md)，查询示例见 [运行包 SQL](app-runtime/README.md)。

## 数据来源与质量

原始素材由 [yxcs/poems-db](https://github.com/yxcs/poems-db) 转储整理，保留古诗文网等来源链接、来源 ID、原始正文及校订依据。

精选包已完成本轮 AI 辅助审核，当前待核清单为空，42 条解释、版本或地望分歧保留明确提示。审核范围限于精选包；`raw/` 中另有 214526 条全库素材，其收录与审核范围另行区分。

审核标记表示已完成相应流程，不构成专家学术审定。后续修订及状态含义见 [内容审核与修订](docs/review.md)。现代译注、作者资料及生成内容的使用依据需分别核实，使用时应保留来源与审核说明。

## 文档导航

| 阅读目的 | 文档 |
|---|---|
| 完成 App 初始化、选择 SQLite 或 Room | [App 接入指南](docs/integration.md) |
| 理解作品结构、查看真实 JSON | [数据结构与 JSON 示例](docs/data-format.md) |
| 读取名句、生成诗词卡片 | [名句与诗词卡片](docs/famous-lines.md) |
| 查询表、视图与字段定义 | [SQLite 字段手册](docs/sqlite-schema.md) |
| 编写列表、详情、筛选与搜索 SQL | [运行包查询与档案读取](app-runtime/README.md) |
| 重建、导出或验证数据包 | [构建与维护](docs/maintenance.md) |
| 理解审核状态、追溯内容修订 | [内容审核与修订](docs/review.md) |

验收结果：[完整包审计](reports/app-data-audit.md) · [运行包验收](reports/app-runtime-audit.md)。

## 仓库目录

```text
app-runtime/  App 运行数据库与清单
app-data/     完整维护数据库与 JSON 文件
docs/         接入、数据结构与维护文档
raw/          来源素材、审核意见与修订决定
scripts/      构建、导出、审核与验证工具
reports/      审计及验收报告
backups/      本机历史快照，不纳入 Git
```
