import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from official_sources import parse_index, index_item, official_relevance, collect_official_news
from fetch_news import prepare_official_item, collect_news, assess_relevance, deduplicate, fetch_article_details
from news_dates import parse_date, verified_news
from news_scoring import apply_fallback
from generate_dashboard import select_daily_digest, assign_daily_section
import generate_dashboard

NOW = datetime(2026, 9, 8, 9, tzinfo=timezone.utc)


class OfficialSourceTests(unittest.TestCase):
    def item(self, title='ソフィ 新発売', raw_date='2026-09-08', **kwargs):
        return index_item(title, 'https://www.unicharm.co.jp/news/new.html', raw_date, '本文。' * 80,
                          company='ユニ・チャーム', source='unicharm',
                          index_url='https://www.unicharm.co.jp/news/', now=NOW, **kwargs)

    def test_date_formats_and_invalid_dates(self):
        for raw in ('2026.9.8', '2026/09/08', '2026年9月8日', '2026-09-08T00:00:00+0900'):
            self.assertEqual(parse_date(raw).date(), date(2026, 9, 8))
        self.assertIsNone(parse_date('2026.02.30'))

    def test_unicharm_binds_each_date_to_its_own_link(self):
        rows = parse_index('unicharm', '''<header>2026年9月8日</header>
          <li class="uc-item"><a href="old.html"><div class="uc-date">2022年11月11日</div>
          <div class="uc-title">ソフィ 新発売</div></a></li>
          <li class="uc-item"><a href="new.html"><div class="uc-date">2026年9月8日</div>
          <div class="uc-title">ソフィ 新商品</div></a></li>''', 'https://www.unicharm.co.jp/news/')
        self.assertEqual(rows[0][2], '2022年11月11日')
        self.assertEqual(rows[1][1], 'https://www.unicharm.co.jp/news/new.html')
        self.assertIsNone(self.item(raw_date=rows[0][2]))
        self.assertIsNone(self.item(raw_date='2026-09-09'))

    def test_daio_visible_release_date_not_wordpress_edit_time(self):
        rows = parse_index('daio', '''<li class="clearfix"><p class="date">
          <time datetime="2026-09-04T17:35:24+09:00">2026.09.07</time></p>
          <p class="title"><a href="/new/" title="ウエットティシュー新発売">短縮…</a></p></li>''', 'https://www.daio-paper.co.jp/news/')
        self.assertEqual(rows[0][0], 'ウエットティシュー新発売')
        self.assertEqual(rows[0][2], '2026.09.07')

    def test_nippon_uses_pub_on_not_mod_on_or_global_build_time(self):
        rows = parse_index('nippon', {'rebuild': '2026-09-08', 'article': [{
            'title': '工場の設備投資', 'url': '/old.pdf', 'pub_on': '2022-11-11',
            'mod_on': '2026-09-08', 'url_type': 'file'}]}, 'https://www.nipponpapergroup.com/data/news_data_ja.json')
        self.assertEqual(rows[0][2], '2022-11-11')
        self.assertIsNone(self.item(title=rows[0][0], raw_date=rows[0][2]))

    def test_kao_ignores_rolling_archive_updates(self):
        rows = parse_index('kao', {'items': [{'title': '決算説明会を更新', 'time': '2026-09-08',
                          'link': {'url': 'https://www.kao.com/ir/'}, 'label': {'title': '更新情報'}}]}, 'https://www.kao.com/index.json')
        self.assertEqual(rows, [])

    def test_missing_detail_meta_does_not_discard_bound_official_date(self):
        with patch('fetch_news.fetch_article_details', return_value={'publication_date_status': 'unverified', 'excerpt': '企業の本文。' * 30}):
            item = prepare_official_item(self.item())
        self.assertTrue(verified_news(item))
        self.assertEqual(item['date'], '2026-09-08')

    def test_old_detail_date_overrules_newer_index_date(self):
        with patch('fetch_news.fetch_article_details', return_value={
                'publication_date_status': 'verified', 'publisher_date': '2022-11-11',
                'publisher_published_at': '2022-11-10T15:00:00Z'}):
            item = prepare_official_item(self.item())
        self.assertEqual(item['date'], '2022-11-11')
        self.assertEqual(select_daily_digest([item], reference_date=NOW.date()), [])

    def test_manufacturer_name_does_not_admit_beauty_food_or_sports(self):
        for title in ('花王、北欧で化粧品事業を拡大', '愛猫用フード新発売', 'ゴルフ選手が優勝', 'ウェーブくんカプセルトイ発売'):
            self.assertFalse(official_relevance(title, '花王'))
        self.assertTrue(official_relevance('花王、需要計画立案を支援するAIエージェントを開発', '花王'))

    def test_product_patent_mention_is_news_and_wipes_are_wet(self):
        with patch('fetch_news.fetch_article_details', return_value={}):
            item = prepare_official_item(self.item(title='特許技術の超快適マスク 新発売'))
            wet = prepare_official_item(self.item(title='ムーニーおしりふき 新発売'))
        self.assertNotEqual(item['category_id'], '⑦')
        self.assertNotEqual(item['info_type'], '特許')
        self.assertFalse(item['permanent_record'])
        self.assertEqual(assign_daily_section(wet), 'wet')

    def test_empty_or_failed_source_is_visible_in_health(self):
        response = Mock(content=b'<html><time>2026-09-08</time></html>')
        _, health = collect_official_news(now=NOW, get=Mock(return_value=response),
                                         sources=[('zuiko', '瑞光', 'https://www.zuiko.co.jp/')])
        self.assertEqual(health[0]['status'], 'error')
        self.assertEqual(health[0]['parsed'], 0)

    def test_rule_score_and_excerpt_are_not_mislabeled_ai(self):
        item = self.item()
        apply_fallback(item, reference_date=NOW.date())
        self.assertEqual(item['score'], sum(item['score_components'].values()))
        self.assertEqual(item['summary_method'], 'publisher_excerpt')
        self.assertEqual(item['score_method'], 'rules_v1')
        self.assertEqual(item['impact_analysis'], '')
        self.assertTrue(item['source_excerpt'].startswith(item['summary']))

    def test_incidental_rss_mentions_do_not_fill_the_quota(self):
        for title in ('紙おむつ姿の男の子が行方不明', 'ティッシュに取り付けるフィギュア新発売',
                      '女子トイレに侵入し生理用品を持ち去り停職処分', '4人育児で紙おむつがなくなる'):
            self.assertFalse(assess_relevance(title, '', 'ニュースサイト')[0])
        self.assertTrue(assess_relevance('住友精化、吸水性樹脂リサイクル設備を稼働', '使用済み紙おむつのリサイクル', '業界紙')[0])

    def test_same_url_prefers_verified_publisher_record(self):
        official = self.item()
        search = dict(official, title='別の表示名', date='2026-09-07', publication_date_status='unverified', summary='長い検索スニペット' * 100)
        rows = deduplicate([search, official])
        self.assertEqual(len(rows), 1)
        self.assertTrue(verified_news(rows[0]))

    def test_recommendation_paragraphs_do_not_replace_article_meta(self):
        response = Mock(url='https://example.com/news', encoding='utf-8',
                        headers={'Content-Type': 'text/html'}, content=b'html')
        response.text = '<h1>衛生用品メーカーが新型おむつを発売</h1><meta name="description" content="' + '衛生用品メーカーが新型おむつを全国で発売すると発表しました。' * 3 + '"><main><p>' + '料理と食材のおすすめランキングを紹介しています。' * 80 + '</p></main>'
        session = Mock()
        session.get.return_value = response
        details = fetch_article_details(response.url, session=session)
        self.assertIn('新型おむつ', details['excerpt'])
        self.assertNotIn('料理', details['excerpt'])

    def test_zuiko_article_body_beats_generic_company_meta(self):
        response = Mock(url='https://www.zuiko.co.jp/news/ppe/', encoding='utf-8',
                        headers={'Content-Type': 'text/html'}, content=b'html')
        response.text = '<meta name="description" content="' + '会社の汎用案内です。' * 100 + '"><div class="news_body"><p>' + 'Proga-ZUIKOは全自動PPE製造機の稼働を開始します。' * 3 + '</p></div>'
        session = Mock()
        session.get.return_value = response
        details = fetch_article_details(response.url, session=session)
        self.assertIn('Proga-ZUIKO', details['excerpt'])
        self.assertNotIn('汎用案内', details['excerpt'])

    def test_ai_failure_keeps_original_excerpt_without_fake_ai_label(self):
        item = self.item()
        with patch('generate_dashboard.ai_summarize', return_value=(True, 'AI Summary Pending')):
            self.assertTrue(generate_dashboard.process_item_with_retry(item))
        self.assertEqual(item['summary_method'], 'publisher_excerpt')
        self.assertNotIn('AI Summary Pending', item['summary'])

    def test_ai_outage_does_not_retry_for_every_article(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-only-not-a-key'}), \
                patch('generate_dashboard._OPENROUTER_UNAVAILABLE', False), \
                patch('generate_dashboard._OPENROUTER_MAX_RETRIES', 1), \
                patch('generate_dashboard.requests.post', side_effect=RuntimeError('service unavailable')) as post:
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    generate_dashboard._openrouter_generate('test')
            self.assertEqual(post.call_count, 1)

    def test_verified_but_missing_body_is_retried_not_cached_forever(self):
        old = dict(self.item(), fulltext_status='unavailable')
        repaired = dict(old, fulltext_status='excerpt_extracted')
        with patch('official_sources.collect_official_news', return_value=([self.item()], [])), \
                patch('fetch_news.prepare_official_item', return_value=repaired) as enrich, \
                patch('fetch_news.fetch_google_patents', return_value=[]):
            rows, _ = collect_news(query_limit=0, existing=[old], now=NOW)
        enrich.assert_called_once()
        self.assertEqual(rows[0]['fulltext_status'], 'excerpt_extracted')


if __name__ == '__main__':
    unittest.main()
