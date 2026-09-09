"""Company/topic discovery coverage, kept separate from digest selection.

Queries are intentionally not required to mention both a machine and diapers:
transferable packing/handling technology is part of this industry's supply chain.
"""
import re

LOCALES = {
    'ja': {'hl': 'ja', 'gl': 'JP', 'ceid': 'JP:ja', 'region': 'Japan'},
    'en': {'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en', 'region': 'International'},
    'zh': {'hl': 'zh-CN', 'gl': 'CN', 'ceid': 'CN:zh-Hans', 'region': 'China'},
}

# One company/family per query prevents a high-volume brand from consuming all
# returned slots. A source registry can be expanded without changing collectors.
QUERY_GROUPS = {
    ('ja', 'machine'): [
        '瑞光', 'GDM 不織布', 'Fameccanica', 'Joa おむつ',
        '(不織布 OR 吸収体) (加工機 OR 製造ライン OR 超音波 OR 接合)',
        '(スリッター OR 巻取機 OR コンバーティング) (新製品 OR 開発 OR 導入)',
    ],
    ('ja', 'packaging'): [
        'フジキカイ', '大森機械工業', '川島製作所 包装', '東京自働機械',
        'PACRAFT', 'イシダ 包装', 'OPTIMA 包装',
        '(包装機 OR 装箱機 OR ピロー包装 OR ケーサー) (発売 OR 開発 OR 出展 OR 導入)',
        '(包装 OR 充填 OR 封緘) (検査装置 OR 画像検査 OR 検査機) (新製品 OR 発売 OR 出展)',
    ],
    ('ja', 'palletizer'): [
        'ファナック ロボット', '安川電機 ロボット', '川崎重工 ロボット',
        '三菱電機 ロボット', 'オムロン ロボット', 'ヤマハ発動機 産業用ロボット',
        '不二輸送機', 'ユニバーサルロボット', 'ABB ロボット', 'オカムラ パレタイザー',
        '(協働ロボット OR パレタイジング OR ピッキング OR ロボットハンド) (発売 OR 開発 OR 導入 OR 展示)',
        '(物流自動化 OR AMR OR AGV) (工場 OR 出荷 OR パレット OR 包装)',
        '"国際物流総合展" (ロボット OR 包装 OR パレタイザー)',
        '"国際物流総合展" (仕分け OR 搬送 OR 自動倉庫)',
        '(ロボット OR ピッキング) (ビジョン OR センサー OR 制御装置) (発売 OR 開発 OR 新製品)',
        '(パナソニックコネクト OR ダイフク OR Mujin OR ラピュタロボティクス) (新製品 OR 開発 OR 導入 OR 出展)',
    ],
    ('ja', 'rivals'): [
        'ユニ・チャーム 新製品', '大王製紙 エリエール', '日本製紙 クレシア',
        '花王 (メリーズ OR ロリエ OR おむつ)', '王子ネピア', 'リブドゥコーポレーション',
        '白十字 おむつ', '住友精化 吸水性樹脂', '日本触媒 吸水性樹脂',
    ],
    ('ja', 'tissue'): [
        '丸富製紙', 'カミ商事', '大分製紙', '丸住製紙 家庭紙', '春日製紙',
        '(ティシュー OR トイレットペーパー OR ペーパータオル) (新発売 OR 生産 OR 値上げ)',
    ],
    ('ja', 'wet'): [
        'ユニ・チャーム おしりふき', 'レック ウェット', '大一紙工', '昭和紙工',
        '(ウエットティシュー OR ウェットシート OR ウェットワイプ) (発売 OR 工場 OR 技術)',
    ],
    ('en', 'machine'): [
        'GDM Coesia', 'Fameccanica', 'Curt G Joa', 'ANDRITZ (nonwoven OR tissue)',
        'Valmet (tissue OR converting)', 'PCMC tissue',
        '(diaper OR nonwoven) (converting OR machinery OR production line)',
    ],
    ('en', 'packaging'): [
        'OPTIMA Nonwovens', 'PAC Machinery', 'Cama Group packaging', 'IMA packaging',
        '(cartoning OR case packing OR flow wrapping) (launch OR unveils OR automation)',
    ],
    ('en', 'palletizer'): [
        'FANUC (robot OR automation)', 'Universal Robots', 'ABB Robotics',
        'Yaskawa palletizing', 'Robotiq', 'KUKA (handling OR palletizing)',
        '(robotic packing OR palletizing robot OR robot gripper) (launch OR unveils OR partnership)',
    ],
    ('en', 'rivals'): [
        'Essity (hygiene OR tissue OR investment)', 'Kimberly-Clark (diaper OR tissue OR hygiene)',
        'Procter Gamble (Pampers OR Always)', '(nonwoven OR superabsorbent) (investment OR launches)',
    ],
    ('zh', 'machine'): [
        '金卫机械 卫生用品', '汉威机械 卫生用品', '培新 纸尿裤',
        '(卫生巾 OR 纸尿裤 OR 无纺布) (生产线 OR 设备 OR 超声波)',
    ],
    ('zh', 'packaging'): [
        '(生活用纸 OR 纸巾 OR 湿巾) (包装机 OR 装箱机 OR 自动化)',
        '(达意隆 OR 松川 OR 中亚股份) (包装 OR 机器人)',
    ],
    ('zh', 'palletizer'): [
        '(埃斯顿 OR 新松 OR 埃夫特 OR 节卡 OR 越疆) (码垛 OR 搬运 OR 协作机器人)',
        '(码垛机器人 OR 装箱机器人 OR 机器视觉) (发布 OR 新品 OR 投产)',
    ],
    ('zh', 'rivals'): [
        '恒安 卫生用品', '维达 生活用纸', '中顺洁柔', '稳健医疗 全棉 湿巾',
    ],
}


def expanded_queries():
    return [dict(query=q, language=language, group=group, max_age_days=7)
            for (language, group), queries in QUERY_GROUPS.items() for q in queries]


EQUIPMENT_COMPANIES = {
    '瑞光': 'machine', 'Zuiko': 'machine', 'GDM': 'machine', 'Fameccanica': 'machine',
    'Curt G. Joa': 'machine', 'Joa': 'machine', 'ANDRITZ': 'machine', 'Valmet': 'machine',
    'フジキカイ': 'packaging', '大森機械工業': 'packaging', '川島製作所': 'packaging',
    'PACRAFT': 'packaging', '東京自働機械': 'packaging', 'OPTIMA': 'packaging',
    'PAC Machinery': 'packaging', 'Cama Group': 'packaging',
    'ファナック': 'palletizer', 'FANUC': 'palletizer', '安川電機': 'palletizer',
    'Yaskawa': 'palletizer', 'MOTOMAN': 'palletizer', 'Universal Robots': 'palletizer',
    'ユニバーサルロボット': 'palletizer', 'Robotiq': 'palletizer', 'ABB': 'palletizer',
    '川崎重工': 'palletizer', 'KUKA': 'palletizer', '不二輸送機': 'palletizer',
    'オムロン': 'palletizer', '三菱電機': 'palletizer', 'Palladyne': 'palletizer',
    'Orbbec': 'palletizer', 'ダイフク': 'palletizer', 'パナソニックコネクト': 'palletizer',
    'Highlanders': 'palletizer', 'Huayan Robotics': 'palletizer', 'Techman': 'palletizer', '達明': 'palletizer',
    '埃斯顿': 'palletizer', '节卡': 'palletizer', '越疆': 'palletizer', '新松': 'palletizer',
}

EQUIPMENT_TERMS = {
    'machine': ('不織布製造', 'コンバーティング', 'スリッター', '巻取機', '超音波接合',
                'converting machine', 'converting line', 'diaper machine', 'tissue machine',
                'nonwoven line', 'nonwoven machinery', '卫生用品设备', '纸尿裤生产线'),
    'packaging': ('包装機', '包装ライン', '包装技術', '装箱', 'ピロー包装', 'ケーサー',
                  'packaging machine', 'packaging automation', 'packing system', 'cartoning',
                  'case packer', 'flow wrap', '包装机'),
    'palletizer': ('ロボット', 'パレタイ', 'ピッキング', '搬送', 'ハンドリング', 'robot',
                   'cobot', 'palletiz', 'palletis', 'gripper', 'pick-and-place', 'robotics',
                   '机器臂', '机器人', '码垛', 'autonomous mobile robot', 'openarm', 'unitree g1'),
}


CONGLOMERATES = {'三菱電機', 'オムロン', '川崎重工', 'ABB', 'ANDRITZ', 'Valmet'}


def company_matches(company, text):
    if company.isascii():
        return bool(re.search(r'(?<![a-z])' + re.escape(company.lower()) + r'(?![a-z])', text.lower()))
    return company.lower() in text.lower()


def equipment_section(text):
    text = text.lower()
    # Handling/packing capabilities, not consumer robots or unrelated welding.
    if any(term in text for term in ('ロボット掃除機', 'ロボットサッカー', '溶接', 'welding',
                                     'vacuum cleaner', 'robot vacuum', 'surgical robot', '手术机器人', '掃除ロボット',
                                     'robot soccer', 'robotaxi', '掃除機', 'ロボットアニメ')):
        return None
    if ('フィジカルai' in text or 'physical ai' in text) and any(t in text for t in ('工場', '物流', 'factory', 'manufacturing')):
        return 'palletizer'
    for section in ('palletizer', 'packaging', 'machine'):
        if any(term in text for term in EQUIPMENT_TERMS[section]):
            return section
    for company, section in EQUIPMENT_COMPANIES.items():
        if company in CONGLOMERATES:
            continue
        if company_matches(company, text) and any(t in text for t in ('展示', '出展', '新製品', '製品', '開発', '発表', '受賞', 'launch', 'unveil', 'automation')):
            return section
    return None
