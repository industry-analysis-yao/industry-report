"""Narrow, evidence-based admission rules, independent of model randomness.

This decides subject scope only. Dates, body availability and published-history
deduplication remain mandatory gates in generate_dashboard.
"""
import unicodedata
from fetch_news import assess_relevance

SCOPE_VERSION = 1


def classify_scope(title, body, company=''):
    title = unicodedata.normalize('NFKC', title or '').lower()
    body = unicodedata.normalize('NFKC', body or '').lower()
    text = title + ' ' + body

    def result(verdict, rule, evidence=()):
        return dict(verdict=verdict, rule=rule, evidence=list(evidence), version=SCOPE_VERSION)

    exclusions = ('家庭用ロボット', '家事ロボット', 'ロボット住宅', '掃除ロボット',
                  'ロボット掃除機', 'ロボットサッカー', '手術ロボット', '溶接専用',
                  'robot vacuum', 'surgical robot', 'robot soccer', 'home robot')
    matched = [term for term in exclusions if term in title]
    if matched:
        return result('exclude', 'consumer_or_specialist_robot', matched)
    if '大学単独' in text or 'university-only' in text:
        return result('exclude', 'university_only_research')
    relevant, flags = assess_relevance(title, body)
    hard_flags = [flag for flag in flags if flag not in {'no_industry_signal'}]
    if not relevant and hard_flags:
        return result('exclude', 'existing_scope_exclusion', hard_flags)
    if len(body.strip()) < 60:
        return result('review', 'insufficient_body_for_rule_admission')

    companies = ('大王製紙', '日本製紙', 'ユニ・チャーム', 'ユニチャーム', '花王',
                 '王子', 'unicharm', 'essity', 'kimberly-clark', 'p&g', '恒安', '维达')
    subject_company = unicodedata.normalize('NFKC', company or '').lower() + ' ' + title
    makers = [name for name in companies if name in subject_company]
    business = [term for term in ('工場', '事故', '調査委員会', '操業', '投資', '決算', '買収',
                                  '原材料', '生産', '新製品', '価格改定', 'factory', 'investment', 'acquisition')
                if term in text]
    if makers and business:
        return result('include', 'target_manufacturer_activity', makers + business)

    equipment = [term for term in ('包装機', '装箱機', '金属異物検査', '金属検出機', '重量チェック',
                                  'ウェイトチェッカ', '計量センサ', '搬送ロボット', '協働ロボット',
                                  '巡回点検', 'ピッキングロボット', '産業用ロボット', '吸収体加工機',
                                  '不織布製造', 'checkweigher', 'case packer', 'industrial robot',
                                  'packaging machine', 'palletizing robot') if term in body]
    contexts = [term for term in ('包装', '工場', '物流', '出荷', '生産ライン', '製造',
                                 'factory', 'warehouse', 'manufacturing', 'packaging') if term in body]
    # Title must describe equipment or its industrial application; footer mentions
    # of robots in an unrelated company's press release are not admission proof.
    subjects = [term for term in ('包装', 'tokyo pack', '検出機', 'チェッカ', '加工機', 'ロボット',
                                 '搬送', 'robot', 'packaging', 'checkweigher', 'converting') if term in title]
    events = [term for term in ('展示', '出展', '導入', '発売', '開発', '採用', '発表', 'launch',
                               'introduc', 'deploy', 'adopt', 'unveil') if term in text]
    if equipment and contexts and subjects and events:
        return result('include', 'industrial_equipment_event', equipment + contexts + events)
    return result('review', 'requires_contextual_review')
