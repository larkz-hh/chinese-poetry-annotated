"""Build full JSON/SQLite data from raw inputs and existing annotation records."""
import argparse
import collections
import hashlib
import json
import sqlite3
from pathlib import Path

from data_utils import (ROOT, FIELDS, SCHEMA_VERSION, annotation_valid, body_hash, clean_lines,
                        compact, dump, editions, fts_text, identity_body, load, unique)
from content_review import apply_catalog
from review_application import apply_resolution
from famous_lines import FAMOUS_LINE_SCHEMA, attach_famous_lines, write_famous_lines

COLLECTIONS = {"唐诗三百首", "宋词三百首", "古诗三百首", "元曲三百首", "诗经", "乐府",
               "古文观止", "宋词精选", "唐诗精选", "最美", "早教古诗100首",
               "小学生必背古诗70首", "小学生必背古诗80首", "古诗十九首", "千家诗", "楚辞"}
LEVELS = {"小学古诗", "初中古诗", "高中古诗", "小学文言文", "初中文言文", "高中文言文"}
PROSE = {"论语十二章", "三峡", "廉颇蔺相如列传(节选)", "核舟记", "卖油翁"}
QU = {"山坡羊", "天净沙", "折桂令", "一枝花", "沉醉东风", "阳春曲", "蟾宫曲", "水仙子", "清江引", "寿阳曲", "卖花声", "普天乐", "殿前欢"}


def generated_records(path):
    result = {}
    if Path(path).exists():
        with Path(path).open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except ValueError as exc:
                    raise ValueError(f"Invalid generation log {path}:{number}") from exc
                if "error" not in value:
                    result[value["id"]] = value
    return result


def valid(value, originals):
    return annotation_valid(value, originals) and identity_body(value) != identity_body(originals)


def strip_opening_quote(value, originals):
    """Retain paragraphs; remove a leading full-original quotation only when substantial prose follows."""
    body = "\n".join(value)
    chars, indices = [], []
    for index, char in enumerate(body):
        if compact(char):
            chars.append(compact(char))
            indices.append(index)
    original = compact(originals)
    position = "".join(chars).find(original) if original else -1
    if 0 <= position <= 6:
        remainder = body[indices[position + len(original) - 1] + 1:].lstrip(" \n\t。；;　")
        if len(remainder) >= 80:
            return [p for p in remainder.split("\n") if p.strip()]
    return value


def infer_genre(row, cipai):
    title = row["title"].split(" / ")[0]
    if title in PROSE:
        return "文", "title_rule"
    if title.endswith("赋"):
        return "赋", "title_rule"
    prefix = title.split("·")[0]
    if prefix in QU or "元曲三百首" in row["tags"]:
        return "曲", "title_or_collection_rule"
    if prefix in cipai or any("宋词" in s for s in row["tags"]):
        return "词", "cipai_or_collection_rule"
    if row["format"] != "古诗词" or any(s in row["tags"] for s in ("诗经", "唐诗三百首", "古诗三百首", "乐府", "楚辞")):
        return "诗", "source_format_or_collection"
    return "未分类", "unknown"


def build(raw_dir, output, legacy_dir=ROOT / "app-data", legacy_raw=ROOT / "raw", generated_path=None):
    raw_dir, output, legacy_dir, legacy_raw = map(Path, (raw_dir, output, legacy_dir, legacy_raw))
    output.mkdir(parents=True, exist_ok=True)
    rows = apply_catalog(load(raw_dir / "poems_lite.json"), load(raw_dir / "content_review.json", {}))
    legacy = {p["id"]: p for p in load(legacy_dir / "poems.json", [])}
    legacy_raw_rows = {p["id"]: p for p in load(legacy_raw / "poems_lite.json", [])}
    legacy_authors = load(legacy_dir / "authors.json", [])
    old_author_ids = {p["author"]: p["author_id"] for p in legacy.values() if p.get("author_id")}
    generated = generated_records(generated_path or legacy_dir / "generated.jsonl")
    generated.update(generated_records(raw_dir / "annotation_additions.jsonl"))
    fixes = load(ROOT / "raw/editorial_fixes.json", {})
    author_fixes = load(raw_dir / "author_overrides.json", {})
    resolutions = load(raw_dir / "review_resolutions.json", {}).get("works", {})
    cipai = set(load(raw_dir / "cipai.json", []))
    poems, migration, changes = [], {}, load(legacy_dir / "repairs.json", [])
    for row in rows:
        if "古文观止" in row["tags"] + row.get("collections", [row.get("collection", "")]) and not any(i in legacy for i in row.get("source_ids", [row["id"]])):
            continue
        pid = row["id"]
        ids = unique([pid] + row.get("source_ids", []))
        old = next((legacy[i] for i in ids if i in legacy), {})
        old_raw = next((legacy_raw_rows[i] for i in ids if i in legacy_raw_rows), row)
        gen = next((generated[i] for i in ids if i in generated), {})
        versions = editions(pid, row["content"])
        for alternate in row.get("alternate_contents", []):
            extra = editions(pid, alternate["content"])
            for edition in extra:
                edition.update(id=f"{pid}:v{len(versions) + 1}", is_primary=False,
                               source=alternate["source"], source_id=alternate["source_id"])
                versions.append(edition)
        content = versions[0]["content"]
        title_parts = row["title"].split(" / ")
        tags = unique(row["tags"])
        colls = unique(t for t in tags + row.get("collections", [row.get("collection", "")]) if t in COLLECTIONS)
        levels = [t for t in tags if t in LEVELS]
        themes = [t for t in tags if t not in COLLECTIONS and t not in LEVELS]
        genre, genre_basis = infer_genre(row, cipai)
        catalog = row.get("catalog_review", {})
        if catalog.get("genre"):
            genre, genre_basis = catalog["genre"], catalog.get("genre_basis", "catalog_review")
        poem = dict(id=pid, title=catalog.get("title", title_parts[0]), source_title=row["title"],
                    aliases=unique(title_parts[1:] + row.get("aliases", [])), author=row["author"],
                    dynasty=row["dynasty"], format=row["format"], genre=genre, genre_basis=genre_basis,
                    collections=colls, themes=themes, levels=levels, tags=tags,
                    source=row["source"], sources=row.get("sources", [row["source"]]),
                    source_ids=ids, reference=row.get("reference", []),
                    original_content=row["content"], content=content, editions=versions,
                    body_hash=body_hash(content), field_sources={}, alignment={},
                    review_status="unreviewed", quality_issues=[])
        poem["catalog_review"] = catalog
        poem["text_scope"] = catalog.get("text_scope", "source_text")
        if row.get("source_author"):
            poem["source_author"] = row["source_author"]
            if row["author"] not in old_author_ids and row["source_author"] in old_author_ids:
                old_author_ids[row["author"]] = old_author_ids[row["source_author"]]
        if poem["title"] != title_parts[0]:
            poem["aliases"] = unique(poem["aliases"] + title_parts)
        for edition in versions:
            edition["units"] = [dict(id=f"{edition['id']}:u{i + 1}", ordinal=i,
                                     kind="passage", text=line) for i, line in enumerate(edition["content"])]
        fix = next((fixes[i] for i in ids if i in fixes), {})
        for key in FIELDS:
            candidates = [(old.get(key), "legacy"), (row.get(key), "original")]
            # Generation logs predating hashes are reusable only by original record ID.
            if not gen.get("body_hash") or gen["body_hash"] == poem["body_hash"]:
                candidates.append((gen.get(key), "ai"))
            value, origin = [], "missing"
            for candidate, candidate_origin in candidates:
                if valid(candidate, row["content"]) and valid(candidate, old_raw["content"]) and valid(candidate, content):
                    value, origin = candidate, candidate_origin
                    break
            if origin == "legacy":
                origin = (old.get("field_sources", {}).get(key, {}).get("type") or
                          ("ai" if value == gen.get(key) else "original" if value == old_raw.get(key) else "legacy_unverified"))
            if key == "appreciation":
                value = strip_opening_quote(value, row["content"])
            if key in fix:
                value, origin = fix[key], fix.get("source_type", "ai_editorial")
                changes.append(dict(id=pid, field=key, reason=fix["reason"]))
            replacements = fix.get("replace", {}).get(key, {})
            # Apply replacements to the original invalid value too, if no valid alternative exists.
            if replacements:
                value = value or old.get(key) or row.get(key) or gen.get(key) or []
                before = value
                value = [s for s in value]
                for find, replace in replacements.items():
                    value = [s.replace(find, replace) for s in value]
                if not any(find in "".join(before) or replace in "".join(value) for find, replace in replacements.items()):
                    raise ValueError(f"Editorial replacement no longer matches {pid}:{key}")
                origin = fix.get("source_type", "ai_editorial")
                changes.append(dict(id=pid, field=key, reason=fix["reason"]))
            if not valid(value, content):
                value, origin = [], "missing"
            poem[key] = value
            meta = dict(type=origin, source_url=row["source"] if origin == "original" else None,
                        model=gen.get("model") if origin == "ai" else "codex" if origin == "ai_editorial" else None,
                        review_status="unreviewed", body_hash=poem["body_hash"],
                        alignment_verified=False)
            if origin == "ai":
                meta["generation_binding"] = "body_hash" if gen.get("body_hash") else "legacy_record_id"
                meta["generated_at"] = gen.get("generated_at")
                meta["prompt_version"] = gen.get("prompt_version")
            if origin == "ai_editorial":
                meta["revision"] = "editorial_fixes-v1"
                meta["reason"] = fix.get("reason")
            poem["field_sources"][key] = meta
            previous_meta = old.get("field_sources", {}).get(key)
            accepted_body_hashes = {poem["body_hash"], resolutions.get(pid, {}).get("body_change", {}).get("after_hash")}
            if previous_meta and value == old.get(key) and previous_meta.get("body_hash") in accepted_body_hashes:
                poem["field_sources"][key] = previous_meta.copy()
            # No alignment has been semantically checked; use whole-document rendering by default.
            poem["alignment"][key] = dict(mode="document" if value else "missing",
                                          equal_length=key != "appreciation" and len(value) == len(content),
                                          verified=False, unit_ids=[])
            if not value:
                poem["quality_issues"].append("missing_" + key)
        apply_resolution(poem, resolutions.get(pid))
        poem["complete"] = all(poem[k] for k in FIELDS)
        poem["ai_generated"] = any(poem["field_sources"][k]["type"] in ("ai", "ai_editorial") for k in FIELDS) or bool(old.get("ai_generated"))
        if genre == "未分类":
            poem["quality_issues"].append("genre_unclassified")
        poems.append(poem)
        for old_id in ids:
            migration[old_id] = pid
    poems.sort(key=lambda p: p["id"])
    by_name = collections.defaultdict(list)
    for author in load(raw_dir / "authors.json"):
        by_name[author["name"]].append(author)
    previous_authors = {a["id"]: a for a in legacy_authors}
    authors = {}
    for poem in poems:
        aid = old_author_ids.get(poem["author"], "au_" + hashlib.sha256(poem["author"].encode()).hexdigest()[:20])
        poem["author_id"] = aid
        if aid not in authors:
            candidates = by_name[poem["author"]]
            selected = max(candidates, key=lambda a: (a["dynasty"] == poem["dynasty"], len(a["lifetime"])), default={})
            previous = previous_authors.get(aid, {})
            author_fix = author_fixes.get(poem["author"], {})
            bio = author_fix.get("lifetime") or selected.get("lifetime") or previous.get("lifetime") or ("佚名表示作者姓名不可考。" if poem["author"] == "佚名" else "")
            authors[aid] = dict(id=aid, name=poem["author"], dynasty=author_fix.get("dynasty", selected.get("dynasty", "")),
                                dynasties=[], lifetime=bio, works=0, source_works=selected.get("works"),
                                avatar=selected.get("avatar", ""), describe=selected.get("describe", []),
                                source_id=selected.get("id"), bio_status="available_unreviewed" if bio else "missing",
                                entity_type="collection" if poem["author"] == "乐府诗集" else "unknown" if poem["author"] == "佚名" else "person")
            if author_fix:
                authors[aid]["bio_status"] = author_fix.get("review_status", "source_checked")
                authors[aid]["bio_sources"] = author_fix["sources"]
                authors[aid]["bio_reviewed_at"] = author_fix["reviewed_at"]
                authors[aid]["bio_reviewer"] = "codex"
        author = authors[aid]
        author["works"] += 1
        author["dynasties"] = unique(author["dynasties"] + [poem["dynasty"]])
        poem["has_author_bio"] = bool(author["lifetime"])
    authors = sorted(authors.values(), key=lambda a: a["id"])
    collisions = collections.defaultdict(list)
    for p in poems:
        collisions[(p["source_title"], p["author"])].append(p)
    for group in collisions.values():
        if len(group) > 1:
            for p in group:
                if p["catalog_review"].get("status") not in {"text_compared", "source_checked"}:
                    p["quality_issues"].append("same_title_identity_review")
    for old_id in legacy:
        if old_id not in migration:
            raise ValueError(f"Existing poem ID lost without migration: {old_id}")
    for old_id, previous_target in load(legacy_dir / "id_map.json", {}).items():
        if old_id not in migration or migration[old_id] != migration.get(previous_target):
            raise ValueError(f"Existing source alias lost or redirected: {old_id}")
    by_id = {p["id"]: p for p in poems}
    for before in load(ROOT / "backups/pre-v3/app-data/poems.json", []):
        after = by_id.get(migration.get(before["id"]))
        if not after:
            continue
        for key in FIELDS:
            old_value = before[key]
            if old_value and (compact(old_value) == compact(before["content"]) or any("\ufffd" in s for s in old_value)) and old_value != after[key]:
                changes.append(dict(id=after["id"], field=key,
                                    reason="修复迁移前的原文冒充注解或替换字符；保留 pre-v3 快照供回查。"))
    changes = sorted({(r["id"], r["field"]): r for r in changes}.values(), key=lambda r: (r["id"], r["field"]))
    categories = {}
    for name, key in (("题材", "themes"), ("选集", "collections"), ("学段", "levels")):
        counts = collections.Counter(t for p in poems for t in p[key])
        categories[name] = [dict(name=tag, count=count) for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    quote_catalog = load(raw_dir / "famous_lines.json", dict(schema_version=1, works={}))
    for pid, previous in legacy.items():
        if previous.get("famous_lines") and pid not in quote_catalog.get("works", {}):
            raise ValueError(f"Existing famous lines lost without an explicit curation entry: {pid}")
    attach_famous_lines(poems, quote_catalog)
    dump(output / "poems.json", poems)
    dump(output / "authors.json", authors)
    dump(output / "categories.json", categories)
    dump(output / "id_map.json", migration)
    dump(output / "repairs.json", changes)
    todo = [dict(id=p["id"], title=p["title"], author=p["author"], dynasty=p["dynasty"],
                 content=p["content"], body_hash=p["body_hash"], missing=[k for k in FIELDS if not p[k]])
            for p in poems if not p["complete"]]
    (output / "todo_annotations.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in todo), encoding="utf-8")
    review_todo = [dict(id=p["id"], title=p["title"], author=p["author"], body_hash=p["body_hash"],
                        output_hash=p["content_review"]["output_hash"], findings=p["content_review"]["pending_findings"])
                   for p in poems if p.get("content_review", {}).get("pending_findings")]
    (output / "todo_content_review.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in review_todo), encoding="utf-8")
    cautions = [dict(id=p["id"], title=p["title"], author=p["author"], **c)
        for p in poems for c in p.get("content_review", {}).get("final_review", {}).get("cautions", [])]
    (output / "review_cautions.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cautions), encoding="utf-8")
    dump(output / "source_evidence.json", load(raw_dir / "source_evidence.json", {"sources": {}}))
    write_sqlite(output / "poems.db", poems, authors, migration)
    stats = dict(诗词总数=len(poems), 作者数=len(authors), 有原文=len(poems),
                 有译文=sum(bool(p["translate"]) for p in poems), 有注释=sum(bool(p["notes"]) for p in poems),
                 有赏析=sum(bool(p["appreciation"]) for p in poems), 三样齐全=sum(bool(p["complete"]) for p in poems),
                 AI补全过=sum(p["ai_generated"] for p in poems), 仍缺任一项=len(todo),
                 作者简介待补=sum(not a["lifetime"] for a in authors),
                 名句总数=sum(len(p["famous_lines"]) for p in poems),
                 已收录名句作品=sum(bool(p["famous_lines"]) for p in poems),
                 AI初审覆盖=sum(bool(p.get("content_review")) for p in poems),
                 AI二审覆盖=sum(p.get("content_review", {}).get("second_reviewed", False) for p in poems),
                 内容待核作品=len(review_todo), 内容待核疑点=sum(len(p["findings"]) for p in review_todo),
                 编辑终审作品=sum(bool(p.get("content_review", {}).get("final_review")) for p in poems),
                 编辑终审疑点=sum(p.get("content_review", {}).get("final_review", {}).get("findings", 0) for p in poems),
                 已明示解释分歧=len(cautions), 正文校订作品=sum(bool(p.get("content_review", {}).get("body_correction")) for p in poems),
                 对照方式="document：未经语义审核的注解按整篇展示，不按数组下标配对",
                 文体=dict(collections.Counter(p["genre"] for p in poems)))
    dump(output / "stats.json", stats)
    payload = (output / "poems.json").read_bytes()
    manifest = dict(schema_version=SCHEMA_VERSION, data_version=f"{SCHEMA_VERSION}." + hashlib.sha256(payload).hexdigest()[:16],
                    counts=dict(poems=len(poems), authors=len(authors),
                        famous_lines=sum(len(p["famous_lines"]) for p in poems),
                        poems_with_famous_lines=sum(bool(p["famous_lines"]) for p in poems)), read_only_corpus=True,
                    search=dict(tokenizer="unicode61", normalization="NFC/casefold/character tokens with punctuation boundaries"),
                    files={p.name: dict(bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                           for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"})
    manifest["source_inputs"] = {name: hashlib.sha256((raw_dir / name).read_bytes()).hexdigest()
                                for name in ("content_review.json", "author_overrides.json", "editorial_fixes.json", "annotation_additions.jsonl", "content_reviews.jsonl", "review_triage.jsonl", "approved_review_edits.json", "review_resolutions.json", "final_content_decisions.json", "source_evidence.json", "famous_lines.json")
                                if (raw_dir / name).is_file()}
    dump(output / "manifest.json", manifest)
    return stats


def write_sqlite(path, poems, authors, migration):
    if path.exists():
        raise FileExistsError("Build into a new directory; publish only after validation")
    con = sqlite3.connect(path)
    try:
        con.executescript(f"""
        PRAGMA foreign_keys=ON;
        PRAGMA user_version={SCHEMA_VERSION};
        CREATE TABLE authors(id TEXT PRIMARY KEY,name TEXT NOT NULL,dynasty TEXT,lifetime TEXT,works INTEGER,
                             avatar TEXT,source_works INTEGER,bio_status TEXT,metadata_json TEXT NOT NULL);
        CREATE TABLE author_desc(author_id TEXT NOT NULL REFERENCES authors(id),kind TEXT,body TEXT);
        CREATE TABLE poems(id TEXT PRIMARY KEY,title TEXT NOT NULL,author TEXT NOT NULL,
            author_id TEXT NOT NULL REFERENCES authors(id),dynasty TEXT,format TEXT,collection TEXT,
            content TEXT NOT NULL,translate TEXT,notes TEXT,appreciation TEXT,
            complete INTEGER NOT NULL,ai_generated INTEGER NOT NULL,genre TEXT,source TEXT NOT NULL,
            body_hash TEXT NOT NULL,metadata_json TEXT NOT NULL);
        CREATE TABLE themes(poem_id TEXT REFERENCES poems(id),theme TEXT,PRIMARY KEY(poem_id,theme));
        CREATE TABLE collections(poem_id TEXT REFERENCES poems(id),collection TEXT,PRIMARY KEY(poem_id,collection));
        CREATE TABLE levels(poem_id TEXT REFERENCES poems(id),level TEXT,PRIMARY KEY(poem_id,level));
        CREATE TABLE editions(id TEXT PRIMARY KEY,poem_id TEXT REFERENCES poems(id),label TEXT,is_primary INTEGER,metadata_json TEXT);
        CREATE TABLE poem_units(id TEXT PRIMARY KEY,poem_id TEXT REFERENCES poems(id),edition_id TEXT REFERENCES editions(id),ordinal INTEGER,kind TEXT,body TEXT);
        CREATE TABLE annotations(poem_id TEXT REFERENCES poems(id),kind TEXT,body_json TEXT NOT NULL,
            mode TEXT NOT NULL,source_type TEXT,review_status TEXT,metadata_json TEXT,PRIMARY KEY(poem_id,kind));
        CREATE TABLE id_aliases(old_id TEXT PRIMARY KEY,poem_id TEXT REFERENCES poems(id));
        CREATE INDEX idx_p_author ON poems(author_id);
        CREATE INDEX idx_p_author_name ON poems(author);
        CREATE INDEX idx_p_dynasty ON poems(dynasty);
        CREATE INDEX idx_p_title ON poems(title);
        CREATE INDEX idx_t_theme ON themes(theme);
        CREATE INDEX idx_c_collection ON collections(collection);
        CREATE INDEX idx_l_level ON levels(level);
        CREATE VIRTUAL TABLE poems_fts USING fts5(pid UNINDEXED,title,author,content,tokenize='unicode61');
        """)
        con.executescript(FAMOUS_LINE_SCHEMA.format(poem_table="poems"))
        encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        for a in authors:
            con.execute("INSERT INTO authors VALUES(?,?,?,?,?,?,?,?,?)", (a["id"], a["name"], a["dynasty"], a["lifetime"], a["works"], a["avatar"], a["source_works"], a["bio_status"], encode(a)))
            for d in a["describe"]:
                con.execute("INSERT INTO author_desc VALUES(?,?,?)", (a["id"], d["type"], "\n".join(d["content"])))
        for p in poems:
            con.execute("INSERT INTO poems VALUES(" + ",".join("?" for _ in range(17)) + ")",
                        (p["id"], p["title"], p["author"], p["author_id"], p["dynasty"], p["format"], "、".join(p["collections"]),
                         "\n".join(p["content"]), *("\n".join(p[k]) for k in FIELDS), int(p["complete"]), int(p["ai_generated"]),
                         p["genre"], p["source"], p["body_hash"], encode(p)))
            for table, key in (("themes", "themes"), ("collections", "collections"), ("levels", "levels")):
                con.executemany(f"INSERT INTO {table} VALUES(?,?)", [(p["id"], t) for t in p[key]])
            for edition in p["editions"]:
                con.execute("INSERT INTO editions VALUES(?,?,?,?,?)", (edition["id"], p["id"], edition["label"], int(edition["is_primary"]), encode(edition)))
                con.executemany("INSERT INTO poem_units VALUES(?,?,?,?,?,?)", [(u["id"], p["id"], edition["id"], u["ordinal"], u["kind"], u["text"]) for u in edition["units"]])
            for kind in FIELDS:
                con.execute("INSERT INTO annotations VALUES(?,?,?,?,?,?,?)", (p["id"], kind, encode(p[kind]), p["alignment"][kind]["mode"], p["field_sources"][kind]["type"], p["field_sources"][kind]["review_status"], encode(p["field_sources"][kind])))
            con.execute("INSERT INTO poems_fts VALUES(?,?,?,?)", (p["id"], fts_text("\n".join([p["title"]] + p["aliases"])), fts_text(p["author"]), fts_text("\n".join(p["content"]))))
        write_famous_lines(con, poems)
        con.executemany("INSERT INTO id_aliases VALUES(?,?)", sorted(migration.items()))
        con.commit()
        if con.execute("PRAGMA foreign_key_check").fetchall() or con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite validation failed")
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "raw")
    parser.add_argument("--output-dir", type=Path, required=True, help="New staging directory")
    args = parser.parse_args()
    print(json.dumps(build(args.raw_dir, args.output_dir), ensure_ascii=False, indent=2))
