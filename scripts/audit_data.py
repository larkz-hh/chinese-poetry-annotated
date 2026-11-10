"""Audit the shipped corpus without changing poems.json, poems.db or raw data.

Usage: python -X utf8 scripts/audit_data.py
Only reports/ is written. The original dump is optional; no API calls are made.
Exit status 1 means release-blocking findings, rather than an execution failure.
"""

import argparse
import collections
import hashlib
import html
import json
import re
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_FIELDS = ("content", "translate", "notes", "appreciation")
ANNOTATIONS = TEXT_FIELDS[1:]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def text(value):
    return "\n".join(value) if isinstance(value, list) else str(value or "")


def compact(value):
    return re.sub(r"[\W_]", "", text(value))


def label(poem):
    return {key: poem.get(key) for key in ("id", "title", "author")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT.parent / "poems-db")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    app = ROOT / "app-data"
    poems = read_json(app / "poems.json")
    lite = {p["id"]: p for p in read_json(ROOT / "raw/poems_lite.json")}
    categories = read_json(app / "categories.json")
    findings = []

    def add(code, severity, message, records=None, **details):
        finding = dict(code=code, severity=severity, message=message)
        if records is not None:
            finding.update(count=len(records), records=records)
        finding.update(details)
        findings.append(finding)

    # Stable identity, shape and annotation checks.
    counts = collections.Counter(p["id"] for p in poems)
    duplicates = [key for key, count in counts.items() if count > 1]
    if duplicates:
        add("duplicate_ids", "error", "词条 ID 重复。", duplicates)
    invalid = [label(p) for p in poems if any(
        not isinstance(p.get(k), list)
        or not all(isinstance(s, str) for s in p[k]) for k in TEXT_FIELDS)]
    if invalid:
        add("invalid_text_shape", "error", "正文或注解不是字符串数组。", invalid)
        raise ValueError("Invalid corpus shape; repair before running content checks")
    empty = [{**label(p), "field": k} for p in poems for k in TEXT_FIELDS
             if not any(s.strip() for s in p[k])]
    if empty:
        add("empty_text", "error", "必需正文或注解为空。", empty)
    same_body = [{**label(p), "field": k, "ai_generated": p.get("ai_generated")}
                 for p in poems for k in ANNOTATIONS
                 if compact(p[k]) and compact(p[k]) == compact(p["content"])]
    if same_body:
        add("annotation_is_original", "error",
            "注解字段去标点后与原文相同；非空不能代表有效注解。", same_body)
    misaligned = [{**label(p), "content_lines": len(p["content"]),
                   "translate_lines": len(p["translate"]), "notes_lines": len(p["notes"]),
                   "ai_generated": p.get("ai_generated")}
                  for p in poems if any(len(p[k]) != len(p["content"])
                                        for k in ("translate", "notes"))]
    if misaligned:
        add("line_alignment", "error", "译文或注释行数与正文不等，不能默认按下标对应。", misaligned)
    versions = [label(p) for p in poems if any(re.search(r"版本[一二三四五六七八九十\d]", s)
                                             for s in p["content"])]
    if versions:
        add("versions_in_body", "error", "多个版本串联在正文中，需独立版本与主显示版本。", versions)
    dirty = [{**label(p), "field": k, "excerpt": text(p[k])[max(0, match.start()-12):match.end()+12]}
             for p in poems for k in TEXT_FIELDS
             for match in [re.search(r"\ufffd|[\ue000-\uf8ff]|</?[a-zA-Z][^>]*>|&(?:[a-z]+|#\d+);", text(p[k]))]
             if match]
    if dirty:
        add("text_artifacts", "error", "字段含替换字符、私用字符或未清理标记，需人工核对。", dirty)
    prose_titles = {"论语十二章", "三峡", "廉颇蔺相如列传(节选)", "核舟记", "卖油翁"}
    prose = [label(p) for p in poems if p["title"] in prose_titles]
    if prose:
        add("prose_still_present", "warning", "仍包含这些古文；明确产品范围并标注文体，不按学段标签直接删除。", prose)
    generic_formats = [label(p) for p in poems if p["format"] == "古诗词"]
    add("generic_format", "warning", "通用文体“古诗词”不能支持可靠的诗/词/曲/文筛选。", generic_formats)

    # Category and provenance preservation.
    category_mismatches = []
    for kind, key in (("题材", "themes"), ("选集", "collections"), ("学段", "levels")):
        actual = collections.Counter(tag for p in poems for tag in set(p[key]))
        for row in categories[kind]:
            if row["count"] != actual[row["name"]]:
                category_mismatches.append(dict(kind=kind, name=row["name"],
                                                reported=row["count"], actual=actual[row["name"]]))
    if category_mismatches:
        add("category_count", "error", "分类字典统计与实际词条不符。", category_mismatches)
    lost = [{**label(p), "tags": sorted(set(lite[p["id"]]["tags"])
                                       - set(p["themes"] + p["collections"] + p["levels"]))}
            for p in poems if p["id"] in lite]
    lost = [r for r in lost if r["tags"]]
    add("lost_tags", "warning", "原始标签被筛选截断；展示热门项时应保留完整关系。", lost,
        top_lost_tags=collections.Counter(t for r in lost for t in r["tags"]).most_common(20))
    source_lost = [label(p) for p in poems if lite.get(p["id"], {}).get("source") and not p.get("source")]
    add("lost_source", "warning", "发布词条未保留 raw 中的来源 URL。", source_lost)
    partial_ai = [label(p) for p in poems if p.get("ai_generated")
                  and any(lite.get(p["id"], {}).get(k) for k in ANNOTATIONS)]
    add("field_provenance", "warning", "这些 AI 标记词条同时保留了原始注解；需要逐字段来源与审核状态。", partial_ai)

    # Read-only SQLite validation; do not accidentally create a missing database.
    con = sqlite3.connect((app / "poems.db").as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        integrity = [r[0] for r in con.execute("PRAGMA integrity_check")]
        tables = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        schema = [dict(r) for r in con.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL")]
        db_poems = {r["id"]: dict(r) for r in con.execute("SELECT * FROM poems")}
        db_authors = {r["id"]: dict(r) for r in con.execute("SELECT * FROM authors")}
        mismatch = []
        for p in poems:
            row = db_poems.get(p["id"])
            if row is None:
                mismatch.append({**label(p), "field": "missing_row"})
                continue
            for key in ("title", "author", "author_id", "dynasty", "format", *TEXT_FIELDS,
                        "complete", "ai_generated"):
                if row.get(key) != (text(p[key]) if isinstance(p[key], list) else p[key]):
                    mismatch.append({**label(p), "field": key})
            if row["collection"] != "、".join(p["collections"]):
                mismatch.append({**label(p), "field": "collections"})
            db_themes = {r[0] for r in con.execute("SELECT theme FROM themes WHERE poem_id=?", (p["id"],))}
            if db_themes != set(p["themes"]):
                mismatch.append({**label(p), "field": "themes"})
        for poem_id in set(db_poems) - set(counts):
            mismatch.append(dict(id=poem_id, field="extra_sqlite_row"))
        if mismatch:
            add("json_sqlite_disagreement", "error", "JSON 与 SQLite 的内容不一致。", mismatch)
        missing_authors = [label(p) for p in poems if p["author_id"] not in db_authors]
        if missing_authors:
            add("missing_authors", "error", "作者关联缺失，需补作者记录或明确未知作者处理。", missing_authors)
        dynasty_conflicts = [{**label(p), "poem_dynasty": p["dynasty"],
                             "author_dynasty": db_authors[p["author_id"]]["dynasty"]}
                            for p in poems if p["author_id"] in db_authors
                            and db_authors[p["author_id"]]["dynasty"]
                            and db_authors[p["author_id"]]["dynasty"] != p["dynasty"]]
        if dynasty_conflicts:
            add("dynasty_conflicts", "warning", "作品与作者的朝代标签不同，需核对或解释跨朝代归属。", dynasty_conflicts)
        if "levels" not in tables and "poem_levels" not in tables:
            add("sqlite_missing_levels", "error", "JSON 有学段，SQLite 无学段列或关联表，筛选能力不一致。")
        if not any("REFERENCES" in (r["sql"] or "").upper() for r in schema):
            add("no_foreign_keys", "warning", "当前表结构没有外键声明，关系完整性依赖脚本自行保证。")
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            add("no_schema_version", "warning", "SQLite user_version=0；尚无明确的发布清单和迁移版本。")
        search = []
        for keyword in ("明月", "东风", "静夜思", '明月"'):
            query = '"' + " ".join(keyword) + '"'  # Exactly the README's construction.
            try:
                rows = list(con.execute("SELECT pid FROM poems_fts WHERE poems_fts MATCH ?", (query,)))
                ids = {r[0] for r in rows}
                exact = {p["id"] for p in poems if any(keyword in text(p[k]) for k in ("title", "author", "content"))}
                search.append(dict(keyword=keyword, fts_count=len(rows), literal_count=len(exact),
                                   extra_ids=sorted(ids-exact), missing_ids=sorted(exact-ids)))
            except sqlite3.OperationalError as exc:
                search.append(dict(keyword=keyword, error=str(exc)))
        if any("error" in r for r in search):
            add("fts_query_escaping", "error", "README 查询拼接遇双引号会报 FTS 语法错误，参数化 SQL 仍需转义 MATCH 语法。",
                [r for r in search if "error" in r])
        if any(r.get("extra_ids") or r.get("missing_ids") for r in search):
            add("fts_boundary_semantics", "warning", "索引去标点后可跨标点命中；需明确连续文本搜索的语义。")
        sqlite_summary = dict(integrity=integrity, schema_version=version,
                              counts={t: con.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
                                      for t in ("poems", "authors", "themes", "author_desc", "poems_fts")},
                              json_sqlite_mismatches=len(mismatch), search=search)
        if integrity != ["ok"]:
            add("sqlite_integrity", "error", "SQLite 完整性检查未通过。", integrity)
    finally:
        con.close()

    # Inspect collisions against the original dump. Different text can be a version,
    # a different work, or a source mistake; preserve candidates for human review.
    wanted = {(p["title"], p["author"]) for p in poems}
    original_groups = collections.defaultdict(dict)
    source_files = [args.source_dir / f"poems{i}.json" for i in range(1, 5)]
    source_scanned = all(path.is_file() for path in source_files)
    parse_errors = []
    if source_scanned:
        for path in source_files:
            with path.open(encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        parse_errors.append(dict(file=path.name, line=line_no))
                        continue
                    key = ((row.get("name") or row.get("title") or "").strip(),
                           (row.get("author") or "").strip())
                    if key not in wanted:
                        continue
                    body = html.unescape(re.sub(r"</?[a-zA-Z][^>]*>", "", text(row.get("content"))))
                    normalized = compact(body)
                    original_groups[key].setdefault(normalized, dict(
                        file=path.name, line=line_no, source_id=row.get("_id"),
                        source_url=row.get("sourceLink"), first_text=body.strip()[:160]))
        collisions = [dict(title=key[0], author=key[1], variants=list(variants.values()))
                      for key, variants in original_groups.items() if len(variants) > 1]
        if collisions:
            add("title_author_dedup", "error",
                "原库同名同作者存在不同正文；当前去重键会丢作品。列表含异文候选，不代表全部都是不同作品。", collisions)
        if parse_errors:
            add("original_parse_errors", "warning", "原库存在无法解析的行。", parse_errors)

    build_v2 = (ROOT / "scripts/build_v2.py").read_text(encoding="utf-8")
    if 'os.path.join(SRC, "poems_lite.json")' in build_v2 and not (ROOT / "poems_lite.json").exists():
        add("build_paths", "error", "build_v2.py 从根目录读 raw 输入并输出 scripts/v2，不能重建当前 app-data。")
    theme_names = {t["name"] for t in categories["题材"]}
    if "小学生必背古诗70首" in theme_names:
        add("taxonomy_mixed", "warning", "“小学生必背古诗70首”仍被归为题材，分类维度混杂。")

    summary = dict(poems=len(poems), ai_generated=sum(bool(p.get("ai_generated")) for p in poems),
                   original_only=sum(not p.get("ai_generated") for p in poems),
                   required_text_nonempty=sum(all(any(s.strip() for s in p[k]) for k in TEXT_FIELDS) for p in poems),
                   empty_themes=sum(not p["themes"] for p in poems),
                   annotation_alignment_failures=len(misaligned),
                   original_dump_scanned=source_scanned,
                   findings_by_severity=dict(collections.Counter(f["severity"] for f in findings)))
    fingerprints = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (app / "poems.json", app / "poems.db", app / "categories.json")}
    report = dict(summary=summary, fingerprints=fingerprints, sqlite=sqlite_summary, findings=findings)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "app-data-audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Report:", output)
    return 1 if any(f["severity"] == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
