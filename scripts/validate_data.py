"""Release checks for schema v3, usable on a staging package before publication."""
import collections
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from data_utils import ROOT, FIELDS, SCHEMA_VERSION, body_hash, compact, fts_text, identity_body, load, match_query
from review_application import input_hash, fragmented_array


def validate(app, baseline=None):
    app = Path(app).resolve()
    poems = load(app / "poems.json")
    authors = load(app / "authors.json")
    manifest = load(app / "manifest.json")
    ids = {p["id"] for p in poems}
    author_ids = {a["id"] for a in authors}
    migrations = load(app / "id_map.json")
    errors, warnings = [], []

    def error(code, rows):
        if rows:
            errors.append(dict(code=code, count=len(rows), records=rows))

    def warning(code, rows):
        if rows:
            warnings.append(dict(code=code, count=len(rows), records=rows))

    def label(p, **extra):
        return dict(id=p["id"], title=p["title"], author=p["author"], **extra)

    error("duplicate_ids", [pid for pid, n in collections.Counter(p["id"] for p in poems).items() if n > 1])
    error("missing_author_links", [label(p) for p in poems if p["author_id"] not in author_ids])
    error("missing_sources", [label(p) for p in poems if not p.get("source") or not p.get("sources")])
    error("invalid_alias_targets", [key for key, value in migrations.items() if value not in ids])
    if baseline:
        error("lost_legacy_ids", [p["id"] for p in load(baseline, []) if p["id"] not in migrations])
    dirty, same, alignment, version_mix, missing, provenance = [], [], [], [], [], []
    fragmented, review_errors = [], []
    for poem in poems:
        if poem["body_hash"] != body_hash(poem["content"]):
            errors.append(dict(code="body_hash", records=[label(poem)]))
        if not poem["content"]:
            errors.append(dict(code="empty_content", records=[label(poem)]))
        for key in ("content", *FIELDS):
            value = poem[key]
            if not isinstance(value, list) or any(not isinstance(s, str) for s in value):
                errors.append(dict(code="text_shape", records=[label(poem, field=key)]))
                continue
            if any("\ufffd" in s or re.search(r"</?[a-zA-Z][^>]*>|&(?:[a-z]+|#\d+);", s) for s in value):
                dirty.append(label(poem, field=key))
            if key in FIELDS:
                if fragmented_array(value):
                    fragmented.append(label(poem, field=key))
                if value and identity_body(value) == identity_body(poem["content"]):
                    same.append(label(poem, field=key))
                if not value:
                    missing.append(label(poem, field=key))
                meta = poem["field_sources"].get(key, {})
                if not meta.get("type") or not meta.get("review_status") or meta.get("body_hash") != poem["body_hash"]:
                    provenance.append(label(poem, field=key))
                mode = poem["alignment"][key]["mode"]
                if mode == "line" and (len(value) != len(poem["content"]) or not poem["alignment"][key]["verified"]):
                    alignment.append(label(poem, field=key))
        if any(re.search(r"版本[一二三四五六七八九十\d]", s) for s in poem["content"]):
            version_mix.append(label(poem))
        review = poem.get("content_review")
        if review:
            pending = review["pending_findings"]
            indexes = [f["finding_index"] for f in pending] + [d["finding_index"] for d in review["decisions"]]
            if (review["output_hash"] != input_hash(poem)
                    or sorted(indexes) != list(range(review["initial_findings"]))
                    or poem["review_status"] != ("needs_source_check" if pending else "ai_reviewed")
                    or review.get("academic_review_complete") is not False):
                review_errors.append(label(poem))
            for key in FIELDS:
                expected = "needs_source_check" if any(f.get("field") == key for f in pending) else "ai_reviewed"
                if poem["field_sources"][key]["review_status"] != expected:
                    review_errors.append(label(poem, field=key))
    error("text_artifacts", dirty)
    error("annotation_is_original", same)
    error("unsafe_line_alignment", alignment)
    error("versions_in_primary_body", version_mix)
    error("field_provenance", provenance)
    error("fragmented_annotations", fragmented)
    error("content_review_integrity", review_errors)
    warning("missing_annotations", missing)
    warning("author_bio_missing", [dict(id=a["id"], name=a["name"]) for a in authors if not a["lifetime"]])
    warning("genre_unclassified", [label(p) for p in poems if p["genre"] == "未分类"])
    warning("same_title_identity_review", [label(p) for p in poems if "same_title_identity_review" in p["quality_issues"]])
    warning("author_attribution_review", [label(p) for p in poems if next(a for a in authors if a["id"] == p["author_id"])["entity_type"] == "collection"])
    warning("content_source_verification", [label(p, findings=len(p["content_review"]["pending_findings"]))
            for p in poems if p.get("content_review", {}).get("pending_findings")])
    if any(p.get("content_review") for p in poems):
        warning("content_review_missing", [label(p) for p in poems if not p.get("content_review")])
        review_todo_path = app / "todo_content_review.jsonl"
        review_todo = [json.loads(s) for s in review_todo_path.read_text(encoding="utf-8").splitlines() if s] if review_todo_path.exists() else []
        expected_review_todo = [dict(id=p["id"], title=p["title"], author=p["author"], body_hash=p["body_hash"],
            output_hash=p["content_review"]["output_hash"], findings=p["content_review"]["pending_findings"])
            for p in poems if p.get("content_review", {}).get("pending_findings")]
        if review_todo != expected_review_todo:
            errors.append(dict(code="content_review_todo_mismatch"))
    categories = load(app / "categories.json")
    for kind, field in (("题材", "themes"), ("选集", "collections"), ("学段", "levels")):
        counts = collections.Counter(t for p in poems for t in p[field])
        if dict(counts) != {r["name"]: r["count"] for r in categories[kind]}:
            errors.append(dict(code="category_counts", records=[kind]))
    error("lost_tags", [label(p) for p in poems if not set(p["tags"]).issubset(p["themes"] + p["collections"] + p["levels"])])
    todo = [json.loads(s) for s in (app / "todo_annotations.jsonl").read_text(encoding="utf-8").splitlines() if s]
    expected_todo = {p["id"]: sorted(k for k in FIELDS if not p[k]) for p in poems if not all(p[k] for k in FIELDS)}
    if {p["id"]: sorted(p["missing"]) for p in todo} != expected_todo:
        errors.append(dict(code="todo_mismatch"))
    for p in poems:
        if bool(p["complete"]) != all(bool(p[k]) for k in FIELDS):
            errors.append(dict(code="complete_mismatch", records=[label(p)]))
    hash_errors = []
    for name, info in manifest["files"].items():
        path = app / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            hash_errors.append(name)
    error("manifest_hash", hash_errors)
    con = sqlite3.connect((app / "poems.db").as_uri() + "?mode=ro", uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            errors.append(dict(code="sqlite_integrity", records=[integrity]))
        error("foreign_keys", con.execute("PRAGMA foreign_key_check").fetchall())
        if con.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            errors.append(dict(code="schema_version"))
        actual = {pid: json.loads(meta) for pid, meta in con.execute("SELECT id,metadata_json FROM poems")}
        error("json_sqlite_metadata", [p["id"] for p in poems if actual.get(p["id"]) != p] + sorted(set(actual) - ids))
        if dict(con.execute("SELECT old_id,poem_id FROM id_aliases")) != migrations:
            errors.append(dict(code="sqlite_id_aliases"))
        error("json_sqlite_authors", [a["id"] for a in authors if json.loads(con.execute("SELECT metadata_json FROM authors WHERE id=?", (a["id"],)).fetchone()[0]) != a])
        relations = []
        text_rows = {r[0]: r[1:] for r in con.execute("SELECT id,content,translate,notes,appreciation FROM poems")}
        for p in poems:
            if text_rows.get(p["id"]) != tuple("\n".join(p[k]) for k in ("content", *FIELDS)):
                relations.append(label(p, field="legacy_text_columns"))
            for table, column, key in (("themes", "theme", "themes"), ("collections", "collection", "collections"), ("levels", "level", "levels")):
                values = {r[0] for r in con.execute(f"SELECT {column} FROM {table} WHERE poem_id=?", (p["id"],))}
                if values != set(p[key]):
                    relations.append(label(p, field=key))
            for kind in FIELDS:
                row = con.execute("SELECT body_json,mode,metadata_json,review_status FROM annotations WHERE poem_id=? AND kind=?", (p["id"], kind)).fetchone()
                if row is None or json.loads(row[0]) != p[kind] or row[1] != p["alignment"][kind]["mode"] or json.loads(row[2]) != p["field_sources"][kind] or row[3] != p["field_sources"][kind]["review_status"]:
                    relations.append(label(p, field=kind))
        error("sqlite_relations", relations)
        fts = {r[0]: r[1:] for r in con.execute("SELECT pid,title,author,content FROM poems_fts")}
        error("fts_sync", [p["id"] for p in poems if fts.get(p["id"]) != (fts_text("\n".join([p["title"]] + p["aliases"])), fts_text(p["author"]), fts_text("\n".join(p["content"])))] + sorted(set(fts) - ids))
        if con.execute("SELECT COUNT(*) FROM poems_fts").fetchone()[0] != len(poems):
            errors.append(dict(code="fts_count"))
        search = []
        for keyword in ("明月", "东风", "静夜思", "李白", '明月"', '" OR *', "", "   ", "()", "123", "𠮷"):
            query = match_query(keyword)
            try:
                hits = {r[0] for r in con.execute("SELECT pid FROM poems_fts WHERE poems_fts MATCH ?", (query,))} if query else set()
                search.append(dict(keyword=keyword, count=len(hits)))
                if keyword in ("明月", "东风", "静夜思", "李白"):
                    expected = {p["id"] for p in poems if any(keyword in value for value in [p["title"], p["author"], *p["aliases"], *p["content"]])}
                    if expected != hits:
                        errors.append(dict(code="search_semantics", keyword=keyword, extra_ids=sorted(hits-expected), missing_ids=sorted(expected-hits)))
            except sqlite3.OperationalError as exc:
                errors.append(dict(code="search_error", keyword=keyword, message=str(exc)))
    finally:
        con.close()
    return dict(summary=dict(poems=len(poems), authors=len(authors), schema_version=manifest["schema_version"],
                             data_version=manifest["data_version"], integrity=integrity,
                             errors=len(errors), warnings=len(warnings),
                             ai_reviewed=sum(bool(p.get("content_review")) for p in poems),
                             content_review_pending=sum(bool(p.get("content_review", {}).get("pending_findings")) for p in poems),
                             missing_annotations=len(missing), legacy_ids_resolved=True if baseline and not any(e["code"] == "lost_legacy_ids" for e in errors) else None),
                search=search, errors=errors, warnings=warnings)
