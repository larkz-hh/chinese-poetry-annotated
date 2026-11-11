"""Regression checks for note formatting, source guards and review replay."""
import copy
import unittest

from data_utils import body_hash
from notes_format import apply_notes_normalization, normalize_notes, notes_hash, NOTES_FORMAT
from prepare_review_resolutions import prepare
from review_application import apply_resolution, input_hash, reviewed_input


class NotesFormatTests(unittest.TestCase):
    def poem(self, notes, content=None):
        content=content or ['君自故乡来，应知故乡事。', '来日绮窗前，寒梅著花未？']
        return dict(id='p', title='杂诗', author='王维', content=content, body_hash=body_hash(content),
            notes=notes, translate=['译文'], appreciation=['赏析'], quality_issues=[],
            field_sources={k:dict(type='original',body_hash=body_hash(content),review_status='unreviewed')
                           for k in ('translate','notes','appreciation')},
            alignment={k:dict(mode='document',verified=False,equal_length=False,unit_ids=[])
                       for k in ('translate','notes','appreciation')})

    def record(self, poem, after):
        return dict(body_hash=poem['body_hash'],before=list(poem['notes']),after=after,
                    before_hash=notes_hash(poem['notes']),after_hash=notes_hash(after),semantic_change=False)

    def test_placeholder_removed_and_readings_kept_with_lemmas(self):
        poem=self.poem(['君自故乡来，应知故乡事。',
            '来日绮(qǐ)窗前，寒梅著(zhuó)花未？来日：来的时候。绮窗：雕花窗户。著花：开花。'])
        after,operations=normalize_notes(poem)
        self.assertEqual(after,['来日：来的时候。','绮（qǐ）窗：雕花窗户。','著（zhuó）花：开花。'])
        self.assertEqual(len(operations[0]['removed_body_quotes']),1)

    def test_quoted_speech_in_body_is_removed_as_a_whole(self):
        verse='子曰：“学而时习之，不亦说乎？”《学而》'
        after,_=normalize_notes(self.poem([verse+'子：先生，指孔子。'],[verse]))
        self.assertEqual(after,['子：先生，指孔子。'])

    def test_nested_quotes_and_decimal_explanation_survive(self):
        text='说明：古籍记载：“甲：乙。丙：丁。”据此说明。长：约1.5尺。'
        after,_=normalize_notes(self.poem([text]))
        self.assertEqual(after,['说明：古籍记载：“甲：乙。丙：丁。”据此说明。','长：约1.5尺。'])

    def test_variant_and_definition_quote_are_retained(self):
        notes=['“来日”句：一作“来时”。','来日：指“来的时候”，不是“明日”。']
        after,_=normalize_notes(self.poem(notes))
        self.assertEqual(after,notes)

    def test_empty_pinyin_parentheses_do_not_block_source_matching(self):
        poem=self.poem(['迸泉飒()飒飞木末，野鹿呦()呦走堂下。迸泉：喷泉。'],
                       ['迸泉飒飒飞木末，野鹿呦呦走堂下。'])
        self.assertEqual(normalize_notes(poem)[0],['迸泉：喷泉。'])

    def test_comma_definitions_split_without_splitting_explanation_commas(self):
        poem=self.poem(['绮，雕花，精美的花纹；寒梅，寒冬的梅花。'])
        self.assertEqual(normalize_notes(poem)[0],['绮：雕花，精美的花纹。','寒梅：寒冬的梅花。'])
        poem['notes']=['绮：雕花。寒梅 ： 冬梅。']
        self.assertEqual(normalize_notes(poem)[0],['绮：雕花。','寒梅：冬梅。'])

    def test_variant_prefix_is_detached_before_splitting_definitions(self):
        poem=self.poem(['(馀（yú） 一作 余)绮窗:雕花窗。寒梅：冬梅。'])
        after=normalize_notes(poem)[0]
        self.assertEqual(after,['异文：馀（yú） 一作 余。','绮窗：雕花窗。','寒梅：冬梅。'])
        poem['notes']=after
        self.assertEqual(normalize_notes(poem)[0],after)

    def test_replay_rejects_stale_body_notes_hash_and_empty_output(self):
        poem=self.poem(['绮窗：雕花的窗户。'])
        record=self.record(poem,['绮窗：雕花窗。'])
        for key,value in [('body_hash','stale'),('before_hash','stale'),('after_hash','stale'),('after',[])]:
            bad=copy.deepcopy(record)
            bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                apply_notes_normalization(copy.deepcopy(poem),{'p':bad})
        poem['notes']=['未经记录的修改']
        with self.assertRaises(ValueError):
            apply_notes_normalization(poem,{'p':record})

    def test_formatting_preserves_origin_and_initial_review_preimage(self):
        poem=self.poem(['君自故乡来，应知故乡事。','绮窗：雕花窗。'])
        original=copy.deepcopy(poem)
        records={'p':self.record(poem,['绮窗：雕花窗。'])}
        reviews={'p':dict(input_hash=input_hash(poem),model='test',findings=[])}
        approvals=dict(reviewed_at='2026-11-11',edits=[],rejections=[])
        resolution=prepare([poem],reviews,{},approvals,{}, {},notes_normalizations=records)
        apply_resolution(poem,resolution['p'])
        self.assertEqual(poem['field_sources']['notes']['type'],'original')
        self.assertEqual(poem['field_sources']['notes']['display_format'],NOTES_FORMAT)
        self.assertNotIn('format_repaired',poem['field_sources']['notes'])
        self.assertEqual(input_hash(reviewed_input(poem,resolution['p'])),input_hash(original))
        again=prepare([poem],reviews,{},approvals,{},resolution,notes_normalizations=records)
        self.assertEqual(again,resolution)
        once=copy.deepcopy(poem)
        apply_resolution(poem,again['p'])
        self.assertEqual(poem,once)

    def test_semantic_addition_requires_evidence_and_changes_provenance(self):
        poem=self.poem(['翟衣。'])
        record=self.record(poem,['翟衣：以翟羽为饰的礼服。'])
        record['semantic_change']=True
        with self.assertRaises(ValueError):
            apply_notes_normalization(copy.deepcopy(poem),{'p':record})
        record['evidence']=['https://example.test/classic']
        reviews={'p':dict(input_hash=input_hash(poem),model='test',findings=[])}
        resolution=prepare([poem],reviews,{},dict(reviewed_at='2026-11-11'),{}, {},
                           notes_normalizations={'p':record})
        apply_resolution(poem,resolution['p'])
        self.assertEqual(poem['field_sources']['notes']['type'],'ai_editorial')
        self.assertTrue(poem['content_review']['notes_normalization']['semantic_change'])

    def test_partial_normalization_coverage_is_rejected(self):
        poem=self.poem(['绮窗：雕花窗。'])
        reviews={'p':dict(input_hash=input_hash(poem),model='test',findings=[])}
        with self.assertRaises(ValueError):
            prepare([poem],reviews,{},dict(reviewed_at='2026-11-11'),{}, {},notes_normalizations={})

    def test_splitting_terms_is_not_marked_as_a_character_array_repair(self):
        poem=self.poem(['绮窗：雕花窗。寒梅：冬梅。'])
        records={'p':self.record(poem,['绮窗：雕花窗。','寒梅：冬梅。'])}
        reviews={'p':dict(input_hash=input_hash(poem),model='test',findings=[])}
        result=prepare([poem],reviews,{},dict(reviewed_at='2026-11-11'),{}, {},notes_normalizations=records)
        apply_resolution(poem,result['p'])
        self.assertNotIn('format_repaired',poem['field_sources']['notes'])


if __name__=='__main__':
    unittest.main()
