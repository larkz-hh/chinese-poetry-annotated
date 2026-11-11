"""Lossless App SQLite profile: queryable reading data plus compressed archives."""
import hashlib
import json
import sqlite3
import zlib
from pathlib import Path

from data_utils import FIELDS, fts_text

APPLICATION_ID = int.from_bytes(b"POET", "big")
RUNTIME_SCHEMA = 1
ARCHIVE_CODEC = "zlib-json-textrefs-v1"


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def connect_readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def read_archive(con, kind, record_id, text_cache=None):
    row = con.execute("SELECT payload,sha256,raw_bytes,codec FROM record_archives WHERE kind=? AND id=?", (kind, record_id)).fetchone()
    if row is None:
        raise KeyError((kind, record_id))
    if row[3] != ARCHIVE_CODEC:
        raise ValueError("Unsupported archive codec")
    tree = json.loads(zlib.decompress(row[0]))
    cache = {} if text_cache is None else text_cache
    needed = set()

    def collect(node):
        tag, value = node
        if tag == "s":
            if value not in cache:
                needed.add(value)
        elif tag == "l":
            for child in value:
                collect(child)
        elif tag == "d":
            for child in value.values():
                collect(child)
        elif tag != "v":
            raise ValueError("Invalid archive node")

    def unpack(node):
        tag, value = node
        if tag == "s":
            return cache[value]
        if tag == "l":
            return [unpack(v) for v in value]
        if tag == "d":
            return {k: unpack(v) for k, v in value.items()}
        return value

    collect(tree)
    pending = sorted(needed)
    for start in range(0, len(pending), 900):
        batch = pending[start:start+900]
        cache.update(con.execute("SELECT id,body FROM text_blocks WHERE id IN (" + ",".join("?" for _ in batch) + ")", batch))
    if any(tid not in cache for tid in needed):
        raise ValueError(f"Missing archive text: {kind}:{record_id}")
    value = unpack(tree)
    raw = encode(value).encode("utf-8")
    if len(raw) != row[2] or hashlib.sha256(raw).hexdigest() != row[1]:
        raise ValueError(f"Archive integrity failed: {kind}:{record_id}")
    return value


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE text_blocks(id INTEGER PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE authors(
 id TEXT PRIMARY KEY,name TEXT NOT NULL,dynasty TEXT,lifetime TEXT,works INTEGER,
 source_works INTEGER,avatar TEXT,bio_status TEXT,entity_type TEXT,
 dynasties_json TEXT NOT NULL,bio_sources_json TEXT NOT NULL);
CREATE TABLE author_sections(
 author_id TEXT REFERENCES authors(id),ordinal INTEGER,kind TEXT,
 PRIMARY KEY(author_id,ordinal)) WITHOUT ROWID;
CREATE TABLE author_section_text(
 author_id TEXT,section_ordinal INTEGER,ordinal INTEGER,text_id INTEGER REFERENCES text_blocks(id),
 PRIMARY KEY(author_id,section_ordinal,ordinal),
 FOREIGN KEY(author_id,section_ordinal) REFERENCES author_sections(author_id,ordinal)) WITHOUT ROWID;
CREATE VIEW author_desc AS
 SELECT s.author_id,s.ordinal,s.kind,
 coalesce((SELECT group_concat(t.body,char(10)) FROM
   (SELECT b.body FROM author_section_text x JOIN text_blocks b ON b.id=x.text_id
    WHERE x.author_id=s.author_id AND x.section_ordinal=s.ordinal ORDER BY x.ordinal) t),'') AS body
 FROM author_sections s;
CREATE TABLE poem_records(
 rowid INTEGER PRIMARY KEY,id TEXT NOT NULL UNIQUE,title TEXT NOT NULL,source_title TEXT,
 author_id TEXT NOT NULL REFERENCES authors(id),dynasty TEXT,format TEXT,genre TEXT,genre_basis TEXT,
 source TEXT NOT NULL,body_hash TEXT NOT NULL,complete INTEGER NOT NULL,ai_generated INTEGER NOT NULL,
 review_status TEXT NOT NULL,text_scope TEXT,reference_json TEXT NOT NULL,quality_issues_json TEXT NOT NULL);
CREATE TABLE poem_text(
 poem_id TEXT REFERENCES poem_records(id),kind TEXT,ordinal INTEGER,text_id INTEGER REFERENCES text_blocks(id),
 PRIMARY KEY(poem_id,kind,ordinal)) WITHOUT ROWID;
CREATE VIEW passages AS
 SELECT x.poem_id,x.kind,x.ordinal,b.body FROM poem_text x JOIN text_blocks b ON b.id=x.text_id;
CREATE TABLE poem_aliases(poem_id TEXT REFERENCES poem_records(id),ordinal INTEGER,title TEXT,
 PRIMARY KEY(poem_id,ordinal)) WITHOUT ROWID;
CREATE TABLE poem_sources(poem_id TEXT REFERENCES poem_records(id),ordinal INTEGER,url TEXT,
 PRIMARY KEY(poem_id,ordinal)) WITHOUT ROWID;
CREATE TABLE poem_source_ids(poem_id TEXT REFERENCES poem_records(id),ordinal INTEGER,source_id TEXT,
 PRIMARY KEY(poem_id,ordinal)) WITHOUT ROWID;
CREATE TABLE poem_terms(poem_id TEXT REFERENCES poem_records(id),kind TEXT,ordinal INTEGER,value TEXT,
 PRIMARY KEY(poem_id,kind,ordinal)) WITHOUT ROWID;
CREATE INDEX idx_term_value ON poem_terms(kind,value,poem_id);
CREATE VIEW themes AS SELECT poem_id,value AS theme FROM poem_terms WHERE kind='themes';
CREATE VIEW collections AS SELECT poem_id,value AS collection FROM poem_terms WHERE kind='collections';
CREATE VIEW levels AS SELECT poem_id,value AS level FROM poem_terms WHERE kind='levels';
CREATE TABLE annotation_info(
 poem_id TEXT REFERENCES poem_records(id),kind TEXT,source_type TEXT,review_status TEXT,model TEXT,
 source_url TEXT,body_hash TEXT,alignment_mode TEXT,alignment_verified INTEGER,
 equal_length INTEGER,unit_ids_json TEXT NOT NULL,PRIMARY KEY(poem_id,kind)) WITHOUT ROWID;
CREATE TABLE editions(
 id TEXT PRIMARY KEY,poem_id TEXT REFERENCES poem_records(id),ordinal INTEGER,label TEXT,is_primary INTEGER,
 source TEXT,source_id TEXT,revision TEXT,reason TEXT,variants_json TEXT NOT NULL,evidence_json TEXT NOT NULL,
 UNIQUE(poem_id,ordinal));
CREATE UNIQUE INDEX idx_primary_edition ON editions(poem_id) WHERE is_primary=1;
CREATE TABLE poem_units(
 id TEXT PRIMARY KEY,edition_id TEXT REFERENCES editions(id),ordinal INTEGER,kind TEXT,
 text_id INTEGER REFERENCES text_blocks(id),UNIQUE(edition_id,ordinal));
CREATE VIEW edition_passages AS
 SELECT u.id,e.poem_id,u.edition_id,u.ordinal,u.kind,b.body
 FROM poem_units u JOIN editions e ON e.id=u.edition_id JOIN text_blocks b ON b.id=u.text_id;
CREATE TABLE edition_originals(
 edition_id TEXT REFERENCES editions(id),ordinal INTEGER,text_id INTEGER REFERENCES text_blocks(id),
 PRIMARY KEY(edition_id,ordinal)) WITHOUT ROWID;
CREATE TABLE id_aliases(old_id TEXT PRIMARY KEY,poem_id TEXT NOT NULL REFERENCES poem_records(id)) WITHOUT ROWID;
CREATE TABLE review_cautions(
 poem_id TEXT REFERENCES poem_records(id),finding_index INTEGER,field TEXT,body TEXT NOT NULL,
 PRIMARY KEY(poem_id,finding_index)) WITHOUT ROWID;
CREATE TABLE record_archives(
 kind TEXT,id TEXT,codec TEXT NOT NULL CHECK(codec='zlib-json-textrefs-v1'),payload BLOB NOT NULL,
 sha256 TEXT NOT NULL,raw_bytes INTEGER NOT NULL,PRIMARY KEY(kind,id));
CREATE TABLE package_info(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE INDEX idx_poem_author ON poem_records(author_id);
CREATE INDEX idx_poem_dynasty_genre ON poem_records(dynasty,genre);
CREATE INDEX idx_poem_title ON poem_records(title);
CREATE VIEW poems AS SELECT r.rowid,r.id,r.title,r.source_title,a.name AS author,r.author_id,
 r.dynasty,r.format,r.genre,r.genre_basis,r.source,r.body_hash,r.complete,r.ai_generated,
 r.review_status,r.text_scope,
 coalesce((SELECT group_concat(value,'、') FROM
   (SELECT value FROM poem_terms WHERE poem_id=r.id AND kind='collections' ORDER BY ordinal)),'') AS collection,
 (SELECT group_concat(body,char(10)) FROM
   (SELECT body FROM passages WHERE poem_id=r.id AND kind='content' ORDER BY ordinal)) AS content,
 (SELECT group_concat(body,char(10)) FROM
   (SELECT body FROM passages WHERE poem_id=r.id AND kind='translate' ORDER BY ordinal)) AS translate,
 (SELECT group_concat(body,char(10)) FROM
   (SELECT body FROM passages WHERE poem_id=r.id AND kind='notes' ORDER BY ordinal)) AS notes,
 (SELECT group_concat(body,char(10)) FROM
   (SELECT body FROM passages WHERE poem_id=r.id AND kind='appreciation' ORDER BY ordinal)) AS appreciation
 FROM poem_records r JOIN authors a ON a.id=r.author_id;
CREATE VIRTUAL TABLE poems_fts USING fts5(pid UNINDEXED,title,author,content,content='',tokenize='unicode61');
"""


def write_runtime(path, poems, authors, aliases, source_manifest, evidence):
    """Write only a new file. All original record fields survive in archives."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    con = sqlite3.connect(path)
    strings = {}

    def text_id(body):
        # A UNIQUE index on the full text would store large paragraphs twice.
        if body not in strings:
            tid = len(strings) + 1
            con.execute("INSERT INTO text_blocks VALUES(?,?)", (tid, body))
            strings[body] = tid
        return strings[body]

    def archive(kind, rid, record):
        def pack(value):
            if isinstance(value, str):
                return ["s", text_id(value)]
            if isinstance(value, list):
                return ["l", [pack(v) for v in value]]
            if isinstance(value, dict):
                return ["d", {k: pack(v) for k, v in value.items()}]
            return ["v", value]
        raw = encode(record).encode("utf-8")
        references = encode(pack(record)).encode("utf-8")
        con.execute("INSERT INTO record_archives VALUES(?,?,?,?,?,?)",
            (kind, rid, ARCHIVE_CODEC, zlib.compress(references, level=9), hashlib.sha256(raw).hexdigest(), len(raw)))

    try:
        con.executescript(SCHEMA)
        con.execute(f"PRAGMA application_id={APPLICATION_ID}")
        con.execute(f"PRAGMA user_version={RUNTIME_SCHEMA}")
        for a in sorted(authors, key=lambda a: a["id"]):
            con.execute("INSERT INTO authors VALUES(?,?,?,?,?,?,?,?,?,?,?)", (a["id"], a["name"],
                a["dynasty"], a["lifetime"], a["works"], a.get("source_works"), a.get("avatar"),
                a["bio_status"], a["entity_type"], encode(a["dynasties"]), encode(a.get("bio_sources", []))))
            for i, section in enumerate(a["describe"]):
                con.execute("INSERT INTO author_sections VALUES(?,?,?)", (a["id"], i, section["type"]))
                con.executemany("INSERT INTO author_section_text VALUES(?,?,?,?)",
                    [(a["id"], i, n, text_id(s)) for n, s in enumerate(section["content"])])
            archive("author", a["id"], a)
        for rowid, p in enumerate(sorted(poems, key=lambda p: p["id"]), 1):
            con.execute("INSERT INTO poem_records VALUES(" + ",".join("?" for _ in range(17)) + ")",
                (rowid, p["id"], p["title"], p["source_title"], p["author_id"], p["dynasty"], p["format"],
                 p["genre"], p["genre_basis"], p["source"], p["body_hash"], int(p["complete"]),
                 int(p["ai_generated"]), p["review_status"], p["text_scope"], encode(p["reference"]), encode(p["quality_issues"])))
            for kind in ("content", *FIELDS, "original_content"):
                con.executemany("INSERT INTO poem_text VALUES(?,?,?,?)",
                    [(p["id"], kind, i, text_id(s)) for i, s in enumerate(p[kind])])
            for table, column in (("poem_aliases", "aliases"), ("poem_sources", "sources"), ("poem_source_ids", "source_ids")):
                con.executemany(f"INSERT INTO {table} VALUES(?,?,?)", [(p["id"], i, s) for i, s in enumerate(p[column])])
            for kind in ("themes", "collections", "levels", "tags"):
                con.executemany("INSERT INTO poem_terms VALUES(?,?,?,?)", [(p["id"], kind, i, v) for i, v in enumerate(p[kind])])
            for kind in FIELDS:
                meta, alignment = p["field_sources"][kind], p["alignment"][kind]
                con.execute("INSERT INTO annotation_info VALUES(?,?,?,?,?,?,?,?,?,?,?)", (p["id"], kind,
                    meta["type"], meta["review_status"], meta.get("model"), meta.get("source_url"), meta["body_hash"],
                    alignment["mode"], int(alignment["verified"]), int(alignment["equal_length"]), encode(alignment["unit_ids"])))
            for i, e in enumerate(p["editions"]):
                con.execute("INSERT INTO editions VALUES(?,?,?,?,?,?,?,?,?,?,?)", (e["id"], p["id"], i, e["label"],
                    int(e["is_primary"]), e.get("source"), e.get("source_id"), e.get("revision"), e.get("reason"),
                    encode(e["variants"]), encode(e.get("source_evidence", []))))
                con.executemany("INSERT INTO poem_units VALUES(?,?,?,?,?)",
                    [(u["id"], e["id"], u["ordinal"], u["kind"], text_id(u["text"])) for u in e["units"]])
                con.executemany("INSERT INTO edition_originals VALUES(?,?,?)",
                    [(e["id"], n, text_id(s)) for n, s in enumerate(e["original_content"])])
            for caution in p.get("content_review", {}).get("final_review", {}).get("cautions", []):
                con.execute("INSERT INTO review_cautions VALUES(?,?,?,?)",
                    (p["id"], caution["finding_index"], caution["field"], caution["text"]))
            con.execute("INSERT INTO poems_fts(rowid,pid,title,author,content) VALUES(?,?,?,?,?)", (rowid, None,
                fts_text("\n".join([p["title"]] + p["aliases"])), fts_text(p["author"]), fts_text("\n".join(p["content"]))))
            archive("poem", p["id"], p)
        con.executemany("INSERT INTO id_aliases VALUES(?,?)", sorted(aliases.items()))
        archive("package", "source_manifest", source_manifest)
        archive("package", "source_evidence", evidence)
        info = dict(profile="app-runtime", runtime_schema=RUNTIME_SCHEMA, source_data_version=source_manifest["data_version"],
            archive_codec=ARCHIVE_CODEC, preservation="All source poem/author fields retained losslessly in record_archives")
        con.executemany("INSERT INTO package_info VALUES(?,?)", [(k, encode(v)) for k, v in sorted(info.items())])
        con.execute("INSERT INTO poems_fts(poems_fts) VALUES('optimize')")
        con.execute("INSERT INTO poems_fts(poems_fts) VALUES('integrity-check')")
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


def validate_runtime(path, poems, authors, aliases, source_manifest, evidence):
    """Check every record and every queryable paragraph against the full package."""
    con = connect_readonly(path)
    cache = {}
    try:
        if (con.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or con.execute("PRAGMA user_version").fetchone()[0] != RUNTIME_SCHEMA):
            raise ValueError("Unexpected runtime database profile")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or con.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Runtime SQLite integrity failure")
        if dict(con.execute("SELECT old_id,poem_id FROM id_aliases")) != aliases:
            raise ValueError("Runtime aliases differ")
        ids = {p["id"] for p in poems}
        if {r[0] for r in con.execute("SELECT id FROM poems")} != ids:
            raise ValueError("Runtime poem IDs differ")
        if {r[0] for r in con.execute("SELECT id FROM authors")} != {a["id"] for a in authors}:
            raise ValueError("Runtime author IDs differ")
        if con.execute("SELECT COUNT(*) FROM record_archives").fetchone()[0] != len(poems) + len(authors) + 2:
            raise ValueError("Runtime archive count differs")
        main_columns = ("id", "title", "source_title", "author_id", "dynasty", "format", "genre", "genre_basis",
                        "source", "body_hash", "complete", "ai_generated", "review_status", "text_scope")
        native = {r[0]: r for r in con.execute("SELECT " + ",".join(main_columns) + " FROM poem_records")}
        views = {r[0]: r[1:] for r in con.execute("SELECT id,author,collection,content,translate,notes,appreciation FROM poems")}
        for p in poems:
            pid = p["id"]
            if native[pid] != tuple(p[k] for k in main_columns):
                raise ValueError(f"Runtime poem fields differ: {pid}")
            if views[pid] != (p["author"], "、".join(p["collections"]), *("\n".join(p[k]) for k in ("content", *FIELDS))):
                raise ValueError(f"Runtime reading view differs: {pid}")
            if read_archive(con, "poem", pid, cache) != p:
                raise ValueError(f"Runtime poem archive differs: {pid}")
            for kind in ("content", *FIELDS, "original_content"):
                lines = [r[0] for r in con.execute("SELECT body FROM passages WHERE poem_id=? AND kind=? ORDER BY ordinal", (pid, kind))]
                if lines != p[kind]:
                    raise ValueError(f"Runtime paragraphs differ: {pid}:{kind}")
            for table, column, key in (("poem_aliases", "title", "aliases"), ("poem_sources", "url", "sources"), ("poem_source_ids", "source_id", "source_ids")):
                if [r[0] for r in con.execute(f"SELECT {column} FROM {table} WHERE poem_id=? ORDER BY ordinal", (pid,))] != p[key]:
                    raise ValueError(f"Runtime source/alias differs: {pid}:{key}")
            for kind in ("themes", "collections", "levels", "tags"):
                if [r[0] for r in con.execute("SELECT value FROM poem_terms WHERE poem_id=? AND kind=? ORDER BY ordinal", (pid, kind))] != p[kind]:
                    raise ValueError(f"Runtime terms differ: {pid}:{kind}")
            stored = con.execute("SELECT id,label,is_primary,variants_json FROM editions WHERE poem_id=? ORDER BY ordinal", (pid,)).fetchall()
            if stored != [(e["id"], e["label"], int(e["is_primary"]), encode(e["variants"])) for e in p["editions"]]:
                raise ValueError(f"Runtime editions differ: {pid}")
            for e in p["editions"]:
                units = con.execute("SELECT id,ordinal,kind,body FROM edition_passages WHERE edition_id=? ORDER BY ordinal", (e["id"],)).fetchall()
                if units != [(u["id"], u["ordinal"], u["kind"], u["text"]) for u in e["units"]]:
                    raise ValueError(f"Runtime units differ: {e['id']}")
                originals = [r[0] for r in con.execute("SELECT b.body FROM edition_originals o JOIN text_blocks b ON b.id=o.text_id WHERE o.edition_id=? ORDER BY o.ordinal", (e["id"],))]
                if originals != e["original_content"]:
                    raise ValueError(f"Runtime edition originals differ: {e['id']}")
            expected_cautions = p.get("content_review", {}).get("final_review", {}).get("cautions", [])
            actual_cautions = con.execute("SELECT finding_index,field,body FROM review_cautions WHERE poem_id=? ORDER BY finding_index", (pid,)).fetchall()
            if actual_cautions != sorted((c["finding_index"], c["field"], c["text"]) for c in expected_cautions):
                raise ValueError(f"Runtime cautions differ: {pid}")
            for kind in FIELDS:
                a = p["alignment"][kind]
                m = p["field_sources"][kind]
                actual = con.execute("SELECT source_type,review_status,model,source_url,body_hash,alignment_mode,alignment_verified,equal_length,unit_ids_json FROM annotation_info WHERE poem_id=? AND kind=?", (pid, kind)).fetchone()
                expected = (m["type"], m["review_status"], m.get("model"), m.get("source_url"), m["body_hash"], a["mode"], int(a["verified"]), int(a["equal_length"]), encode(a["unit_ids"]))
                if actual != expected:
                    raise ValueError(f"Runtime annotation provenance differs: {pid}:{kind}")
        for a in authors:
            if read_archive(con, "author", a["id"], cache) != a:
                raise ValueError(f"Runtime author archive differs: {a['id']}")
            native_author = con.execute("SELECT name,dynasty,lifetime,works,source_works,avatar,bio_status,entity_type,dynasties_json,bio_sources_json FROM authors WHERE id=?", (a["id"],)).fetchone()
            expected_author = tuple(a.get(k) for k in ("name", "dynasty", "lifetime", "works", "source_works", "avatar", "bio_status", "entity_type")) + (encode(a["dynasties"]), encode(a.get("bio_sources", [])))
            if native_author != expected_author:
                raise ValueError(f"Runtime author fields differ: {a['id']}")
            sections = con.execute("SELECT ordinal,kind FROM author_sections WHERE author_id=? ORDER BY ordinal", (a["id"],)).fetchall()
            if sections != [(i, s["type"]) for i, s in enumerate(a["describe"])]:
                raise ValueError(f"Runtime author sections differ: {a['id']}")
            for i, s in enumerate(a["describe"]):
                lines = [r[0] for r in con.execute("SELECT b.body FROM author_section_text x JOIN text_blocks b ON b.id=x.text_id WHERE x.author_id=? AND x.section_ordinal=? ORDER BY x.ordinal", (a["id"], i))]
                if lines != s["content"]:
                    raise ValueError(f"Runtime author text differs: {a['id']}:{i}")
        for rid, value in (("source_manifest", source_manifest), ("source_evidence", evidence)):
            if read_archive(con, "package", rid, cache) != value:
                raise ValueError(f"Runtime package archive differs: {rid}")
        if con.execute("SELECT COUNT(*) FROM poems_fts").fetchone()[0] != len(poems):
            raise ValueError("Runtime search row count differs")
        return dict(poems=len(poems), authors=len(authors), editions=sum(len(p["editions"]) for p in poems),
            units=sum(len(e["units"]) for p in poems for e in p["editions"]), aliases=len(aliases),
            cautions=con.execute("SELECT COUNT(*) FROM review_cautions").fetchone()[0],
            author_sections=con.execute("SELECT COUNT(*) FROM author_sections").fetchone()[0],
            full_record_equality=True, reading_text_equality=True, originals_preserved=True,
            foreign_keys="ok", integrity="ok")
    finally:
        con.close()
