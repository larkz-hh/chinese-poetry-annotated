# 名句与诗词卡片

[项目首页](../README.md) · [字段手册](sqlite-schema.md) · [数据结构](data-format.md)

作品的 `famous_lines` 是名句与代表句对象数组，一项表示一组完整摘录。当前精选库每篇提供 1–3 组，可直接用于诗词卡片。

## 收录范围

当前已覆盖精选库全部 **1524 篇作品、3389 组摘录**，没有空数组。其中 191 篇有 1 组、801 篇有 2 组、532 篇有 3 组。原有《游子吟》等 9 组名句及其 ID 保持不变。该范围为 App 精选库，不包括 `raw/` 的二十余万条全库素材。

已有来源选句继续保留，其余作品由 DeepSeek 从原文候选中选择代表句，并通过逐字、单元位置和重复检查。每篇至少有可展示的代表性摘录，不将全部摘录宣称为公认名句。`source_url` 说明文本来源，不单独证明传播度。

## JSON 格式

以下示例取自当前作品 JSON：

```json
{
  "id": "5c22086597880d3b825c9837",
  "title": "游子吟",
  "author": "孟郊",
  "famous_lines": [
    {
      "id": "5c22086597880d3b825c9837:q1",
      "text": "谁言寸草心，报得三春晖。",
      "unit_ids": [
        "5c22086597880d3b825c9837:v1:u3"
      ],
      "source_url": "https://m.gushiwen.cn/mingju/juv_9361bcf3e14b.aspx"
    }
  ]
}
```

| 字段 | 类型 | 用途 |
|---|---|---|
| `id` | string | 名句稳定 ID，用于收藏、分享和浏览记录 |
| `text` | string | 卡片展示文本，可能为一句或连续多句 |
| `unit_ids` | string[] | 当前主版本内有序、连续的正文单元 ID |
| `source_url` | string | 名句页或正文来源链接 |

`unit_ids` 标记摘录所在的正文单元。名句可覆盖一个单元中的片段，也可跨越连续多个单元，显示时使用 `text`。关联信息用于定位原文，不表示整段内容都应放入卡片。

## SQLite 查询

完整维护包 **schema 4** 与 App 运行包 **runtime schema 2** 均提供相同的两张名句表：

| 表 | 职责 |
|---|---|
| `famous_lines` | 名句文本、所属作品、顺序和来源 |
| `famous_line_units` | 名句到正文单元的有序关联 |

### 读取一篇作品的名句

绑定作品 ID，按 `ordinal` 保留编辑顺序。

```sql
SELECT id, text, source_url
FROM famous_lines
WHERE poem_id = ?
ORDER BY ordinal;
```

### 获取随机卡片

以下查询直接返回名句及作品信息，无需解压完整档案。当前名句池可直接使用此查询；不保证跨次请求无重复，连续浏览可在 App 端维护打乱后的 ID 队列。

```sql
SELECT q.id AS quote_id, q.text, p.id AS poem_id,
       p.title, p.author, p.dynasty
FROM famous_lines q
JOIN poems p ON p.id = q.poem_id
ORDER BY random()
LIMIT 1;
```

### 定位正文

绑定名句 ID，返回有序正文单元。App 运行包可通过 `edition_passages.id` 读取对应文本；完整维护包使用 `poem_units.id`。

```sql
SELECT unit_id
FROM famous_line_units
WHERE quote_id = ?
ORDER BY ordinal;
```

## 维护与验证

选句输入保存于 `raw/famous_lines.json`，每篇绑定当前 `body_hash`。修改时保留已有名句 ID，新增名句分配新 ID；改变顺序使用数组顺序，不重编号已有 ID。

更新选句后，按 [常规重建](maintenance.md#常规重建) 重新发布完整包并导出运行包。当前收录策略要求全库覆盖；任何作品缺少选句或返回空数组时构建均会中止。新增作品也须补充选句后再发布。

发布检查涵盖：名句 ID 与文本去重、来源 URL、正文哈希、当前主版本、单元连续性及文本精确一致性，以及两种 SQLite 表与 JSON 的逐项一致性。

### 增量选句工具

`scripts/complete_famous_lines.py` 可为缺少选句的作品调用已配置模型，选择候选编号，不生成或改写原文。默认读取当前作品 JSON；`--input-poems` 可指定包含新增作品的完整目标集合。已完成输入可续跑，存在重叠或无效候选时会重试；全部成功才编译维护文件。

```powershell
python -X utf8 scripts/complete_famous_lines.py --env-file .env --workers 4 --batch-size 8 --compile
```

该命令需配置模型接口并产生接口用量。原始选择、理由与失败重试记录保存在 `raw/famous_line_selections.jsonl`，最终编辑结果保存在 `raw/famous_lines.json`。本轮对 12 组摘录收窄了展示边界，原模型结果与前后值均保留；作品原文未改动。

覆盖及原字段保持情况见 [名句验收记录](../reports/famous-lines-audit.json)。

## 格式升级

本次由完整库 schema 3 升至 **schema 4**，运行库 runtime schema 1 升至 **runtime schema 2**。原有作品、作者、段落、FTS 和档案接口保留，新增名句表及 JSON 字段。

接入方应更新格式版本判断。使用 Room 预置库时，还需将新增表纳入适配与结构校验；仅替换数据文件不代表已完成 Room 适配。
