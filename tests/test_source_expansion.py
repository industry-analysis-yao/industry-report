import sys
import unittest
from pathlib import Path
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fetch_news import build_feed_url, assess_relevance, map_category, extract_company, fetch_article_details, fetch_google_news_rss
from official_sources import parse_index
from news_dates import parse_date, publication_evidence
from source_catalog import expanded_queries
from generate_dashboard import same_news_story, select_daily_digest, assign_daily_section
import test_generate_dashboard
from test_fetch_news import FakeParser, entry
from bs4 import BeautifulSoup


class SourceExpansionTests(unittest.TestCase):
    def test_locales_and_company_topic_coverage(self):
        for lang, suffix in [('ja', 'ceid=JP:ja'), ('en', 'ceid=US:en'), ('zh', 'ceid=CN:zh-Hans')]:
            self.assertIn(suffix, build_feed_url('robot', 7, lang))
        queries = expanded_queries()
        self.assertGreater(len(queries), 75)
        self.assertEqual({q['language'] for q in queries}, {'ja','en','zh'})
        self.assertTrue({'machine','packaging','palletizer','rivals','tissue','wet'} <= {q['group'] for q in queries})

    def test_transferable_equipment_without_diaper_keyword(self):
        for title in ['フジキカイ 包装機を出展', 'FANUC and Palladyne announce robotic automation collaboration',
                      'PAC Machinery unveils packaging machine', '安川電機 協働ロボットを発売',
                      '节卡发布码垛机器人新品']:
            with self.subTest(title=title):
                self.assertTrue(assess_relevance(title, '')[0])
                self.assertEqual(map_category(title)[0], '④')

    def test_components_materials_and_consumer_robots_are_not_equivalent(self):
        for title in ['新発売 ロボット掃除機', 'Meltio launches robot cell for metal 3D printing',
                      'ABB nuclear small modular reactor collaboration', '三菱電機 霧ヶ峰 新製品を発表',
                      'Pharmaceutical Packaging Machine Market Growth Report']:
            self.assertFalse(assess_relevance(title, '')[0], title)
        self.assertNotEqual(map_category('new nonwoven material launches')[0], '③')
        self.assertEqual(extract_company('cabbage product'), '不明')

    def test_date_formats(self):
        for raw in ('September 8, 2026', 'Sep 8, 2026', 'Sep.8.2026'):
            self.assertEqual(parse_date(raw).date(), date(2026,9,8))
        self.assertIsNone(parse_date('Sep 31, 2026'))

    def test_new_registered_index_selectors(self):
        fixtures = {
            'fuji': '<article class="item"><a href="/one"><h3 class="title">包装機</h3><div class="time">26.09.09</div></a></article>',
            'yaskawa': '<dl><dt><b>2026年9月9日</b></dt><dd><a href="/one">ロボット</a></dd></dl>',
            'omori': '<a class="home-slider__item" href="/one"><span class="home-slider__date">2026.09.09</span><span class="home-slider__name">包装機</span></a>',
            'kawashima': '<a class="newsList" href="/one"><span class="title">包装機</span><div class="date"><span>Sep.9.2026</span></div></a>',
            'universal': '<div class="sir-card-body"><a class="sir-card__link" href="/one"><h3>Robot</h3></a><time>September 9, 2026</time></div>',
            'valmet': '<div class="content-card"><a class="card" href="/one"><h3 class="card-title">Tissue machine</h3><time>Sep 9, 2026</time></a></div>',
            'andritz': '<a href="/one"><div class="ci-teaser-content"><h7 class="h-4">Nonwoven line</h7><div class="ci-kicker">2026-09-09</div></div></a>',
        }
        for source, html in fixtures.items():
            with self.subTest(source=source):
                rows = parse_index(source, html, 'https://example.com/news')
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0][1], 'https://example.com/one')
                self.assertEqual(parse_date(rows[0][2]).date(), date(2026,9,9))

    def test_orbbec_published_date_not_modified_date(self):
        rows=parse_index('orbbec',[dict(status='publish',title={'rendered':'Robotic vision'},link='https://example.com/one',
             date_gmt='2026-09-08T12:00:00',modified_gmt='2026-09-09T00:00:00',excerpt={'rendered':'<p>Body</p>'})], 'https://example.com')
        self.assertEqual(rows[0][2], '2026-09-08T12:00:00Z')

    def test_five_calendar_days_and_three_day_preference(self):
        make=test_generate_dashboard.DailyDigestTests().make_item
        items=[make(i,'①',published=d,score=s) for i,(d,s) in enumerate([
            ('2026-09-10',20),('2026-09-08',30),('2026-09-07',99),('2026-09-06',98),('2026-09-05',100),('2026-09-11',100)])]
        result=select_daily_digest(items, reference_date=date(2026,9,10),minimum=0,target=20)
        self.assertEqual([r['date'] for r in result], ['2026-09-08','2026-09-10','2026-09-07','2026-09-06'])

    def test_translations_and_original_source_identity(self):
        self.assertTrue(same_news_story({'url':'https://finance.biggo.jp/news/TW_1'}, {'url':'https://finance.biggo.com/news/TW_1'}))
        self.assertFalse(same_news_story({'url':'https://finance.biggo.jp/news/TW_1'}, {'url':'https://finance.biggo.com/news/TW_2'}))
        self.assertTrue(same_news_story({'url':'https://media/news','original_source_url':'https://maker/one'}, {'url':'https://maker/one'}))

    def test_wet_packaging_is_not_a_wet_tissue_product_or_robot(self):
        item={'title':'wet wipe packaging machine automation launch','category_id':'④'}
        self.assertEqual(assign_daily_section(item),'packaging')

    def test_source_counts_include_raw_and_rejection_reasons(self):
        now=datetime(2026,9,9,tzinfo=timezone.utc)
        parser=FakeParser([entry(title='FANUC robotic automation launch',published=now),
                           entry(title='ロボット掃除機 新発売',published=now)])
        health={}
        items=fetch_google_news_rss('robot',language='en',group='palletizer',now=now,feed_parser=parser,diagnostics=health)
        self.assertEqual((health['raw'],health['date_eligible'],len(items)),(2,2,1))
        self.assertEqual(health['rejected'],{'outside_supply_chain_scope':1})

    def test_reporter_date_cannot_replace_linked_manufacturer_date(self):
        def response(url,body):
            return Mock(url=url,encoding='utf-8',headers={'Content-Type':'text/html'},content=body.encode(),text=body)
        reporter='https://www.automation-news.jp/2026/09/one'
        manufacturer='https://www.yaskawa.co.jp/newsrelease/product/one'
        session=Mock()
        session.get.side_effect=[response(reporter,'<meta property="article:published_time" content="2026-09-09"><article><div class="post_content"><p>'+'Robot launch facts. '*20+'</p><a class="p-blogCard__title" href="'+manufacturer+'">Source</a></div></article>'),
                                 response(manufacturer,'<p class="news_date">2026年8月31日</p><article><p>'+'Manufacturer details. '*20+'</p></article>')]
        result=fetch_article_details(reporter,session=session)
        self.assertEqual(result['publisher_date'],'2026-08-31')
        self.assertEqual(result['reporting_publication_evidence']['publisher_date'],'2026-09-09')

    def test_earlier_date_is_not_inferred_from_product_name_or_url(self):
        result=publication_evidence(BeautifulSoup('<p>展示会は2026年8月31日開催</p>','html.parser'),'https://example.com/20260831')
        self.assertEqual(result['publication_date_status'],'unverified')

    def test_shared_product_code_collapses_rewritten_release(self):
        left={'title':'大型LEDピッキング表示器の新製品を発売','date':'2026-09-08','summary':'機種SGLT2-1-200Tは投入を検知する。'}
        right={'title':'アイオイ、新しい検知技術を搭載した機器を発売へ','date':'2026-09-09','summary':'新製品の名称はSGLT2-1-200T。'}
        self.assertTrue(same_news_story(left,right))
        right['summary']='新製品の名称はABCD9-7-300T。'
        self.assertFalse(same_news_story(left,right))

    def test_unrelated_conglomerate_and_consumer_robot_news_are_rejected(self):
        for title in ['三菱電機、量子CAEの技術基盤を開発', 'TANIOBIS、半導体用タンタル粉末の製造設備を増強',
                      'LOVOTのアニマルウェアを新発売', '生理用品を無償提供 すこやか薬局が実証事業']:
            self.assertFalse(assess_relevance(title,'')[0],title)

    def test_raw_source_link_is_followed_not_only_a_blog_card(self):
        def response(url,body):
            return Mock(url=url,encoding='utf-8',headers={'Content-Type':'text/html'},content=body.encode(),text=body)
        url='https://www.automation-news.jp/2026/09/factory'
        source='https://www.omori.co.jp/news/10424/'
        session=Mock()
        session.get.side_effect=[response(url,'<meta property="article:published_time" content="2026-09-09"><article><div class="post_content"><p>'+'Factory technical facts. '*20+'</p><a href="'+source+'">Source</a></div></article>'),
            response(source,'<meta property="article:published_time" content="2026-06-15"><p>Manufacturer original release.</p>')]
        self.assertEqual(fetch_article_details(url,session=session)['publisher_date'],'2026-06-15')


if __name__=='__main__':
    unittest.main()
