# -*- coding: utf-8 -*-
"""测试：加大 token 上限 / 关闭思考，看哪种能出正文。"""
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
PROMPT = ("直接输出 JSON，不要分析、不要解释过程。\n"
          '格式：{"translate":[%d 条译文],"notes":[%d 条注释]}\n'
          "每句一条，注释解释生僻字与典故，无需解释给空字符串。\n\n原文：\n%s"
          % (len(lines), len(lines), body))


def run(label, extra, max_tokens):
    body_d = {
        "model": G.MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    body_d.update(extra)
    req = G.urllib.request.Request(G.URL, data=json.dumps(body_d).encode(), headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + G.KEY})
    try:
        with G.urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode())
        msg = d["choices"][0]["message"]
        content = msg.get("content") or ""
        u = d.get("usage", {})
        print("%-22s finish=%-8s content=%-5d reasoning=%s"
              % (label, d["choices"][0].get("finish_reason"), len(content),
                 u.get("completion_tokens_details", {}).get("reasoning_tokens")))
        if content:
            print("    样例:", content[:120])
    except Exception as e:
        print("%-22s 失败 %s %s" % (label, type(e).__name__, str(e)[:100]))


run("大 token (16k)", {}, 16384)
run("关思考 (thinking)", {"thinking": {"type": "disabled"}}, 4096)
run("大 token + 关思考", {"thinking": {"type": "disabled"}}, 16384)
