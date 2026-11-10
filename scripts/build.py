# -*- coding: utf-8 -*-
"""把 poems-db 改造成「出题数据包」。

输入：D:\\project\\poems-db  （原始 Mongo 转储）
输出：.<out>/ 下的分层数据集
    poems_all.jsonl.gz      全库清洗后（约 19 万首，只留正文+元数据）
    poems_lite.json         精选 ~2000 首（三百首系列 + 全部带注解的）
    seed_annotated.json     金标准种子：注释/译文/赏析三样齐全的（约 115 首）
    authors.json            作者资料（简介、轶事、头像、作品数）
    poems_seed.db           SQLite（lite + authors，可直接放 Android assets）
    report.json             体检数据，写说明文档用
"""
import gzip
import json
import os
import re
import sqlite3
import sys
from collections import Counter, OrderedDict

SRC = r"D:\project\poems-db"
OUT = os.path.dirname(os.path.abspath(__file__))
POEM_FILES = ["poems1.json", "poems2.json", "poems3.json", "poems4.json"]

# 三百首系列：数据里最常被引用的精选集
CURATED = ("唐诗三百首", "宋词三百首", "古诗三百首", "元曲三百首",
           "古文观止", "诗经", "乐府", "小学古诗", "初中古诗", "高中古诗")
BAD_CHAR = re.compile(r"[\ue000-\uf8ff]|鍏|鐨|涓ゆ|銆")


def has(v):
    return v not in (None, "", [], {}, "[]")


TAG = re.compile(r"</?[a-zA-Z][^>]*>")
ENT = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}


def strip_html(s):
    s = TAG.sub("", s)
    for k, v in ENT.items():
        s = s.replace(k, v)
    s = s.replace("\u3000", "　")
    return s


def clean_lines(arr):
    """正文/译文/注释：去 HTML、按换行拆句、去掉空行。"""
    out = []
    for x in arr or []:
        if not isinstance(x, str):
            continue
        for piece in strip_html(x).split("\n"):
            s = piece.strip("\r\t ")
            if s:
                out.append(s)
    return out


def oid(v):
    if isinstance(v, dict):
        return v.get("$oid") or json.dumps(v, ensure_ascii=False)
    return str(v)


def norm(r):
    """原始记录 -> 干净记录。"""
    name = (r.get("name") or r.get("title") or "").strip()
    content = clean_lines(r.get("content"))
    if not name or not content:
        return None
    tags = [t for t in (r.get("tags") or []) if isinstance(t, str) and t.strip()]
    col = r.get("type")
    col = col.strip() if isinstance(col, str) else ""
    if col and BAD_CHAR.search(col):
        col = ""                                   # 丢掉乱码的集合名
    return OrderedDict([
        ("id", oid(r.get("_id"))),
        ("title", name),
        ("author", (r.get("author") or "").strip()),
        ("dynasty", (r.get("dynasty") or "").strip()),
        ("format", (r.get("format") or "").strip()),
        ("collection", col),
        ("tags", tags),
        ("content", content),
        ("translate", clean_lines(r.get("translate"))),
        ("notes", clean_lines(r.get("notes"))),
        ("appreciation", clean_lines(r.get("appreciation"))),
        ("reference", clean_lines(r.get("reference"))),
        ("source", r.get("sourceLink") or ""),
    ])


def iter_raw(fn):
    with open(os.path.join(SRC, fn), encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    os.makedirs(OUT, exist_ok=True)
    seen = {}                     # (title, author) -> record（保留注解更全的）
    stat = Counter()
    collections = Counter()
    tag_counter = Counter()

    for fn in POEM_FILES:
        print("读取", fn, file=sys.stderr)
        for raw in iter_raw(fn):
            stat["raw"] += 1
            rec = norm(raw)
            if not rec:
                stat["dropped"] += 1
                continue
            rec["_score"] = (len(rec["translate"]) > 0) + (len(rec["notes"]) > 0) + \
                            (len(rec["appreciation"]) > 0)
            key = (rec["title"], rec["author"])
            old = seen.get(key)
            if old is None or rec["_score"] > old["_score"]:
                if old is not None:
                    stat["dup"] += 1
                seen[key] = rec
            else:
                stat["dup"] += 1
            collections[rec["collection"] or "-"] += 1
            for t in rec["tags"][:2]:
                tag_counter[t] += 1

    print("去重后 %d 首" % len(seen), file=sys.stderr)
    poems = list(seen.values())
    for p in poems:
        p.pop("_score", None)

    annotated = [p for p in poems if p["translate"] and p["notes"] and p["appreciation"]]
    with_ap = [p for p in poems if p["appreciation"]]
    curated = [p for p in poems if p["collection"] in CURATED or
               any(t in CURATED for t in p["tags"])]
    lite_map = {(p["title"], p["author"]): p for p in curated + with_ap}
    lite = list(lite_map.values())

    def dump(path, data, indent=None):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            if path.endswith(".jsonl.gz"):
                with gzip.open(path, "wt", encoding="utf-8", newline="\n") as g:
                    for x in data:
                        g.write(json.dumps(x, ensure_ascii=False) + "\n")
            elif path.endswith(".jsonl"):
                for x in data:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
            else:
                json.dump(data, f, ensure_ascii=False, indent=indent)

    # 1) 全库（压缩）
    dump(os.path.join(OUT, "poems_all.jsonl.gz"), sorted(poems, key=lambda p: p["id"]))
    # 2) 精选
    lite.sort(key=lambda p: (-len(p["appreciation"]), -len(p["translate"]), p["title"]))
    dump(os.path.join(OUT, "poems_lite.json"), lite, indent=1)
    # 3) 金标准种子
    annotated.sort(key=lambda p: (-len(p["appreciation"]), p["title"]))
    dump(os.path.join(OUT, "seed_annotated.json"), annotated, indent=1)

    # 4) 作者
    authors = []
    with open(os.path.join(SRC, "poems-authors.json"), encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = (r.get("name") or "").strip()
            if not name:
                continue
            desc = []
            for d in r.get("describe") or []:
                if isinstance(d, dict) and d.get("content"):
                    desc.append({"type": (d.get("type") or "").strip(),
                                 "content": clean_lines(d.get("content"))})
            authors.append(OrderedDict([
                ("id", oid(r.get("_id"))),
                ("name", name),
                ("dynasty", (r.get("dynasty") or "").strip()),
                ("lifetime", (r.get("lifetime") or "").strip()),
                ("works", r.get("quantity") or 0),
                ("avatar", r.get("avatar") or ""),
                ("describe", desc),
            ]))
    # 作者去重：同名同朝代保留资料最全的一条
    best = {}
    for a in authors:
        k = (a["name"], a["dynasty"])
        score = len(a["lifetime"]) + sum(len(d["content"]) for d in a["describe"])
        if k not in best or score > best[k][0]:
            best[k] = (score, a)
    authors = [a for _, a in best.values()]
    authors.sort(key=lambda a: -a["works"])
    dump(os.path.join(OUT, "authors.json"), authors, indent=1)
    # 5) SQLite（lite + 作者），给 App 直接放 assets
    db = os.path.join(OUT, "poems_seed.db")
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE poems(
            id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT, dynasty TEXT,
            format TEXT, collection TEXT, tags TEXT,
            content TEXT NOT NULL, translate TEXT, notes TEXT, appreciation TEXT);
        CREATE TABLE authors(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, dynasty TEXT, lifetime TEXT,
            works INTEGER, avatar TEXT);
        CREATE TABLE author_desc(
            author_id TEXT, kind TEXT, body TEXT,
            FOREIGN KEY(author_id) REFERENCES authors(id));
        CREATE INDEX idx_poems_author ON poems(author);
        CREATE INDEX idx_poems_dynasty ON poems(dynasty);
        CREATE INDEX idx_poems_title ON poems(title);
    """)
    for p in lite:
        cur.execute("INSERT OR REPLACE INTO poems VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (p["id"], p["title"], p["author"], p["dynasty"], p["format"],
                     p["collection"], "、".join(p["tags"]), "\n".join(p["content"]),
                     "\n".join(p["translate"]), "\n".join(p["notes"]),
                     "\n".join(p["appreciation"])))
    ids = {p["author"] for p in lite}
    for a in authors:
        if a["name"] not in ids:
            continue
        cur.execute("INSERT OR REPLACE INTO authors VALUES(?,?,?,?,?,?)",
                    (a["id"], a["name"], a["dynasty"], a["lifetime"], a["works"], a["avatar"]))
        for d in a["describe"]:
            cur.execute("INSERT INTO author_desc VALUES(?,?,?)",
                        (a["id"], d["type"], "\n".join(d["content"])))
    con.commit()
    con.close()

    report = {
        "原始记录": stat["raw"],
        "丢弃(无标题/正文)": stat["dropped"],
        "重复(被合并)": stat["dup"],
        "去重后诗歌": len(poems),
        "有译文": sum(1 for p in poems if p["translate"]),
        "有注释": sum(1 for p in poems if p["notes"]),
        "有赏析": len(with_ap),
        "三样齐全": len(annotated),
        "精选集条数(lite)": len(lite),
        "作者数": len(authors),
        "top 集合": collections.most_common(12),
        "top 标签": tag_counter.most_common(15),
        "体积": {},
    }
    for fn in ("poems_all.jsonl.gz", "poems_lite.json", "seed_annotated.json",
               "authors.json", "poems_seed.db"):
        p = os.path.join(OUT, fn)
        report["体积"][fn] = "%d KB" % (os.path.getsize(p) // 1024)

    with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
