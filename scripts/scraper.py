import requests
import json
from bs4 import BeautifulSoup

# Constants
NEWS_SOURCES = [
    'https://www.nikkei.com/',
    'https://www.sanspo.com/',
    'https://www.asahi.com/',
    'https://news.yahoo.co.jp/',
    'https://news.google.com/'
]

COMPETITORS = [
    'ユニ・チャーム',
    '花王',
    'ライオン',
    'P&G',
    '大王製紙',
    '王子ホールディングス',
    '日本製紙'
]

CATEGORIES = {
    '競合メーカー動向': 1,
    'おむつ加工機設備': 2,
    '包装機': 3,
    'パレタイザー': 4,
    'ティシュー業界': 5,
    'ウェットティシュー': 6,
    'トイレット業界': 7,
    '競合他社特許': 8,
    '論文情報': 9
}

# Function to scrape news from various sources

def scrape_news():
    news_data = []
    for source in NEWS_SOURCES:
        response = requests.get(source)
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('article')  # This may need adjustment based on actual structure

        for article in articles:
            title = article.find('h2').text
            date = article.find('time')['datetime'] if article.find('time') else 'Unknown Date'
            url = article.find('a')['href']
            source_name = source

            # Filter articles based on competitor keywords
            if any(competitor in title for competitor in COMPETITORS):
                summary = summarize_article(title)
                category_name, category_id = categorize_article(title)
                confidence = 0.95  # Example confidence level
                news_data.append({
                    'title': title,
                    'summary': summary,
                    'date': date,
                    'source': source_name,
                    'company': ', '.join([c for c in COMPETITORS if c in title]),
                    'category_id': category_id,
                    'category_name': category_name,
                    'info_type': 'news',
                    'url': url,
                    'confidence': confidence
                })
    return news_data

# Function to summarize articles using Groq API

def summarize_article(title):
    # Call Groq API for summarization (pseudo code)
    response = requests.post('https://api.groq.com/summarize', json={'text': title})
    summary = response.json().get('summary', '')
    return summary

# Function to categorize articles

def categorize_article(title):
    for category_name, category_id in CATEGORIES.items():
        if category_name in title:
            return category_name, category_id
    return 'その他', 0

# Main execution
if __name__ == '__main__':
    news = scrape_news()
    with open('scripts/news_data.json', 'w', encoding='utf-8') as f:
        json.dump(news, f, ensure_ascii=False, indent=4)
