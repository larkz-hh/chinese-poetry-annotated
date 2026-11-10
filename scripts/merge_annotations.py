# -*- coding: utf-8 -*-
"""把 generated.jsonl 合并进 poems.json / poems.db，并刷新统计与待补清单。

规则：
  · 只补空字段，不覆盖原始数据里已有的注释/赏析（那部分是人工编辑过的权威内容）
  · AI 生成的内容打 ai_generated=1，App 里可以据此标注「AI 辅助生成」
"""
import json
import os
import sqlite3
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "app-data")


def main():
    gen = {}
    path = os.path.join(APP, "generated.jsonl")
    if not os.path.exists(path):
        raise SystemExit("没有 generated.jsonl，先跑 gen_annotations.py")
    bad = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if "error" in r:
            bad += 1
            continue
        gen[r["id"]] = r
    print("已生成 %d 首（失败记录 %d 条）" % (len(gen), bad))

    poems = json.load(open(os.path.join(APP, "poems.json"), encoding="utf-8"))
    filled = Counter()
    for p in poems:
        g = gen.get(p["id"])
        p.setdefault("ai_generated", False)
        if not g:
            continue
        touched = False
        for k in ("translate", "notes", "appreciation"):
            if not p[k] and g.get(k):
                p[k] = g[k]
                filled[k] += 1
                touched = True
        if touched:
            p["ai_generated"] = True
        p["complete"] = bool(p["notes"] and p["translate"] and p["appreciation"])

    json.dump(poems, open(os.path.join(APP, "poems.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---- SQLite ----
    db = os.path.join(APP, "poems.db")
    con = sqlite3.connect(db)
    cur = con.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(poems)")]
    if "ai_generated" not in cols:
        cur.execute("ALTER TABLE poems ADD COLUMN ai_generated INTEGER NOT NULL DEFAULT 0")
    for p in poems:
        cur.execute("""UPDATE poems SET translate=?, notes=?, appreciation=?,
                       complete=?, ai_generated=? WHERE id=?""",
                    ("\n".join(p["translate"]), "\n".join(p["notes"]),
                     "\n".join(p["appreciation"]), 1 if p["complete"] else 0,
                     1 if p.get("ai_generated") else 0, p["id"]))
    con.commit()

    n = len(poems)
    stats = {
        "诗词总数": n,
        "有原文": n,
        "有译文": sum(1 for p in poems if p["translate"]),
        "有注释": sum(1 for p in poems if p["notes"]),
        "有赏析": sum(1 for p in poems if p["appreciation"]),
        "三样齐全": sum(1 for p in poems if p["complete"]),
        "AI 补全过": sum(1 for p in poems if p.get("ai_generated")),
        "仍缺任一项": sum(1 for p in poems if not (p["notes"] and p["translate"] and p["appreciation"])),
    }
    json.dump(stats, open(os.path.join(APP, "stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---- 剩余待补清单 ----
    todo = [p for p in poems if not (p["notes"] and p["translate"] and p["appreciation"])]
    with open(os.path.join(APP, "todo_annotations.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for p in todo:
            f.write(json.dumps({
                "id": p["id"], "title": p["title"], "author": p["author"],
                "dynasty": p["dynasty"], "content": p["content"],
                "missing": [k for k in ("translate", "notes", "appreciation") if not p[k]],
            }, ensure_ascii=False) + "\n")

    con.close()
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print("本次补写：", dict(filled))


if __name__ == "__main__":
    main()

