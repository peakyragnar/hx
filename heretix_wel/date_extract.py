from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

USER_AGENT = "Heretix-WEL/1.0 (+https://heretix.ai)"


DATE_HINT_REGEX = re.compile(
    r"(Published|Updated|Posted|Last\s+modified|Last\s+updated)\s*[:\-–]\s*(.{5,80})",
    flags=re.IGNORECASE,
)
URL_DATE_REGEX = re.compile(
    r"/(20\d{2})[\/\-](\d{1,2})[\/\-](\d{1,2})/"
)

JSONLD_DATE_KEYS = ("datePublished", "dateCreated", "dateModified")
OG_DATE_KEYS = (
    "article:published_time",
    "article:modified_time",
    "og:updated_time",
    "date",
    "pubdate",
)

CONFIDENCE_MAP = {
    "jsonld": 1.0,
    "og": 0.9,
    "time": 0.8,
    "url": 0.7,
    "body": 0.6,
    "header": 0.4,
}


@dataclass
class PublishSignal:
    published_at: Optional[datetime]
    method: Optional[str]
    confidence: float


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = date_parser.parse(value, fuzzy=True, default=datetime.now(timezone.utc))
    except (ValueError, OverflowError, TypeError):
        return None
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_jsonld_dates(soup: BeautifulSoup) -> Iterable[str]:
    for script in soup.find_all("script"):
        script_type = script.get("type", "") or ""
        if "ld+json" not in script_type.lower():
            continue
        try:
            data = json.loads(script.string or script.text or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            typ = item.get("@type")
            if isinstance(typ, list):
                is_article = any(t in ("Article", "NewsArticle", "BlogPosting") for t in typ)
            else:
                is_article = typ in ("Article", "NewsArticle", "BlogPosting")
            if not is_article:
                continue
            for key in JSONLD_DATE_KEYS:
                if key in item:
                    yield str(item[key])


def _extract_meta_dates(soup: BeautifulSoup) -> Iterable[str]:
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        if prop in OG_DATE_KEYS:
            content = meta.get("content")
            if content:
                yield content


def _extract_time_tags(soup: BeautifulSoup) -> Iterable[str]:
    for time_tag in soup.find_all("time"):
        if time_tag.get("datetime"):
            yield time_tag["datetime"]
        elif time_tag.text:
            yield time_tag.text


def _extract_body_dates(text: str) -> Iterable[str]:
    for match in DATE_HINT_REGEX.finditer(text):
        yield match.group(2)


def _extract_url_date(url: str) -> Optional[datetime]:
    match = URL_DATE_REGEX.search(url)
    if not match:
        return None
    year, month, day = match.groups()
    candidate = f"{year}-{month}-{day}"
    return _parse_date(candidate)


def extract_publish_signal(
    url: str,
    html: str,
    headers: Optional[requests.structures.CaseInsensitiveDict] = None,
) -> Tuple[PublishSignal, str]:
    soup = BeautifulSoup(html, "html.parser")
    body_text = soup.get_text(separator=" ", strip=True)
    signal = _extract_publish_signal_from_soup(url, soup, headers)
    return signal, body_text


def _extract_publish_signal_from_soup(
    url: str,
    soup: BeautifulSoup,
    headers: Optional[requests.structures.CaseInsensitiveDict] = None,
) -> PublishSignal:
    # JSON-LD
    for candidate in _extract_jsonld_dates(soup):
        dt = _parse_date(candidate)
        if dt:
            return PublishSignal(dt, "jsonld", CONFIDENCE_MAP["jsonld"])

    # Open Graph / meta
    for candidate in _extract_meta_dates(soup):
        dt = _parse_date(candidate)
        if dt:
            return PublishSignal(dt, "og", CONFIDENCE_MAP["og"])

    # <time> tags
    for candidate in _extract_time_tags(soup):
        dt = _parse_date(candidate)
        if dt:
            return PublishSignal(dt, "time", CONFIDENCE_MAP["time"])

    # URL pattern
    url_dt = _extract_url_date(url)
    if url_dt:
        return PublishSignal(url_dt, "url", CONFIDENCE_MAP["url"])

    # Body heuristics
    body_text = soup.get_text(separator=" ", strip=True)[:4000]
    for candidate in _extract_body_dates(body_text):
        dt = _parse_date(candidate)
        if dt:
            return PublishSignal(dt, "body", CONFIDENCE_MAP["body"])

    # HTTP headers fallback
    if headers:
        last_modified = headers.get("Last-Modified") or headers.get("last-modified")
        if last_modified:
            dt = _parse_date(last_modified)
            if dt:
                return PublishSignal(dt, "header", CONFIDENCE_MAP["header"])

    return PublishSignal(None, None, 0.0)


def enrich_docs_with_publish_dates(
    docs,
    timeout: float = 6.0,
    max_docs: int = 16,
) -> None:
    session = requests.Session()
    for doc in docs[:max_docs]:
        if doc.published_at and doc.published_confidence >= 0.5:
            continue
        try:
            response = session.get(
                doc.url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue
        signal, page_text = extract_publish_signal(doc.url, response.text, response.headers)
        if signal.published_at:
            doc.published_at = signal.published_at
            doc.published_method = signal.method
            doc.published_confidence = signal.confidence
        if page_text:
            doc.page_text = page_text[:4000]
