import json
import os
import re
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai as google_genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


def strip_html(text):
    """Remove HTML tags from a string."""
    return re.sub(r'<[^>]+>', '', text or '').strip()


def ai_summarize(title, snippet, company, api_key):
    """Generate a Japanese analytical summary using Gemini API."""
    if not GENAI_AVAILABLE or not api_key:
        return None
    try:
        client = google_genai.Client(api_key=api_key)
        prompt = (
            f'あなたは家庭紙・衛生用品業界の上級アナリストです。'
            f'以下のニュースを読み、大王製紙の技術開発部向けに、'
            f'業界動向・競合への影響・大王製紙へのビジネスインパクトの観点から'
            f'日本語で150字以内の洞察コメントを作成してください。'
            f'タイトルや本文をそのまま繰り返すのではなく、'
            f'戦略的な意義や示唆を簡潔に述べてください。\n'
            f'会社名: {company}\n'
            f'タイトル: {title}\n'
            f'内容: {snippet}\n'
            f'洞察コメント（日本語のみ、150字以内）:'
        )
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
        )
        return response.text.strip()[:300]
    except Exception as e:
        print(f'  Gemini error for "{title[:40]}...": {e}')
        return None


def load_data(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return raw, None
        return raw.get('items', []), raw.get('last_updated')
    return [], None


def save_data(path, items, last_updated=None):
    payload = {
        'last_updated': last_updated or datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'items': items,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'news_data.json')
    data_path = os.path.normpath(data_path)

    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        print('WARNING: GEMINI_API_KEY not set. Summaries will not be updated.')

    data, last_updated = load_data(data_path)
    if not data:
        print('No data found. Run fetch_news.py first.')
        return

    updated = 0
    for item in data:
        summary = strip_html(item.get('summary', ''))
        # Strip HTML from existing summary if it contains tags
        if item.get('summary', '') != summary:
            item['summary'] = summary

        # Skip if already has a quality AI-generated summary (plain text, >=80 chars)
        if len(summary) >= 80 and '<' not in summary:
            continue

        title = item.get('title', '')
        company = item.get('company', '不明')
        snippet = summary or title

        new_summary = ai_summarize(title, snippet, company, api_key)
        if new_summary:
            item['summary'] = new_summary
            updated += 1
        elif not summary:
            item['summary'] = title[:200]

    # Sort newest first
    data.sort(key=lambda x: x.get('date', ''), reverse=True)

    save_data(data_path, data)
    print(f'Updated {updated} summaries. Total items: {len(data)}')


if __name__ == '__main__':
    main()
