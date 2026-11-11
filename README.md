# 古诗词 App 数据源

面向古诗词阅读、检索和背诵 App 的离线数据仓库，提供 SQLite、JSON 数据及构建维护工具。

当前精选包包含 **1524 条作品、372 条作者记录**，覆盖诗、词、曲、文、赋；每条作品均有译文、注释和赏析，并保留作者资料、分类、正文版本、来源及审核信息。

## 数据包选择

| 数据包 | 适合用途 | 大小 / 格式 |
|---|---|---|
| [app-runtime/poems.db](app-runtime/poems.db) | **App 离线阅读、筛选和搜索，优先选用** | 约 18.7 MiB，runtime schema 1 |
| [app-data/poems.db](app-data/poems.db) | 完整数据维护、核查和导入 | 约 38.2 MiB，schema 3 |
| [app-data/poems.json](app-data/poems.json) | 脚本处理或 JSON 接入 | 完整作品记录；作者资料见 [authors.json](app-data/authors.json) |

两种数据库来自同一份精选数据，**内容无损保留，表结构不同**。运行包通过文本去重、引用和压缩减少重复存储，详细审核档案仍可完整读取。App 通常只需携带运行库和同目录的 [manifest.json](app-runtime/manifest.json)，无须重复打包其他格式。

`raw/` 中另有 214526 条全库素材，供构建维护使用，不等同于精选包的内容和审核范围。体积单位 MiB 为 1024² 字节。

## 如何接入

1. 获取 `app-runtime/poems.db`，放入 App 资源目录，首次启动复制到应用私有目录。
2. 使用 SQLite API，或在 App 中编写 Room 实体、视图映射和 DAO，按表结构查询；SQLite 驱动需支持 FTS5。
3. 诗词库按只读内容库使用，收藏、阅读历史和背诵进度由 App 另建用户库保存。

**无需把整个仓库导入 App。** Python 脚本用于生产和维护数据，不是 App 的运行依赖。

```sql
-- 列表查询示例，针对 App 运行包
SELECT id,title,author,dynasty,genre FROM poems ORDER BY id LIMIT 20;
```

完整接入步骤、格式差异和展示约定见 [App 接入指南](docs/integration.md)；表结构、SQL、搜索与审核档案解码见 [运行包说明](app-runtime/README.md)。

## 项目目录

```text
app-runtime/  App 交付包
app-data/     完整维护包及 JSON 数据
raw/          构建素材、审核意见和显式修订决定
scripts/      构建、导出、搜索、审核和测试工具
docs/         接入、维护和审核专题文档
reports/      审计与验收报告
backups/      本机历史快照，不纳入 Git
```

## 数据来源与质量

原始素材从 [yxcs/poems-db](https://github.com/yxcs/poems-db) 转储整理而来，保留了古诗文网等来源链接，以及来源 ID、原始正文和校订依据。

精选包已完成本轮 AI 辅助审核，原审核待核清单为空；42 条解释、版本或地望分歧已明确标注。后续抽查新增的质量问题及审核范围见 [审核说明](docs/review.md)，审核状态不代表专家学术校勘完成。

古代作品原文、现代译注、作者资料和生成内容的使用依据应分别核实；使用和更新时应保留对应来源与审核说明。

## 更多文档

- [App 接入指南](docs/integration.md)：SQLite / Room 接入、格式版本、展示与稳定 ID。
- [数据格式与 JSON 示例](docs/data-format.md)：表与视图、字段类型、关联关系和真实记录实例。
- [运行包说明](app-runtime/README.md)：表结构、查询 SQL、全文搜索、完整档案读取。
- [构建与维护](docs/maintenance.md)：目录职责、重建、导出、验证和工具入口。
- [内容审核与修订](docs/review.md)：质量状态、修订记录、补注及模型接口配置。
- [完整包审计](reports/app-data-audit.md) · [运行包验收](reports/app-runtime-audit.md)。
