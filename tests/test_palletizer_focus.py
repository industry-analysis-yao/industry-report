import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_dashboard as g
from fetch_news import assess_relevance
from source_catalog import equipment_section, robot_scope_exclusion, expanded_queries
from news_scope import classify_scope
from test_generate_dashboard import DailyDigestTests


class PalletizerFocusTests(unittest.TestCase):
    def test_general_robot_does_not_mean_palletizer(self):
        for title in ['ABB Robotics launches E-Device robot control',
                      'FANUC and Palladyne announce robotic automation collaboration',
                      '工場向けPhysical AIと人型ロボットを発表',
                      'ロボットの基盤モデルに投資', '協働ロボットの新モデルを発売']:
            with self.subTest(title=title):
                self.assertIsNone(equipment_section(title))
                self.assertFalse(assess_relevance(title, '工場・物流向けの汎用AI制御技術を開発。' * 5)[0])
                self.assertEqual(classify_scope(title, 'manufacturing technology ' * 8)['verdict'], 'exclude')

    def test_actual_palletizing_in_three_languages(self):
        for title in ['段ボール箱のパレタイズロボットを発売',
                      'FANUC launches robotic depalletizing system',
                      '节卡发布码垛机器人新品']:
            self.assertTrue(assess_relevance(title, '')[0], title)
            self.assertEqual(equipment_section(title), 'palletizer')
            self.assertEqual(g.assign_daily_section({'title': title, 'category_id': '④'}), 'palletizer')

    def test_robot_on_packing_line_is_packaging_not_palletizer(self):
        title = '工場で袋詰めロボットを導入'
        self.assertTrue(assess_relevance(title, '')[0])
        self.assertEqual(equipment_section(title), 'packaging')
        self.assertEqual(g.assign_daily_section({'title': title, 'category_id': '④'}), 'packaging')

    def test_concrete_lead_can_explain_generic_robot_headline_not_footer(self):
        title = '協働ロボットの新モデルを発売'
        self.assertIsNone(robot_scope_exclusion(title, '包装ラインの箱詰め工程に導入する新製品です。'))
        self.assertIsNotNone(robot_scope_exclusion(title, '汎用ロボットの基盤モデルを発表。' * 40 + '会社紹介：パレタイザーも販売。'))
        self.assertIsNotNone(robot_scope_exclusion(title, '包装や積付けの具体的用途はない。'))

    def test_previous_ai_acceptance_cannot_bypass_changed_scope(self):
        item = DailyDigestTests().make_item(700, '④', published='2026-09-30')
        item.update(title='AIロボット制御モデルを発売', source_excerpt='工場・倉庫向けの一般的なAI機能を紹介。' * 8,
                    summary_method='ai', score_method='ai', impact_analysis='previous approval')
        item['ai_review'] = {'fingerprint': g.review_fingerprint(item), 'status': 'accepted'}
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test'}), patch.object(g, '_openrouter_generate') as model:
            ready, _ = g.prepare_daily_candidates([item], [], date(2026, 9, 30))
        self.assertEqual(ready, [])
        model.assert_not_called()
        self.assertEqual(g.select_daily_digest([item], reference_date=date(2026, 9, 30)), [])

    def test_core_manufacturers_and_wet_tissue_are_retained(self):
        for title in ['日本製紙クレシア ティシューを新発売', '瑞光 おむつ加工機を開発',
                      '大王製紙 ウエットティシューを新発売', 'フジキカイ 包装機を出展']:
            self.assertTrue(assess_relevance(title, '')[0], title)
        self.assertEqual(g.assign_daily_section({'title': 'ウエットティシューを新発売', 'category_id': '⑥'}), 'wet')

    def test_core_hygiene_spelling_and_renewal_discovery(self):
        for title in ['ポイズ 肌ケアパッド 全方位ガード 新発売',
                      'ポイズ さらさらシリーズ リニューアル',
                      'アクティ 大きなおしりふきタオルをリニューアル発売',
                      'ネピア 保湿ソフトパックティシュ リニューアル',
                      'スコッティからスヌーピーデザインをリニューアル発売']:
            self.assertTrue(assess_relevance(title, '')[0], title)
        self.assertEqual(g.assign_daily_section({'title': 'ウエットティシュ新発売', 'category_id': '⑥'}), 'wet')
        self.assertEqual(g.assign_daily_section({'title': '保湿ティシュ新発売', 'category_id': '①'}), 'tissue')

    def test_queries_and_quota_do_not_allow_robot_flood_to_crowd_out_equipment(self):
        queries = expanded_queries()
        self.assertFalse(any(q['query'] in {'ABB Robotics', 'Universal Robots', 'ファナック ロボット'} for q in queries))
        make = DailyDigestTests().make_item
        items = [make(i, '④', published='2026-09-30', score=99) for i in range(20)]
        for i in items:
            i['summary'] = 'パレタイザー'
        for offset, cat, summary in [(30, '①', ''), (40, '③', ''), (50, '④', '包装機'),
                                      (60, '⑤', ''), (70, '⑥', '')]:
            for n in range(6):
                i = make(offset+n, cat, published='2026-09-30', score=50)
                i['summary'] = summary
                items.append(i)
        result = g.select_daily_digest(items, reference_date=date(2026, 9, 30))
        self.assertEqual(len(result), 20)
        sections = [g.assign_daily_section(i) for i in result]
        self.assertGreaterEqual(sections.count('machine'), 3)
        self.assertGreaterEqual(sections.count('packaging'), 4)
        self.assertLessEqual(sections.count('palletizer'), 3)

    def test_roundup_is_not_one_industry_event(self):
        self.assertFalse(assess_relevance('【オートメーション新聞 No.462】ロボット・包装機特集', '')[0])

    def test_evening_schedule_keeps_one_daily_generation(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/update_data.yml').read_text(encoding='utf8')
        self.assertIn("cron: '35 10 * * *'", workflow)
        self.assertEqual(workflow.count('cron:'), 1)
        self.assertEqual(workflow.count('run: python scripts/generate_dashboard.py'), 1)


if __name__ == '__main__':
    unittest.main()
