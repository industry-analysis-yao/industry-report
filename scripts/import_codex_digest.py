"""Publish an already source-reviewed Codex edition. No model/network calls.

The input is editorial evidence, NOT raw search results. Run in a clean checkout,
review the generated diff, test, then commit/push to publish via GitHub Pages.
"""
import argparse
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from generate_dashboard import load_previous_digest_items, same_news_story, assign_daily_section
from editorial_language import validate_japanese_item
from codex_review_gate import validate_review
from source_catalog import robot_scope_exclusion, PALLETIZER_TERMS

SECTIONS = {
    '卫生用品・吸收护理': ('rivals', '①', '日用品・衛生用品メーカー'),
    '竞争厂家经营・物流': ('rivals', '②', '競合・物流・経営'),
    'Tissue・干式生活用纸': ('tissue', '⑥', 'ティッシュペーパー・家庭紙'),
    'Wet Tissue・湿巾': ('wet', '⑤', 'ウェットティッシュ・ワイプ'),
    'Toilet Paper・卫生纸': ('toilet', '⑥', 'トイレットペーパー'),
    '包装设备・包装材料': ('packaging', '④', '包装設備・包装材料'),
    '加工・制浆设备': ('machine', '③', '加工・パルプ設備'),
    '机器人・生产自动化': ('palletizer', '④', 'パレタイザー・積付け設備'),
    '材料・无纺布': ('rivals', '②', '材料・不織布'),
    '企业专利': ('patent', '⑦', '企業特許'),
}


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def public_item(raw, issue_date):
    required = ('id', 'kind', 'section', 'date', 'event_id', 'company', 'title_ja',
                'summary_ja', 'relevance_ja', 'url', 'date_evidence', 'verification_level',
                'caution', 'priority', 'region', 'relationship')
    if any(not isinstance(raw.get(k), str) or not raw[k].strip() for k in required):
        raise ValueError('Missing editorial evidence: ' + str(raw.get('id')))
    if raw['kind'] not in ('news', 'patent'):
        raise ValueError('Unknown record kind')
    if not 0 <= (issue_date - date.fromisoformat(raw['date'])).days < 5:
        raise ValueError('Outside five-calendar-day issue window: ' + raw['id'])
    parts = urlsplit(raw['url'])
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('A public HTTPS source is required')
    section, cid, category = SECTIONS[raw['section']]
    patent = raw['kind'] == 'patent'
    if patent != (section == 'patent'):
        raise ValueError('Patent/news section mismatch')
    if len(raw['summary_ja']) < 60:
        raise ValueError('Insufficient source-reviewed summary')
    if raw['priority'] not in ('重点', '観察'):
        raise ValueError('Unknown editorial priority')
    # Whitelist output fields: never publish local evidence paths or raw captures.
    result = {k: raw[k] for k in ('id', 'event_id', 'company', 'date', 'url',
                                  'date_evidence', 'verification_level', 'caution',
                                  'priority', 'region', 'relationship')}
    result.update(
        title=raw['title_ja'], summary=raw['summary_ja'],
        impact_analysis=raw['relevance_ja'], category_id=cid, category_name=category,
        content_language=raw.get('content_language'),
        info_type='特許' if patent else '業界動向', dashboard_section=section,
        source_name=parts.hostname, summary_method='codex_editorial',
        publication_date_status='verified', publisher_date=raw['date'],
        # Date precision only: do not manufacture a midnight publication time.
        published_at=raw['date'], publisher_published_at=raw['date'],
        publication_date_precision='day', fulltext_status='editorially_reviewed',
        permanent_record=patent, is_academic=False, editorial_issue=issue_date.isoformat(),
        event_type=raw.get('event_type', ''), score=0,
    )
    if patent:
        for key in ('publication_number', 'application_number', 'application_date', 'patent_family_status'):
            if not raw.get(key):
                raise ValueError('Missing patent evidence: ' + key)
            result[key] = raw[key]
        if date.fromisoformat(raw['application_date']) > date.fromisoformat(raw['date']):
            raise ValueError('Patent application after publication')
        result.update(patent_number=raw['publication_number'], grant_date=raw.get('grant_date'),
                      legal_status='未確認（公開公報を確認。登録・有効性は未確認）')
    validate_japanese_item(result)
    if not re.search(r'[ぁ-ゖァ-ヺ一-龯]', result['title']):
        raise ValueError('Translate the headline into Japanese before publication')
    automatic_section = assign_daily_section({**result, 'summary_method': ''})
    if section == 'tissue' and automatic_section == 'wet':
        raise ValueError('Wet tissue must not be classified as dry tissue')
    if not patent and robot_scope_exclusion(result['title'], result['summary']):
        raise ValueError('Robot article has no concrete packaging/converting/palletizing application')
    if section == 'palletizer' and not any(
            term in (result['title'] + ' ' + result['summary']).lower() for term in PALLETIZER_TERMS):
        raise ValueError('Palletizer section requires concrete palletizing evidence')
    return result


def merge_records(existing, incoming):
    urls = {it['url'] for it in incoming}
    numbers = {it.get('patent_number') for it in incoming} - {None, ''}
    return incoming + [it for it in existing if it.get('url') not in urls and
                       (it.get('patent_number') or it.get('publication_number')) not in numbers]


def publish(source, data_dir):
    raw = read(Path(source), {})
    review = validate_review(raw)
    issue_date = date.fromisoformat(raw['date'])
    converted = [public_item(it, issue_date) for it in raw['items']]
    news_count = sum(not it['permanent_record'] for it in converted)
    if not 1 <= news_count <= 20 or len(converted) - news_count > 30:
        raise ValueError('Edition requires 1–20 reviewed NEWS; patents are a separate quota (max 30)')
    directory = Path(data_dir)
    previous = load_previous_digest_items(str(directory), issue_date)
    seen_ids, seen_urls, seen_numbers = set(), set(), set()
    existing_vault = read(directory / 'permanent_vault.json', [])
    news, patents = [], []
    for it in converted:
        if it['event_id'] in seen_ids or it['url'] in seen_urls:
            raise ValueError('Duplicate event or source in edition')
        seen_ids.add(it['event_id'])
        seen_urls.add(it['url'])
        if it['permanent_record']:
            if it['patent_number'] in seen_numbers:
                raise ValueError('Duplicate patent publication')
            if any((old.get('patent_number') or old.get('publication_number')) == it['patent_number']
                   and old.get('editorial_issue') != raw['date'] for old in existing_vault):
                raise ValueError('Patent already in archive; do not count as newly added')
            seen_numbers.add(it['patent_number'])
            patents.append(it)
        else:
            if any(same_news_story(it, old) for old in previous + news):
                raise ValueError('Duplicate in edition/30-day history: ' + it['id'])
            news.append(it)
    counts = dict(Counter(it['dashboard_section'] for it in news))
    highlights = [dict(title=it['title'], company=it['company'], date=it['date'],
                       category=it['category_name'], impact=it['impact_analysis'],
                       url=it['url'], score=0) for it in news if it['priority'] == '重点'][:3]
    snapshot = dict(
        date=raw['date'], digest_window_days=5, target_count=20,
        publication_mode='codex_editorial',
        editorial_review=review,
        publication_note='Codex編集版：ニュース18件＋企業特許2件。原文公開日を確認。展示会予告・観察情報を含みます。'
                         if len(news) == 18 and len(patents) == 2 else
                         f'Codex編集版：ニュース{len(news)}件＋企業特許{len(patents)}件。原文公開日を確認。',
        edition_counts=dict(news=len(news), new_patents=len(patents), total=len(converted)),
        selection_health=dict(target=20, selected=len(news), shortfall=max(0, 20-len(news)),
                              history_records_checked=len(previous), section_counts=counts),
        items=news, new_patents=patents, highlights=highlights,
    )
    main = read(directory / 'news_data.json', {})
    if main and (not isinstance(main, dict) or main.get('schema_version') != 2):
        raise ValueError('Expected schema_version 2; migrate legacy data first')
    main.setdefault('schema_version', 2)
    buckets = main.setdefault('dates', {})
    for day in {it['date'] for it in news}:
        buckets[day] = merge_records(buckets.get(day, []), [it for it in news if it['date'] == day])
    main['patents'] = merge_records(main.get('patents', []), patents)
    main['highlights'] = highlights
    main['last_updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    vault = merge_records(existing_vault, patents)
    vault.sort(key=lambda it: it.get('date', ''), reverse=True)
    index = sorted(set(read(directory / 'dates_index.json', []) + [raw['date']]), reverse=True)
    # All validation precedes writes; Git makes the reviewed multi-file release atomic.
    for filename, payload in [(raw['date']+'.json', snapshot), ('news_data.json', main),
                              ('permanent_vault.json', vault), ('dates_index.json', index)]:
        (directory / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return snapshot


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1]/'data')
    args = parser.parse_args()
    if args.data_dir.resolve() == (Path(__file__).resolve().parents[1]/'data').resolve():
        from news_dates import JST
        if read(args.source, {}).get('date') != datetime.now(JST).date().isoformat():
            parser.error('Public release must be for today in JST; use an isolated directory for historical tests')
    result = publish(args.source, args.data_dir)
    print(json.dumps(result['edition_counts'], ensure_ascii=False))
