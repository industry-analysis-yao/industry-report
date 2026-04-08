import json
import os
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


def ai_summarize(title, snippet, company, api_key):
    """Generate a Japanese summary using Gemini API."""
    if not GENAI_AVAILABLE or not api_key:
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f'以下のニュースについて、業界アナリストとして日本語で150字以内の要約を作成してください。\n'
            f'会社名: {company}\n'
            f'タイトル: {title}\n'
            f'内容: {snippet}\n'
            f'要約（日本語のみ、150字以内）:'
        )
        response = model.generate_content(prompt)
        return response.text.strip()[:300]
    except Exception as e:
        print(f'  Gemini error for "{title[:40]}...": {e}')
        return None


def load_data(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_data(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'news_data.json')
    data_path = os.path.normpath(data_path)

    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        print('WARNING: GEMINI_API_KEY not set. Summaries will not be updated.')

    data = load_data(data_path)
    if not data:
        print('No data found. Run fetch_news.py first.')
        return

    updated = 0
    for item in data:
        summary = item.get('summary', '')
        if len(summary) >= 80:
            continue  # Already has a good summary

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
