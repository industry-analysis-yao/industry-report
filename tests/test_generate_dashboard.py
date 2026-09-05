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

    def test_uses_sixty_day_unique_fallback_before_recycling_history(self):
        recent = [self.make_item(i, "①", published="2026-09-01") for i in range(10)]
        older_unique = [self.make_item(100 + i, "②", published="2026-07-25") for i in range(10)]

        selected = generate_dashboard.select_daily_digest(
            recent + older_unique,
            reference_date=date(2026, 9, 3),
            target=20,
            minimum=15,
            maximum=20,
        )

        self.assertEqual(len(selected), 20)
        self.assertEqual(sum(item["date"] == "2026-07-25" for item in selected), 10)

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

    def test_excludes_articles_already_used_in_an_earlier_digest(self):
        repeated = self.make_item(0, "⑥", published="2026-08-26", score=100)
        repeated["title"] = "シリーズ初 フタつきウエットティシュー新発売"
        candidates = [repeated] + [
            self.make_item(index, "①", published="2026-09-01", score=90 - index)
            for index in range(1, 22)
        ]

        selected = generate_dashboard.select_daily_digest(
            candidates,
            previous_items=[repeated.copy()],
            reference_date=date(2026, 9, 3),
            target=20,
            minimum=15,
            maximum=20,
        )

        self.assertEqual(len(selected), 20)
        self.assertNotIn(repeated["url"], {item["url"] for item in selected})

    def test_excludes_a_rewritten_headline_for_the_same_event(self):
        press_release = self.make_item(0, "⑥", published="2026-08-26", score=100)
        press_release["title"] = "シリーズ初！詰め替え不要の最後まで乾きにくいフタつきタイプが新登場！エリエール フタつきウエットティシュー新発売"
        press_release["summary"] = "大王製紙株式会社は2026年9月21日、エリエール フタつきウエットティシューを全国発売します。同製品はフタつきパッケージを採用し、詰め替え不要で密閉性が高く最後まで乾きにくい設計。除菌アルコールタイプ、ノンアルコールタイプ、純水タイプの3種類を展開します。"
        syndicated = self.make_item(1, "②", published="2026-08-26", score=99)
        syndicated["title"] = "大王製紙、蓋付きのウエットティッシュ 詰め替え負担軽減"
        syndicated["summary"] = "大王製紙は9月21日、蓋付き大容量ウエットティッシュ エリエール フタつきウエットティシューを全国発売する。アルコール入りや純水タイプなど3種類を展開。蓋付きパッケージは乾燥を防ぎ、詰め替えの手間を省く。"

        self.assertTrue(generate_dashboard.same_news_story(press_release, syndicated))
        selected = generate_dashboard.select_daily_digest(
            [syndicated],
            previous_items=[press_release],
            reference_date=date(2026, 9, 3),
            target=20,
            minimum=1,
            maximum=20,
        )
        self.assertEqual(selected, [])

    def test_daily_sections_are_mutually_exclusive_and_sum_to_total(self):
        examples = [
            ("①", "ユニ・チャームの新製品", "rivals"),
            ("②", "日本製紙の設備投資", "rivals"),
            ("③", "瑞光のおむつ加工機", "machine"),
            ("④", "包装ラインを新設", "packaging"),
            ("④", "FANUCロボットパレタイザー", "palletizer"),
            ("⑤", "ウェットティッシュ新製品", "wet"),
            ("⑥", "ウエットティッシュ新製品", "wet"),
            ("⑥", "ウエットティシュー新製品", "wet"),
            ("⑥", "New wet tissue product", "wet"),
            ("⑥", "New wet wipes product", "wet"),
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
