# -*- coding: utf-8 -*-
"""按「古诗词 App」赛题规格重建数据包 v2。

在 poems_lite.json 基础上：
  · 剔除古文（《古文观止》那批不是诗）
  · 标签拆成三类：选集 / 题材 / 学段（分类筛选只该用「题材」）
  · 关联作者简介（author_id）
  · 建 FTS5 全文索引（标题+正文+作者），学生直接能搜
  · 导出「缺注释/赏析」的任务清单，方便用 AI 批量补齐
"""
import json
import os
import re
import sqlite3
from collections import Counter, OrderedDict

SRC = r"D:\project\poems-clean"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2")

COLLECTIONS = {
    "唐诗三百首", "宋词三百首", "古诗三百首", "元曲三百首", "诗经", "乐府",
    "古文观止", "宋词精选", "唐诗精选", "最美", "早教古诗100首",
    "小学生必背古诗80首", "古诗十九首", "千家诗", "楚辞",
}
LEVELS = {"小学古诗", "初中古诗", "高中古诗", "小学文言文", "初中文言文", "高中文言文"}
DROP = {"古文观止"}      # 这批是散文，不属于诗词 App 的内容

# 常见题材白名单（用于把「分类筛选」限定成可控规模）
THEMES = {
    "写景", "抒情", "咏物", "咏史怀古", "怀古", "边塞", "思乡", "送别", "离别",
    "爱情", "友情", "哲理", "励志", "爱国", "战争", "忧国忧民", "婉约", "豪放",
    "写人", "写雨", "写雪", "写风", "写花", "写山", "写水", "写鸟", "写马",
    "春天", "夏天", "秋天", "冬天", "节日", "春节", "元宵节", "寒食节",
    "清明节", "端午节", "七夕节", "中秋节", "重阳节", "月亮", "梅花", "荷花",
    "菊花", "柳树", "山水", "田园", "地名", "长江", "黄河", "儿童", "母亲",
    "老师", "女子", "生活", "读书", "惜时", "悼亡", "闺怨", "民歌", "歌谣",
    "叙事", "抒怀", "归隐", "孤独", "时光", "人生", "回忆", "思念", "亲情",
    "羁旅", "宴饮", "登高", "讽喻", "闲适", "豪迈", "清雅", "感伤", "感叹",
}


def has(v):
    return bool(v)


def main():
    os.makedirs(OUT, exist_ok=True)
    poems = json.load(open(os.path.join(SRC, "poems_lite.json"), encoding="utf-8"))
    authors = json.load(open(os.path.join(SRC, "authors.json"), encoding="utf-8"))

    # ---------- 作者索引 ----------
    by_name = {}
    for a in authors:
        k = a["name"]
        if k not in by_name or len(a["lifetime"]) > len(by_name[k]["lifetime"]):
            by_name[k] = a
    for a in authors:
        a["author_id"] = "au_" + re.sub(r"\W", "", a["name"])[:24]

    # ---------- 清洗 + 分类 ----------
    kept, dropped_gw = [], 0
    theme_counter, coll_counter, level_counter = Counter(), Counter(), Counter()
    for p in poems:
        tags = p.get("tags") or []
        if DROP & set(tags) or p.get("collection") in DROP:
            dropped_gw += 1
            continue
        themes, colls, levels = [], [], []
        for t in tags:
            if t in COLLECTIONS:
                colls.append(t)
            elif t in LEVELS:
                levels.append(t)
            elif t in THEMES:
                themes.append(t)
            else:
                themes.append(t)          # 其余当题材，后面按频次截断
        if p.get("collection") and p["collection"] in COLLECTIONS and p["collection"] not in colls:
            colls.append(p["collection"])
        a = by_name.get(p["author"])
        rec = OrderedDict([
            ("id", p["id"]),
            ("title", p["title"]),
            ("author", p["author"]),
            ("author_id", a["author_id"] if a else ""),
            ("has_author_bio", bool(a and a.get("lifetime"))),
            ("dynasty", p["dynasty"]),
            ("format", p["format"]),
            ("collections", colls),
            ("themes", list(dict.fromkeys(themes))),
            ("levels", levels),
            ("content", p["content"]),
            ("translate", p["translate"]),
            ("notes", p["notes"]),
            ("appreciation", p["appreciation"]),
            ("complete", bool(p["notes"] and p["translate"] and p["appreciation"])),
        ])
        kept.append(rec)
        for t in colls:
            coll_counter[t] += 1
        for t in themes:
            theme_counter[t] += 1
        for t in levels:
            level_counter[t] += 1

    # 题材只保留出现 >= 8 次的，且最多 40 个，避免筛选项上百个
    themes_ok = [t for t, c in theme_counter.most_common() if c >= 8][:40]
    for p in kept:
        p["themes"] = [t for t in p["themes"] if t in themes_ok]

    # 佚名：合成一条作者资料，避免详情页「作者简介」空白
    if "佚名" not in by_name:
        ghost = {"author_id": "au_yiming", "name": "佚名", "dynasty": "",
                 "lifetime": "佚名，指姓名不可考的作者。先秦至汉魏的许多诗篇，"
                             "如《诗经》、乐府民歌，多由民间传唱、后人整理，作者已无从查证。",
                 "works": 0, "avatar": "", "describe": []}
        authors.append(ghost)
        by_name["佚名"] = ghost
    for p in kept:
        if not p["author_id"] and p["author"] in by_name:
            p["author_id"] = by_name[p["author"]]["author_id"]
            p["has_author_bio"] = bool(by_name[p["author"]].get("lifetime"))

    n = len(kept)
    stats = {
        "诗词总数": n,
        "剔除古文": dropped_gw,
        "有注释": sum(1 for p in kept if p["notes"]),
        "有译文": sum(1 for p in kept if p["translate"]),
        "有赏析": sum(1 for p in kept if p["appreciation"]),
        "三样齐全": sum(1 for p in kept if p["complete"]),
        "有作者简介": sum(1 for p in kept if p["has_author_bio"]),
        "题材数": len(themes_ok),
        "选集数": len(coll_counter),
        "学段数": len(level_counter),
    }

    # ---------- 导出 ----------
    json.dump(kept, open(os.path.join(OUT, "poems.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({
        "题材": [{"name": t, "count": theme_counter[t]} for t in themes_ok],
        "选集": [{"name": t, "count": c} for t, c in coll_counter.most_common()],
        "学段": [{"name": t, "count": c} for t, c in level_counter.most_common()],
    }, open(os.path.join(OUT, "categories.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=1)

    # 补全任务清单（给 AI 批量补注释/赏析用）
    todo = [p for p in kept if not (p["notes"] and p["appreciation"])]
    with open(os.path.join(OUT, "todo_annotations.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for p in todo:
            f.write(json.dumps({
                "id": p["id"], "title": p["title"], "author": p["author"],
                "dynasty": p["dynasty"], "content": p["content"],
                "missing": [k for k in ("translate", "notes", "appreciation") if not p[k]],
            }, ensure_ascii=False) + "\n")

    # ---------- SQLite + FTS5 ----------
    db = os.path.join(OUT, "poems.db")
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.executescript("""
      PRAGMA journal_mode=WAL;
      CREATE TABLE poems(
        id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT, author_id TEXT,
        dynasty TEXT, format TEXT, collection TEXT,
        content TEXT NOT NULL, translate TEXT, notes TEXT, appreciation TEXT,
        complete INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE themes(poem_id TEXT, theme TEXT, PRIMARY KEY(poem_id, theme));
      CREATE TABLE authors(
        id TEXT PRIMARY KEY, name TEXT, dynasty TEXT, lifetime TEXT,
        works INTEGER, avatar TEXT);
      CREATE TABLE author_desc(author_id TEXT, kind TEXT, body TEXT);
      CREATE INDEX idx_p_author ON poems(author);
      CREATE INDEX idx_p_dynasty ON poems(dynasty);
      CREATE INDEX idx_t_theme ON themes(theme);
    """)
    for p in kept:
        cur.execute("INSERT INTO poems VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (p["id"], p["title"], p["author"], p["author_id"], p["dynasty"],
                     p["format"], "、".join(p["collections"]),
                     "\n".join(p["content"]), "\n".join(p["translate"]),
                     "\n".join(p["notes"]), "\n".join(p["appreciation"]),
                     1 if p["complete"] else 0))
        for t in p["themes"]:
            cur.execute("INSERT OR IGNORE INTO themes VALUES(?,?)", (p["id"], t))
    used = {p["author"] for p in kept}
    for a in authors:
        if a["name"] not in used:
            continue
        cur.execute("INSERT OR REPLACE INTO authors VALUES(?,?,?,?,?,?)",
                    (a["author_id"], a["name"], a["dynasty"], a["lifetime"],
                     a["works"], a["avatar"]))
        for d in a.get("describe") or []:
            cur.execute("INSERT INTO author_desc VALUES(?,?,?)",
                        (a["author_id"], d["type"], "\n".join(d["content"])))
    # FTS5：中文没有空格，unicode61 会把整行当一个词。
    # 做法：入库前把文本逐字加空格（"床 前 明 月 光"），查询时同样把关键词
    # 变成短语（MATCH '"明 月"'）即可命中任意 2 字词；1 字词也能用。
    DROP_CHARS = ("，。！？、；：“”‘’（）《》〈〉【】…—·,.!?;:\"'()[]<>/\\|"
                  "`~@#$%^&*+=_- \t\n\r　0123456789")
    TABLE = str.maketrans("", "", DROP_CHARS)

    def seg(s):
        return " ".join(s.translate(TABLE))

    cur.execute("""CREATE VIRTUAL TABLE poems_fts USING fts5(
        pid UNINDEXED, title, author, content, tokenize='unicode61')""")
    for p in kept:
        cur.execute("INSERT INTO poems_fts(pid, title, author, content) VALUES(?,?,?,?)",
                    (p["id"], seg(p["title"]), seg(p["author"]), seg("\n".join(p["content"]))))
    con.commit()
    con.close()

    stats["体积"] = {fn: "%d KB" % (os.path.getsize(os.path.join(OUT, fn)) // 1024)
                     for fn in os.listdir(OUT)}
    stats["待补全"] = len(todo)
    json.dump(stats, open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
