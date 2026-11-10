# 古诗词 App · 出题数据包

给「古诗词 App」这道赛题准备的数据起点。数据源：[yxcs/poems-db](https://github.com/yxcs/poems-db)（古诗文网 2019 年抓取），
已做清洗、分类、索引，并用 AI 补全了缺失的注释与赏析。

```
poems-clean\
├─ app-data\              ← 给新生的起点（直接用这个）
│   ├─ poems.db               SQLite，1470 首 + 359 位作者 + FTS5（11.5 MB）
│   ├─ poems.json             同上，JSON 版（4.5 MB）
│   ├─ categories.json        题材/选集/学段 分类字典
│   ├─ generated.jsonl        AI 补写的原始产出（可追溯/可重跑）
│   ├─ todo_annotations.jsonl 仍缺注解的诗（现在只剩 1 首）
│   └─ stats.json             统计数字
├─ raw\                   ← 需要更大体量时的素材
│   ├─ poems_lite.json        1692 首原始精选（未剔古文）
│   ├─ seed_annotated.json    112 首人工注解样板
│   ├─ poems_all.jsonl.gz     19.2 万首全库（34 MB，进阶挑战用）
│   └─ authors.json           7729 位作者
└─ scripts\
    ├─ build.py               原始 NDJSON → 分层数据
    ├─ build_v2.py            赛题数据包（剔古文/分类/建索引）
    ├─ gen_annotations.py     AI 批量补注释/赏析（断点续跑）
    ├─ merge_annotations.py   把补写结果合并进 db/json
    ├─ gen_long_poem.py       超长诗分段生成（远游 90 句）
    ├─ strip_quoted_original.py 去掉赏析开头重复引用的原文
    ├─ spotcheck.py           抽检脚本
    └─ test_llm.py            接口连通性测试
```

---

## 一、数据现状（已完成补全）

| 赛题要求 | 数据 | 覆盖 |
|---|---|---|
| 列表：标题/作者/朝代/分类 | 1470 首 | ✅ 100% |
| 详情：原文 | 1470 首 | ✅ 100% |
| 详情：**赏析** | 1470 首 | ✅ **100%** |
| 详情：**注释** | 1470 首 | ✅ 100% |
| 详情：**译文** | 1470 首 | ✅ 100% |
| 详情：作者简介 | 1457 / 1470（"佚名"有兜底） | ✅ 99% |
| 筛选：朝代 | 唐代 511、宋代 382、先秦 311… | ✅ |
| 筛选：作者 | 359 位（李白 108、杜甫 48） | ✅ |
| 筛选：分类 | 40 题材 + 11 选集 + 5 学段 | ✅ 已规范化 |
| 搜索：标题/正文 | FTS5，「明月」48 首、「东风」37 首 | ✅ |

> 1470 首全部齐全。《远游》这类 90 句的长诗用 `gen_long_poem.py` 分段生成（并关闭模型思考，否则 token 全被推理吃光、正文为空）。

### 数据来源要标清楚

- 其中 **112 首**的注释/赏析是原始数据里就有的（人工编辑，权威）；
- 另外 **1357 首**是我用 DeepSeek 批量生成的，`poems.db` 里 `ai_generated=1` 标了出来。
- **App 里应该显示「AI 辅助生成」字样**——既诚实，也正好呼应赛题里"合理使用 AI 辅助开发"那条。
- 生成内容我抽检过（每批 3 首人工看），字词注释基本准确，赏析 190~350 字，讲意象/手法/情感，不臆造典故。
  但**不是学术级**，别当成《唐诗鉴赏辞典》引用。

---

## 二、注释/赏析是怎么补的

```bash
# 1) 需要 key：默认读 D:\project\agent\.env 里的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID
# 2) 批量生成（按 id 断点续跑，重复执行不会重复花钱）
python scripts/gen_annotations.py --workers 12
# 3) 合并进 poems.json / poems.db（只填空字段，不覆盖原始人工注解）
python scripts/merge_annotations.py
```

生成规则写死在 `gen_annotations.py` 里：

- `translate`、`notes` 数组长度必须等于正文句数（长诗 > 40 句允许整段处理），**逐句对齐**；
- `appreciation` 1~2 段、200~350 字；
- 校验不通过自动重试 2 次，仍失败就记 error 跳过（下次重跑会自动补）。

实测 1470 首约 40 分钟（12 并发），失败主因是 429 限流，重跑即可。

---

## 三、为什么不能直接用原始仓库

我全量扫过 22 万条，原始数据有几个坑，现在都已处理：

| 坑 | 处理 |
|---|---|
| 22 万条里 16.3 万是从「作者页」抓的、4.9 万从「词牌页」抓的 | 去重合并，保留注解更全的那条 |
| 字段叫 `name` 不叫 `title` | 重命名为 `title` |
| `_id` 是 `{"$oid": "..."}` | 解包成字符串 |
| `type` 是"从哪抓的"不是题材，题材在 `tags` | 拆成 `collections` / `themes` / `levels` |
| 222 条古文（《报任安书》《祭十二郎文》）混在诗里 | 剔除，剩 1470 首纯诗词 |
| 正文带 `<p>` 标签、行首带 `\n` | 清洗 |
| 51 条集合名是双重编码乱码 | 丢弃该字段 |
| 标签 453 个混杂不可用 | 收敛到 40 个题材（出现 ≥8 次） |
| 注释/赏析只有 20% | AI 补全到 99.9%（见上） |

---

## 四、怎么用

### 数据库结构

```sql
poems(id, title, author, author_id, dynasty, format, collection,
      content, translate, notes, appreciation, complete, ai_generated)
themes(poem_id, theme)          -- 题材，一首可多个
authors(id, name, dynasty, lifetime, works, avatar)
author_desc(author_id, kind, body)  -- 生平/轶事典故，长文
poems_fts(pid, title, author, content)  -- FTS5 全文索引
```

`content / translate / notes / appreciation` 都是 `\n` 连接的文本，**行号对齐**
（`content.split("\n")[i]` ↔ `notes.split("\n")[i]`），可以据此做逐句对照。
但**不是严格等长**：1357 首 AI 补写里有 16 首行数不一致（长诗按整段处理），
所以代码必须容错：

```kotlin
val notes = poem.notes.split("\n")
lines.indices.map { i -> notes.getOrNull(i) }   // 别直接用 notes[i]
```

### ⚠️ 全文搜索必须用「短语查询」

中文没有空格，FTS5 默认分词器会把整行当一个词，直接 `MATCH '明月'` 只能查到标题刚好是"明月"的（2 首）。
我在入库时把文本逐字加了空格（`"床 前 明 月 光"`），所以查询也要转换：

```sql
-- 正确：把关键词逐字加空格，包成短语（命中 48 首）
SELECT p.* FROM poems_fts f JOIN poems p ON p.id = f.pid
WHERE poems_fts MATCH '"明 月"';

-- 只搜标题
WHERE poems_fts MATCH 'title:"明 月"';

-- 错误写法（只有 2 首）
WHERE poems_fts MATCH '明月';
```

Kotlin：`val q = "\"" + keyword.toCharArray().joinToString(" ") + "\""`

### 常用查询

```sql
-- 朝代 + 题材 组合筛选
SELECT p.title,p.author FROM poems p JOIN themes t ON t.poem_id=p.id
WHERE p.dynasty='唐代' AND t.theme='思乡';

-- 详情（含作者简介）
SELECT p.*, a.lifetime FROM poems p LEFT JOIN authors a ON a.id=p.author_id
WHERE p.id=?;

-- 分类字典
SELECT theme, count(*) FROM themes GROUP BY theme ORDER BY count(*) DESC;
```

---

## 五、出题时的建议锚点

| 维度 | 观测点 |
|---|---|
| 数据完整 | 1470 首是否都能打开；`ai_generated=1` 的内容有没有标注 |
| 逐句对照 | 是否按行号渲染，而不是把数组拼成一段；行数不等时会不会崩 |
| 搜索 | 「明月」能不能出 48 首；有没有踩 FTS 短语这个坑 |
| 筛选 | 朝代/作者/题材 三者能否组合，结果数与数据包是否一致 |
| 收藏与历史 | 是否真的按登录用户隔离（换账号后数据不串；用 SharedPreferences 全局存一份是典型错误） |
| 性能 | 列表滚动、搜索响应、离线可用 |

**建议把「AI 标注」也写进评分点**：用了 AI 生成内容却不标注的作品，说明作者没想过内容溯源——这正好对应赛题里"合理使用 AI，杜绝许愿式编程"。

---

## 六、授权

诗词原文属公共领域；原始数据里的 `translate / notes / appreciation` 来自古诗文网及其引用书目
（如《唐诗鉴赏辞典》），属他人著作权内容；AI 补写的部分没有这个问题。

校内比赛、课程作业没问题；**公开上架或商用前**，建议把古诗文网来源的内容换掉或改写，
并保留「AI 辅助生成」标注。

