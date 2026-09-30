"""Direct publisher feeds: discovery without Google's index or redirect service.

Feed timestamps remain discovery evidence, with the same publisher-page date
and body verification as search results. These are not manufacturer indexes.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import calendar
import requests
import feedparser
from news_dates import parse_date

PUBLISHER_FEEDS = [
    ('Automation News', 'https://www.automation-news.jp/wp-json/wp/v2/posts?per_page=100&orderby=date&order=desc', 'equipment', 'ja'),
    ('PR TIMES', 'https://prtimes.jp/index.rdf', 'general', 'ja'),
    ('IoTNEWS', 'https://iotnews.jp/feed/', 'equipment', 'ja'),
    # The global feed's 200 slots are quickly consumed by unrelated releases.
    # Company feeds remain discovery only: article date/body must be verified.
    ('PR TIMES ユニ・チャーム', 'https://prtimes.jp/companyrdf.php?company_id=26351', 'rivals', 'ja'),
    ('PR TIMES 大王製紙', 'https://prtimes.jp/companyrdf.php?company_id=1310', 'rivals', 'ja'),
    ('PR TIMES ラピュタロボティクス', 'https://prtimes.jp/companyrdf.php?company_id=21229', 'palletizer', 'ja'),
    ('PR TIMES LexxPluss', 'https://prtimes.jp/companyrdf.php?company_id=56714', 'palletizer', 'ja'),
    ('PR TIMES 日本製紙クレシア', 'https://prtimes.jp/companyrdf.php?company_id=73407', 'tissue', 'ja'),
    ('PR TIMES 王子ネピア', 'https://prtimes.jp/companyrdf.php?company_id=61604', 'tissue', 'ja'),
    ('PR TIMES リブドゥ', 'https://prtimes.jp/companyrdf.php?company_id=96567', 'rivals', 'ja'),
    ('PR TIMES フジキカイ', 'https://prtimes.jp/companyrdf.php?company_id=170548', 'packaging', 'ja'),
    ('PR TIMES 丸富製紙', 'https://prtimes.jp/companyrdf.php?company_id=20832', 'tissue', 'ja'),
    ('PR TIMES レック', 'https://prtimes.jp/companyrdf.php?company_id=173565', 'wet', 'ja'),
    ('PR TIMES カミ商事', 'https://prtimes.jp/companyrdf.php?company_id=186260', 'tissue', 'ja'),
]


def discovery_timestamp(entry, parse_published_at):
    """RSS 1.0 dc:date maps to updated in feedparser (not published).

    This fallback ONLY schedules publisher verification. Never promote an RSS
    updated timestamp to verified publication evidence; an old updated article
    must still fail the article-page publication-date gate.
    """
    published = parse_published_at(entry) or parse_date(entry.get('published'))
    if published:
        return published, 'published'
    parsed = entry.get('updated_parsed')
    if parsed:
        try:
            return datetime.fromtimestamp(calendar.timegm(parsed), timezone.utc), 'updated_discovery_only'
        except (TypeError, ValueError, OverflowError):
            pass
    return parse_date(entry.get('updated')), 'updated_discovery_only'


def collect_publisher_feeds(*, now=None, get=None, sources=None):
    from fetch_news import (parse_published_at, strip_html, assess_relevance, map_category,
                            extract_company, isoformat_utc, article_fingerprint, JST)
    get = get or requests.get
    now = now or datetime.now(timezone.utc)

    def fetch(spec):
        name, url, group, language = spec
        health = dict(source=name, url=url, raw=0, accepted=0, recent_7_days=0,
                      rejected_scope=0, missing_or_outside_date=0)
        try:
            response = get(url, timeout=20, headers={'User-Agent': 'industry-report/3.0'})
            response.raise_for_status()
            if '/wp-json/' in url:
                entries = [dict(title=r['title']['rendered'], summary=r['excerpt']['rendered'],
                                link=r['link'], published=r['date_gmt']+'Z') for r in response.json()]
            else:
                feed = feedparser.parse(response.content)
                entries = feed.entries
                if feed.bozo and not entries:
                    raise ValueError('Invalid publisher RSS')
            health['raw'] = len(entries)
            items=[]
            for entry in entries[:200]:
                published, timestamp_source = discovery_timestamp(entry, parse_published_at)
                if not published or not now-timedelta(days=7) <= published <= now:
                    health['missing_or_outside_date'] += 1
                    continue
                health['recent_7_days'] += 1
                title, snippet = strip_html(entry.get('title','')), strip_html(entry.get('summary',''))
                relevant, flags = assess_relevance(title, snippet, name)
                if not relevant or not entry.get('link'):
                    health['rejected_scope'] += 1
                    continue
                cat, cat_name = map_category(title)
                item = dict(title=title, summary=snippet, url=entry['link'],
                    date=published.astimezone(JST).date().isoformat(), published_at=isoformat_utc(published),
                    rss_published_at=isoformat_utc(published), publication_date_status='unverified',
                    discovery_timestamp_source=timestamp_source,
                    source_name=name, source_url=url, source_kind='publisher_feed',
                    discovery_provider='Publisher RSS', discovery_group=group, discovery_language=language,
                    category_id=cat, category_name=cat_name, company=extract_company(title+' '+snippet),
                    confidence='中', quality_flags=flags, permanent_record=False)
                item['fingerprint']=article_fingerprint(item)
                items.append(item)
            health.update(status='ok', accepted=len(items))
            return items, health
        except Exception as exc:
            health.update(status='error', error=str(exc))
            return [], health

    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(fetch, PUBLISHER_FEEDS if sources is None else sources))
    return [it for rows,_ in results for it in rows], [h for _,h in results]
