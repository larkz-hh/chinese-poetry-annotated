# -*- coding: utf-8 -*-
"""抽检 AI 补写的内容质量 + 校验数据库。"""
import json
import os
import random
import sqlite3

APP = r"D:\project\poems-clean\app-data"
poems = json.load(open(os.path.join(APP, "poems.json"), encoding="utf-8"))
ai = [p for p in poems if p.get("ai_generated")]
print("AI 补写条数:", len(ai))

# 行数对齐检查
bad = [p for p in ai if len(p["translate"]) not in (len(p["content"]), 1)
       or len(p["notes"]) not in (len(p["content"]), 1)]
print("行数与正文不匹配:", len(bad), "/", len(ai))

random.seed(7)
for p in random.sample(ai, 3):
    print("\n" + "=" * 64)
    print("《%s》 %s（%s）" % (p["title"], p["author"], p["dynasty"]))
    print("正文:", " / ".join(p["content"][:3])[:80])
    print("译文:", p["translate"][0][:60] if p["translate"] else "-")
    print("注释:", (p["notes"][0][:70] if p["notes"] else "-"))
    print("赏析:", p["appreciation"][0][:120] if p["appreciation"] else "-")
    print("  赏析字数:", len("".join(p["appreciation"])))

con = sqlite3.connect(os.path.join(APP, "poems.db"))
cur = con.cursor()
print("\n== 数据库校验 ==")
print("poems:", cur.execute("select count(*) from poems").fetchone()[0])
print("有注释:", cur.execute("select count(*) from poems where notes<>''").fetchone()[0])
print("ai_generated=1:", cur.execute("select count(*) from poems where ai_generated=1").fetchone()[0])
print("complete=1:", cur.execute("select count(*) from poems where complete=1").fetchone()[0])


def q(kw):
    s = '"' + " ".join(kw) + '"'
    return cur.execute("""select count(*) from poems_fts f join poems p on p.id=f.pid
                          where poems_fts match ?""", (s,)).fetchone()[0]


print("检索: 明月", q("明月"), "| 东风", q("东风"), "| 长江", q("长江"))
print("详情联查:", cur.execute("""select p.title,a.name,length(a.lifetime)
                                  from poems p join authors a on a.id=p.author_id
                                  where p.title='静夜思'""").fetchone())
