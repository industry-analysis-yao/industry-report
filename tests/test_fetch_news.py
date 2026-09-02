import os
import json
import sys
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import fetch_news


class FakeParser:
    def __init__(self, entries):
        self.entries = entries
        self.last_url = None

    def parse(self, url, **_kwargs):
        self.last_url = url
        return SimpleNamespace(entries=self.entries, bozo=False)


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeSession:
    def get(self, *_args, **_kwargs):
        return FakeResponse('<c-wiz data-n-a-ts="1788356253" data-n-a-sg="signature-value"></c-wiz>')

    def post(self, *_args, **_kwargs):
        nested = '["garturlres","https://publisher.example/news/123?utm_source=google"]'
        return FakeResponse(json.dumps([["wrb.fr", "Fbv4je", nested, None, None, None, "1"]]))


def entry(*, title, published=None, link="https://news.google.com/rss/articles/example", source="日本経済新聞", summary=""):
    row = {
        "title": f"{title} - {source}",
        "link": link,
        "summary": summary or title,
        "source": {"title": source, "href": "https://www.nikkei.com/"},
    }
    if published is not None:
        row["published_parsed"] = time.gmtime(published.timestamp())
    return row


class FetchNewsTests(unittest.TestCase):
    NOW = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)

    def test_preserves_real_publication_time_and_jst_date(self):
        published = datetime(2026, 9, 1, 23, 30, tzinfo=timezone.utc)
        parser = FakeParser([
            entry(
                title="ユニ・チャームが新しいおむつ素材を発表",
                published=published,
                summary="ユニ・チャームは吸収性能を高めた新しいおむつ素材を発表した。",
            )
        ])

        rows = fetch_news.fetch_google_news_rss("ユニ・チャーム おむつ", now=self.NOW, feed_parser=parser)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["published_at"], "2026-09-01T23:30:00Z")
        self.assertEqual(rows[0]["date"], "2026-09-02")
        self.assertEqual(rows[0]["collected_at"], "2026-09-02T00:00:00Z")
        self.assertIn("when%3A14d", parser.last_url)

    def test_rejects_old_missing_and_future_dates(self):
        parser = FakeParser([
            entry(title="古いおむつ記事", published=datetime(2026, 7, 1, tzinfo=timezone.utc)),
            entry(title="日付なしのおむつ記事", published=None),
            entry(title="未来のおむつ記事", published=datetime(2026, 9, 3, tzinfo=timezone.utc)),
        ])

        rows = fetch_news.fetch_google_news_rss("おむつ", now=self.NOW, feed_parser=parser)

        self.assertEqual(rows, [])

    def test_filters_market_report_spam(self):
        parser = FakeParser([
            entry(
                title="不織布の世界市場予測 2032年までの予測",
                published=datetime(2026, 9, 1, tzinfo=timezone.utc),
            )
        ])

        rows = fetch_news.fetch_google_news_rss("不織布", now=self.NOW, feed_parser=parser)

        self.assertEqual(rows, [])

    def test_deduplicates_same_story_across_queries(self):
        base = {
            "title": "花王が生理用品の新製品を発表",
            "summary": "花王が生理用品の新製品を発表した。",
            "source_name": "共同通信",
            "date": "2026-09-01",
            "published_at": "2026-09-01T03:00:00Z",
            "confidence": "高",
        }
        first = {**base, "url": "https://news.google.com/rss/articles/one"}
        second = {**base, "url": "https://news.google.com/rss/articles/two"}

        rows = fetch_news.deduplicate([first, second])

        self.assertEqual(len(rows), 1)

    def test_deduplicates_near_identical_syndicated_headlines(self):
        base = {
            "summary": "イオンは対象商品の値下げを発表した。",
            "date": "2026-09-01",
            "published_at": "2026-09-01T03:00:00Z",
            "confidence": "中",
        }
        first = {**base, "title": "イオンが145品目で2～40％値下げ トイレットペーパーも対象", "source_name": "FNN", "url": "https://example.com/1"}
        second = {**base, "title": "イオンが145品目で2〜40％値下げ トイレットペーパーも対象", "source_name": "Yahoo", "url": "https://example.com/2"}

        rows = fetch_news.deduplicate([first, second])

        self.assertEqual(len(rows), 1)

    def test_company_name_alone_is_relevant_but_offtopic_brand_is_not(self):
        self.assertTrue(fetch_news.assess_relevance("ユニ・チャーム 決算発表", "", "日本経済新聞")[0])
        self.assertFalse(fetch_news.assess_relevance("花王が新しいシャンプーを発売", "", "PR TIMES")[0])

    def test_resolves_google_news_url_with_page_signature(self):
        url = "https://news.google.com/rss/articles/AU_yqL-test-id?oc=5"

        resolved = fetch_news.resolve_google_news_url(url, session=FakeSession())

        self.assertEqual(resolved, "https://publisher.example/news/123")


if __name__ == "__main__":
    unittest.main()
