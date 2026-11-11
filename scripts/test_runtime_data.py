"""Contract tests for a separate, lossless App database."""
import copy
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_v2 import write_sqlite
from data_utils import ROOT, FIELDS, SCHEMA_VERSION, body_hash, dump
from export_app_runtime import export, verify_source
from runtime_db import write_runtime, read_archive, connect_readonly, validate_runtime
from search import search


def fixture():
    author = dict(id="a", name="文人", dynasty="唐", dynasties=["唐"], lifetime="作者简介",
        works=1, source_works=3, avatar="", bio_status="source_checked", entity_type="person",
        describe=[dict(type="生平", content=["相同段落", "另一段落", "相同段落"])],
        bio_sources=["https://example.test/author"], arbitrary_metadata={"$text": [1, True, None, "𠮷"]})
    content = ["匪东方则明，月出之光。", "𠮷明月，春风。"]
    versions = []
    for n, lines in enumerate((["旧正文"], content), 1):
        eid = f"p:v{n}"
        versions.append(dict(id=eid, label="旧本" if n == 1 else "校本", content=lines,
            original_content=lines, variants=[], is_primary=n == 2,
            units=[dict(id=f"{eid}:u{i+1}", ordinal=i, kind="passage", text=s) for i, s in enumerate(lines)]))
    poem = dict(id="p", title="测试·𠮷", source_title="旧题", aliases=["旧题"], author="文人", author_id="a",
        dynasty="唐", format="古体", genre="诗", genre_basis="test", source="https://example.test/p",
        sources=["https://example.test/p"], source_ids=["p", "old-p"], reference=[{"text": "参考资料"}],
        body_hash=body_hash(content), content=content, original_content=["旧正文"], editions=versions,
        translate=["译文", "译文"], notes=["相同段落", "相同段落"], appreciation=["鉴赏"],
        collections=["选集"], themes=["月亮"], levels=["小学"], tags=["月亮", "选集", "小学"],
        complete=True, ai_generated=True, review_status="editorially_reviewed", text_scope="source_corrected",
        quality_issues=[], field_sources={k:dict(type="ai_editorial", review_status="editorially_reviewed",
            model="test", source_url=None, body_hash=body_hash(content)) for k in FIELDS},
        alignment={k:dict(mode="document", verified=False, equal_length=False, unit_ids=[]) for k in FIELDS},
        famous_lines=[dict(id="p:q1", text="月出之光。𠮷明月，", unit_ids=["p:v2:u1", "p:v2:u2"],
            source_url="https://example.test/quote")],
        content_review=dict(academic_review_complete=False, decisions=[dict(reason="原始审核理由")],
            final_review=dict(cautions=[dict(finding_index=0, field="notes", text="解释存在分歧")])) )
    return [poem], [author], {"p": "p", "old-p": "p"}, {"data_version": f"{SCHEMA_VERSION}.test", "schema_version": SCHEMA_VERSION}, {"sources": {"e1": {"excerpt": "古籍原文"}}}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix=".stage-test-runtime-", dir=ROOT)
        self.path = Path(self.folder.name)
        self.args = fixture()
        self.db = self.path / "runtime.db"
        write_runtime(self.db, *self.args)

    def tearDown(self):
        self.folder.cleanup()

    def test_full_records_and_native_paragraphs_survive_without_loss(self):
        report = validate_runtime(self.db, *self.args)
        self.assertTrue(report["full_record_equality"])
        self.assertTrue(report["originals_preserved"])
        con = connect_readonly(self.db)
        try:
            self.assertEqual(read_archive(con, "poem", "p"), self.args[0][0])
            self.assertEqual(read_archive(con, "author", "a"), self.args[1][0])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM text_blocks WHERE body='相同段落'").fetchone()[0], 1)
            self.assertEqual([r[0] for r in con.execute("SELECT body FROM passages WHERE poem_id='p' AND kind='notes' ORDER BY ordinal")], ["相同段落", "相同段落"])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM review_cautions").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM editions").fetchone()[0], 2)
        finally:
            con.close()

    def test_existing_search_has_the_same_results_on_both_profiles(self):
        full = self.path / "full.db"
        poems, authors, aliases, _, _ = self.args
        write_sqlite(full, poems, authors, aliases)
        for keyword, column in (("明月", None), ("则明月", None), ("𠮷", None), ("旧题", "title"),
                                ("春风", "content"), ("文人", "author"), ('" OR *', None)):
            self.assertEqual(search(self.db, keyword, column), search(full, keyword, column), keyword)

    def test_archive_detects_changed_shared_text(self):
        con = sqlite3.connect(self.db)
        con.execute("UPDATE text_blocks SET body='未经授权的修改' WHERE body='原始审核理由'")
        con.commit()
        try:
            with self.assertRaises(ValueError):
                read_archive(con, "poem", "p")
        finally:
            con.close()

    def test_reading_view_keeps_empty_collection_as_empty_text(self):
        poems, authors, aliases, manifest, evidence = copy.deepcopy(self.args)
        poems[0]["collections"] = []
        target = self.path / "empty-collection.db"
        write_runtime(target, poems, authors, aliases, manifest, evidence)
        validate_runtime(target, poems, authors, aliases, manifest, evidence)
        con = connect_readonly(target)
        try:
            self.assertEqual(con.execute("SELECT collection FROM poems WHERE id='p'").fetchone()[0], "")
        finally:
            con.close()

    def test_build_is_deterministic_and_does_not_mutate_source_objects(self):
        original = copy.deepcopy(self.args)
        second = self.path / "second.db"
        write_runtime(second, *self.args)
        self.assertEqual(self.args, original)
        self.assertEqual(hashlib.sha256(second.read_bytes()).digest(), hashlib.sha256(self.db.read_bytes()).digest())
        with self.assertRaises(FileExistsError):
            write_runtime(self.db, *self.args)

    def test_export_cannot_overwrite_full_package_or_unrelated_database(self):
        with self.assertRaises(ValueError):
            export(self.path, self.path)
        with self.assertRaises(ValueError):
            export(self.path, self.path / "inside-source")
        source = self.path / "source"
        target = self.path / "unrelated"
        target.mkdir()
        (target / "poems.db").write_bytes(b"unrelated")
        with self.assertRaises(ValueError):
            export(source, target)
        self.assertEqual((target / "poems.db").read_bytes(), b"unrelated")

    def test_changed_source_checksum_stops_export(self):
        source = self.path / "source"
        source.mkdir()
        (source / "poems.json").write_bytes(b"changed")
        dump(source / "manifest.json", dict(schema_version=SCHEMA_VERSION, files={"poems.json":dict(sha256="stale")}))
        with self.assertRaises(ValueError):
            verify_source(source)


class DiagnosticImportTests(unittest.TestCase):
    def test_manual_api_diagnostic_does_not_read_credentials_or_call_api_on_import(self):
        path = Path(__file__).with_name("test_llm.py")
        source = path.read_text(encoding="utf-8")
        with patch("builtins.open") as opened, patch("urllib.request.urlopen") as request:
            exec(compile(source, str(path), "exec"), {"__name__": "diagnostic_import"})
        opened.assert_not_called()
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
