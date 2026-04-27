import json
import os
import re
import time
import requests
import pytz
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Maximum retry attempts for high-value items that fail the formatting check
MAX_RETRIES = 3
RETRY_SCORE_THRESHOLD = 80

# OpenRouter configuration
_OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1/chat/completions'
_OPENROUTER_MODEL = 'deepseek/deepseek-chat'
_OPENROUTER_MAX_RETRIES = 5

_LENIENT_THRESHOLD_DEFAULT = 15

# ============================================================
# 新增：过滤过期专利（日期严格限制30天内）
# ============================================================
def filter_old_patents_from_items(items, max_age_days=30):
    """过滤 items 列表中的专利/学术条目，只保留 max_age_days 天内的"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    filtered = []
    for item in items:
        # 只对专利或学术条目进行日期检查
        is_patent_or_academic = (item.get('category_id') == '⑦' or 
                                  item.get('info_type') == '特許' or 
                                  item.get('is_academic') or
                                  item.get('permanent_record'))
        if not is_patent_or_academic:
            filtered.append(item)
            continue
        # 检查日期字段
        date_str = item.get('date')
        if not date_str:
            # 没有日期，保守保留
            filtered.append(item)
            continue
        try:
            item_date = datetime.strptime(date_str, '%Y-%m-%d')
            if item_date >= cutoff:
                filtered.append(item)
            else:
                print(f'  [PATENT-FILTER] Removed old patent/academic: {item.get("title", "")[:60]} ({date_str})')
        except Exception:
            # 日期解析失败，保留
            filtered.append(item)
    return filtered

# ============================================================
# AGENT A — Summarizer
# ============================================================
def strip_html(text):
    return re.sub(r'<[^>]+>', '', text or '').strip()

def _openrouter_generate(prompt):
    api_key = os.environ.get('OPENROUTER_API_KEY', '')
    if not api_key:
        raise RuntimeError('OPENROUTER_API_KEY not set')
    headers = {
        'Authorization': f'Bearer {api_key}',
        'HTTP-Referer': 'https://github.com/industry-analysis-yao/industry-report',
        'X-Title': 'Industry Analysis Report',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': _OPENROUTER_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
    }
    last_error = None
    for attempt in range(_OPENROUTER_MAX_RETRIES):
        try:
            resp = requests.post(_OPENROUTER_BASE_URL, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f'  [OPENROUTER] Attempt {attempt + 1}/{_OPENROUTER_MAX_RETRIES} failed: {e}')
            last_error = e
            if attempt < _OPENROUTER_MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    raise last_error if last_error else RuntimeError('OpenRouter failed after all retries')

def ai_summarize(title, snippet, company, api_key=None, retry_feedback=None, lenient_mode=False):
    clean_snippet = (snippet or '').strip()
    COMPETITOR_COMPANIES = [
        'ユニ・チャーム', 'unicharm', '花王', 'p&g', 'ライオン',
        'essity', 'kimberly', 'キンバリー', 'vinda', '维达', 'hengan', '恒安',
    ]
    is_competitor = any(kw in (company or '').lower() for kw in COMPETITOR_COMPANIES)
    min_snippet_len = 10 if (is_competitor or lenient_mode) else 30
    if len(clean_snippet) < min_snippet_len or clean_snippet == title.strip():
        print(f'  [SKIP paywall/no-body] {title[:60]}')
        return False, None
    try:
        retry_section = ''
        if retry_feedback:
            retry_section = (
                f'\n\n【前回審査からのフィードバック（必ず反映してください）】\n'
                f'{retry_feedback}\n'
                f'上記の指摘をすべて改善した新しい要約を作成してください。\n'
            )
        lenient_section = ''
        if lenient_mode:
            lenient_section = (
                '\n【重要：本日の新規ニュース数が少ないため、関連性判定を通常より緩やかに行ってください】\n'
                '・競合他社（ユニ・チャーム・花王・P&G・ライオン・Essity・Kimberly-Clark等）のニュースは、'
                'スニペットが短くても・情報量が少なくても「IRRELEVANT」にしないでください。\n'
                '・業界関連企業の動向であれば、間接的な情報も保持してください。\n'
            )
        prompt_parts = [
            'あなたは家庭紙・衛生用品業界の専門記者です。\n\n',
            '【ステップ1: 関連性チェック】\n',
            'この記事が「家庭紙・ティッシュ・トイレットペーパー・おむつ・ナプキン・衛生用品・不織布・',
            '吸収体加工機・包装機・パレタイザー・学術論文・特許」に直接関連する業界ニュースかどうかを判断してください。\n',
            '洗剤・柔軟剤・シャンプー・化粧品・食品・飲料など、家庭紙／衛生用品と無関係な',
            'FMCGニュースであれば「IRRELEVANT」とだけ出力してください。\n',
            '※ ユニ・チャーム・花王・P&G・ライオン・Essity・Kimberly-Clark等の競合他社のニュースは',
            'スニペットが短くても「IRRELEVANT」にしないでください。競合情報として必ず保持してください。\n',
            lenient_section,
            '\n【ステップ2: 要約（関連する場合のみ）】\n',
            '業界関連ニュースの場合は、本文スニペットを深く読み込み、',
            '「誰が・いつ・何を・どのように・数値」が明確に伝わる、',
            '業界関係者向けの日本語ニュースサマリーを80〜150字で作成してください。\n',
            'スニペットが短い場合は、入手可能な情報を最大限活用して要約を作成してください。\n\n',
            '【厳禁事項】\n',
            '・タイトルに含まれる単語・フレーズを要約中で使用することは絶対禁止です。\n',
            '・本文スニペットから、タイトルに記載されていない具体的な数値・技術仕様・戦略的事実を',
            '必ず1つ以上抽出して要約に含めてください。\n',
            '・タイトルの言い換えや単純な要約は不可です。本文から独自の情報を付加してください。\n',
            retry_section,
            '\n【出力例】\n',
            '「ユニ・チャームは2026年4月1〜3日に普通株式584,800株を取得価額約5.5億円で取得し、',
            '2月12日決議の自己株式取得を完了した。」\n\n',
            f'会社名: {company}\n',
            f'タイトル: {title}\n',
            f'本文スニペット: {clean_snippet}\n\n',
            '出力（「IRRELEVANT」またはサマリー日本語のみ）:',
        ]
        prompt = ''.join(prompt_parts)
        text = _openrouter_generate(prompt)
        if text and text.strip().upper() == 'IRRELEVANT':
            print(f'  [AI-IRRELEVANT] {title[:60]}')
            return False, None
        return True, (text or '')[:300]
    except Exception as e:
        print(f'  OpenRouter error for "{title[:40]}...": {e}')
        return True, 'AI Summary Pending'

# ============================================================
# AGENT B — Auditor
# ============================================================
def audit_item(title, summary, company, api_key=None):
    try:
        prompt = (
            'あなたは大王製紙の最上席研究開発ディレクターです。業界歴30年以上、競合他社の技術動向・'
            '市場変化・設備投資・研究開発に精通した、業界随一の厳格な審査官として行動してください。\n\n'
            '以下のニュース要約を容赦なく評価し、JSON形式のみで回答してください。\n\n'
            '【評価基準（合計100点、同点禁止・必ず整数）】\n'
            '1. 大王製紙R&D戦略への直接的インパクト（最重要・40点）\n'
            '2. 市場・業界構造への影響度（25点）\n'
            '3. 情報の具体性・信頼性（20点）\n'
            '4. 緊急性・時宜性（15点）\n\n'
            '【フォーマット失格チェック】\n'
            '【出力形式（JSON以外は一切出力禁止）】\n'
            '{\n'
            '  "score": <1〜100の整数>,\n'
            '  "impact_analysis": "<戦略的含意（60〜120字）>",\n'
            '  "formatting_feedback": <null または "改善指示">\n'
            '}\n\n'
            f'会社名: {company}\n'
            f'タイトル: {title}\n'
            f'要約: {summary}\n'
        )
        text = _openrouter_generate(prompt)
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        result = json.loads(text)
        score = int(result.get('score', 0))
        score = max(1, min(100, score))
        impact_analysis = (result.get('impact_analysis') or '')[:300]
        formatting_feedback = result.get('formatting_feedback') or None
        return score, impact_analysis, formatting_feedback
    except Exception as e:
        print(f'  Audit error for "{title[:40]}...": {e}')
        return 0, '', None

# ============================================================
# DUAL-AGENT PIPELINE WITH RETRY
# ============================================================
def process_item_with_retry(item, api_key=None, lenient_mode=False):
    title = item.get('title', '')
    snippet = strip_html(item.get('summary', ''))
    company = item.get('company', '不明')
    best_score = item.get('score') or 0
    best_summary = snippet
    best_impact = item.get('impact_analysis') or ''
    feedback = None
    for attempt in range(MAX_RETRIES):
        is_relevant, new_summary = ai_summarize(
            title, snippet, company, retry_feedback=feedback, lenient_mode=lenient_mode
        )
        if not is_relevant:
            return False
        current_summary = new_summary or best_summary
        if not current_summary:
            break
        score, impact_analysis, fmt_feedback = audit_item(title, current_summary, company)
        is_better = score > best_score or (score == best_score and fmt_feedback is None and best_impact == '')
        if is_better:
            best_score = score
            best_summary = current_summary
            best_impact = impact_analysis
        summary_too_short = len(current_summary) < 80
        needs_retry = (summary_too_short or (score > RETRY_SCORE_THRESHOLD)) and fmt_feedback
        if needs_retry and attempt < MAX_RETRIES - 1:
            reason = 'short summary' if summary_too_short else f'score={score}'
            print(f'  [RETRY {attempt + 1}/{MAX_RETRIES - 1}] {reason}, feedback: {fmt_feedback[:80]}')
            feedback = fmt_feedback
        else:
            break
    item['summary'] = best_summary or '分析待ち'
    item['score'] = best_score
    item['impact_analysis'] = best_impact
    return True

# ============================================================
# TOP-3 HIGHLIGHTS
# ============================================================
def generate_highlights(items, api_key=None, excluded_urls=None, today_str=None):
    excluded = excluded_urls or set()
    def _sorted_scored(pool):
        scored = [it for it in pool if it.get('score', 0) > 0]
        scored.sort(key=lambda x: (x.get('score', 0), x.get('date', '')), reverse=True)
        return scored
    ref_date_str = today_str
    if not ref_date_str:
        jst = pytz.timezone('Asia/Tokyo')
        ref_date_str = datetime.now(jst).strftime('%Y-%m-%d')
    try:
        ref_date = datetime.strptime(ref_date_str, '%Y-%m-%d').date()
    except ValueError:
        ref_date = None
    def _within_days(item, n):
        if ref_date is None:
            return True
        item_date_str = item.get('date', '')
        try:
            item_date = datetime.strptime(item_date_str[:10], '%Y-%m-%d').date()
            return (ref_date - item_date).days <= n
        except (ValueError, TypeError):
            return False
    for window_days in (1, 7, None):
        if window_days is None:
            daily_pool = items
        else:
            daily_pool = [it for it in items if _within_days(it, window_days)]
        scored = _sorted_scored(daily_pool)
        if len(scored) >= 3:
            break
    if not scored:
        scored = _sorted_scored(items)
    candidates = [it for it in scored if it.get('url', '') not in excluded]
    if len(candidates) < 3:
        candidates = scored
    top3 = (candidates if candidates else items)[:3]
    highlights = []
    for i, item in enumerate(top3):
        highlights.append({
            'rank': i + 1,
            'title': item.get('title', ''),
            'url': item.get('url', ''),
            'company': item.get('company', '不明'),
            'category': (item.get('category_name') or '') + ' / ' + (item.get('info_type') or ''),
            'date': item.get('date', ''),
            'impact': item.get('impact_analysis') or item.get('summary') or '',
            'score': item.get('score', 0),
            'is_patent': (item.get('permanent_record', False) or item.get('info_type') == '特許' or item.get('is_academic', False)),
        })
    return highlights

def load_data(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return raw, None, []
        if 'dates' in raw:
            items = []
            for date_items in raw.get('dates', {}).values():
                items.extend(date_items)
            items.extend(raw.get('patents', []))
            return items, raw.get('last_updated'), raw.get('highlights', [])
        return raw.get('items', []), raw.get('last_updated'), raw.get('highlights', [])
    return [], None, []

def save_data(path, items, highlights=None, last_updated=None):
    patents = [i for i in items if i.get('permanent_record')]
    regular = [i for i in items if not i.get('permanent_record')]
    dates = {}
    for item in regular:
        d = item.get('date', 'unknown')
        dates.setdefault(d, []).append(item)
    payload = {
        'last_updated': last_updated or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'highlights': highlights or [],
        'dates': dates,
        'patents': patents,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def main():
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'news_data.json')
    data_path = os.path.normpath(data_path)
    jst = pytz.timezone('Asia/Tokyo')
    today = datetime.now(jst).strftime('%Y-%m-%d')
    today_dt = datetime.now(jst).date()
    data_dir = os.path.dirname(data_path)
    today_file = os.path.join(data_dir, f'{today}.json')

    # 新增：加载数据前先过滤掉过期的专利/学术内容（严格30天）
    data, last_updated, existing_highlights = load_data(data_path)
    print(f"Before patent filter: {len(data)} items.")
    data = filter_old_patents_from_items(data, max_age_days=30)
    print(f"After patent filter: {len(data)} items.")

    # 快照锁定检查（仅当日文件存在且已完全评分时才跳过）
    if os.path.exists(today_file):
        try:
            with open(today_file, 'r', encoding='utf-8') as f:
                locked_data = json.load(f)
            locked_items = locked_data.get('items', [])
            locked_highlights = locked_data.get('highlights', [])
            all_scored = bool(locked_items) and all(
                (it.get('score') or 0) > 0 and it.get('impact_analysis')
                for it in locked_items
            )
            if all_scored and locked_highlights:
                print(f'[SNAPSHOT-LOCKED] {today_file} is already fully scored ({len(locked_items)} items, {len(locked_highlights)} highlights). Skipping AI analysis.')
                return
        except Exception as e:
            print(f'  [WARN] Could not read today_file for lock check: {e}')

    if not os.environ.get('OPENROUTER_API_KEY', ''):
        print('WARNING: OPENROUTER_API_KEY not set. Summaries and scores will not be generated.')

    # 去重
    url_map = {}
    no_url_items = []
    for item in data:
        url = item.get('url') or ''
        if not url:
            no_url_items.append(item)
        elif url not in url_map or (item.get('score') or 0) > (url_map[url].get('score') or 0):
            url_map[url] = item
    data = list(url_map.values()) + no_url_items

    today_items = [it for it in data if it.get('date') == today]
    unscored_today = [
        it for it in today_items
        if not ((it.get('score') or 0) > 0 and it.get('impact_analysis'))
        and strip_html(it.get('summary', '')) != 'AI Summary Pending'
    ]
    lenient_mode = len(unscored_today) < _LENIENT_THRESHOLD_DEFAULT
    if lenient_mode and unscored_today:
        print(f'[LENIENT-MODE] Only {len(unscored_today)} new items to score — lowering AI relevance threshold.')

    updated = 0
    irrelevant_items = []
    for item in today_items:
        summary = strip_html(item.get('summary', ''))
        if item.get('summary', '') != summary:
            item['summary'] = summary
        has_quality_summary = len(summary) >= 80 and '<' not in summary
        has_score = (item.get('score') is not None) and (item.get('score', 0) > 0)
        has_impact = bool(item.get('impact_analysis'))
        if has_quality_summary and has_score and has_impact:
            continue
        if summary == 'AI Summary Pending':
            continue
        if not os.environ.get('OPENROUTER_API_KEY', ''):
            if not has_score:
                item['score'] = 0
            if not has_impact:
                item['impact_analysis'] = ''
            continue
        is_relevant = process_item_with_retry(item, lenient_mode=lenient_mode)
        if not is_relevant:
            irrelevant_items.append(item)
        else:
            updated += 1

    if irrelevant_items:
        irrelevant_ids = {id(it) for it in irrelevant_items}
        for item in irrelevant_items:
            print(f'  Removing irrelevant item: {item.get("title", "")[:60]}')
        data = [it for it in data if id(it) not in irrelevant_ids]
        today_items = [it for it in today_items if id(it) not in irrelevant_ids]
        print(f'Removed {len(irrelevant_items)} irrelevant/paywall items.')

    for item in today_items:
        if item.get('score') is None:
            item['score'] = 0
        if not item.get('impact_analysis'):
            item['impact_analysis'] = ''

    for item in today_items:
        if item.get('info_type') == '特許' and not item.get('permanent_record'):
            item['permanent_record'] = True
            item['category'] = 'patent'
            print(f'  [PATENT-SAVED] {item.get("title", "")[:60]}')

    today_items.sort(key=lambda x: x.get('score', 0), reverse=True)

    recent_top3_urls = set()
    for days_back in range(1, 4):
        past_date = (today_dt - timedelta(days=days_back)).strftime('%Y-%m-%d')
        past_file = os.path.join(data_dir, f'{past_date}.json')
        if os.path.exists(past_file):
            try:
                with open(past_file, 'r', encoding='utf-8') as f:
                    past_data = json.load(f)
                for h in past_data.get('highlights', []):
                    url = h.get('url', '')
                    if url:
                        recent_top3_urls.add(url)
            except Exception:
                pass
    if recent_top3_urls:
        print(f'  [TOP3-EXCL] Excluding {len(recent_top3_urls)} URL(s) featured in the last 3 days.')

    highlights = generate_highlights(today_items, excluded_urls=recent_top3_urls, today_str=today) if today_items else existing_highlights
    if not highlights:
        highlights = existing_highlights

    save_data(data_path, data, highlights=highlights)
    print(f'Updated {updated} items today. Highlights: {len(highlights)}. Total items in library: {len(data)}')

    date_payload = {
        'date': today,
        'items': today_items,
        'highlights': highlights,
    }
    with open(today_file, 'w', encoding='utf-8') as f:
        json.dump(date_payload, f, ensure_ascii=False, indent=2)
    print(f'  [DATE-FILE] Wrote {today_file} ({len(today_items)} items)')

    index_path = os.path.join(data_dir, 'dates_index.json')
    existing_index = []
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                existing_index = json.load(f)
        except Exception:
            existing_index = []
    unique_dates = set(existing_index)
    for item in data:
        if not item.get('permanent_record'):
            d = item.get('date', '')
            if d and d != 'unknown':
                unique_dates.add(d)
    merged_dates = sorted(unique_dates, reverse=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(merged_dates, f, ensure_ascii=False, indent=2)
    print(f'  [INDEX] dates_index.json updated: {merged_dates}')

    def is_bucket_c(item):
        return item.get('category_id') == '⑦' or bool(item.get('is_academic'))
    vault_path = os.path.join(data_dir, 'permanent_vault.json')
    existing_vault = []
    if os.path.exists(vault_path):
        try:
            with open(vault_path, 'r', encoding='utf-8') as f:
                existing_vault = json.load(f)
        except Exception:
            existing_vault = []
    vault_urls = {item.get('url') for item in existing_vault if item.get('url')}
    new_vault_items = [
        item for item in today_items
        if is_bucket_c(item) and item.get('url') and item.get('url') not in vault_urls
    ]
    if new_vault_items:
        updated_vault = existing_vault + new_vault_items
        with open(vault_path, 'w', encoding='utf-8') as f:
            json.dump(updated_vault, f, ensure_ascii=False, indent=2)
        print(f'  [VAULT] Added {len(new_vault_items)} items to permanent_vault.json (total: {len(updated_vault)})')
    else:
        print(f'  [VAULT] No new Bucket C items (existing vault: {len(existing_vault)})')

if __name__ == '__main__':
    main()
