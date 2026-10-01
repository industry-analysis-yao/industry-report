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
        'エー・アンド・デイ (包装 OR 検査 OR 計量)',
        '(アンリツ OR イシダ OR ニッカ電測) (検査機 OR 包装 OR 計量)',
        '(ゼネラルパッカー OR 静岡シブヤ精機 OR シンワ機械) (発売 OR 出展 OR 開発)',
        '(コニカミノルタ OR ダックエンジニアリング) (包装 OR フィルム OR 印字検査)',
        '"TOKYO PACK" (新製品 OR 技術 OR 包装機 OR 検査)',
        'シリウスビジョン (検査 OR 包装 OR 開発)',
        'ミヤコシ (軟包装 OR 加工 OR 開発)',
        'ホリゾン (包装 OR 自動化 OR 開発)',
    ],
    ('ja', 'palletizer'): [
        'ファナック (パレタイザー OR パレタイズ OR 箱詰め)',
        '安川電機 (パレタイズ OR パレタイジング OR 積付け)',
        '川崎重工 (パレタイザー OR デパレタイザー)',
        '不二輸送機', 'オカムラ パレタイザー',
        '(パレタイザー OR デパレタイザー OR パレタイズ) (発売 OR 開発 OR 導入 OR 展示)',
        '(Mujin OR ダイフク OR ユニバーサルロボット) (積付け OR 荷積み OR パレタイズ OR 箱詰め)',
        '(ロボットハンド OR グリッパー) (段ボール OR 包装ライン OR 袋詰め OR 積付け)',
    ],
    ('ja', 'rivals'): [
        'ユニ・チャーム 新製品', '大王製紙 エリエール', '日本製紙 クレシア',
        '花王 (メリーズ OR ロリエ OR おむつ)', '王子ネピア', 'リブドゥコーポレーション',
        '白十字 おむつ', '住友精化 吸水性樹脂', '日本触媒 吸水性樹脂',
        'ユニ・チャーム (設備投資 OR 工場 OR 特許 OR 価格改定 OR 決算)',
        '日本製紙 (家庭紙 OR クレシア OR パルプ OR セルロース)',
        '王子ネピア (新製品 OR 設備 OR 価格改定 OR 生産)',
        '王子ホールディングス (設備投資 OR パルプ OR セルロース OR リサイクル)',
        'レンゴー (包装 OR 原紙 OR 設備投資)',
    ],
    ('ja', 'tissue'): [
        '丸富製紙', 'カミ商事', '大分製紙', '丸住製紙 家庭紙', '春日製紙',
        '(ティシュー OR トイレットペーパー OR ペーパータオル) (新発売 OR 生産 OR 値上げ)',
    ],
    ('ja', 'wet'): [
        'ユニ・チャーム おしりふき', 'レック ウェット', '大一紙工', '昭和紙工',
        '(ウエットティシュー OR ウェットシート OR ウェットワイプ) (発売 OR 工場 OR 技術)',
        '大富士製紙 (不織布 OR ウェット OR 生産)',
        '服部製紙 (ウエット OR ウェット OR 新製品)',
        'コーヨー化成 (ウエット OR ウェット OR 工場)',
        'サンジャパン (おしりふき OR ウェット OR 不織布)',
    ],
    ('en', 'machine'): [
        'GDM Coesia', 'Fameccanica', 'Curt G Joa', 'ANDRITZ (nonwoven OR tissue)',
        'Valmet (tissue OR converting)', 'PCMC tissue',
        '(diaper OR nonwoven) (converting OR machinery OR production line)',
        '(Reifenhauser OR Dilo OR A.Celli) (nonwoven OR tissue OR production)',
        '(Kansan OR Teknoweb OR DCY) (wet wipes OR converting)',
    ],
    ('en', 'packaging'): [
        'OPTIMA Nonwovens', 'PAC Machinery', 'Cama Group packaging', 'IMA packaging',
        '(cartoning OR case packing OR flow wrapping) (launch OR unveils OR automation)',
    ],
    ('en', 'palletizer'): [
        'FANUC (palletizing OR depalletizing OR case packing)',
        'Universal Robots palletizing', 'ABB (palletizing OR depalletizing)',
        'Yaskawa palletizing', 'Robotiq palletizing', 'KUKA palletizing',
        '(palletizing robot OR depalletizer OR palletiser) (launch OR unveils OR installation)',
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
        '(埃斯顿 OR 新松 OR 埃夫特 OR 节卡 OR 越疆) (码垛 OR 拆垛 OR 装箱)',
        '(码垛机器人 OR 装箱机器人) (发布 OR 新品 OR 投产)',
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

PALLETIZER_TERMS = ('パレタイ', 'パレタイズ', 'パレタジング', 'デパレタイ', 'デパレタイズ',
                    '積付け', '積み付け', '荷積み', '荷下ろし', '段積み',
                    'palletiz', 'palletis', 'depallet', '码垛', '碼垛', '拆垛', '码盘')

EQUIPMENT_TERMS = {
    'machine': ('不織布製造', 'コンバーティング', 'スリッター', '巻取機', '超音波接合',
                'converting machine', 'converting line', 'diaper machine', 'tissue machine',
                'nonwoven line', 'nonwoven machinery', '卫生用品设备', '纸尿裤生产线'),
    'packaging': ('包装機', '包装設備', '包装ライン', '包装技術', '装箱', 'ピロー包装', 'ケーサー',
                  'packaging machine', 'packaging automation', 'packing system', 'cartoning',
                  'case packer', 'flow wrap', '包装机', '包装システム', 'tokyo pack', '印字検査',
                  '重量選別機', '金属検出機', 'checkweigher', '箱詰め', '袋詰め', '封函',
                  'case packing', 'case-packing', 'robotic packing', 'automatic bagging',
                  'carton handling', 'end-of-line', '包装検査', '包装ライン搬送'),
    'palletizer': PALLETIZER_TERMS,
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
    for section in ('palletizer', 'packaging', 'machine'):
        if any(term in text for term in EQUIPMENT_TERMS[section]):
            return section
    for company, section in EQUIPMENT_COMPANIES.items():
        if company in CONGLOMERATES or section == 'palletizer':
            continue
        if company_matches(company, text) and any(t in text for t in ('展示', '出展', '新製品', '製品', '開発', '発表', '受賞', 'launch', 'unveil', 'automation')):
            return section
    return None


def robot_scope_exclusion(title, body=''):
    """A robot brand/AI label is not proof of a packaging-line application.

    Inspect the headline and lead only: navigation/footer mentions must not
    qualify an unrelated humanoid or general robot financing announcement.
    """
    title = (title or '').lower()
    if not any(t in title for t in ('ロボット', 'robot', 'cobot', '机器人', '機器人',
                                   'ヒューマノイド', '人型', 'humanoid', 'フィジカルai', 'physical ai')):
        return None
    lead = (body or '')[:350].lower()
    # A sentence explicitly saying there is no application is not evidence.
    lead = ' '.join(s for s in re.split(r'[。!?\n]', lead)
                    if not re.search(r'(?:用途|対応).{0,12}(?:ない|なし|未記載|不明)|no (?:packaging|palletizing) application', s))
    application = title + ' ' + lead
    concrete = PALLETIZER_TERMS + EQUIPMENT_TERMS['packaging'] + EQUIPMENT_TERMS['machine']
    if any(t in application for t in concrete):
        return None
    return 'robot_without_packaging_line_application'
