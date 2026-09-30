import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from official_sources import collect_official_news, parse_index
from publisher_feeds import collect_publisher_feeds, discovery_timestamp
from fetch_news import deduplicate, enrich_item, parse_published_at
from generate_dashboard import eligibility_reason


NOW = datetime(2026, 9, 24, 9, tzinfo=timezone.utc)


class TargetedSourceTests(unittest.TestCase):
    def test_explicit_publication_wins_over_new_update_in_feed(self):
        published, source = discovery_timestamp(
            {'published': '2022-11-11', 'updated': '2026-09-24'}, parse_published_at)
        self.assertEqual(published.date().isoformat(), '2022-11-11')
        self.assertEqual(source, 'published')

    def test_new_indexes_bind_release_date_to_article_not_event_or_category(self):
        fixtures = {
            'siriusvision': '<a href="/one"><time>2026.09.17</time><h2>TOKYO PACK 2026に10月14日出展</h2></a>',
            'miyakoshi': '<div class="p-article04__inner"><time>2026.09.17</time><a href="/category">イベント</a><h2 class="p-article04__title"><a href="/one">包装機を出展</a></h2></div>',
            'crecia': '<div class="container"><dt><time>2026年09月17日</time></dt><dd><a href="/one">ティシュー新発売</a></dd></div>',
            'pacraft': '<div class="c-link-list_item"><a href="/one"><div class="date">2026/09/17</div><div class="title">包装機を出展</div></a></div>',
        }
        for source, html in fixtures.items():
            with self.subTest(source=source):
                response = Mock(content=html.encode())
                items, health = collect_official_news(now=NOW, get=Mock(return_value=response),
                    sources=[(source, 'メーカー', 'https://example.com/news/')])
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]['url'], 'https://example.com/one')
                self.assertEqual(items[0]['date'], '2026-09-17')
                self.assertEqual(health[0]['latest_index_publication'], '2026-09-17')
                self.assertEqual(health[0]['recent_5_days'], 0)
                self.assertEqual(health[0]['recent_index_rows'], 0)

    def test_pacraft_event_schedule_is_not_a_release_index(self):
        html = '<table><tr><td>2026/09/24〜2026/09/26</td><td><a href="/event">包装展示会</a></td></tr></table>'
        self.assertEqual(parse_index('pacraft', html, 'https://example.com/'), [])

    def test_company_feed_is_independent_of_global_feed_and_still_unverified(self):
        def response(title, link):
            return Mock(content=('''<rss version="2.0"><channel><title>Feed</title><item>
              <title>''' + title + '''</title><link>''' + link + '''</link>
              <pubDate>Thu, 24 Sep 2026 00:00:00 GMT</pubDate>
              <description>新しい包装機を開発し、工場の生産ライン向けに発売。</description>
              </item></channel></rss>''').encode())
        get = Mock(side_effect=[response('包装機を新発売', 'https://example.com/one'),
                                response('包装機を新発売', 'https://example.com/one')])
        sources = [('global', 'https://example.com/feed', 'general', 'ja'),
                   ('company', 'https://example.com/companyfeed', 'packaging', 'ja')]
        items, health = collect_publisher_feeds(now=NOW, get=get, sources=sources)
        self.assertEqual(len(items), 2)
        self.assertEqual(len(deduplicate(items)), 1)
        self.assertEqual({x['publication_date_status'] for x in items}, {'unverified'})
        self.assertEqual([h['recent_7_days'] for h in health], [1, 1])

    def test_feed_errors_are_visible_and_do_not_suppress_other_sources(self):
        get = Mock(side_effect=RuntimeError('publisher unavailable'))
        items, health = collect_publisher_feeds(now=NOW, get=get,
            sources=[('company', 'https://example.com/feed', 'general', 'ja')])
        self.assertEqual(items, [])
        self.assertEqual(health[0]['status'], 'error')
        self.assertIn('publisher unavailable', health[0]['error'])

    def test_old_feed_date_cannot_be_replaced_with_today(self):
        response = Mock(content=b'''<rss version="2.0"><channel><title>Feed</title><item>
          <title>Packaging machine launch</title><link>https://example.com/old</link>
          <pubDate>Fri, 24 Sep 2021 00:00:00 GMT</pubDate>
          </item></channel></rss>''')
        items, health = collect_publisher_feeds(now=NOW, get=Mock(return_value=response),
            sources=[('company', 'https://example.com/feed', 'packaging', 'en')])
        self.assertEqual(items, [])
        self.assertEqual(health[0]['missing_or_outside_date'], 1)

    def test_rdf_dc_date_discovers_articles_but_cannot_refresh_old_publication(self):
        response = Mock(content='''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
          xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <item rdf:about="https://example.com/one"><title>包装機の新製品を発売</title>
          <link>https://example.com/one</link><dc:date>2026-09-24T10:00:00+09:00</dc:date>
          <description>包装機の開発を発表しました。</description></item></rdf:RDF>'''.encode())
        items, health = collect_publisher_feeds(now=NOW, get=Mock(return_value=response),
            sources=[('PR TIMES', 'https://example.com/feed', 'packaging', 'ja')])
        self.assertEqual(health[0]['accepted'], 1)
        self.assertEqual(items[0]['discovery_timestamp_source'], 'updated_discovery_only')
        self.assertEqual(items[0]['publication_date_status'], 'unverified')
        self.assertEqual(eligibility_reason(items[0], NOW.date()), 'unverified_publication_date')
        details = dict(excerpt='新製品の包装機を工場へ導入するために開発しました。' * 5,
                       publication_date_status='verified', publisher_date='2022-11-11',
                       publisher_published_at='2022-11-10T15:00:00Z')
        with patch('fetch_news.fetch_article_details', return_value=details):
            item = enrich_item(items[0])
        self.assertEqual(item['date'], '2022-11-11')
        self.assertEqual(eligibility_reason(item, NOW.date()), 'outside_five_calendar_days')


if __name__ == '__main__':
    unittest.main()
