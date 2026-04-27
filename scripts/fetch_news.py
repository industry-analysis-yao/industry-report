#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复版本 - FETCHNEWS.PY
包含所有修复：设备查询、分类逻辑、日期检查
"""

import re
import requests
from datetime import datetime, timedelta, timezone
import json
import os
import time

try:
    import pytz
    _PYTZ_AVAILABLE = True
except ImportError:
    _PYTZ_AVAILABLE = False

try:
    import feedparser
    _feedparser_available = True
except ImportError:
    _feedparser_available = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================
# 配置常量
# ============================================================
MAX_AGE_DAYS = 50               # 普通新闻放宽到50天
PATENT_MAX_AGE_DAYS = 30        # 专利严格限制30天

_SCRIPT_DIR = os.path.dirname(__file__)

# ============================================================
# 增强的搜索查询
# ============================================================
SEARCH_QUERIES_GENERAL = [
    'ユニ・チャーム 決算', 'ユニ・チャーム 投資', 'ユニ・チャーム 新製品',
    'ユニ・チャーム ティシュー', 'ユニ・チャーム おむつ', 'ユニ・チャーム 衛生用品', 'ユニ・チャーム ナプキン',
    '花王 決算', '花王 投資', '花王 研究開発', '花王 ティシュー', '花王 おむつ', '花王 衛生用品', '花王 家庭紙',
    'P&G Japan おむつ', 'P&G Japan ナプキン', 'P&G Japan ティシュー', 'P&G Japan 衛生用品',
    'ライオン トイレット', 'ライオン 衛生用品', 'ライオン 新製品', 'ライオン 投資',
    '大王製紙 家庭紙', '王子ホールディングス トイレット', '日本製紙 家庭紙', '丸富製紙 ティシュー', 'カミ商事 ティシュー',
    'Essity 衛生用品', 'Kimberly-Clark おむつ',
    '家庭紙 トイレットペーパー 規制', '家庭紙 値上げ', '家庭紙 価格',
    'おむつ 技術 素材', 'おむつ 新製品 発売',
    'ナプキン 生理用品 技術', 'ナプキン 新製品', '生理用品 環境 サステナ',
    'ウェットティッシュ 市場', 'ウェットティッシュ 新製品',
    '不織布 製造 材料', '不織布 技術 素材',
    'パルプ 製造 技術', 'パルプ 価格 相場',
    'Vinda ティシュー', 'Vinda おむつ',
    'Hengan おむつ', 'Hengan ナプキン',
    '中顺洁柔 家庭紙', '中顺洁柔 衛生用品',
]

# 增强的设备查询
SEARCH_QUERIES_MACHINE = [
    '瑞光 Zuiko 加工機',
    'GDM Fameccanica 吸収体',
    'OPTIMA 包装機',
    'ファナック FANUC パレタイザー',
    '加工機 不織布 製造',
    '加工機 吸収体 製造',
    '包装機 自動化 衛生用品',
    'パレタイザー 自動化 包装',
    'パレタイザー 衛生用品',
    '衛生用品 製造 設備',
    '衛生用品 製造 自動化',
    '不織布 製造 機械',
    'おむつ 製造 機械',
    'おむつ 製造 設備',
    'ナプキン 加工 機械',
    'ナプキン 製造 技術',
    '充填機 衛生用品',
    '全自動包装機 衛生',
    '産業用ロボット パレタイザー',
    '包装ライン 衛生用品',
    '国際不織布会議 2026',
    'テックスフォーラム 衛生用品',
    'テックスアシア 2026',
]

SEARCH_QUERIES = SEARCH_QUERIES_GENERAL + SEARCH_QUERIES_MACHINE

ACADEMIC_QUERIES = [
    'site:jstage.jst.go.jp 王子ホールディングス 特許',
    'site:jstage.jst.go.jp 日本製紙 特許',
    'site:jstage.jst.go.jp ユニ・チャーム 特許',
    'site:jstage.jst.go.jp 花王 特許',
    'site:patents.google.com 王子ホールディングス 特許',
    'site:patents.google.com 日本製紙 特許',
    'site:patents.google.com ユニ・チャーム 特許',
    'site:patents.google.com 花王 特許',
]

# ============================================================
# 修复的分类映射
# ============================================================
CATEGORY_KEYWORDS = {
    '③': [
        '加工機', '包装機', 'パレタイザー', '設備', 'マシン', 
        'GDM', 'Fameccanica', '瑞光', 'Zuiko', 'ファナック', 'FANUC', 'OPTIMA',
        '自動化', 'automation', 'packaging machinery', 'machinery', '機械',
        '充填機', '産業用ロボット', 'robot',
    ],
    '⑥': [
        'ティシュー', 'ティッシュ', 'トイレット', 'トイレットペーパー',
        '家庭紙', '衛生用紙', 'ペーパータオル', 'キッチンペーパー', 
        'ティシューペーパー', 'toilet paper', 'tissue'
    ],
    '①': [
        'ユニ・チャーム', '花王', 'P&G', 'ライオン', 'キンバリー', 'Kimberly', 'Essity',
        'おむつ', 'オムツ', 'ナプキン', '生理用', '生理用品', 
        '衛生用品', '衛生ナプキン', '失禁', 'sanitary napkin', 'diaper',
        'Vinda', '维达', 'Hengan', '恒安', '中顺洁柔'
    ],
    '②': ['製紙', 'パルプ', '王子', '日本製紙', '大王製紙', '紙製品'],
    '⑤': ['ウェット', 'wet tissue', 'Winner Medical', '稳健', 'wet wipe'],
    '⑦': ['jstage', 'patents.google', 'scholar.google', '特許', '論文', '学会', 'patent', 'thesis'],
}

CATEGORY_NAMES = {
    '①': '日用品・衛生用品メーカー',
    '②': '製紙・パルプメーカー',
    '③': '不織布・吸収体加工機メーカー',
    '④': '包装機・パレタイジング設備メーカー',
    '⑤': 'ウェットティッシュ製造メーカー',
    '⑥': 'ティッシュペーパー・家庭紙専業メーカー',
    '⑦': '学術論文・特許情報',
}

KNOWN_COMPANIES = [
    'ユニ・チャーム', '花王', 'P&G Japan', 'P&G', 'ライオン', 'キンバリー・クラーク',
    'Kimberly-Clark', '大王製紙', '王子ホールディングス', '日本製紙', 'Essity',
    '株式会社瑞光（Zuiko）', '瑞光', 'GDM', 'Fameccanica', 'OPTIMA Packaging', 'ファナック',
    'Winner Medical（稳健医疗）', '丸富製紙', 'カミ商事', 'Vinda（维达）', 'Hengan（恒安）', '中顺洁柔', 'C&S Paper',
]

TISSUE_CORE_TERMS = [
    '家庭紙', 'ティシュー', 'ティッシュ', 'トイレット', 'ちり紙', 'キッチンペーパー',
    'おむつ', 'オムツ', 'ナプキン', '生理用', '失禁', '衛生用品', '衛生用紙',
    'ウェットティシュ', 'ウェットティッシュ', '不織布', '吸収体', 'パルプ',
    '抽紙', '衛生紙', '加工機', '包装機', 'パレタイザー',
]

TISSUE_INDUSTRY_COMPANIES = [
    'ユニ・チャーム', 'unicharm', '大王製紙', '王子製紙', '王子ホールディングス', '日本製紙', '丸富製紙',
    '瑞光', 'zuiko', 'gdm', 'fameccanica', 'winner medical', '稳健', 'essity', 'kimberly-clark',
    'キンバリー', 'カミ商事', 'vinda', '维达', 'hengan', '恒安', '中顺洁柔', 'c&s paper',
]

OFFTOPIC_TERMS = [
    '洗剤', '柔軟剤', '洗濯洗剤', 'アリエール', 'レノア', 'ボールド', 'ジョイ',
    'ファブリーズ', '漂白剤', '洗濯槽', 'シャンプー', 'リンス', 'コンディショナー', 'ボディソープ',
    '化粧品', 'リップ', 'ファンデーション', '美容液', 'スキンケア', '口紅',
    '食品', '飲料', 'コーヒー', 'ビール', '菓子', 'サプリ',
]

# ============================================================
# 辅助函数
# ============================================================
def _today_jst():
    if _PYTZ_AVAILABLE:
        return datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d')
    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime('%Y-%m-%d')

def is_industry_relevant(title, snippet):
    text = (title + ' ' + snippet).lower()
    has_core = any(term.lower() in text for term in TISSUE_CORE_TERMS)
    has_company = any(name.lower() in text for name in TISSUE_INDUSTRY_COMPANIES)
    has_offtopic = any(term.lower() in text for term in OFFTOPIC_TERMS)
    if has_offtopic and not has_core:
        return False
    return has_core or has_company

def map_category(text):
    """修复的分类逻辑：确保正确优先级"""
    text_lower = text.lower()
    
    # 优先级 1：设备类（③）
    for kw in CATEGORY_KEYWORDS.get('③', []):
        if kw.lower() in text_lower:
            return '③', CATEGORY_NAMES['③']
    
    # 优先级 2：ウェット（⑤）
    for kw in CATEGORY_KEYWORDS.get('⑤', []):
        if kw.lower() in text_lower:
            return '⑤', CATEGORY_NAMES['⑤']
    
    # 优先级 3：製紙（②）
    for kw in CATEGORY_KEYWORDS.get('②', []):
        if kw.lower() in text_lower:
            return '②', CATEGORY_NAMES['②']
    
    # 优先级 4：學術（⑦）
    for kw in CATEGORY_KEYWORDS.get('⑦', []):
        if kw.lower() in text_lower:
            return '⑦', CATEGORY_NAMES['⑦']
    
    # 优先级 5：トイレット（⑥），但排除おむつ/ナプキン
    has_toilet_paper = any(kw.lower() in text_lower for kw in CATEGORY_KEYWORDS.get('⑥', []))
    has_diaper_or_napkin = any(kw.lower() in text_lower for kw in ['おむつ', 'オムツ', 'ナプキン', '生理用品', 'diaper', 'napkin'])
    
    if has_toilet_paper and not has_diaper_or_napkin:
        return '⑥', CATEGORY_NAMES['⑥']
    
    # 优先级 6：衛生用品（①）
    for kw in CATEGORY_KEYWORDS.get('①', []):
        if kw.lower() in text_lower:
            return '①', CATEGORY_NAMES['①']
    
    return '①', CATEGORY_NAMES['①']

def extract_company(text):
    for company in KNOWN_COMPANIES:
        if company.lower() in text.lower():
            return company
    return '不明'

def determine_info_type(text):
    if any(k in text for k in ['投資', '買収', '出資', 'M&A', '資金', 'acquisition', '決算', '株価']):
        return '投資'
    if any(k in text for k in ['特許', 'patent', '知的']):
        return '特許'
    if any(k in text for k in ['研究', '論文', '学会', '技術開発', 'research', 'development', 'NEDO']):
        return '研究開発'
    if any(k in text for k in ['加工機', 'マシン', '設備', 'machine']):
        return '加工機技術'
    if any(k in text for k in ['包装機', 'パッケージ', '充填', 'packaging']):
        return '包装機技術'
    if any(k in text for k in ['新製品', '新商品', '新発売', 'new product', 'launch', 'リニューアル']):
        return '新製品'
    if any(k in text for k in ['環境', 'エコ', 'サステナ', 'sustainability', 'eco', 'carbon', 'CDP']):
        return '環境'
    if any(k in text for k in ['規制', 'law', '法律', 'regulation', '値上げ', '施行']):
        return '規制'
    return '其他'

def strip_html(text):
    return re.sub(r'<[^>]+>', '', text or '').strip()

# ============================================================
# RSS 抓取
# ============================================================
def fetch_from_google_news_rss(query, max_items=100, max_age_days=MAX_AGE_DAYS):
    if not _feedparser_available:
        return []
    feed_url = 'https://news.google.com/rss/search?q={}&hl=ja&gl=JP&ceid=JP:ja'.format(
        requests.utils.quote(query)
    )
    try:
        feed = feedparser.parse(feed_url)
        items = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        for entry in feed.entries[:max_items]:
            published = entry.get('published_parsed')
            if published:
                pub_date = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
                if pub_date < cutoff:
                    continue
            title = entry.get('title', '')
            link = entry.get('link', '')
            summary = entry.get('summary', '')
            source_info = entry.get('source')
            source = source_info.get('title', '') if isinstance(source_info, dict) else ''
            items.append({
                'title': title,
                'link': link,
                'snippet': summary,
                'displayLink': source,
            })
        print(f'  [Google-RSS] {len(items)} fresh (≤{max_age_days}d) for: {query[:60]}')
        return items
    except Exception as e:
        print(f'  [RSS] Error: {e}')
        return []

# ============================================================
# 爬虫函数
# ============================================================
def fetch_news(existing_urls=None):
    if not _feedparser_available:
        return []
    
    _existing = existing_urls or set()
    all_articles = []
    
    for query in SEARCH_QUERIES:
        items = fetch_from_google_news_rss(query)
        for item in items:
            url = item.get('link', '')
            if url and url not in _existing:
                title = item.get('title', '')
                snippet = item.get('snippet', '')
                if is_industry_relevant(title, snippet):
                    company = extract_company(title + ' ' + snippet)
                    category_id, category_name = map_category(title + ' ' + snippet)
                    info_type = determine_info_type(title + ' ' + snippet)
                    all_articles.append({
                        'title': title,
                        'summary': snippet,
                        'company': company,
                        'date': _today_jst(),
                        'category_id': category_id,
                        'category_name': category_name,
                        'info_type': info_type,
                        'url': url,
                        'source_name': item.get('displayLink', ''),
                        'confidence': '高' if company != '不明' else '中',
                    })
    
    return all_articles

def fetch_academic_news(existing_urls=None, max_age_days=PATENT_MAX_AGE_DAYS):
    """只保留30天内的专利/学术条目"""
    if not _feedparser_available:
        return []
    
    _existing = existing_urls or set()
    results = []
    today = _today_jst()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    
    print(f'\n[ACADEMIC FETCH] Strict patent filter: only {max_age_days} days')
    
    for source_name, feed_url in [
        ('J-STAGE', 'https://www.jstage.jst.go.jp/browse/-char/ja'),
        ('Google Patents', 'https://patents.google.com/?q=tissue OR diaper OR napkin'),
    ]:
        try:
            feed = feedparser.parse(feed_url)
            added = 0
            skipped_age = 0
            
            for entry in feed.entries[:100]:
                published = entry.get('published_parsed')
                pub_date_str = None
                
                if published:
                    try:
                        pub_date = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
                        pub_date_str = pub_date.strftime('%Y-%m-%d')
                        
                        if pub_date < cutoff:
                            skipped_age += 1
                            continue
                    except:
                        pass
                
                title = entry.get('title', '')
                link = entry.get('link', '')
                snippet = entry.get('summary', '')
                
                if not title or not link or link in _existing:
                    continue
                if not is_industry_relevant(title, snippet):
                    continue
                
                company = extract_company(title + ' ' + snippet)
                info_type = determine_info_type(title + ' ' + snippet)
                
                results.append({
                    'title': title,
                    'summary': snippet,
                    'company': company,
                    'date': pub_date_str or today,
                    'category_id': '⑦',
                    'category_name': CATEGORY_NAMES['⑦'],
                    'info_type': info_type or '特許',
                    'url': link,
                    'source_name': source_name,
                    'confidence': '高' if company != '不明' else '中',
                    'is_academic': True,
                    'permanent_record': True,
                })
                added += 1
            
            print(f'  [{source_name}] Added: {added}, Skipped (too old): {skipped_age}')
        
        except Exception as e:
            print(f'  [ERROR] Fetching {source_name}: {e}')
    
    return results

def clean_old_patents_from_existing(items, max_age_days=30):
    """清理旧专利"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    cutoff_str = cutoff.strftime('%Y-%m-%d')
    
    kept = []
    removed = 0
    
    for item in items:
        if item.get('permanent_record'):
            try:
                item_date_str = item.get('date', '9999-99-99')
                if item_date_str >= cutoff_str:
                    kept.append(item)
                else:
                    removed += 1
                    print(f'  [CLEAN-OLD-PATENT] Removed: {item.get("title", "")[:60]} ({item_date_str})')
            except:
                kept.append(item)
        else:
            kept.append(item)
    
    if removed > 0:
        print(f'[CLEANUP] Removed {removed} old patents from existing data')
    
    return kept

# ============================================================
# 数据持久化
# ============================================================
def load_existing(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return raw, None, [], []
        if 'dates' in raw:
            items = []
            for date_items in raw.get('dates', {}).values():
                items.extend(date_items)
            patents = raw.get('patents', [])
            return items, raw.get('last_updated'), raw.get('highlights', []), patents
        return raw.get('items', []), raw.get('last_updated'), raw.get('highlights', []), []
    return [], None, [], []

def save_data(path, items, highlights=None, patents=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    dates = {}
    for item in items:
        d = item.get('date', 'unknown')
        dates.setdefault(d, []).append(item)
    payload = {
        'last_updated': now,
        'highlights': highlights or [],
        'dates': dates,
        'patents': patents or [],
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

# ============================================================
# 主入口
# ============================================================
if __name__ == '__main__':
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'news_data.json')
    data_path = os.path.normpath(data_path)

    existing, _, highlights, patents = load_existing(data_path)
    existing = clean_old_patents_from_existing(existing, max_age_days=PATENT_MAX_AGE_DAYS)
    
    existing_urls = {item['url'] for item in existing if item.get('url')}
    existing_urls.update(item['url'] for item in patents if item.get('url'))

    print(f'Existing items: {len(existing)} regular, {len(patents)} patents')
    print(f'Fetching news (general max age = {MAX_AGE_DAYS} days, patent max age = {PATENT_MAX_AGE_DAYS} days) ...')

    industry_items = fetch_news(existing_urls=existing_urls)
    academic_items = fetch_academic_news(existing_urls=existing_urls)

    def dedupe_by_title_summary(items):
        seen = set()
        deduped = []
        for it in items:
            key = (it['title'], it['summary'][:120])
            if key not in seen:
                seen.add(key)
                deduped.append(it)
        return deduped

    industry_items = dedupe_by_title_summary(industry_items)
    academic_items = dedupe_by_title_summary(academic_items)

    all_new = []
    seen_urls = set()
    for item in industry_items + academic_items:
        u = item.get('url')
        if not u:
            continue
        if u in existing_urls or u in seen_urls:
            continue
        seen_urls.add(u)
        all_new.append(item)

    appended = 0
    for item in all_new:
        existing.append(item)
        appended += 1
        print(f'  [NEW] {item["title"][:60]}')

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    cutoff_str = cutoff.strftime('%Y-%m-%d')
    kept = []
    for item in existing:
        if item.get('permanent_record'):
            kept.append(item)
        elif item.get('date', '9999-99-99') >= cutoff_str:
            kept.append(item)
        else:
            print(f'  [PRUNED-OLD-NEWS] {item.get("title", "")[:60]} ({item.get("date", "")})')
    pruned = len(existing) - len(kept)
    if pruned:
        print(f'Pruned {pruned} items older than 30 days.')
    existing = kept

    existing.sort(key=lambda x: x.get('date', ''), reverse=True)
    save_data(data_path, existing, highlights=highlights, patents=patents)

    print(f'Appended {appended} new items. Total: {len(existing)} regular + {len(patents)} patents saved to {data_path}')
