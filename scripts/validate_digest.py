"""Fail publication on invalid dates, duplicates, empty bodies or bad counts."""
import json
from datetime import datetime
from pathlib import Path
from news_dates import JST, verified_news
from generate_dashboard import load_previous_digest_items, same_news_story, assign_daily_section, DAILY_DIGEST_MAX_AGE_DAYS


def validate_digest(data_dir, reference_date):
    payload = json.loads((Path(data_dir) / f'{reference_date.isoformat()}.json').read_text(encoding='utf-8'))
    items = payload['items']
    history = load_previous_digest_items(str(data_dir), reference_date)
    errors = []
    if len(items) > payload['target_count']:
        errors.append('More items than target')
    counts = {}
    for i, item in enumerate(items):
        label = item.get('title', str(i))
        if not verified_news(item):
            errors.append('Unverified publication date: ' + label)
        try:
            age = (reference_date - datetime.strptime(item['date'], '%Y-%m-%d').date()).days
            if not 0 <= age < DAILY_DIGEST_MAX_AGE_DAYS:
                errors.append('Publication date out of window: ' + label)
        except (ValueError, KeyError):
            errors.append('Invalid date: ' + label)
        if len(item.get('summary', '').strip()) < 30 or item.get('fulltext_status') == 'unavailable':
            errors.append('Missing article body: ' + label)
        if any(same_news_story(item, previous) for previous in history + items[:i]):
            errors.append('Duplicate in current/30-day digest: ' + label)
        section = assign_daily_section(item)
        if item.get('dashboard_section') != section:
            errors.append('Wrong dashboard section: ' + label)
        counts[section] = counts.get(section, 0) + 1
    if counts != payload.get('selection_health', {}).get('section_counts'):
        errors.append('Section counts do not match digest')
    if errors:
        raise ValueError('\n'.join(errors))
    print(f'Validated {len(items)}/{payload["target_count"]} articles: dates, bodies, 30-day history and section counts OK.')
    return payload


if __name__ == '__main__':
    validate_digest(Path(__file__).resolve().parent.parent / 'data', datetime.now(JST).date())
