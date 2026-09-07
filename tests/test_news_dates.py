import os
import sys
import unittest
from datetime import date
from unittest.mock import patch
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from news_dates import article_url, publication_evidence
from fetch_news import enrich_item, parse_published_at
from generate_dashboard import select_daily_digest


class PublisherDateTests(unittest.TestCase):
    def evidence(self, html, url='https://example.com/article'):
        return publication_evidence(BeautifulSoup(html, 'html.parser'), url)

    def test_first_publication_wins_over_update_and_page_build_date(self):
        details = self.evidence('''<meta property="article:published_time" content="2022-11-11">
            <meta property="article:modified_time" content="2026-09-05">
            <script type="application/ld+json">{"@type":"NewsArticle",
            "datePublished":"2022-11-11","dateModified":"2026-09-05"}</script>''')
        self.assertEqual(details['publisher_date'], '2022-11-11')

    def test_walker_image_dates_and_parent_identity(self):
        for article_id, image_id, raw, expected in [
            ('1109815', '11231201', '2022年11月11日', '2022-11-11'),
            ('1121163', '11537960', '2023年2月24日', '2023-02-24'),
        ]:
            url = f'https://www.walkerplus.com/article/{article_id}/image{image_id}.html'
            details = self.evidence(f'<meta name="date" content="2026-09-05"><time>{raw}</time>', url)
            self.assertEqual(details['publisher_date'], expected)
            self.assertEqual(article_url(url), f'https://www.walkerplus.com/article/{article_id}/')

    def test_modified_only_and_sidebar_dates_are_unverified(self):
        details = self.evidence('''<meta property="article:modified_time" content="2026-09-05">
            <aside><time>2026-09-05</time></aside>''')
        self.assertEqual(details['publication_date_status'], 'unverified')
        self.assertIsNone(parse_published_at({'updated': 'Fri, 05 Sep 2026 00:00:00 GMT'}))

    def test_recent_feed_cannot_override_old_publisher_date(self):
        item = {'url': 'https://www.walkerplus.com/article/1109815/image11231201.html',
                'title': 'セサミストリート 生理用品', 'date': '2026-09-01',
                'published_at': '2026-09-01T00:00:00Z', 'category_id': '①', 'score': 99}
        details = self.evidence('<time>2022年11月11日</time>', item['url'])
        with patch('fetch_news.fetch_article_details', return_value=details):
            fixed = enrich_item(item)
        self.assertEqual(fixed['date'], '2022-11-11')
        self.assertEqual(fixed['rss_published_at'], '2026-09-01T00:00:00Z')
        self.assertEqual(select_daily_digest([fixed], reference_date=date(2026, 9, 8)), [])

    def test_unverified_date_never_fills_digest_even_with_high_score(self):
        item = {'url': 'https://example.com/article', 'title': 'Very high scoring news',
                'date': '2026-09-08', 'score': 100}
        self.assertEqual(select_daily_digest([item], reference_date=date(2026, 9, 8)), [])


if __name__ == '__main__':
    unittest.main()
