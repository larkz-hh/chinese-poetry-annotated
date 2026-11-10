# -*- coding: utf-8 -*-
"""扫描：赏析/注释/译文 字段里是否被塞进了「原文」（源数据污染）。"""
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

APP = str(Path(__file__).resolve().parents[1] / "app-data")
poems = json.load(open(os.path.join(APP, "poems.json"), encoding="utf-8"))
DROP = "，。！？、；：“”‘’（）《》〈〉【】…—·,.!?;:\"'()[]<>/\\|`~@#$%^&*+=_- \t\n\r　"


def norm(s):
    return s.translate(str.maketrans("", "", DROP))


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


bad = []
for p in poems:
    c = norm("".join(p["content"]))
    if len(c) < 8:
        continue
    for k in ("appreciation", "notes", "translate"):
        v = norm("".join(p[k]))
        if not v:
            continue
        # 原文整段出现在该字段里，或高度相似
        if c in v or (len(v) > len(c) * 0.8 and similarity(c[:400], v[:400]) > 0.75):
            bad.append((p["title"], p["author"], k, len(c), len(v), p.get("ai_generated")))
            break

print("疑似「字段里塞了原文」的条数:", len(bad))
for b in bad[:20]:
    print("   《%s》%s  %s  正文%d字 / 字段%d字  ai=%s" % b)
