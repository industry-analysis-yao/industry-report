import os
import sys
import unittest
from datetime import date


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import generate_dashboard


class DailyDigestTests(unittest.TestCase):
    def make_item(self, index, category, published="2026-09-01", score=50):
        return {
            "title": chr(0x4E00 + index) * 15,
            "summary": "relevant industry summary",
            "url": f"https://example.com/{index}",
            "date": published,
            "published_at": f"{published}T00:00:00Z",
            "category_id": category,
            "score": score,
            "confidence": "高",
            "fulltext_status": "excerpt_extracted",
        }

    def test_builds_twenty_item_balanced_digest(self):
        categories = ["①"] * 8 + ["②"] * 6 + ["③"] * 3 + ["④"] * 3 + ["⑤"] * 2 + ["⑥"] * 3
        items = [self.make_item(i, category, score=100 - i) for i, category in enumerate(categories)]

        selected = generate_dashboard.select_daily_digest(
            items,
            reference_date=date(2026, 9, 3),
            target=20,
            minimum=15,
            maximum=20,
        )

        self.assertEqual(len(selected), 20)
        selected_categories = {item["category_id"] for item in selected}
        self.assertEqual(selected_categories, {"①", "②", "③", "④", "⑤", "⑥"})
        self.assertTrue(all(item["date"] == "2026-09-01" for item in selected))

    def test_uses_thirty_day_fallback_only_when_recent_pool_is_too_small(self):
        recent = [self.make_item(i, "①", published="2026-09-01") for i in range(10)]
        older = [self.make_item(100 + i, "②", published="2026-08-15") for i in range(10)]

        selected = generate_dashboard.select_daily_digest(
            recent + older,
            reference_date=date(2026, 9, 3),
            target=18,
            minimum=15,
            maximum=20,
            lookback_days=14,
        )

        self.assertEqual(len(selected), 18)
        self.assertTrue(any(item["date"] == "2026-08-15" for item in selected))

    def test_collapses_syndicated_versions_of_the_same_story(self):
        items = [self.make_item(i, "①", score=80 - i) for i in range(20)]
        items[0]["title"] = "ポケモンのトイレットペーパーが新登場"
        items[1]["title"] = "丸富製紙 ポケモン トイレットペーパー12ロールダブルを発売"

        selected = generate_dashboard.select_daily_digest(
            items,
            reference_date=date(2026, 9, 3),
            target=18,
            minimum=15,
            maximum=20,
        )

        matching = [item for item in selected if "ポケモン" in item["title"]]
        self.assertEqual(len(matching), 1)

    def test_daily_sections_are_mutually_exclusive_and_sum_to_total(self):
        examples = [
            ("①", "ユニ・チャームの新製品", "rivals"),
            ("②", "日本製紙の設備投資", "rivals"),
            ("③", "瑞光のおむつ加工機", "machine"),
            ("④", "包装ラインを新設", "packaging"),
            ("④", "FANUCロボットパレタイザー", "palletizer"),
            ("⑤", "ウェットティッシュ新製品", "wet"),
            ("⑥", "箱ティッシュを発売", "tissue"),
            ("⑥", "トイレットペーパーを発売", "toilet"),
            ("①", "競合メーカーがウェットティシューを発売", "wet"),
            ("②", "製紙会社がトイレットペーパーを増産", "toilet"),
        ]
        items = []
        for index, (category, title, expected) in enumerate(examples):
            item = self.make_item(index, category)
            item["title"] = title
            self.assertEqual(generate_dashboard.assign_daily_section(item), expected)
            items.append(item)

        counts = {}
        for item in items:
            section = generate_dashboard.assign_daily_section(item)
            counts[section] = counts.get(section, 0) + 1
        self.assertEqual(sum(counts.values()), len(items))


if __name__ == "__main__":
    unittest.main()
