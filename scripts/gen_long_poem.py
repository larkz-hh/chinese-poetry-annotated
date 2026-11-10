# -*- coding: utf-8 -*-
"""给超长诗（如《远游》90 句）分段生成注释/译文，再拼成一整条。

主脚本对 >40 句的诗会让模型整段输出，容易超 token 被截断；这里改成按 20 句切块逐段生成。
用法：python gen_long_poem.py 远游
"""
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "app-data")
ENV = r"D:\project\agent\.env"
CHUNK = 20

SYSTEM = ("你是古籍出版社的古诗词注释编辑，语言简洁准确，不臆造典故。只输出 JSON。")


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
KEY, BASE, MODEL = CFG["LLM_API_KEY"], CFG["LLM_BASE_URL"].rstrip("/"), CFG["LLM_MODEL_ID"]
URL = BASE + ("/chat/completions" if BASE.endswith("/v1") else "/v1/chat/completions")


def call(messages, max_tokens=4096, temperature=0.3):
    body = json.dumps({
        "model": MODEL, "messages": messages, "temperature": temperature,
        "max_tokens": max_tokens, "response_format": {"type": "json_object"},"thinking": {"type": "disabled"},
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode())


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    i, j = text.find("{"), text.rfind("}")
    return json.loads(text[i:j + 1])


def gen_chunk(title, author, dynasty, lines, idx, total):
    body = "\n".join("%d. %s" % (i + 1, s) for i, s in enumerate(lines))
    prompt = f"""这是《{title}》（{author}·{dynasty}）的第 {idx}/{total} 段，共 {len(lines)} 句。
为每句生成白话译文和注释，返回 JSON：
{{"translate": [{len(lines)} 个元素], "notes": [{len(lines)} 个元素]}}
要求：两个数组长度都必须等于 {len(lines)}；notes 解释生僻字、典故、地名，无需解释给 ""；注释每条 15~60 字。

段落原文：
{body}"""
    for attempt in range(3):
        try:
            resp = call([{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}],
                        max_tokens=min(8192, 600 + len(lines) * 120))
            d = parse_json(resp["choices"][0]["message"]["content"])
            tr = [str(x).strip() for x in d.get("translate") or []]
            nt = [str(x).strip() for x in d.get("notes") or []]
            if len(tr) == len(lines) and len(nt) == len(lines):
                return tr, nt
            print("  段 %d 长度不符 (%d/%d)，重试" % (idx, len(tr), len(nt)), flush=True)
        except Exception as e:
            print("  段 %d 失败 %s，重试" % (idx, type(e).__name__), flush=True)
        time.sleep(2 * (attempt + 1))
    return None


def gen_appreciation(title, author, content):
    prompt = f"""为《{title}》（{author}）写一段赏析，返回 JSON：{{"appreciation": ["段落1", "段落2"]}}
要求：1~2 段，合计 250~400 字，讲意象、结构、手法、情感与写作背景，不要逐句翻译。

全诗：
{chr(10).join(content)}"""
    for _ in range(3):
        try:
            resp = call([{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}], max_tokens=2048)
            d = parse_json(resp["choices"][0]["message"]["content"])
            ap = [str(x).strip() for x in d.get("appreciation") or [] if str(x).strip()]
            if 100 <= len("".join(ap)) <= 900:
                return ap
        except Exception:
            pass
        time.sleep(2)
    return None


def main():
    title = sys.argv[1] if len(sys.argv) > 1 else "远游"
    todo = [json.loads(l) for l in open(os.path.join(APP, "todo_annotations.jsonl"), encoding="utf-8") if l.strip()]
    poem = next((p for p in todo if p["title"] == title), None)
    if not poem:
        raise SystemExit("待补清单里没有《%s》" % title)
    lines = poem["content"]
    chunks = [lines[i:i + CHUNK] for i in range(0, len(lines), CHUNK)]
    print("《%s》共 %d 句，切 %d 段" % (title, len(lines), len(chunks)), flush=True)

    tr_all, nt_all = [], []
    for k, ch in enumerate(chunks, 1):
        r = gen_chunk(title, poem["author"], poem["dynasty"] or "不详", ch, k, len(chunks))
        if not r:
            raise SystemExit("第 %d 段生成失败" % k)
        tr_all += r[0]
        nt_all += r[1]
        print("  段 %d/%d 完成" % (k, len(chunks)), flush=True)

    ap = gen_appreciation(title, poem["author"], lines)
    if not ap:
        raise SystemExit("赏析生成失败")
    assert len(tr_all) == len(lines) and len(nt_all) == len(lines)

    rec = {"id": poem["id"], "translate": tr_all, "notes": nt_all,
           "appreciation": ap, "model": MODEL, "from": "ai"}
    with open(os.path.join(APP, "generated.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("已写入 generated.jsonl：《%s》%d 句，赏析 %d 字"
          % (title, len(lines), len("".join(ap))))


if __name__ == "__main__":
    main()

