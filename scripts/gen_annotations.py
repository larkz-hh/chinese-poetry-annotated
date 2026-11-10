# -*- coding: utf-8 -*-
"""用 LLM 批量补全「注释 / 译文 / 赏析」。

输入  : app-data/todo_annotations.jsonl（1327 首缺注解的诗）
输出  : app-data/generated.jsonl（一行一首，可断点续跑）
用法  : python gen_annotations.py            # 全量
        python gen_annotations.py --limit 3  # 先跑 3 首看看
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TODO = os.path.join(ROOT, "app-data", "todo_annotations.jsonl")
OUT = os.path.join(ROOT, "app-data", "generated.jsonl")
ENV = r"D:\project\agent\.env"

SYSTEM = (
    "你是古籍出版社的古诗词注释编辑，语言简洁准确，不臆造典故，"
    "不确定的字词按常见义项处理。只输出 JSON，不输出任何其他内容。"
)

PROMPT = """为下面这首诗生成注释数据，返回 JSON 对象（不要 markdown 代码块、不要解释）：

{{"translate": [逐句白话译文], "notes": [逐句注释], "appreciation": [赏析段落]}}

硬性要求：
1. translate 数组长度必须等于正文句数（{n} 句），一句译文对应一句原文；
2. notes 数组长度也必须等于 {n}，逐句解释生僻字、典故、地名、人物；某句无需解释就给空字符串 ""；
3. appreciation 用 1~2 段，合计 200~350 字，讲意象、手法、情感与写作背景，不要复述译文；
4. 全部用简体中文，注释要短（每句 15~60 字）。

诗题：{title}
作者：{author}（{dynasty}）
正文：
{body}"""


def load_env(path):
    cfg = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


CFG = load_env(ENV)
KEY = CFG.get("LLM_API_KEY", "")
BASE = CFG.get("LLM_BASE_URL", "").rstrip("/")
MODEL = CFG.get("LLM_MODEL_ID", "")
URL = BASE + ("/chat/completions" if BASE.endswith("/v1") else "/v1/chat/completions")

lock = threading.Lock()
done = set()


def call(messages, max_tokens=4096, temperature=0.3):
    body = json.dumps({
        "model": MODEL, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        text = text[i:j + 1]
    return json.loads(text)


def gen_one(poem, attempt=0):
    n = len(poem["content"])
    body = "\n".join("%d. %s" % (i + 1, s) for i, s in enumerate(poem["content"]))
    prompt = PROMPT.format(title=poem["title"], author=poem["author"],
                           dynasty=poem["dynasty"] or "不详", body=body, n=n)
    try:
        budget = min(8192, max(4096, n * 140 + 1200)) if attempt == 0 else 8192
        resp = call([{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}], max_tokens=budget)
        data = parse_json(resp["choices"][0]["message"]["content"])
        tr = [str(x).strip() for x in (data.get("translate") or [])]
        nt = [str(x).strip() for x in (data.get("notes") or [])]
        ap = [str(x).strip() for x in (data.get("appreciation") or []) if str(x).strip()]
        ok = (len(tr) == n or (n > 40 and len(tr) == 1)) and \
             (len(nt) == n or (n > 40 and len(nt) == 1)) and \
             (100 <= len("".join(ap)) <= 900)
        if not ok:
            raise ValueError("长度校验失败 tr=%d nt=%d ap=%d n=%d" % (len(tr), len(nt), len(ap), n))
        return {"id": poem["id"], "translate": tr, "notes": nt,
                "appreciation": ap, "model": MODEL, "from": "ai"}
    except Exception as e:
        if attempt < 2:
            time.sleep(2 * (attempt + 1))
            return gen_one(poem, attempt + 1)
        return {"id": poem["id"], "error": "%s: %s" % (type(e).__name__, str(e)[:160])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    todo = [json.loads(l) for l in open(TODO, encoding="utf-8") if l.strip()]
    if os.path.exists(OUT):
        for l in open(OUT, encoding="utf-8"):
            try:
                r = json.loads(l)
                if "error" not in r:
                    done.add(r["id"])
            except Exception:
                pass
    todo = [p for p in todo if p["id"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print("待生成 %d 首（已完成 %d）" % (len(todo), len(done)), flush=True)

    ok = err = 0
    t0 = time.time()
    with open(OUT, "a", encoding="utf-8", newline="\n") as fout, \
            ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(gen_one, p): p for p in todo}
        for k, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            with lock:
                fout.write(json.dumps(r, ensure_ascii=False) + "\n")
                fout.flush()
                if "error" in r:
                    err += 1
                else:
                    ok += 1
            if k % 20 == 0 or k == len(todo):
                el = time.time() - t0
                print("进度 %d/%d  成功 %d 失败 %d  %.0fs  预计剩余 %.0f min"
                      % (k, len(todo), ok, err, el, (len(todo) - k) * el / k / 60),
                      flush=True)
    print("完成：成功 %d，失败 %d" % (ok, err))


if __name__ == "__main__":
    main()

