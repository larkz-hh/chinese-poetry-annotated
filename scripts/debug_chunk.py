# -*- coding: utf-8 -*-
"""调试：看单段调用的原始返回。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_long_poem as G

APP = G.APP
todo = [json.loads(l) for l in open(os.path.join(APP, "todo_annotations.jsonl"), encoding="utf-8") if l.strip()]
poem = next(p for p in todo if p["title"] == "远游")
lines = poem["content"][:20]
body = "\n".join("%d. %s" % (i + 1, s) for i, s in enumerate(lines))
prompt = f"""这是《远游》（屈原·先秦）的第 1/5 段，共 {len(lines)} 句。
为每句生成白话译文和注释，返回 JSON：
{{"translate": [{len(lines)} 个元素], "notes": [{len(lines)} 个元素]}}
要求：两个数组长度都必须等于 {len(lines)}；notes 解释生僻字、典故、地名，无需解释给 ""；注释每条 15~60 字。

段落原文：
{body}"""
resp = G.call([{"role": "system", "content": G.SYSTEM},
               {"role": "user", "content": prompt}], max_tokens=4096)
msg = resp["choices"][0]["message"]
raw = msg.get("content") or ""
print("usage:", resp.get("usage"))
print("finish_reason:", resp["choices"][0].get("finish_reason"))
print("content 长度:", len(raw))
print("前 600 字:\n", raw[:600])
print("\n尾部 200 字:\n", raw[-200:])
