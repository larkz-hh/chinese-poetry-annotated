# 古诗词 App 数据源 · schema v3

从 [yxcs/poems-db](https://github.com/yxcs/poems-db) 的原始转储整理而来，提供可离线使用的 JSON 和 SQLite。当前包含 **1524 条作品记录、372 条作者记录**，每条作品均有译文、注释和赏析。全量 AI 初审及有疑点作品的二审已完成，二审后剩余 565 个疑点也已逐条作出编辑决定。解释分歧另行明示，记录数不代表已经过专家学术校勘的独立作品数。

本次修复保留原有 1470 个作品 ID，以及中间版本全部 1579 个作品 ID 的解析能力。合并的旧 ID 通过 `id_map.json` 或 SQLite 的 `id_aliases` 查找，旧收藏仍能定位。恢复此前丢失的杜甫“迟日江山丽”、李商隐“紫泉宫殿锁烟霞”等同题作品后，又显式核对并合并 55 条同作品异文或排版重复，其他正文版本保存在 `editions` 中。

**App 可使用单独生成的 [app-runtime/poems.db](app-runtime/poems.db)**，约 18.7 MiB，比完整库约 38.2 MiB 小 51.1%。作品、译注、作者长文、版本、来源、旧 ID 和完整记录中的审核资料全部保留；通过文本去重、元数据引用与压缩减少重复存储。完整维护库仍原样保存在 `app-data/`。新库使用 runtime schema 1，阅读 SQL、搜索及完整档案读取方法见 [运行包接入说明](app-runtime/README.md)。

## 文件

```text
app-data/
  poems.db                 SQLite，包含作者、分类、版本、注解和 FTS5
  poems.json               全量作品，含正文与注解来源元数据
  authors.json             当前包关联的作者，ID 与 SQLite 一致
  categories.json          完整题材 / 选集 / 学段字典及计数
  id_map.json              原始/旧记录 ID → 当前作品 ID
  manifest.json            schema/data 版本、文件大小与 SHA-256
  stats.json               实际覆盖率
  repairs.json             已确认污染字段的修复记录
  generated.jsonl          历史生成记录；不会自动调用接口重生成
  todo_annotations.jsonl   仍缺有效注解的待补任务
  todo_content_review.jsonl 内容待查证清单，含作品与具体疑点
  review_cautions.jsonl     已处理但有解释、版本或地望分歧的说明
  source_evidence.json      本轮古籍核对摘录、URL 和摘录哈希
raw/
  poems_all.jsonl.gz        214526 条保守去重后的全库记录
  poems_lite.json           当前精选构建素材
  authors.json              全量作者素材
  cipai.json                来源转储中的词牌名称
  editorial_fixes.json      可复现的修订文本，标为 AI 编辑、未人工审核
  content_review.json       有正文哈希保护的异文合并、文体与作者归属决定
  author_overrides.json     新增作者简介及核查来源
  annotation_additions.jsonl 带正文哈希的补注记录
  content_reviews.jsonl     逐首 AI 初审意见，含误报，不直接作为修改依据
  review_triage.jsonl       AI 二审决定与可续跑的失败记录
  approved_review_edits.json 显式批准的局部修改及依据
  review_resolutions.json   修改前后数组、哈希及疑点处理结果
  final_content_decisions.json 二审后 565 条疑点的逐项决定和精确变更
  source_evidence.json      古籍证据摘录及哈希，构建时校验
  selection.json            固定选取范围，避免重复构建不断扩大数据集
  build-report.json         当前原始库构建统计
reports/
  app-data-audit.json       当前包校验结果与逐条待核清单
  app-data-audit.md         本次修复与剩余工作
  baseline-v2-audit.md      修复前审计，历史记录
backups/pre-v3/             本机迁移前快照，未纳入版本控制
```

旧的 `raw/data-report-v1.json` 是历史统计，当前数字以 `stats.json`、`build-report.json` 为准。

## 质量状态与展示约定

| 项目 | 当前情况 |
|---|---:|
| 正文 | 1524 条 |
| 有译文 / 注释 / 赏析 | 各 1524 条 |
| 三类注解齐全 | 1524 条 |
| 至少缺一类注解 | 0 条 |
| 作者简介待补 | 0 条 |
| 文体待分类 | 0 条 |
| AI 初审覆盖 | 1524 条 |
| AI 二审覆盖 | 805 条；初审有疑点的作品全部覆盖 |
| 二审待跑 | 0 条 |
| 二审后疑点编辑处理 | 385 条作品、565 个疑点，已全部处理 |
| 内容待核 | 0 |
| 已明示解释分歧 | 42 条 |
| 古籍校订正文 | 3 条作品，原版本保留 |

`complete` 只表示三个注解字段都有通过基础污染检查的文本。`review_status="ai_reviewed"` 表示 AI 审核后没有尚未处理的疑点；`editorially_reviewed` 表示 Codex 对本轮剩余疑点逐条作出编辑决定；`needs_source_check` 表示仍待处理。**这些状态均不表示专家审定**，`content_review.academic_review_complete` 当前始终为 false。`content_review.final_review.scope="flagged_passages_after_second_review"` 明确本轮处理范围。App 可展示其中的 `cautions`，也可读取独立的 `review_cautions.jsonl`。

已新增 55 条完整补注、11 位真实作者的有来源简介；原清单中的“乐府诗集”实为书名，其《敕勒歌》已归为佚名。早期 260 处显式修订与 28 处单字数组无损合并继续保留。本轮处理剩余疑点时，校正文字、译义和人物错置，保留有古注依据的读法，删除未经核实且非必要的背景细节，难定之处明确列出分歧。原始值、证据与处理理由均可回查；疑点并不都是真错误。

正文 `content` 是主版本的显示单元数组，单元可能是一联、一段或序言。`editions` 保留其他版本、原始内容与异文提示，`original_content` 保留来源正文。不同版本不会再串成一首展示。

《田家词》《风流子·黄钟商芍药》《除夜自石湖归苕溪十首》新增据古籍校订的主版本；最后一组补回原记录遗漏的第一首并订正旧题“除放”。旧正文、原版本 ID 和单元 ID 都保留。请按 `is_primary` 选择版本，不能假设 `editions[0]` 永远是主版本；详情页直接使用 `content`。注解来源元数据的 `previous_body_hash` 记录校订前绑定，避免把原生成记录冒充成针对新正文生成的内容。

**未经语义核对的译文、注释、赏析均使用 `alignment[field].mode="document"`，按整篇展示。** 不要把 `content[i]` 与 `translate[i]`、`notes[i]` 默认绑定；`equal_length=true` 也不代表语义对齐。当前没有声称已验证的逐句映射，后续可人工核对单元 ID 再开放逐句模式。

每个 `field_sources[field]` 都有来源类型、审核状态与正文哈希。类型包括 `original`、`ai`、`ai_editorial`、`legacy_unverified`、`missing`。历史生成记录没有时间戳或正文哈希时，不补造这些信息，使用 `generation_binding="legacy_record_id"` 标识。模型内容应显示“AI 辅助生成”，其他未核对内容也应保留来源和待审核状态。

文体 `genre` 包括诗、词、曲、文、赋、未分类，`genre_basis` 记录分类依据；规则分类仍须审核。原 `format` 保留，不能只依赖它判断文体。古文保留在包内并分为“文”，不再把整个包描述为“纯诗词”。`author.entity_type="collection"` 表示来源把书名写在作者位置，不能把它当成已核实的人名。

## 在 App 中使用

SQLite 当前 `PRAGMA user_version=3`，作为只读内容包使用；收藏、历史与背诵进度存放在 App 自己的用户数据库。发布或替换内容包时关闭旧连接。目标运行环境需要支持 FTS5，可选择 JSON 作为另一种接入方式。

主要表：

```text
poems          列表、详情字段与 metadata_json（完整作品 JSON）
authors        作者与 metadata_json（完整作者 JSON）
author_desc    生平/轶事等原始长文
themes         poem_id, theme
collections    poem_id, collection
levels         poem_id, level
editions       正文版本，metadata_json 含原始段落与异文
poem_units     版本内的显示单元及稳定 ID
annotations    poem_id, kind, body_json, mode, source_type, review_status, metadata_json
id_aliases     old_id, poem_id
poems_fts      pid, title, author, content
```

关系表声明了外键，构建与发布校验执行 `foreign_key_check`。App 自己创建可写连接时也应启用 `PRAGMA foreign_keys=ON`。旧的文本列继续保留以兼容简单读取；数组与来源信息应读取 `metadata_json` 或 JSON 文件。

```sql
-- 旧 ID / 原始 ID 定位，当前 ID 也有自映射
SELECT p.* FROM id_aliases i JOIN poems p ON p.id=i.poem_id WHERE i.old_id=?;

-- 朝代、题材、学段组合筛选；使用 EXISTS 避免关系 JOIN 导致重复
SELECT p.id,p.title,p.author FROM poems p
WHERE p.dynasty=?
  AND EXISTS(SELECT 1 FROM themes t WHERE t.poem_id=p.id AND t.theme=?)
  AND EXISTS(SELECT 1 FROM levels l WHERE l.poem_id=p.id AND l.level=?)
ORDER BY p.id LIMIT ? OFFSET ?;

-- 详情与作者
SELECT p.metadata_json,a.metadata_json AS author_json
FROM poems p JOIN authors a ON a.id=p.author_id WHERE p.id=?;
```

`authors.works` 表示当前包实际收录数，`source_works` 保留来源宣称的总作品数。诗作朝代与作者的历史朝代标注可能有不同口径，作者 `metadata_json.dynasties` 列出当前包关联作品涉及的朝代，不视为已完成的历史考证。

## 搜索

提供 `scripts/search.py` 和 `data_utils.match_query()`。标题（含别名）、作者、正文按字符索引；标点和段落之间保留边界，避免“则明，月出”被当作连续的“明月”。查询做 NFC 归一化和大小写转换，把用户输入作为普通文字处理，双引号、星号等不作为 FTS 操作符执行。空字符串或全标点返回空结果。

```powershell
python -X utf8 scripts/search.py 静夜思 --column title
python -X utf8 scripts/search.py 明月
```

```python
# scripts 在模块路径中时
from search import search
rows = search("app-data/poems.db", "明月", limit=20, offset=0)
```

其他语言应实现同一套规则：逐 Unicode 码点处理字母/数字字符，标点空白转为 `zzpoemboundaryzz`，合并连续边界；查询去掉末尾边界，包成 FTS 短语，再通过 SQL 参数绑定。按标题 10、作者 5、正文 1 的权重排序。索引只由构建流程写入；需要修改正文时重建数据包。

## 构建与验证

只依赖 Python 3.10+ 标准库，原始转储默认位于相邻目录 `../poems-db`。

```powershell
# 在临时目录重建 raw 和 app-data，校验通过后替换交付文件；不调用模型
python -X utf8 scripts/rebuild.py

# 指定原始库或只检查临时结果
python -X utf8 scripts/rebuild.py --source-dir D:/project/poems-db --check-only

# 复用 raw，重新合并现有生成记录，并刷新所有关联表、索引和清单
python -X utf8 scripts/merge_annotations.py

# 只读校验当前包
python -X utf8 scripts/audit_data.py

# 回归测试
python -X utf8 -m unittest discover -s scripts -p test_data_pipeline.py -v
```

构建保留同题不同文；同作者且来源 URL 相同，或同作者/朝代且主版本正文规范化后相同的记录可合并，并保留别名、来源 ID、标签和其他版本。其他合并必须列入 `raw/content_review.json`，正文哈希不符时拒绝应用。内容修改必须列入 `approved_review_edits.json` 或 `final_content_decisions.json`，不会自动采纳审核模型的替换提议；`review_resolutions.json` 同时核验修改前后哈希。正文校订必须给出来源，保留旧版，并重新绑定经过核对的译注。

临时包通过校验后才替换文件。替换是逐文件进行的，构建期间不要让 App/服务读取该目录；分发时把完整数据包作为一个版本交付，并通过 `manifest.json` 验证文件。初次迁移自动保存本机快照，快照不随 `.gitignore` 纳入版本控制；可按需另行归档。

## 补注与审核续跑

普通构建和合并不调用外部接口。补注、初审及二审使用已配置的 DeepSeek 模型；现在没有缺注解或未完成二审的任务。以下入口可用于未来增量数据或失败重试。配置环境变量 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL_ID`，或通过 `--env-file` 指定本机配置；不要提交密钥。

```powershell
# 仅有新缺失项时补注；生成与审核输出均可续跑
python -X utf8 scripts/complete_annotations.py --env-file .env --workers 2
python -X utf8 scripts/review_content.py --env-file .env --workers 2
python -X utf8 scripts/resolve_content_reviews.py --env-file .env --workers 2

# 阅读意见并显式编辑 approved_review_edits.json 后，离线编译修订并发布
python -X utf8 scripts/prepare_review_resolutions.py
python -X utf8 scripts/merge_annotations.py
```

生成记录包含正文哈希、时间、模型与提示词版本；不匹配当前正文哈希的记录不会自动合并。审核续跑会从已提交的修改前数组恢复相同审核输入，避免重复请求已完成的条目；输入发生其他变化时拒绝使用旧审核。补充修订只接受显式记录的上一版输出，同段多处相同字样还需指定出现次数，不能随意全局替换。遇到 HTTP 402 会停止后续请求。AI 初审无疑点、二审通过均不等同于逐句对齐或学术审核。

## 来源与审核边界

源数据抓取自古诗文网，发布记录保留来源 URL、来源 ID 和原始内容。原始译注、作者资料及生成内容的具体使用依据需要分别记录与核实；本项目不把“抓取内容”或“AI 内容”当作已确认授权的标记。

当前 `app-data/todo_content_review.jsonl` 为空，本轮列出的疑点已全部处理。解释分歧见 `app-data/review_cautions.jsonl`，每项处理及校订前值见 `raw/final_content_decisions.json`、`raw/review_resolutions.json`；细分结果与验证见 `reports/app-data-audit.md`。本次完成的是有限范围内的 AI 辅助编辑审核，不等同于全库逐字专家校勘。拼音、多音字校读、朗读、教材目录和背诵资源可在此契约上继续增加。
