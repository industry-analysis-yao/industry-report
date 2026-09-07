"""Publisher publication evidence; search/feed timestamps are discovery only."""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

JST = timezone(timedelta(hours=9))
DATE_VERSION = 1


def article_url(url):
    """Collapse known WalkerPlus image pages to their parent article."""
    parts = urlsplit(url)
    if (parts.hostname or '').lower() in {'walkerplus.com', 'www.walkerplus.com'}:
        match = re.fullmatch(r'/article/(\d+)/(?:image\d+\.html)?', parts.path)
        if match:
            return urlunsplit((parts.scheme, parts.netloc, '/article/' + match[1] + '/', '', ''))
    return url


def parse_date(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    japanese = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', value)
    if japanese:
        value = '%04d-%02d-%02d' % tuple(map(int, japanese.groups()))
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=JST) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def publication_evidence(soup, url):
    """Use explicitly published dates, never modified/build/sidebar dates."""
    candidates = []

    def add(value, source):
        parsed = parse_date(value)
        if parsed:
            candidates.append((parsed, source, value))

    for meta in soup.select('meta'):
        key = (meta.get('property') or meta.get('name') or meta.get('itemprop') or '').lower()
        if key in {'article:published_time', 'datepublished', 'pubdate', 'publishdate', 'dc.date.issued'}:
            add(meta.get('content'), 'meta:' + key)
    for node in soup.select('[itemprop="datePublished"]'):
        add(node.get('datetime') or node.get('content') or node.get_text(' ', strip=True), 'itemprop:datePublished')

    def visit(value):
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            kinds = value.get('@type', [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if any(kind in {'NewsArticle', 'Article', 'BlogPosting', 'Report'} for kind in kinds):
                add(value.get('datePublished'), 'jsonld:datePublished')
            # Only top-level graph/main entity; don't inspect related articles.
            for key in ('@graph', 'mainEntity'):
                if key in value:
                    visit(value[key])
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            pass

    if (urlsplit(url).hostname or '').endswith('walkerplus.com'):
        # WalkerPlus's dateless <time> beside the heading is publication time.
        # Its unrelated page-generation meta timestamp must never be used.
        for node in soup.select('time')[:1]:
            add(node.get('datetime') or node.get_text(' ', strip=True), 'walkerplus:time')
    if not candidates:
        return {'publication_date_status': 'unverified'}
    parsed, source, raw = min(candidates, key=lambda row: row[0])
    return {
        'publication_date_status': 'verified',
        'publisher_published_at': parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'publisher_date': parsed.astimezone(JST).date().isoformat(),
        'publication_date_source': source,
        'publication_date_raw': raw,
        'publication_date_url': url,
        'publication_date_version': DATE_VERSION,
    }


def verified_news(item):
    return (item.get('publication_date_status') == 'verified'
            and item.get('date') == item.get('publisher_date')
            and item.get('published_at') == item.get('publisher_published_at'))
