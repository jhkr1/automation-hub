"""Google News RSS provider for Google Finance analysis."""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urlencode, urlparse
from xml.etree import ElementTree

import requests

from google_finance.models import StockNewsArticle

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"


class HttpResponse(Protocol):
    """HTTP response methods used by the provider."""

    content: bytes

    def raise_for_status(self) -> None:
        """Raise an HTTP error for unsuccessful responses."""


class HttpClient(Protocol):
    """Minimal HTTP client contract used by the RSS provider."""

    def get(self, url: str, *, timeout: float) -> HttpResponse:
        """Fetch one RSS URL."""


def _local_name(tag: str) -> str:
    """Return an XML tag name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _child_text(item: ElementTree.Element, name: str) -> str | None:
    """Return trimmed text for one RSS child element."""
    for child in item:
        if _local_name(child.tag) == name:
            value = child.text.strip() if child.text else ""
            return value or None
    return None


def _published_at(value: str | None) -> datetime | None:
    """Parse an optional RSS publication timestamp."""
    if value is None:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None


def parse_google_news_rss(xml: bytes, *, limit: int = 5) -> list[StockNewsArticle]:
    """Parse RSS articles and deduplicate raw URLs within one query."""
    if not isinstance(xml, bytes):
        raise TypeError("RSS response must be bytes")
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit must be a positive integer")

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ValueError("RSS XML could not be parsed") from exc

    articles: list[StockNewsArticle] = []
    seen_urls: set[str] = set()
    for index, item in enumerate(root.iter(), start=1):
        if _local_name(item.tag) != "item":
            continue
        title = _child_text(item, "title")
        url = _child_text(item, "link")
        if title is None:
            raise ValueError(f"RSS item {index} has no title")
        if url is None:
            raise ValueError(f"RSS item {index} has no link")
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError(f"RSS item {index} has an invalid URL")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        articles.append(
            StockNewsArticle(
                title=title,
                url=url,
                source=_child_text(item, "source"),
                published_at=_published_at(_child_text(item, "pubDate")),
            )
        )
        if len(articles) == limit:
            break
    return articles


class GoogleFinanceNewsProvider:
    """Search Google News RSS using a Google Finance company name."""

    def __init__(
        self,
        http_client: HttpClient | None = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._http_client = http_client or requests.Session()
        self._timeout = timeout

    def search(self, company_name: str, limit: int = 5) -> list[StockNewsArticle]:
        """Return recent news articles for one company name."""
        if not isinstance(company_name, str) or not company_name.strip():
            raise ValueError("company_name must not be empty")
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit must be a positive integer")

        query = urlencode({"q": company_name.strip(), "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
        response = self._http_client.get(
            f"{GOOGLE_NEWS_RSS_URL}?{query}",
            timeout=self._timeout,
        )
        response.raise_for_status()
        return parse_google_news_rss(response.content, limit=limit)
