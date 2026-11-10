# -*- coding: utf-8 -*-
"""复核审计报告里的几个关键结论。"""
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict

SRC = r"D:\project\poems-db"
APP = r"D:\project\poems-clean\app-data"
DROP = "，。！？、；：“”‘’（）《》〈〉【】…—·,.!?;:\"'()[]<>/\\|`~@#$%^&*+=_- \t\n\r　"
T = str.maketrans("", "", DROP)

poems = json.load(open(os.path.join(APP, "poems.json"), encoding="utf-8"))
by_key = {(p["title"], p["author"]): p for p in poems}

print("== 1. 同名作者同题、正文不同的作品（抽样）==")
# 原库里同 (name, author) 有多种正文的组数
groups = defaultdict(set)
for fn in ("poems1.json", "poems2.json", "poems3.json", "poems4.json"):
    with open(os.path.join(SRC, fn), encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            nm = (r.get("name") or "").strip()
            au = (r.get("author") or "").strip()
            c = "".join(x.strip() for x in (r.get("content") or []) if isinstance(x, str))
            if nm and au and c:
                groups[(nm, au)].add(re.sub(r"\s+", "", c))
multi = [k for k, v in groups.items() if len(v) > 1]
print("原库同题同作者但正文不同的组数:", len(multi))
for t, a in [("绝句", "杜甫"), ("隋宫", "李商隐")]:
    vs = groups.get((t, a), set())
    print("  《%s》%s 原库正文版本 %d 个；当前包保留: %r"
          % (t, a, len(vs), (by_key.get((t, a)) or {}).get("content", ["<无>"])[0][:24]))

print("\n== 2. 注解字段与正文完全相同 ==")
same = []
for p in poems:
    c = "".join(p["content"]).translate(T)
    for k in ("translate", "notes", "appreciation"):
        v = "".join(p[k]).translate(T)
        if v and v == c:
            same.append((p["title"], k))
print("条数:", len(same))
for x in same[:10]:
    print("   ", x)

print("\n== 3. 乱码字符 ==")
bad = [(p["title"], k) for p in poems for k in ("translate", "notes", "appreciation")
       if "\ufffd" in "".join(p[k])]
print("含 U+FFFD 的:", bad)

print("\n== 4. 古文残留 ==")
gw = [p["title"] for p in poems if p["title"] in
      ("论语十二章", "三峡", "廉颇蔺相如列传(节选)", "核舟记", "卖油翁", "陋室铭", "爱莲说")]
print("仍在包里:", gw)

print("\n== 5. 题材丢失 ==")
print("无题材的诗:", sum(1 for p in poems if not p["themes"]))
print("题材总数:", len({t for p in poems for t in p["themes"]}))

print("\n== 6. 跨句命中 ==")
con = sqlite3.connect(os.path.join(APP, "poems.db"))
cur = con.cursor()
rows = cur.execute("""select p.title from poems_fts f join poems p on p.id=f.pid
                      where poems_fts match '"明 月"'""").fetchall()
print("「明 月」命中 %d 条，其中含《鸡鸣》:" % len(rows), any("鸡鸣" in r[0] for r in rows))
