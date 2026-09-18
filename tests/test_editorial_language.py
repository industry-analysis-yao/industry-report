import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from editorial_language import validate_japanese_item, CHINESE_LEAK


class EditorialLanguageTests(unittest.TestCase):
    def test_published_editorial_copies_and_highlights_are_japanese(self):
        """Check all public copies, not only the day's main cards."""
        expected = {}
        for path in (ROOT/'data').glob('????-??-??.json'):
            issue = json.loads(path.read_text(encoding='utf-8'))
            if issue.get('publication_mode') != 'codex_editorial':
                continue
            for item in issue['items'] + issue.get('new_patents', []):
                validate_japanese_item(item)
                expected[item['url']] = item
            for highlight in issue.get('highlights', []):
                self.assertEqual(highlight['title'], expected[highlight['url']]['title'])
                self.assertEqual(highlight['impact'], expected[highlight['url']]['impact_analysis'])
        main = json.loads((ROOT/'data/news_data.json').read_text(encoding='utf-8'))
        if not isinstance(main, dict):
            return  # legacy data has no editorial import contract
        records = [it for bucket in main.get('dates', {}).values() for it in bucket]
        records += main.get('patents', [])
        records += json.loads((ROOT/'data/permanent_vault.json').read_text(encoding='utf-8'))
        for item in records:
            if item.get('summary_method') == 'codex_editorial':
                validate_japanese_item(item)
                if item['url'] in expected:
                    for key in ('title','summary','impact_analysis','date_evidence','caution'):
                        self.assertEqual(item[key], expected[item['url']][key])
        for highlight in main.get('highlights', []):
            if highlight.get('url') in expected:
                self.assertEqual(highlight['title'], expected[highlight['url']]['title'])
                self.assertEqual(highlight['impact'], expected[highlight['url']]['impact_analysis'])

    def test_lint_preserves_japanese_technical_terms(self):
        self.assertIsNone(CHINESE_LEAK.search('研究開発、特許出願、繊維、製紙、公開日、注意事項'))


if __name__ == '__main__':
    unittest.main()
