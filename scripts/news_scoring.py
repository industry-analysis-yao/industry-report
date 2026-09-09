"""Transparent fallback ranking and verbatim extracts when AI is unavailable."""
import re
from datetime import date
from source_catalog import equipment_section


def apply_fallback(item, *, reference_date=None):
    reference_date = reference_date or date.today()
    title = item.get('title', '').lower()
    core = any(t in title for t in ('おむつ', 'オムツ', 'ソフィ', 'ナプキン', 'マミーポコ', 'ムーニー',
                                    'グーン', 'ティシュ', 'ティッシュ', 'ティシュー', 'ふきん', 'ハンドタオル',
                                    'ウエット', 'ウェット', '生理', '吸収', '不織布', 'diaper', 'tissue',
                                    '纸尿裤', '卫生巾', '生活用纸', '无纺布', '湿巾'))
    technology = bool(equipment_section(title)) or any(t in title for t in ('開発', '技術', '研究', '新素材', '実証', '製造', '設備', '工場',
                                        '火災', '自動化', 'ppe', '需要計画', 'technology', 'automation', 'production', '工厂', '投产', '自动化'))
    business = any(t in title for t in ('事業', '投資', '損失', '決算', '業績', '買収', '価格'))
    new_product = any(t in title for t in ('発売', 'ラインナップ', 'リニューアル', 'launch'))
    relevance = 35 if core else 28 if technology else 23 if business else 15
    impact = 28 if technology else 25 if business else 22 if new_product else 12
    reliability = 20 if item.get('source_kind') == 'manufacturer_official' else {'高': 18, '中': 12}.get(item.get('confidence'), 5)
    try:
        age = (reference_date - date.fromisoformat(item['date'])).days
        recency = 15 if 0 <= age <= 3 else 12 if 0 <= age <= 7 else 9 if 0 <= age <= 14 else 5 if 0 <= age <= 30 else 1
    except (KeyError, ValueError):
        recency = 0
    item['score_components'] = dict(relevance=relevance, impact=impact, reliability=reliability, recency=recency)
    item['score'] = sum(item['score_components'].values())
    item['score_method'] = 'rules_v1'
    item['impact_analysis'] = ''  # No fabricated strategic analysis.
    text = re.sub(r'\s+', ' ', item.get('source_excerpt') or item.get('summary') or '').strip()
    item['source_excerpt'] = text
    if item.get('excerpt_format') == 'pdf':
        # Skip contact/address blocks when the first factual company sentence
        # is present. Keep the untouched source_excerpt for auditability.
        start = re.search(r'当社は[、,]|日本製紙グループの|日本製紙クレシア株式会社', text[:750])
        if start:
            text = text[start.start():]
    # Preserve complete original sentences where possible, not generated facts.
    excerpt = text[:420]
    boundary = excerpt.rfind('。')
    if boundary >= 100:
        excerpt = excerpt[:boundary + 1]
    elif len(text) > len(excerpt):
        excerpt += '…'
    item['summary'] = excerpt
    item['summary_method'] = 'publisher_excerpt'
    return item
