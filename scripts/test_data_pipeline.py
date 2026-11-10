"""Regression tests for identity, version handling, provenance and search."""
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from build import build, combine, norm
from data_utils import ROOT, annotation_valid, editions, fts_text, match_query
from search import search
from validate_data import validate
from content_review import apply_catalog
from data_utils import body_hash


class IdentityTests(unittest.TestCase):
    def row(self, pid, title="绝句", content=None):
        return norm(dict(_id={"$oid": pid}, name=title, author="杜甫", dynasty="唐代",
                         content=content or ["迟日江山丽，春风花草香。"], tags=[]))

    def test_same_title_is_not_the_identity_key(self):
        from data_utils import identity_body
        a = self.row("old")
        b = self.row("new", content=["两个黄鹂鸣翠柳，一行白鹭上青天。"])
        self.assertNotEqual(identity_body(a["content"]), identity_body(b["content"]))

    def test_same_primary_with_extra_versions_can_share_identity(self):
        from data_utils import work_body
        self.assertEqual(work_body(["正文。(版本一)", "异文。(版本二)"]), work_body(["正文。 "]))

    def test_legacy_id_wins_but_fields_and_tags_are_merged(self):
        a, b = self.row("old"), self.row("new", title="绝句二首·其一")
        b["translate"] = ["明丽的春光照着江山。"]
        b["tags"] = ["春天"]
        merged = combine(a, b, {"old": 0})
        self.assertEqual(merged["id"], "old")
        self.assertEqual(set(merged["source_ids"]), {"old", "new"})
        self.assertEqual(merged["tags"], ["春天"])
        self.assertIn("绝句二首·其一", merged["aliases"])
        self.assertEqual(merged["translate"], b["translate"])

    def test_invalid_annotation_does_not_count_as_valid(self):
        self.assertFalse(annotation_valid(["山一程水一程"], ["山一程，水一程。 "]))
        self.assertFalse(annotation_valid(["不完整�"], ["原文"]))
        self.assertFalse(annotation_valid([""], ["原文"]))

    def test_full_ingest_keeps_two_works_and_merges_a_repeated_source(self):
        with tempfile.TemporaryDirectory(prefix=".stage-test-", dir=ROOT) as folder:
            path = Path(folder).resolve()
            path.relative_to(ROOT.resolve())
            source = path / "source"
            source.mkdir()
            first = dict(_id={"$oid": "first"}, name="绝句", author="杜甫", dynasty="唐代",
                         content=["迟日江山丽，春风花草香。"], sourceLink="https://example.test/shiwenv_first.aspx")
            second = dict(first, _id={"$oid": "second"}, content=["两个黄鹂鸣翠柳，一行白鹭上青天。"], sourceLink="https://example.test/shiwenv_second.aspx")
            repeated = dict(first, _id={"$oid": "duplicate"}, tags=["春天"])
            for i, rows in enumerate(([first, second], [repeated], [], []), 1):
                (source / f"poems{i}.json").write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
            for name in ("poems-authors.json", "poems-cipai.json"):
                (source / name).write_text("", encoding="utf-8")
            baseline = path / "legacy.json"
            baseline.write_text(json.dumps([dict(id="first", title="绝句", author="杜甫")], ensure_ascii=False), encoding="utf-8")
            report = build(source, path / "raw", baseline)
            self.assertEqual(report["works"], 2)
            rows = json.loads((path / "raw/poems_lite.json").read_text(encoding="utf-8"))
            self.assertEqual({row["id"] for row in rows}, {"first", "second"})
            self.assertIn("duplicate", next(row for row in rows if row["id"] == "first")["source_ids"])

    def test_explicit_versions_split_and_raw_text_survives(self):
        raw = ["清晨入古寺。", "但余钟磬音。(版本一)", "清晨入古寺。", "惟余钟磬音。(版本二)"]
        result = editions("p", raw)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["content"], ["清晨入古寺。", "但余钟磬音。"])
        self.assertEqual(result[0]["original_content"], raw[:2])
        self.assertTrue(result[0]["is_primary"])
        self.assertFalse(result[1]["is_primary"])

    def test_standalone_variant_is_not_a_poem_line(self):
        result = editions("p", ["天阶夜色凉如水。", "(天阶 一作：天街)"])
        self.assertEqual(result[0]["content"], ["天阶夜色凉如水。"])
        self.assertEqual(result[0]["variants"][0]["text"], "天阶 一作：天街")

    def test_reviewed_merge_preserves_sources_and_does_not_mutate_raw(self):
        a, b = self.row("a"), self.row("b", content=["迟日江山丽，春风花草香！"])
        original = copy.deepcopy([a, b])
        policy = {"works": {"a": {"expected_body_hash": body_hash(a["content"]), "status": "text_compared"},
                            "b": {"expected_body_hash": body_hash(b["content"]), "merge_into": "a", "reason": "核对异文"}}}
        result = apply_catalog([a, b], policy)
        self.assertEqual(len(result), 1)
        self.assertEqual(set(result[0]["source_ids"]), {"a", "b"})
        self.assertEqual(result[0]["alternate_contents"][0]["content"], b["content"])
        self.assertEqual([a, b], original)

    def test_stale_review_cannot_silently_merge_changed_text(self):
        row = self.row("a")
        with self.assertRaises(ValueError):
            apply_catalog([row], {"works": {"a": {"expected_body_hash": "outdated"}}})

    def test_review_does_not_merge_across_authors(self):
        a, b = self.row("a"), self.row("b")
        b["author"] = "王维"
        with self.assertRaises(ValueError):
            apply_catalog([a, b], {"works": {"b": {"merge_into": "a", "reason": "invalid"}}})

    def test_attribution_correction_preserves_source_name(self):
        row = self.row("a")
        result = apply_catalog([row], {"works": {"a": {"author": "佚名", "reason": "来源书名不是作者"}}})
        self.assertEqual(result[0]["source_author"], "杜甫")
        self.assertEqual(result[0]["author"], "佚名")


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute("CREATE VIRTUAL TABLE terms USING fts5(body)")
        self.con.executemany("INSERT INTO terms VALUES(?)", [(fts_text(s),) for s in ["床前明月光", "匪东方则明，月出之光", "𠮷明月"]])

    def tearDown(self):
        self.con.close()

    def count(self, keyword):
        query = match_query(keyword)
        return self.con.execute("SELECT COUNT(*) FROM terms WHERE terms MATCH ?", (query,)).fetchone()[0] if query else 0

    def test_phrase_does_not_cross_punctuation(self):
        self.assertEqual(self.count("明月"), 2)
        self.assertEqual(self.count("床前明月光"), 1)

    def test_user_fts_syntax_is_literal(self):
        self.assertEqual(self.count('明月"'), 2)
        for keyword in ('" OR *', "", "   ", "()", '"NEAR(a b)'):
            self.assertEqual(self.count(keyword), 0)

    def test_astral_characters_and_column_whitelist(self):
        self.assertEqual(self.count("𠮷"), 1)
        with self.assertRaises(ValueError):
            match_query("明月", "body OR 1=1")


class PublishedPackageTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "app-data/manifest.json").exists(), "v3 package not published yet")
    def test_published_package_contract(self):
        report = validate(ROOT / "app-data", baseline=ROOT / "backups/pre-v3/app-data/poems.json")
        self.assertEqual(report["errors"], [])

    @unittest.skipUnless((ROOT / "app-data/manifest.json").exists(), "v3 package not published yet")
    def test_distinct_works_are_restored_and_legacy_ids_resolve(self):
        poems = json.loads((ROOT / "app-data/poems.json").read_text(encoding="utf-8"))
        for line in ("迟日江山丽", "两个黄鹂鸣翠柳", "紫泉宫殿锁烟霞"):
            self.assertTrue(any(any(line in s for s in p["content"]) for p in poems), line)
        migrations = json.loads((ROOT / "app-data/id_map.json").read_text(encoding="utf-8"))
        old = json.loads((ROOT / "backups/pre-v3/app-data/poems.json").read_text(encoding="utf-8"))
        self.assertTrue(all(p["id"] in migrations for p in old))
        self.assertEqual(len(search(ROOT / "app-data/poems.db", "静夜思", "title")), 1)


if __name__ == "__main__":
    unittest.main()
