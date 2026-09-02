#!/usr/bin/env python3
"""Collect recent, relevant industry news from Google News RSS.

Google News is used only as a discovery feed. The RSS publication timestamp is
preserved as ``published_at``; ``collected_at`` records when this job saw the
article. An article without a trustworthy publication timestamp is rejected
instead of being labelled as today's news.
"""

from __future__ import annotations

import argparse
import base64
import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:  # URL enrichment is optional in unit tests.
    requests = None
    BeautifulSoup = None

try:
    import feedparser
except ImportError:  # Unit tests can inject a parser without this dependency.
    feedparser = None


JST = timezone(timedelta(hours=9))
MAX_AGE_DAYS = int(os.getenv("NEWS_MAX_AGE_DAYS", "14"))
PATENT_MAX_AGE_DAYS = int(os.getenv("PATENT_MAX_AGE_DAYS", "30"))
MAX_ITEMS_PER_QUERY = int(os.getenv("NEWS_MAX_ITEMS_PER_QUERY", "25"))
MAX_ENRICH_ARTICLES = int(os.getenv("NEWS_MAX_ENRICH_ARTICLES", "30"))
HTTP_TIMEOUT_SECONDS = int(os.getenv("NEWS_HTTP_TIMEOUT_SECONDS", "15"))

# Fewer, broader queries reduce duplicate results and RSS traffic. The
# ``when:Nd`` clause is appended in build_feed_url(), so Google is asked for
# recent results before our own strict timestamp check runs.
SEARCH_QUERIES_GENERAL = [
    '"ユニ・チャーム" (おむつ OR 生理用品 OR 衛生用品 OR 新製品 OR 決算 OR 投資)',
    '"花王" (おむつ OR 生理用品 OR 衛生用品 OR 家庭紙 OR 研究開発)',
    '("P&G Japan" OR "Kimberly-Clark" OR Essity) (diaper OR tissue OR hygiene OR おむつ)',
    '(大王製紙 OR 王子ホールディングス OR 日本製紙) (家庭紙 OR パルプ OR 衛生用品 OR 投資)',
    '(Vinda OR Hengan OR 中顺洁柔 OR 维达 OR 恒安) (ティシュー OR おむつ OR 衛生用品)',
    '(家庭紙 OR トイレットペーパー OR ティシュー) (価格 OR 値上げ OR 規制 OR 市場)',
    '(おむつ OR 生理用品 OR ナプキン) (新製品 OR 素材 OR 技術 OR リサイクル)',
    '(不織布 OR 吸収体 OR パルプ) (新技術 OR 原料価格 OR 生産設備 OR サステナビリティ)',
    '(ウェットティッシュ OR ウェットワイプ) (新製品 OR 市場 OR 技術)',
]

SEARCH_QUERIES_MACHINE = [
    '(瑞光 OR Zuiko OR GDM OR Fameccanica) (おむつ OR ナプキン OR 吸収体) (加工機 OR 製造設備)',
    '(OPTIMA OR FANUC OR ファナック) (衛生用品 OR 不織布) (包装機 OR パレタイザー OR 自動化)',
    '(衛生用品 OR おむつ OR ナプキン) (製造機械 OR 包装ライン OR パレタイザー)',
]

ACADEMIC_QUERIES = [
    'site:patents.google.com (ユニ・チャーム OR 花王 OR 大王製紙 OR 王子製紙) (おむつ OR 吸収体 OR 衛生用品)',
    'site:jstage.jst.go.jp (家庭紙 OR 衛生用品 OR 不織布 OR 吸収体)',
]

SEARCH_QUERIES = SEARCH_QUERIES_GENERAL + SEARCH_QUERIES_MACHINE

CATEGORY_NAMES = {
    "①": "日用品・衛生用品メーカー",
    "②": "製紙・パルプメーカー",
    "③": "不織布・吸収体加工機メーカー",
    "④": "包装機・パレタイジング設備メーカー",
    "⑤": "ウェットティッシュ製造メーカー",
    "⑥": "ティッシュペーパー・家庭紙専業メーカー",
    "⑦": "学術論文・特許情報",
}

KNOWN_COMPANIES = [
    "ユニ・チャーム", "花王", "P&G Japan", "P&G", "ライオン",
    "Kimberly-Clark", "キンバリー・クラーク", "Essity", "大王製紙",
    "王子ホールディングス", "王子製紙", "日本製紙", "瑞光", "Zuiko",
    "GDM", "Fameccanica", "OPTIMA", "ファナック", "FANUC", "Vinda",
    "维达", "Hengan", "恒安", "中顺洁柔", "Winner Medical", "稳健医疗",
]

CORE_TERMS = [
    "家庭紙", "ティシュー", "ティッシュ", "トイレットペーパー", "衛生用紙",
    "ペーパータオル", "キッチンペーパー", "おむつ", "オムツ", "ナプキン",
    "生理用品", "月経", "ロリエ", "失禁", "ウェットティッシュ", "ウェットワイプ", "不織布",
    "吸収体", "パルプ", "衛生用品", "diaper", "tissue", "hygiene",
    "sanitary napkin", "nonwoven", "absorbent core", "wet wipe",
]

MACHINE_TERMS = [
    "加工機", "包装機", "パレタイザー", "製造設備", "製造機械", "包装ライン",
    "充填機", "産業用ロボット", "自動化", "machinery", "packaging machine",
]

OFFTOPIC_TERMS = [
    "洗濯洗剤", "柔軟剤", "シャンプー", "コンディショナー", "ボディソープ",
    "化粧品", "ファンデーション", "ハミガキ", "歯磨き", "歯ブラシ", "口腔",
    "ペットフード", "ドッグフード", "キャットフード", "コーヒー", "ビール", "サプリメント",
]

MARKET_REPORT_SPAM_TERMS = [
    "市場調査レポートを発表", "市場調査レポート販売", "世界市場予測",
    "市場規模、シェア、成長", "調査レポートの販売を開始", "2030年までの予測",
    "2031年までの予測", "2032年までの予測", "2033年までの予測",
    "おすすめ人気ランキング", "徹底比較", "口コミ・評判",
]

LOW_TRUST_SOURCES = [
    "Fortune Business Insights", "Report Ocean", "Research Nester",
    "Global Information", "Dream News", "NEWSCAST", "newscast.jp",
    "ドリームニュース", "Spherical Insights", "ねとらぼ", "ウォーカープラス",
    "LIMO", "au Webポータル",
]

CLICKBAIT_TERMS = [
    "作者に聞く", "おすすめ人気", "口コミ", "ライフスタイル", "収納ボックス",
    "トイレットペーパーケース", "無印アイテム", "かわいすぎる", "わんちゃん",
    "前場コメント", "後場コメント", "クロワッサン化", "芯に重ねて",
]

HIGH_TRUST_SOURCES = [
    "日本経済新聞", "Reuters", "ロイター", "Bloomberg", "NHK", "共同通信",
    "時事通信", "日刊工業新聞", "化学工業日報", "日本食糧新聞",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def strip_html(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def title_without_source(title: str, source_name: str = "") -> str:
    cleaned = strip_html(title)
    if source_name:
        cleaned = re.sub(rf"\s+(?:-\s*)?{re.escape(source_name)}\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    keep = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(keep), ""))


def parse_published_at(entry: Any) -> datetime | None:
    """Return a timezone-aware UTC timestamp from a feed entry."""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            pass
    return None


def extract_source(entry: Any) -> tuple[str, str]:
    source = entry.get("source") or {}
    if isinstance(source, dict):
        name = strip_html(source.get("title") or source.get("value") or "")
        url = source.get("href") or source.get("url") or ""
        return name, canonicalize_url(url)
    return strip_html(str(source)), ""


def extract_company(text: str) -> str:
    normalized = normalize_text(text)
    for company in KNOWN_COMPANIES:
        if normalize_text(company) in normalized:
            return company
    return "不明"


def determine_info_type(text: str) -> str:
    lowered = unicodedata.normalize("NFKC", text).lower()
    checks = [
        ("特許", ["特許", "patent"]),
        ("研究開発", ["研究", "論文", "学会", "技術開発", "research", "development"]),
        ("包装機技術", ["包装機", "包装ライン", "packaging machine", "パレタイザー"]),
        ("加工機技術", ["加工機", "製造機械", "製造設備", "machinery"]),
        ("新製品", ["新製品", "新商品", "新発売", "launch", "リニューアル"]),
        ("投資", ["投資", "買収", "出資", "m&a", "決算", "業績"]),
        ("環境", ["環境", "サステナ", "リサイクル", "carbon", "eco"]),
        ("規制", ["規制", "法律", "regulation", "値上げ", "価格改定"]),
    ]
    for label, terms in checks:
        if any(term in lowered for term in terms):
            return label
    return "其他"


def map_category(text: str, *, academic: bool = False) -> tuple[str, str]:
    lowered = unicodedata.normalize("NFKC", text).lower()
    if academic or any(term in lowered for term in ("特許", "論文", "j-stage", "patent")):
        category = "⑦"
    elif any(term.lower() in lowered for term in ("包装機", "パレタイザー", "包装ライン", "optima", "fanuc", "ファナック")):
        category = "④"
    elif any(term.lower() in lowered for term in ("加工機", "製造機械", "製造設備", "瑞光", "zuiko", "fameccanica", "gdm")):
        category = "③"
    elif any(term in lowered for term in ("ウェットティッシュ", "ウェットワイプ", "wet wipe")):
        category = "⑤"
    elif any(term in lowered for term in ("パルプ", "製紙", "王子ホールディングス", "日本製紙", "大王製紙")):
        category = "②"
    elif any(term in lowered for term in ("トイレットペーパー", "ティシュー", "ティッシュ", "家庭紙")):
        category = "⑥"
    else:
        category = "①"
    return category, CATEGORY_NAMES[category]


def assess_relevance(title: str, snippet: str, source_name: str = "", *, academic: bool = False) -> tuple[bool, list[str]]:
    text = f"{title} {snippet}"
    lowered = unicodedata.normalize("NFKC", text).lower()
    flags: list[str] = []
    if any(term.lower() in lowered for term in MARKET_REPORT_SPAM_TERMS):
        return False, ["market_report_spam"]
    if "市場" in lowered and "レポート" in lowered:
        return False, ["market_report_spam"]
    if any(term.lower() in lowered for term in CLICKBAIT_TERMS):
        return False, ["consumer_or_market_noise"]
    has_core = any(term.lower() in lowered for term in CORE_TERMS)
    has_machine = any(term.lower() in lowered for term in MACHINE_TERMS)
    has_company = extract_company(text) != "不明"
    has_offtopic = any(term.lower() in lowered for term in OFFTOPIC_TERMS)
    business_signals = (
        "決算", "業績", "投資", "買収", "出資", "m&a", "工場", "生産能力",
        "研究開発", "特許", "中期経営", "事業再編", "提携", "規制", "価格改定",
    )
    has_business_signal = any(term in lowered for term in business_signals)
    if has_offtopic:
        return False, ["off_topic"]
    if academic:
        relevant = (has_core or has_company) and any(k in lowered for k in ("特許", "論文", "patent", "研究"))
    else:
        relevant = has_core or has_machine or (has_company and has_business_signal)
    if not relevant:
        return False, ["no_industry_signal"]
    low_trust = any(name.lower() in source_name.lower() for name in LOW_TRUST_SOURCES)
    if low_trust and ("市場" in lowered or not has_company):
        return False, ["low_trust_source"]
    if low_trust:
        flags.append("low_trust_source")
    return True, flags


def source_confidence(source_name: str, source_url: str, flags: Iterable[str]) -> str:
    if "low_trust_source" in flags:
        return "低"
    host = urlsplit(source_url).netloc.lower()
    if any(name.lower() in source_name.lower() for name in HIGH_TRUST_SOURCES):
        return "高"
    if any(domain in host for domain in (
        "unicharm.co.jp", "kao.com", "daio-paper.co.jp", "ojiholdings.co.jp",
        "nipponpapergroup.com", "zuiko.co.jp", "essity.com", "kimberly-clark.com",
        "jstage.jst.go.jp", "patents.google.com",
    )):
        return "高"
    return "中"


def article_fingerprint(item: dict[str, Any]) -> str:
    title = title_without_source(item.get("title", ""), item.get("source_name", ""))
    raw = "|".join((normalize_text(title), normalize_text(item.get("source_name", "")), item.get("date", "")))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def build_feed_url(query: str, max_age_days: int) -> str:
    dated_query = query if re.search(r"\bwhen:\d+[dhm]\b", query) else f"{query} when:{max_age_days}d"
    return f"https://news.google.com/rss/search?q={quote(dated_query)}&hl=ja&gl=JP&ceid=JP:ja"


def _legacy_google_news_decode(article_id: str) -> str | None:
    """Decode old Google News IDs that directly contain the source URL."""
    try:
        raw = base64.urlsafe_b64decode(article_id + "=" * (-len(article_id) % 4))
    except (ValueError, TypeError):
        return None
    if raw.startswith(b"\x08\x13\x22"):
        raw = raw[3:]
    if raw.endswith(b"\xd2\x01\x00"):
        raw = raw[:-3]
    if not raw:
        return None
    length = raw[0]
    offset = 1
    if length >= 0x80 and len(raw) > 1:
        length = (length & 0x7F) | (raw[1] << 7)
        offset = 2
    candidate = raw[offset:offset + length].decode("utf-8", errors="ignore")
    return candidate if candidate.startswith(("http://", "https://")) else None


def _find_external_url(value: Any) -> str | None:
    if isinstance(value, str):
        if value.startswith(("http://", "https://")) and "news.google.com" not in value:
            return value.replace("\\u003d", "=").replace("\\u0026", "&")
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
        return _find_external_url(decoded)
    if isinstance(value, list):
        for part in value:
            found = _find_external_url(part)
            if found:
                return found
    if isinstance(value, dict):
        for part in value.values():
            found = _find_external_url(part)
            if found:
                return found
    return None


def resolve_google_news_url(url: str, *, session: Any = None) -> str:
    """Best-effort resolution of a Google News RSS URL to the publisher URL.

    Google does not document this redirect protocol, so resolution failure is
    non-fatal and the original discovery URL remains usable in a browser.
    """
    parts = urlsplit(url)
    if not parts.netloc.endswith("news.google.com") or "/articles/" not in parts.path:
        return canonicalize_url(url)
    article_id = parts.path.rsplit("/", 1)[-1]
    legacy = _legacy_google_news_decode(article_id)
    if legacy:
        return canonicalize_url(legacy)
    if requests is None:
        return canonicalize_url(url)

    client = session or requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; industry-report/2.0)", "Accept-Language": "ja,en;q=0.8"}
    try:
        page = client.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
        page.raise_for_status()
        timestamp_match = re.search(r'data-n-a-ts="([^"]+)"', page.text)
        signature_match = re.search(r'data-n-a-sg="([^"]+)"', page.text)
        if not timestamp_match or not signature_match:
            return canonicalize_url(url)
        timestamp = int(timestamp_match.group(1))
        signature = signature_match.group(1)
        request_data = [
            "garturlreq",
            [["X", "X", ["X", "X"], None, None, 1, 1, "JP:ja", None, 1, None, None, None, None, None, 0, 1],
             "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
            article_id,
            timestamp,
            signature,
        ]
        rpc = [[[
            "Fbv4je", json.dumps(request_data, ensure_ascii=False, separators=(",", ":")), None, "1"
        ]]]
        response = client.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            params={"rpcids": "Fbv4je"},
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "Referer": "https://news.google.com/"},
            data={"f.req": json.dumps(rpc, ensure_ascii=False, separators=(",", ":"))},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        for line in response.text.splitlines():
            if not line.startswith("["):
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                continue
            resolved = _find_external_url(decoded)
            if resolved:
                return canonicalize_url(resolved)
    except Exception:
        pass
    return canonicalize_url(url)


def fetch_article_excerpt(url: str, *, session: Any = None) -> str:
    """Extract a short factual text excerpt from an accessible publisher page."""
    if requests is None or BeautifulSoup is None or not url or "news.google.com" in urlsplit(url).netloc:
        return ""
    client = session or requests.Session()
    try:
        response = client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; industry-report/2.0)", "Accept-Language": "ja,en;q=0.8"},
            timeout=HTTP_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        if "html" not in response.headers.get("Content-Type", "").lower():
            return ""
        if len(response.content) > 3_000_000:
            return ""
        # A number of Japanese corporate sites omit charset or are incorrectly
        # interpreted as ISO-8859-1 by requests. Prefer detected encoding in
        # those cases to avoid storing mojibake in the dashboard.
        if not response.encoding or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
            response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        candidates = []
        for attrs in (
            {"property": "og:description"}, {"name": "description"},
            {"name": "twitter:description"},
        ):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                candidates.append(strip_html(tag.get("content")))
        for unwanted in soup(["script", "style", "nav", "footer", "aside", "form", "noscript"]):
            unwanted.decompose()
        container = soup.find("article") or soup.find("main")
        if container:
            paragraphs = [strip_html(node.get_text(" ", strip=True)) for node in container.find_all("p")]
            body = " ".join(part for part in paragraphs if len(part) >= 30)
            if body:
                candidates.append(body[:1800])
        candidates = [text for text in candidates if len(text) >= 60]
        return max(candidates, key=len)[:1800] if candidates else ""
    except Exception:
        return ""


def enrich_item(item: dict[str, Any]) -> dict[str, Any]:
    discovery_url = item.get("url", "")
    resolved = resolve_google_news_url(discovery_url)
    flags = set(item.get("quality_flags", []))
    if resolved and "news.google.com" not in urlsplit(resolved).netloc:
        item["discovery_url"] = discovery_url
        item["url"] = resolved
        flags.discard("aggregator_url")
        excerpt = fetch_article_excerpt(resolved)
        if excerpt and normalize_text(excerpt) != normalize_text(item.get("title", "")):
            item["summary"] = excerpt
            flags.discard("title_only_summary")
            item["fulltext_status"] = "excerpt_extracted"
        else:
            flags.add("fulltext_unavailable")
            item["fulltext_status"] = "unavailable"
    else:
        flags.add("original_url_unresolved")
        item["fulltext_status"] = "unavailable"
    item["quality_flags"] = sorted(flags)
    item["fingerprint"] = article_fingerprint(item)
    return item


def enrich_items(items: list[dict[str, Any]], limit: int = MAX_ENRICH_ARTICLES) -> list[dict[str, Any]]:
    if not items or limit <= 0:
        return items
    selected = items[:limit]
    enriched: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(5, len(selected))) as executor:
        futures = {executor.submit(enrich_item, item.copy()): index for index, item in enumerate(selected)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                enriched[index] = future.result()
            except Exception:
                fallback = selected[index]
                fallback["quality_flags"] = sorted(set(fallback.get("quality_flags", [])) | {"enrichment_error"})
                enriched[index] = fallback
    return [enriched.get(index, item) for index, item in enumerate(items)]


def fetch_google_news_rss(
    query: str,
    *,
    max_items: int = MAX_ITEMS_PER_QUERY,
    max_age_days: int = MAX_AGE_DAYS,
    academic: bool = False,
    now: datetime | None = None,
    feed_parser: Any = None,
) -> list[dict[str, Any]]:
    parser = feed_parser or feedparser
    if parser is None:
        raise RuntimeError("feedparser is not installed; run: pip install -r requirements.txt")

    reference_time = (now or utc_now()).astimezone(timezone.utc)
    cutoff = reference_time - timedelta(days=max_age_days)
    feed_url = build_feed_url(query, max_age_days)
    feed = parser.parse(feed_url, request_headers={"User-Agent": "industry-report/2.0 (+GitHub Actions)"})
    if getattr(feed, "bozo", False) and not getattr(feed, "entries", []):
        raise RuntimeError(f"RSS parse failed for query: {query}")

    results: list[dict[str, Any]] = []
    for entry in list(getattr(feed, "entries", []))[:max_items]:
        published = parse_published_at(entry)
        if published is None:
            continue
        if published < cutoff or published > reference_time + timedelta(hours=12):
            continue

        source_name, source_url = extract_source(entry)
        title = title_without_source(entry.get("title", ""), source_name)
        if not title:
            continue
        raw_summary = strip_html(entry.get("summary") or entry.get("description") or "")
        summary = title_without_source(raw_summary, source_name)
        relevant, flags = assess_relevance(title, summary, source_name, academic=academic)
        if not relevant:
            continue

        if normalize_text(summary) == normalize_text(title) or len(summary) < 20:
            summary = title
            flags.append("title_only_summary")

        discovery_url = canonicalize_url(entry.get("link", ""))
        if urlsplit(discovery_url).netloc.endswith("news.google.com"):
            flags.append("aggregator_url")

        text = f"{title} {summary}"
        company = extract_company(text)
        category_id, category_name = map_category(text, academic=academic)
        published_jst = published.astimezone(JST)
        item = {
            "title": title,
            "summary": summary,
            "company": company,
            "date": published_jst.strftime("%Y-%m-%d"),
            "published_at": isoformat_utc(published),
            "collected_at": isoformat_utc(reference_time),
            "category_id": category_id,
            "category_name": category_name,
            "info_type": "特許" if academic and "特許" in text else determine_info_type(text),
            "url": discovery_url,
            "source_name": source_name or urlsplit(source_url).netloc or "Google News",
            "source_url": source_url,
            "discovery_provider": "Google News RSS",
            "discovery_query": query,
            "confidence": source_confidence(source_name, source_url, flags),
            "quality_flags": sorted(set(flags)),
        }
        if academic:
            item.update({"is_academic": True, "permanent_record": True})
        item["fingerprint"] = article_fingerprint(item)
        results.append(item)
    return results


# Backwards-compatible name used by earlier code/tests.
fetch_from_google_news_rss = fetch_google_news_rss


def deduplicate(items: Iterable[dict[str, Any]], existing: Iterable[dict[str, Any]] = ()) -> list[dict[str, Any]]:
    existing_urls = {canonicalize_url(item.get("url", "")) for item in existing if item.get("url")}
    existing_fingerprints = {item.get("fingerprint") or article_fingerprint(item) for item in existing}
    chosen: dict[str, dict[str, Any]] = {}
    confidence_rank = {"低": 0, "中": 1, "高": 2}

    def quality(item: dict[str, Any]) -> tuple[int, int, int]:
        return (
            confidence_rank.get(item.get("confidence", ""), 0),
            1 if item.get("fulltext_status") == "excerpt_extracted" else 0,
            len(item.get("summary", "")),
        )

    for item in items:
        url = canonicalize_url(item.get("url", ""))
        fingerprint = item.get("fingerprint") or article_fingerprint(item)
        if (url and url in existing_urls) or fingerprint in existing_fingerprints:
            continue
        old_key = fingerprint
        normalized_title = normalize_text(title_without_source(item.get("title", ""), item.get("source_name", "")))
        for candidate_key, candidate in chosen.items():
            if candidate.get("date") != item.get("date"):
                continue
            candidate_title = normalize_text(title_without_source(candidate.get("title", ""), candidate.get("source_name", "")))
            if min(len(normalized_title), len(candidate_title)) >= 18 and SequenceMatcher(None, normalized_title, candidate_title).ratio() >= 0.84:
                old_key = candidate_key
                break
        old = chosen.get(old_key)
        if old is None or quality(item) > quality(old):
            if old is not None and old_key != fingerprint:
                chosen.pop(old_key, None)
            chosen[fingerprint] = item
    return sorted(chosen.values(), key=lambda item: item.get("published_at", ""), reverse=True)


def collect_news(
    *,
    query_limit: int | None = None,
    max_items: int = MAX_ITEMS_PER_QUERY,
    now: datetime | None = None,
    feed_parser: Any = None,
    enrich: bool = True,
    enrich_limit: int = MAX_ENRICH_ARTICLES,
) -> tuple[list[dict[str, Any]], list[str]]:
    jobs = [(query, MAX_AGE_DAYS, False) for query in SEARCH_QUERIES]
    jobs += [(query, PATENT_MAX_AGE_DAYS, True) for query in ACADEMIC_QUERIES]
    if query_limit is not None:
        jobs = jobs[:query_limit]
    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, (query, age, academic) in enumerate(jobs, start=1):
        try:
            rows = fetch_google_news_rss(
                query, max_items=max_items, max_age_days=age, academic=academic,
                now=now, feed_parser=feed_parser,
            )
            collected.extend(rows)
            print(f"[{index:02d}/{len(jobs):02d}] {len(rows):2d} accepted: {query[:72]}")
        except Exception as exc:  # One failed feed must not abort the full daily run.
            message = f"{query}: {exc}"
            errors.append(message)
            print(f"[{index:02d}/{len(jobs):02d}] ERROR: {message}")
        time.sleep(0.1)
    unique = deduplicate(collected)
    if enrich:
        print(f"Enriching up to {min(enrich_limit, len(unique))} unique articles with publisher URLs/text...")
        unique = enrich_items(unique, limit=enrich_limit)
        unique = deduplicate(unique)
    return unique, errors


def load_existing(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not os.path.exists(path):
        return [], [], []
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if isinstance(raw, list):
        return raw, [], []
    if "dates" in raw:
        regular = [item for bucket in raw.get("dates", {}).values() for item in bucket]
        return regular, raw.get("patents", []), raw.get("highlights", [])
    return raw.get("items", []), [], raw.get("highlights", [])


def prune_items(items: Iterable[dict[str, Any]], *, days: int, now: datetime | None = None) -> list[dict[str, Any]]:
    cutoff = (now or utc_now()).astimezone(JST).date() - timedelta(days=days)
    kept = []
    for item in items:
        try:
            item_date = datetime.strptime(item.get("date", ""), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if item_date >= cutoff:
            kept.append(item)
    return kept


def save_data(path: str, regular: list[dict[str, Any]], patents: list[dict[str, Any]], highlights: list[dict[str, Any]]) -> None:
    dates: dict[str, list[dict[str, Any]]] = {}
    for item in sorted(regular, key=lambda row: row.get("published_at", row.get("date", "")), reverse=True):
        dates.setdefault(item["date"], []).append(item)
    payload = {
        "schema_version": 2,
        "last_updated": isoformat_utc(utc_now()),
        "highlights": highlights,
        "dates": dates,
        "patents": patents,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch recent tissue and hygiene industry news")
    parser.add_argument("--dry-run", action="store_true", help="fetch and print results without modifying data")
    parser.add_argument("--query-limit", type=int, default=None, help="run only the first N queries")
    parser.add_argument("--max-items", type=int, default=MAX_ITEMS_PER_QUERY, help="maximum RSS entries inspected per query")
    parser.add_argument("--no-enrich", action="store_true", help="skip publisher URL and article excerpt extraction")
    parser.add_argument("--enrich-limit", type=int, default=MAX_ENRICH_ARTICLES, help="maximum articles enriched per run")
    parser.add_argument("--json-output", help="write dry-run results to this JSON file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.normpath(os.path.join(script_dir, "..", "data", "news_data.json"))
    regular, patents, highlights = load_existing(data_path)
    fresh, errors = collect_news(
        query_limit=args.query_limit,
        max_items=args.max_items,
        enrich=not args.no_enrich,
        enrich_limit=args.enrich_limit,
    )
    fresh = deduplicate(fresh, regular + patents)

    if args.json_output:
        output_path = os.path.abspath(args.json_output)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump({"items": fresh, "errors": errors}, handle, ensure_ascii=False, indent=2)

    print(f"Accepted {len(fresh)} new unique articles; feed errors: {len(errors)}")
    for item in fresh[:10]:
        print(f"  {item['date']} [{item['confidence']}] {item['source_name']}: {item['title'][:90]}")

    if args.dry_run:
        print("Dry run: data/news_data.json was not modified.")
        return 0 if fresh or not errors else 1

    if errors and not fresh:
        print("All usable feed results failed; existing data was left unchanged.")
        return 1

    new_regular = [item for item in fresh if not item.get("permanent_record")]
    new_patents = [item for item in fresh if item.get("permanent_record")]
    regular = prune_items(regular + new_regular, days=30)
    patents = prune_items(patents + new_patents, days=PATENT_MAX_AGE_DAYS)
    save_data(data_path, deduplicate(regular), deduplicate(patents), highlights)
    print(f"Saved {len(regular)} regular articles and {len(patents)} academic/patent articles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
