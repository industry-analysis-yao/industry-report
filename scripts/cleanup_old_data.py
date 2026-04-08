import json
import os
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CUTOFF_DAYS = 90


def main():
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'news_data.json')
    data_path = os.path.normpath(data_path)

    if not os.path.exists(data_path):
        print(f'File not found: {data_path}')
        return

    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS)
    cutoff_str = cutoff.strftime('%Y-%m-%d')

    before = len(data)
    data = [item for item in data if item.get('date', '9999-99-99') >= cutoff_str]
    removed = before - len(data)

    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'Removed {removed} items older than {CUTOFF_DAYS} days (before {cutoff_str}).')
    print(f'Remaining: {len(data)} items.')


if __name__ == '__main__':
    main()
