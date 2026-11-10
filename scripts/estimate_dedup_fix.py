# -*- coding: utf-8 -*-
"""估算修复去重规则会新增多少作品、其中多少需要补注解。"""
import json
import os
import re
from collections import defaultdict

SRC = r"D:\project\poems-db"
APP = r"D:\project\poems-clean\app-data"
DROP = "，。！？、；：“”‘’（）《》〈〉【】…—·,.!?;:\"'()[]<>/\\|`~@#$%^&*+=_- \t\n\r　"
T = str.maketrans("", "", DROP)

poems = json.load(open(os.path.join(APP, "poems.json"), encoding="utf-8"))
keys = {(p["title"], p["author"]) for p in poems}

variants = defaultdict(dict)      # key -> {正文: 记录}
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
            if (nm, au) not in keys:
                continue
            c = "".join(x.strip() for x in (r.get("content") or []) if isinstance(x, str)).translate(T)
            if not c:
                continue
            variants[(nm, au)].setdefault(c, r)

extra = sum(len(v) for v in variants.values()) - len(poems)
need_ai = 0
for v in variants.values():
    for c, r in v.items():
        has_all = all(r.get(k) for k in ("translate", "notes", "appreciation"))
        if not has_all:
            need_ai += 1
print("当前包作品数:", len(poems))
print("按「正文不同即为不同作品」重算后多出:", extra, "首")
print("其中缺注解、需要补 AI 的:", need_ai, "首（含当前已有的）")
