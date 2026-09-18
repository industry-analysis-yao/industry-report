"""Guard reviewed Japanese editions against missing translations/common leaks.

This is a conservative lint, not a language detector or substitute for review.
Company/product names, URLs and publication numbers keep their original spelling.
"""
import re

DISPLAY_FIELDS = (
    'title', 'summary', 'impact_analysis', 'company', 'category_name', 'info_type',
    'date_evidence', 'verification_level', 'caution', 'priority', 'region',
    'relationship', 'event_type', 'patent_family_status', 'legal_status',
)
CHINESE_LEAK = re.compile(r'[这们说为与对发时从进该仅现应将关产过页报显类业处开许专纤维]')


def validate_japanese_item(item):
    if item.get('content_language') != 'ja':
        raise ValueError('Japanese editorial review is required')
    for key in ('title', 'summary', 'impact_analysis', 'date_evidence', 'verification_level', 'caution'):
        if not str(item.get(key, '')).strip():
            raise ValueError('Missing Japanese field: ' + key)
    for key in DISPLAY_FIELDS:
        if CHINESE_LEAK.search(str(item.get(key, ''))):
            raise ValueError('Possible untranslated Chinese in ' + key)
    for key in ('summary', 'impact_analysis'):
        if not re.search(r'[ぁ-ゖァ-ヺ]', item[key]):
            raise ValueError('Expected Japanese prose in ' + key)
