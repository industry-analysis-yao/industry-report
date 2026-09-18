import copy
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from import_codex_digest import publish, public_item
import generate_dashboard as g


def fixture():
    return dict(id='test', kind='news', section='包装设备・包装材料', date='2026-09-18',
                event_id='event-1', company='メーカー', title_ja='包装設備とロボット連携を展示',
                summary_ja='包装設備と連携するロボットの展示予定を企業原文と照合して紹介します。新機種の発売ではなく展示会の予告です。設備導入の実績と混同しないように注意します。',
                relevance_ja='包装工程の検討に役立つ情報として扱う。', content_language='ja', url='https://example.com/news/1',
                date_evidence='原文の署期を確認', verification_level='本文を照合',
                caution='展示会予告', priority='重点', region='日本', relationship='供給元',
                evidence_file='C:/private/not-for-publication.txt')


class CodexImportTests(unittest.TestCase):
    def test_no_chinese_fallback_and_nested_notes_checked(self):
        for key in ('title_ja', 'relevance_ja', 'content_language'):
            raw = fixture()
            del raw[key]
            raw.update(title='中文标题', relevance_zh='中文分析')
            with self.subTest(missing=key), self.assertRaises(ValueError):
                public_item(raw, date(2026, 9, 18))
        for key in ('title_ja', 'relevance_ja', 'caution', 'date_evidence', 'verification_level'):
            raw = fixture()
            raw[key] = '原文の情報：关注设备与产品的变化'
            with self.subTest(field=key), self.assertRaises(ValueError):
                public_item(raw, date(2026, 9, 18))

    def test_public_projection_and_section(self):
        item = public_item(fixture(), date(2026, 9, 18))
        self.assertNotIn('evidence_file', item)
        self.assertNotIn('C:/private', json.dumps(item))
        self.assertEqual(g.assign_daily_section(item), 'packaging')
        self.assertEqual(item['published_at'], '2026-09-18')

    def test_old_future_bad_url_and_missing_evidence_rejected(self):
        for key, value in [('date','2026-09-13'), ('date','2026-09-19'),
                           ('url','javascript:alert(1)'), ('date_evidence','')]:
            with self.subTest(key=key, value=value):
                raw = fixture()
                raw[key] = value
                with self.assertRaises(ValueError):
                    public_item(raw, date(2026, 9, 18))

    def test_idempotent_publication_preserves_history_and_no_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory/'review.json'
            source.write_text(json.dumps(dict(date='2026-09-18', items=[fixture()])), encoding='utf-8')
            old = directory/'2026-09-10.json'
            old.write_text('{"items": []}', encoding='utf-8')
            with patch.object(g, 'process_item_with_retry', side_effect=AssertionError('API forbidden')):
                publish(source, directory)
                publish(source, directory)
                g.main(str(directory), date(2026, 9, 18))
            self.assertEqual(old.read_text(), '{"items": []}')
            main = json.loads((directory/'news_data.json').read_text(encoding='utf-8'))
            self.assertEqual(len(main['dates']['2026-09-18']), 1)

    def test_duplicate_in_history_and_current_issue_fails_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory/'review.json'
            source.write_text(json.dumps(dict(date='2026-09-18', items=[fixture(), fixture()])), encoding='utf-8')
            with self.assertRaises(ValueError):
                publish(source, directory)
            self.assertFalse((directory/'2026-09-18.json').exists())
            source.write_text(json.dumps(dict(date='2026-09-18', items=[fixture()])), encoding='utf-8')
            previous = copy.deepcopy(fixture())
            previous['url'] = 'https://example.com/syndication'
            (directory/'2026-09-17.json').write_text(json.dumps(dict(items=[previous])), encoding='utf-8')
            with self.assertRaises(ValueError):
                publish(source, directory)

    def test_patent_application_is_not_publication(self):
        raw = fixture()
        raw.update(kind='patent', section='企业专利', publication_number='JP2026000001A',
                   application_number='JP2025000001', application_date='2025-03-01',
                   patent_family_status='未確認')
        item = public_item(raw, date(2026, 9, 18))
        self.assertTrue(item['permanent_record'])
        self.assertFalse(item['is_academic'])
        self.assertIsNone(item['grant_date'])
        self.assertEqual(item['application_date'], '2025-03-01')


if __name__ == '__main__':
    unittest.main()
