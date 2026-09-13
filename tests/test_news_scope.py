import copy
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_dashboard as g
from news_scope import classify_scope
from verify_ai_scope import CASES, main as verify_live_scope


def packaging_item():
    _, _, title, company, body = next(case for case in CASES if case[0] == 'packaging_inspection')
    return dict(title=title, company=company, source_excerpt=body, summary=body,
                date='2026-09-11', publisher_date='2026-09-11',
                published_at='2026-09-11T00:00:00Z', publisher_published_at='2026-09-11T00:00:00Z',
                publication_date_status='verified', fulltext_status='excerpt_extracted',
                url='https://www.aandd.co.jp/whatsnew/event/test/',
                source_kind='manufacturer_official', source_name='A&D', category_id='④', confidence='高')


class ScopePolicyTests(unittest.TestCase):
    def test_all_contract_subjects_have_deterministic_decisions(self):
        for name, expected, title, company, body in CASES:
            with self.subTest(name=name):
                decision = classify_scope(title, body, company)
                self.assertEqual(decision['verdict'], 'include' if expected else 'exclude')
                self.assertTrue(decision['rule'])

    def test_explicit_equipment_survives_repeated_model_misjudgment(self):
        rejection = 'IRRELEVANT: 包装検査技術についても製造・物流向けの具体性が不足する'
        with patch.object(g, '_openrouter_generate', return_value=rejection) as model, \
                patch.object(g, 'audit_item') as audit:
            for case in [case for case in CASES if case[1]]:
                for _ in range(5):
                    candidate = packaging_item()
                    candidate.update(title=case[2], company=case[3], source_excerpt=case[4], summary=case[4])
                    self.assertTrue(g.process_item_with_retry(candidate))
                    self.assertEqual(candidate['summary_method'], 'publisher_excerpt')
                    self.assertEqual(candidate['score_method'], 'rules_v1')
                    self.assertEqual(candidate['summary'], case[4])
                    self.assertEqual(candidate['ai_scope_disagreement'], rejection)
                    self.assertEqual(candidate['impact_analysis'], '')
            self.assertEqual(model.call_count, 20)
            audit.assert_not_called()

    def test_irrelevant_subjects_cannot_be_admitted_by_model(self):
        with patch.object(g, '_openrouter_generate', return_value='関連する包装設備の新製品です。') as model:
            for _, expected, title, company, body in CASES:
                if not expected:
                    self.assertFalse(g.ai_summarize(title, body, company)[0])
            model.assert_not_called()

    def test_title_or_footer_mentions_are_not_sufficient(self):
        self.assertEqual(classify_scope('包装機を発売', '包装機を発売した。')['verdict'], 'review')
        text = '会社紹介：包装機と産業用ロボットを製造する企業です。' * 4
        self.assertEqual(classify_scope('本社の花壇整備を発表', text)['verdict'], 'review')
        self.assertEqual(classify_scope('イベントを発表', '当社は新しい活動の計画を紹介しました。' * 5)['verdict'], 'review')

    def test_ambiguous_rejection_is_not_overridden(self):
        with patch.object(g, '_openrouter_generate', return_value='IRRELEVANT: no industrial evidence'):
            accepted, _ = g.ai_summarize('イベントを発表', '当社は新しい活動の計画を紹介しました。' * 5, 'メーカー')
        self.assertFalse(accepted)

    def test_old_and_duplicate_equipment_still_blocked_before_model(self):
        fresh = packaging_item()
        old = copy.deepcopy(fresh)
        old.update(date='2026-08-26', publisher_date='2026-08-26',
                   published_at='2026-08-26T00:00:00Z', publisher_published_at='2026-08-26T00:00:00Z')
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test'}), patch.object(g, '_openrouter_generate') as model:
            self.assertEqual(g.prepare_daily_candidates([old], [], date(2026, 9, 11))[0], [])
            self.assertEqual(g.prepare_daily_candidates([fresh], [fresh], date(2026, 9, 11))[0], [])
            model.assert_not_called()

    def test_rule_extract_cached_and_previous_policy_rejection_invalidated(self):
        candidate = packaging_item()
        with patch.object(g, 'REVIEW_VERSION', 4):
            old_key = g.review_fingerprint(candidate)
        candidate['ai_review'] = dict(fingerprint=old_key, status='rejected', version=4)
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test'}), \
                patch.object(g, '_openrouter_generate', return_value='IRRELEVANT: generic inspection') as model:
            ready, _ = g.prepare_daily_candidates([candidate], [], date(2026, 9, 11))
            self.assertEqual(len(ready), 1)
            self.assertEqual(candidate['ai_review']['method'], 'rule_extract')
            ready, audit = g.prepare_daily_candidates([candidate], [], date(2026, 9, 11))
            self.assertEqual(len(ready), 1)
            self.assertEqual(audit['ai_calls_items'], 0)
            self.assertIn('ai_scope_disagreement', audit['decisions'][0])
            self.assertEqual(model.call_count, 1)

    def test_model_outage_does_not_pass_live_contract(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test'}), \
                patch.object(g, '_openrouter_generate', side_effect=RuntimeError('temporary service failure')):
            with self.assertRaisesRegex(RuntimeError, 'AI scope contract failed'):
                verify_live_scope()


if __name__ == '__main__':
    unittest.main()
