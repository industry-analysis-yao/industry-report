"""Live production scope-policy checks; never publish these synthetic fixtures.

Explicit admission rules own high-confidence scope. The live model may disagree;
production then uses a labeled publisher extract, not a fabricated AI summary.
Service failures still fail this contract, rather than passing on fallback alone.
"""
import os
from generate_dashboard import ai_summarize, RULE_EXTRACT_PREFIX

CASES = [
    ('competitor_factory', True, '日本製紙 工場事故の調査を開始', '日本製紙',
     '日本製紙は同社工場の煙突損傷事故について、原因究明と再発防止策の策定を目的とした調査委員会を設置した。操業への影響と安全対策を調査する。'),
    ('palletizing', True, '工場に段ボール箱のパレタイズロボットを導入', '設備メーカー',
     '工場の出荷ラインに段ボール箱を積付けるパレタイザーを導入。カメラで箱の位置を取得し、積付け作業を自動化する。包装工程から出荷までの作業負荷軽減が目的。'),
    ('robot_simulation', True, '包装ラインの箱詰めロボット導入を支援', '設備メーカー',
     '包装ラインの箱詰めロボット導入に向けて3Dシミュレーションシステムを採用。工場内での干渉チェックと箱詰め動作の検証を仮想空間で実施する。'),
    ('packaging_inspection', True, '包装展で金属検出機を展示', 'エー・アンド・デイ',
     '金属異物検査と重量チェックを一台で実施するウェイトチェッカを展示。大箱や大袋の出荷前検査に対応する。包装機に組み込める計量センサも紹介。'),
    ('home_robot', False, '家庭用ロボットの新色を発売', 'テスト家電',
     '家庭内の家事を支援する家庭用ロボットの新色を発売。掃除や日常会話を楽しむことができる。工場向け製品ではなく家庭での利用を想定した商品。'),
    ('university_only', False, '大学がロボットサッカーの基礎研究を発表', 'テスト大学',
     '大学単独の研究チームがロボットサッカーにおけるボール追跡の基礎研究を発表。企業との共同開発や工場への実導入はなく、競技用の研究である。'),
    ('factory_inspection', False, '工場に巡回点検ロボットを導入', 'TECO',
     'ビール工場の設備点検に四足歩行ロボットを導入。カメラとセンサーで設備の状態を取得し、巡回点検を自動化する。包装や積付けの具体的用途はない。'),
    ('general_robot_ai', False, '工場向けPhysical AIロボット基盤モデルを発表', 'AIメーカー',
     '汎用ロボットの基盤モデル開発に投資。製造・物流への展開を目指し、工場作業に応用するための学習データを収集する。新しい産業用AIの研究開発を進める。'),
]


def main():
    if not os.environ.get('OPENROUTER_API_KEY'):
        raise RuntimeError('Live scope contract requires the configured AI credential')
    failed = []
    for name, expected, title, company, body in CASES:
        accepted, result = ai_summarize(title, body, company)
        valid = accepted == expected and result != 'AI Summary Pending'
        mode = 'rule_extract' if result.startswith(RULE_EXTRACT_PREFIX) else 'rule_exclusion' if result.startswith('RULE_EXCLUDED:') else 'model'
        print(f'[SCOPE-CONTRACT] {name}: {"PASS" if valid else "FAIL"}; mode={mode}; {result}')
        if not valid:
            failed.append(name)
    if failed:
        raise RuntimeError('AI scope contract failed: ' + ', '.join(failed))


if __name__ == '__main__':
    main()
