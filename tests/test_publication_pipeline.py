import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_dashboard as g
from news_dates import JST
from fetch_news import assess_relevance
from official_sources import parse_index


def item(n, day='2026-09-11'):
    unique=''.join(chr(0x4e00+n*100+j) for j in range(80))
    return dict(title=unique+' 包装機の新製品を発売',
                source_excerpt=unique*3, summary=unique,
                url=f'https://manufacturer.example/{n}', company='メーカー', date=day,
                published_at=day+'T00:00:00Z', publisher_published_at=day+'T00:00:00Z',
                publisher_date=day, publication_date_status='verified',
                fulltext_status='excerpt_extracted', category_id='④', confidence='高')


class PublicationPipelineTests(unittest.TestCase):
    def test_weekend_jst_boundary(self):
        friday_utc=datetime(2026,9,11,22,5,tzinfo=timezone.utc)
        sunday_utc=datetime(2026,9,13,22,5,tzinfo=timezone.utc)
        self.assertFalse(g.publication_day(friday_utc.astimezone(JST).date()))
        self.assertTrue(g.publication_day(sunday_utc.astimezone(JST).date()))
        with tempfile.TemporaryDirectory() as d, patch.object(g,'load_data') as load:
            g.main(d, date(2026,9,13))
            load.assert_not_called()
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_old_and_history_items_never_consume_ai_budget(self):
        old, published, fresh = item(1,'2026-08-20'), item(2), item(3)
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test', 'MAX_AI_ITEMS_PER_RUN':'1'}), \
                patch.object(g,'process_item_with_retry',return_value=True) as process:
            ready, audit=g.prepare_daily_candidates([old,published,fresh],[published],date(2026,9,11))
        self.assertEqual([i['url'] for i in ready],[fresh['url']])
        self.assertEqual(process.call_args.args[0]['url'],fresh['url'])
        self.assertEqual(audit['counts']['already_published_in_30_days'],1)

    def test_negative_review_cached_until_source_changes(self):
        candidate=item(10)
        data=[candidate]
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test'}), \
                patch.object(g,'process_item_with_retry',return_value=False) as process:
            self.assertEqual(g.prepare_daily_candidates(data,[],date(2026,9,11))[0],[])
            _,audit=g.prepare_daily_candidates(data,[],date(2026,9,11))
            self.assertEqual(audit['cached_rejections'],1)
            self.assertEqual(process.call_count,1)
            candidate['source_excerpt'] += 'additional published evidence'
            g.prepare_daily_candidates(data,[],date(2026,9,11))
            self.assertEqual(process.call_count,2)
        self.assertEqual(len(data),1)  # Evidence isn't deleted.

    def test_full_source_and_rejection_reason_reach_model_and_cache(self):
        candidate=item(11)
        with patch.object(g,'ai_summarize',return_value=(False,'IRRELEVANT: university only')) as summarize:
            self.assertFalse(g.process_item_with_retry(candidate))
            self.assertEqual(summarize.call_args.args[1],candidate['source_excerpt'])
            self.assertIn('university',candidate['ai_rejection_reason'])

    def test_same_day_rerun_preserves_valid_issued_articles_not_spam(self):
        issued=[item(n) for n in range(20)]
        spam=item(100)
        spam['title']='Tissue Paper Converting Machine Market to Reach USD 7.4 Billion by 2036'
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test'}), \
                patch.object(g,'process_item_with_retry',return_value=False) as process:
            ready,_=g.prepare_daily_candidates(issued+[spam],[],date(2026,9,11),published_today=issued+[spam])
        self.assertEqual(len(ready),20)
        process.assert_not_called()
        self.assertFalse(assess_relevance(spam['title'],'')[0])

    def test_five_working_days_each_twenty_without_cross_day_repeats(self):
        history=[]
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':''}):
            for offset in range(5):
                day=date(2026,9,7)+timedelta(days=offset)
                candidates=[item(offset*30+n,day.isoformat()) for n in range(25)]
                ready,_=g.prepare_daily_candidates(history+candidates,history,day)
                digest=g.select_daily_digest(ready,reference_date=day,previous_items=history)
                self.assertEqual(len(digest),20)
                self.assertFalse({i['url'] for i in history}&{i['url'] for i in digest})
                history+=copy.deepcopy(digest)
        self.assertEqual(len(history),100)

    def test_main_round_trip_does_not_lose_negative_candidates(self):
        with tempfile.TemporaryDirectory() as d:
            g.save_data(str(Path(d)/'news_data.json'),[item(9)])
            with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test'}), \
                    patch.object(g,'process_item_with_retry',return_value=False):
                g.main(d,date(2026,9,11))
            self.assertEqual(len(g.load_data(str(Path(d)/'news_data.json'))[0]),1)
            audit=json.loads((Path(d)/'selection_audit.json').read_text(encoding='utf-8'))
            self.assertEqual(audit['counts']['ai_rejected'],1)

    def test_packaging_inspection_official_index(self):
        html='<div class="newsbox"><a href="/whatsnew/event/7094/"><div class="data">2026年09月11日</div><div class="txt">TOKYO PACK 出展のご案内</div></a></div>'
        rows=parse_index('aandd',html,'https://www.aandd.co.jp/whatsnew/')
        self.assertEqual(rows[0][1],'https://www.aandd.co.jp/whatsnew/event/7094/')
        self.assertEqual(rows[0][2],'2026年09月11日')
