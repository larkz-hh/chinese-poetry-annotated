"""Contracts for curated excerpts, source units and both SQLite packages."""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_v2 import write_sqlite
from data_utils import ROOT
from famous_lines import attach_famous_lines, validate_famous_lines, validate_famous_line_tables
from runtime_db import write_runtime, validate_runtime, connect_readonly, read_archive
from test_runtime_data import fixture


class FamousLineTests(unittest.TestCase):
    def setUp(self):
        self.poems, self.authors, self.aliases, self.manifest, self.evidence = fixture()

    def catalog(self):
        p = self.poems[0]
        return dict(schema_version=1, works={p['id']:dict(body_hash=p['body_hash'], famous_lines=copy.deepcopy(p['famous_lines']))})

    def test_empty_and_multiple_selections_preserve_stable_ids(self):
        original = copy.deepcopy(self.poems[0])
        catalog = self.catalog()
        second = dict(id='p:q7', text='春风。', unit_ids=['p:v2:u2'], source_url='https://example.test/q7')
        catalog['works']['p']['famous_lines'].append(second)
        attach_famous_lines(self.poems, catalog)
        self.assertEqual([q['id'] for q in self.poems[0]['famous_lines']], ['p:q1','p:q7'])
        catalog['works']['p']['famous_lines'].reverse()
        attach_famous_lines(self.poems, catalog)
        self.assertEqual([q['id'] for q in self.poems[0]['famous_lines']], ['p:q7','p:q1'])
        attach_famous_lines(self.poems, dict(schema_version=1, works={}))
        self.assertEqual(self.poems[0]['famous_lines'], [])
        self.assertEqual({k:v for k,v in self.poems[0].items() if k != 'famous_lines'},
                         {k:v for k,v in original.items() if k != 'famous_lines'})

    def test_stale_body_and_missing_work_are_rejected(self):
        catalog = self.catalog()
        catalog['works']['p']['body_hash'] = 'stale'
        with self.assertRaises(ValueError):
            attach_famous_lines(self.poems, catalog)
        catalog = self.catalog()
        catalog['works']['missing'] = catalog['works'].pop('p')
        with self.assertRaises(ValueError):
            attach_famous_lines(self.poems, catalog)

    def test_changed_text_and_invalid_primary_unit_spans_are_rejected(self):
        mutations = [dict(text='不存在于正文的名句'), dict(text='月出之光，𠮷明月，'),
            dict(unit_ids=['other:v2:u1']), dict(unit_ids=['p:v1:u1']),
            dict(unit_ids=['p:v2:u2','p:v2:u1']), dict(unit_ids=['p:v2:u1','p:v2:u1']),
            dict(text='春风。')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                poems = copy.deepcopy(self.poems)
                poems[0]['famous_lines'][0].update(mutation)
                with self.assertRaises(ValueError):
                    validate_famous_lines(poems)

    def test_duplicate_ids_text_and_invalid_sources_are_rejected(self):
        for mutation in ({}, dict(id='p:q2'), dict(source_url='javascript:invalid'), dict(id='foreign:q1')):
            poems = copy.deepcopy(self.poems)
            if mutation in ({}, dict(id='p:q2')):
                second = copy.deepcopy(poems[0]['famous_lines'][0])
                second.update(mutation)
                poems[0]['famous_lines'].append(second)
            else:
                poems[0]['famous_lines'][0].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_famous_lines(poems)

    def test_both_databases_provide_identical_card_queries_and_exact_unit_order(self):
        with tempfile.TemporaryDirectory(prefix='.stage-quotes-', dir=ROOT) as folder:
            path = Path(folder).resolve()
            path.relative_to(ROOT.resolve())
            full, runtime = path/'full.db', path/'runtime.db'
            write_sqlite(full, self.poems, self.authors, self.aliases)
            write_runtime(runtime, self.poems, self.authors, self.aliases, self.manifest, self.evidence)
            results = []
            for database in (full, runtime):
                con = connect_readonly(database)
                try:
                    validate_famous_line_tables(con, self.poems)
                    results.append(con.execute('SELECT q.id,q.text,p.title,p.author FROM famous_lines q JOIN poems p ON p.id=q.poem_id ORDER BY q.id').fetchall())
                    self.assertEqual(con.execute('SELECT unit_id FROM famous_line_units WHERE quote_id=? ORDER BY ordinal', ('p:q1',)).fetchall(), [('p:v2:u1',),('p:v2:u2',)])
                finally:
                    con.close()
            self.assertEqual(results[0], results[1])
            con = connect_readonly(runtime)
            try:
                self.assertEqual(read_archive(con, 'poem', 'p')['famous_lines'], self.poems[0]['famous_lines'])
            finally:
                con.close()
            con = sqlite3.connect(runtime)
            con.execute("UPDATE famous_lines SET text='被篡改的摘录' WHERE id='p:q1'")
            con.commit()
            con.close()
            with self.assertRaises(ValueError):
                validate_runtime(runtime, self.poems, self.authors, self.aliases, self.manifest, self.evidence)

    @unittest.skipUnless((ROOT/'raw/famous_lines.json').exists(), 'No published curation file')
    def test_rebuild_cannot_silently_drop_published_selections(self):
        import build_v2
        real_load = build_v2.load
        if not any(p.get('famous_lines') for p in real_load(ROOT/'app-data/poems.json')):
            self.skipTest('No published selections yet')

        def missing_curation(path, default=None):
            if Path(path).name == 'famous_lines.json':
                return dict(schema_version=1, works={})
            return real_load(path, default)

        with tempfile.TemporaryDirectory(prefix='.stage-missing-quotes-', dir=ROOT) as folder:
            path = Path(folder).resolve()
            path.relative_to(ROOT.resolve())
            with patch('build_v2.load', side_effect=missing_curation), self.assertRaisesRegex(ValueError, 'Existing famous lines lost'):
                build_v2.build(ROOT/'raw', path)


if __name__ == '__main__':
    unittest.main()
