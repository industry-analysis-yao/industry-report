"""Dated manufacturer news indexes, independent of search-engine coverage.

Only a date bound to the SAME title/link in a registered publisher index is
publication evidence. Page build dates, JSON mod_on and PDF metadata are not.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit
import re

import requests
from bs4 import BeautifulSoup
from news_dates import JST, DATE_VERSION, parse_date

KAO_INDEX = 'https://www.kao.com/content/dam/article/newsindex/v4.content.wcm_kao.sites.kao.www-kao-com.jp.ja.newsroom.news.1.json'
NIPPON_INDEX = 'https://www.nipponpapergroup.com/data/news_data_ja.json'


def clean(value):
    return re.sub(r'\s+', ' ', BeautifulSoup(value or '', 'html.parser').get_text(' ', strip=True)).strip()


def parse_index(source, content, index_url):
    """Return bound (title, URL, publication date, excerpt) records; no IO."""
    if source == 'nippon':
        return [(clean(r.get('title')), urljoin(index_url, r.get('url', '')),
                 r.get('pub_on'), clean(r.get('body')))
                for r in content.get('article', []) if r.get('url') and r.get('url_type') != 'none']
    if source == 'kao':
        # 更新情報 links often target a rolling archive rather than this release.
        return [(clean(r.get('title')), r['link']['url'], r.get('time'), clean(r.get('summary')))
                for r in content.get('items', []) if r.get('link', {}).get('url')
                and r.get('label', {}).get('title') != '更新情報']
    soup = BeautifulSoup(content, 'html.parser')
    selectors = {
        'unicharm': ('li.uc-item', 'a[href]', '.uc-title', '.uc-date'),
        'daio': ('li.clearfix', 'p.title a[href]', 'p.title a', 'p.date time'),
        'zuiko': ('li.news_item', 'a.news_link', '.news_text', '.news_date'),
        'oji': ('li.c-newslist__item', 'a.c-newslist__anchor', '.c-newslist__subject', 'time'),
    }
    row_selector, link_selector, title_selector, date_selector = selectors[source]
    rows = []
    for row in soup.select(row_selector):
        link, title, date = row.select_one(link_selector), row.select_one(title_selector), row.select_one(date_selector)
        if link and title and date:
            # Daio's datetime is WordPress's edit timestamp; the visible date is
            # the publisher's release date (e.g. edit Sep4, published Sep7).
            raw_date = date.get_text(' ', strip=True)
            rows.append((title.get('title') or title.get_text(' ', strip=True),
                         urljoin(index_url, link['href']), raw_date, ''))
    return rows


def official_relevance(title, company):
    """Evaluate the release subject, NOT footer/navigation or generic boilerplate."""
    text = title.lower()
    excluded = ('ペットフード', 'キャットフード', 'ドッグフード', '猫用フード', '犬用フード',
                '愛犬用', '愛猫用', 'おやつ', '猫砂', 'ゴルフ', 'ゴルファー', 'カプセルトイ',
                'スキンケア', '化粧品', 'ソフィーナ', '美容液', '乳液', 'シャンプー', '洗濯洗剤', '柔軟剤',
                '夏季休業', '感謝祭', 'ダンス部', 'フォトコンテスト', '短歌')
    if any(term in text for term in excluded):
        return False
    signals = ('おむつ', 'オムツ', 'ナプキン', '生理', '月経', 'ソフィ', 'sofy', 'ムーニー',
               'マミーポコ', 'グーン', 'エリス', 'ロリエ', 'マスク', '失禁', '衛生',
               'ティシュ', 'ティッシュ', 'ティシュー', 'ウエット', 'ウェット', 'おしりふき',
               '家庭紙', 'ペーパー', 'ふきん', 'ハンドタオル', '不織布', 'パルプ', '吸収',
               '加工機', '包装', '設備', '自動化', '製造', '生産', '工場', '火災',
               '投資', '買収', '業績', '決算', '損失', '事業', '株式', '需要計画',
               '研究', '技術', '新素材', 'セルロース', 'バイオ', 'リサイクル', '再資源',
               '環境', '脱炭素', 'esg', 'gx', '人権', 'サプライ', 'ppe', 'packplus')
    return any(term in text for term in signals)


def index_item(title, url, raw_date, excerpt, *, company, source, index_url, now):
    published = parse_date(raw_date)
    if not published or not title or urlsplit(url).scheme not in {'http', 'https'}:
        return None
    age = (now.astimezone(JST).date() - published.astimezone(JST).date()).days
    if not 0 <= age <= 60 or not official_relevance(title, company):
        return None
    date = published.astimezone(JST).date().isoformat()
    timestamp = published.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    return {
        'title': title, 'url': url, 'company': '日本製紙クレシア' if 'クレシア' in title else company, 'date': date,
        'published_at': timestamp, 'publisher_date': date, 'publisher_published_at': timestamp,
        'publication_date_status': 'verified', 'publication_date_source': 'official_index:' + source,
        'publication_date_url': index_url, 'publication_date_raw': raw_date,
        'publication_date_version': DATE_VERSION,
        'source_name': company + ' 公式発表', 'source_url': index_url,
        'source_kind': 'manufacturer_official', 'region': 'Japan',
        'summary': excerpt, 'source_excerpt': excerpt, 'summary_method': 'publisher_excerpt',
        'confidence': '高', 'quality_flags': [], 'permanent_record': False,
        'discovered_at': now.isoformat(),
    }


def collect_official_news(*, now=None, get=None, sources=None):
    now = now or datetime.now(timezone.utc)
    get = get or requests.get
    sources = sources if sources is not None else [
        ('unicharm', 'ユニ・チャーム', f'https://www.unicharm.co.jp/ja/company/news/{year}.html')
        for year in sorted({now.year, (now - timedelta(days=60)).year}, reverse=True)
    ] + [
        ('nippon', '日本製紙', NIPPON_INDEX),
        ('kao', '花王', KAO_INDEX),
        ('daio', '大王製紙', 'https://www.daio-paper.co.jp/news/'),
        ('oji', '王子ホールディングス', 'https://www.ojiholdings.co.jp/news/'),
        ('zuiko', '瑞光', 'https://www.zuiko.co.jp/'),
    ]

    def fetch(spec):
        source, company, index_url = spec
        diagnostic = {'source': source, 'url': index_url, 'parsed': 0, 'accepted': 0}
        try:
            response = get(index_url, timeout=25, headers={'User-Agent': 'industry-report/3.0'})
            response.raise_for_status()
            payload = response.json() if source in {'nippon', 'kao'} else response.content
            rows = parse_index(source, payload, index_url)
            diagnostic['parsed'] = len(rows)
            if not rows:
                raise ValueError('No dated rows found; publisher layout may have changed')
            items = []
            for title, url, raw_date, excerpt in rows:
                item = index_item(title, url, raw_date, excerpt, company=company, source=source, index_url=index_url, now=now)
                if item:
                    items.append(item)
            diagnostic.update(status='ok', accepted=len(items))
            return items, diagnostic
        except Exception as exc:
            diagnostic.update(status='error', error=str(exc))
            return [], diagnostic

    results = list(ThreadPoolExecutor(max_workers=6).map(fetch, sources))
    return [item for items, _ in results for item in items], [d for _, d in results]
