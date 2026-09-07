"""Recheck retained news; repair dates and remove proven stale snapshot entries.

Run without --apply to inspect; --apply mechanically migrates JSON data, retaining
an audit trail. Unverified historical entries are not silently deleted.
"""
import argparse
import json
from pathlib import Path
from datetime import date, datetime, timezone
from fetch_news import enrich_items, article_fingerprint
from news_dates import verified_news


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent.parent / 'data'
    source = directory / 'news_data.json'
    raw = json.loads(source.read_text(encoding='utf-8'))
    rows = [row for bucket in raw.get('dates', {}).values() for row in bucket]
    checked = enrich_items(rows, limit=len(rows))
    by_url = {old['url']: new for old, new in zip(rows, checked)}
    audit = []
    for old, new in zip(rows, checked):
        audit.append({
            'url': old.get('url'), 'canonical_url': new.get('url'),
            'previous_date': old.get('date'), 'publisher_date': new.get('publisher_date'),
            'status': new.get('publication_date_status', 'unverified'),
            'evidence_source': new.get('publication_date_source'),
            'evidence_raw': new.get('publication_date_raw'),
            'evidence_url': new.get('publication_date_url'),
        })
    corrected = [r for r in audit if r['status'] == 'verified' and r['previous_date'] != r['publisher_date']]
    print(json.dumps({'checked': len(rows), 'verified': sum(verified_news(r) for r in checked),
                      'date_corrections': corrected}, ensure_ascii=False, indent=2))
    if not args.apply:
        return

    def write(path, payload):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # Preserve existing editor/AI content, only migrate publication evidence.
    def migrate(old, new):
        result = dict(old)
        for key, value in new.items():
            if key.startswith(('publisher_', 'publication_date_')) or key in {
                'date', 'published_at', 'rss_published_at', 'url', 'discovery_url', 'quality_flags'}:
                result[key] = value
        result['fingerprint'] = article_fingerprint(result)
        return result

    raw['dates'] = {}
    for old, new in zip(rows, checked):
        fixed = migrate(old, new)
        if verified_news(fixed) and (date.today() - date.fromisoformat(fixed['date'])).days > 60:
            continue
        raw['dates'].setdefault(fixed['date'], []).append(fixed)
    removed_urls = set()
    for snapshot in directory.glob('????-??-??.json'):
        snapshot_date = date.fromisoformat(snapshot.stem)
        payload = json.loads(snapshot.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            continue
        items = []
        removed_here = set()
        for item in payload.get('items', []):
            checked_item = by_url.get(item.get('url'))
            if checked_item and verified_news(checked_item):
                age = (snapshot_date - date.fromisoformat(checked_item['date'])).days
                if age > 60 or age < -1:
                    removed_here.add(item.get('url'))
                    continue
                item = migrate(item, checked_item)
            items.append(item)
        if items != payload.get('items', []):
            payload['items'] = items
            payload['highlights'] = [h for h in payload.get('highlights', []) if h.get('url') not in removed_here]
            write(snapshot, payload)
        removed_urls.update(removed_here)
    raw['highlights'] = [h for h in raw.get('highlights', []) if h.get('url') not in removed_urls]
    write(source, raw)
    write(directory / 'publication_date_audit.json', {
        'checked_at': datetime.now(timezone.utc).isoformat(), 'records': audit,
        'removed_stale_urls': sorted(removed_urls),
    })
    print(f'Removed {len(removed_urls)} proven stale URLs from daily snapshots; audit saved.')


if __name__ == '__main__':
    main()
