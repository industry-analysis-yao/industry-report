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

    def test_parses_recent_relevant_patents_and_rejects_animal_only_results(self):
        patent_html = """
        <article class="result">
          <state-modifier data-result="patent/JP2026069657A/en"></state-modifier>
          <h3>Absorbent articles</h3>
          <h4 class="dates">Priority 2021-12-16 • Filed 2026-02-18 • Published 2026-04-23</h4>
          <div class="abstract"><raw-html>An absorbent article with an improved absorbent core for disposable diapers and sanitary products.</raw-html></div>
        </article>
        <article class="result">
          <state-modifier data-result="patent/JP2026083350A/en"></state-modifier>
          <h3>Animal litter</h3>
          <h4 class="dates">Priority 2023-03-10 • Filed 2026-03-12 • Published 2026-05-19</h4>
          <div class="abstract"><raw-html>Granular litter for cats that suppresses unpleasant odors in an animal toilet.</raw-html></div>
        </article>
        <article class="result">
          <state-modifier data-result="patent/JP2019000001A/en"></state-modifier>
          <h3>Disposable diaper</h3>
          <h4 class="dates">Published 2019-01-01</h4>
          <div class="abstract"><raw-html>An old absorbent article publication.</raw-html></div>
        </article>
        """

        rows = fetch_news.parse_google_patents_html(
            patent_html,
            company="ユニ・チャーム",
            now=self.NOW,
            max_age_days=365,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["patent_number"], "JP2026069657A")
        self.assertEqual(rows[0]["date"], "2026-04-23")
        self.assertEqual(rows[0]["info_type"], "特許")
        self.assertEqual(rows[0]["category_id"], "⑦")
        self.assertTrue(rows[0]["permanent_record"])
        self.assertEqual(rows[0]["url"], "https://patents.google.com/patent/JP2026069657A/en")

    def test_parses_google_patents_structured_payload(self):
        payload = {
            "results": {
                "cluster": [{
                    "result": [{
                        "patent": {
                            "title": " Absorbent article for absorbing menstrual blood",
                            "snippet": "This absorbent article uses a hydrophilic gradient and absorbent core in a sanitary napkin.",
                            "publication_date": "2026-02-24",
                            "publication_number": "JP2026031759A",
                            "language": "en",
                            "assignee": "<b>ユニ・チャーム</b>株式会社",
                        }
                    }]
                }]
            }
        }

        rows = fetch_news.parse_google_patents_payload(
            payload,
            now=self.NOW,
            max_age_days=365,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["patent_number"], "JP2026031759A")
        self.assertEqual(rows[0]["company"], "ユニ・チャーム")
        self.assertIn("direct_patent_source", rows[0]["quality_flags"])


if __name__ == "__main__":
    unittest.main()
