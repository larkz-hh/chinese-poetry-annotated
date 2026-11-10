# -*- coding: utf-8 -*-
"""去掉「赏析」开头重复引用的原文（古诗文网的赏析习惯先抄全文再点评）。

只在开头的引用与原诗高度一致、且删掉后仍有足够正文时才处理。
"""
import json
import os
import sqlite3

APP = r"D:\project\poems-clean\app-data"
DROP = "，。！？、；：“”‘’（）《》〈〉【】…—·,.!?;:\"'()[]<>/\\|`~@#$%^&*+=_- \t\n\r　"
TABLE = str.maketrans("", "", DROP)


def norm_with_map(s):
    """返回 (规范化文本, 每个字符对应的原始下标)。"""
    out, idx = [], []
    for i, ch in enumerate(s):
        if ch.translate(TABLE):
            out.append(ch)
            idx.append(i)
    return "".join(out), idx


def strip_quote(content_lines, appreciation):
    body = "".join(appreciation)
    c = "".join(content_lines).translate(TABLE)
    if len(c) < 8 or not body:
        return body, False
    n, idx = norm_with_map(body)
    pos = n.find(c)
    if pos < 0 or pos > 6:
        return body, False
    cut = idx[pos + len(c) - 1] + 1          # 引用结束的原始下标
    rest = body[cut:].lstrip(" \t\r\n　.。；;")
    if len(rest) < 80:                        # 剩下的太少，说明整段就是原文，别动
        return body, False
    return rest, True


def main():
    poems = json.load(open(os.path.join(APP, "poems.json"), encoding="utf-8"))
    stripped = 0
    for p in poems:
        new, changed = strip_quote(p["content"], p["appreciation"])
        if changed:
            p["appreciation"] = [new] if new else p["appreciation"]
            stripped += 1
    json.dump(poems, open(os.path.join(APP, "poems.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    con = sqlite3.connect(os.path.join(APP, "poems.db"))
    cur = con.cursor()
    for p in poems:
        cur.execute("UPDATE poems SET appreciation=? WHERE id=?",
                    ("\n".join(p["appreciation"]), p["id"]))
    con.commit()
    con.close()
    print("已去掉重复引文的诗:", stripped, "/", len(poems))


if __name__ == "__main__":
    main()
