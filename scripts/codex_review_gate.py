"""Validate a Codex editorial receipt bound to exact reviewed input.

This is an accidental-bypass/tampering guard, NOT a cryptographic identity proof.
Only the reviewing Codex task may write approval; API drafting must never do so.
"""
import argparse
import hashlib
import json
from datetime import datetime

REQUIRED_CHECKS = ('original_sources', 'publication_dates', 'deduplication_30_days',
                   'industry_scope', 'japanese_complete', 'category_counts', 'coverage_search')


def fingerprint(payload):
    content = dict(date=payload['date'], items=payload['items'])
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def validate_review(payload):
    review = payload.get('review') or {}
    if review.get('reviewer') != 'codex' or review.get('status') != 'approved':
        raise ValueError('Explicit Codex approval required; API drafts cannot publish')
    if review.get('content_sha256') != fingerprint(payload):
        raise ValueError('Content changed after review; repeat Codex review')
    reviewed_at = datetime.fromisoformat(review.get('reviewed_at', ''))
    if reviewed_at.tzinfo is None:
        raise ValueError('Review timestamp requires a timezone')
    ids = [item['id'] for item in payload['items']]
    reviewed_ids = review.get('reviewed_item_ids', [])
    if len(ids) != len(set(ids)) or sorted(ids) != sorted(reviewed_ids):
        raise ValueError('Approval must cover every item exactly once')
    checks = review.get('checks', {})
    if any(checks.get(check) is not True for check in REQUIRED_CHECKS):
        raise ValueError('Incomplete Codex editorial checklist')
    sources = review.get('draft_sources', [])
    allowed_sources = {'codex', 'openrouter/deepseek-chat', 'publisher_excerpt'}
    if not isinstance(sources, list) or not sources or any(s not in allowed_sources for s in sources):
        raise ValueError('Record the actual drafting providers separately from the Codex reviewer')
    news_count = sum(it.get('kind') == 'news' for it in payload['items'])
    reason = review.get('shortfall_reason_ja', '')
    if news_count < 20 and (not isinstance(reason, str) or len(reason.strip()) < 20):
        raise ValueError('Below 20 news: document supplemental searches and remaining shortfall')
    # Whitelist public audit fields; never leak local paths or source captures.
    return {key: review[key] for key in ('reviewer', 'status', 'content_sha256', 'reviewed_at',
                                          'reviewed_item_ids', 'checks', 'draft_sources')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Calculate fingerprint only; never approves an edition')
    parser.add_argument('source')
    args = parser.parse_args()
    with open(args.source, encoding='utf-8') as handle:
        print(fingerprint(json.load(handle)))
