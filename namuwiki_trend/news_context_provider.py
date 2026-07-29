"""Google News RSS에서 검색어 하나의 최신 뉴스 문맥을 가져오는 PoC."""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urlencode, urlparse
from xml.etree import ElementTree

import requests

from namuwiki_trend.models import NewsArticle

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"


class HttpResponse(Protocol):
    """Provider가 사용하는 HTTP 응답의 최소 계약."""

    content: bytes

    def raise_for_status(self) -> None:
        """HTTP 오류 상태를 예외로 변환한다."""


class HttpClient(Protocol):
    """Provider가 사용하는 HTTP client의 최소 계약."""

    def get(self, url: str, *, timeout: float) -> HttpResponse:
        """URL을 조회한다."""


def _local_name(tag: str) -> str:
    """XML namespace가 포함된 태그에서 local name을 반환한다."""
    return tag.rsplit("}", 1)[-1]


def _child_text(item: ElementTree.Element, name: str) -> str | None:
    """RSS item의 자식 텍스트를 trim하여 반환한다."""
    for child in item:
        if _local_name(child.tag) == name:
            value = child.text.strip() if child.text else ""
            return value or None
    return None


def _parse_published_at(value: str | None) -> datetime | None:
    """RSS pubDate를 datetime으로 변환하고 선택 필드는 없으면 None으로 둔다."""
    if value is None:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None


def _validate_url(value: str, *, item_index: int) -> str:
    """기사 URL이 HTTP(S) 절대 URL인지 검증한다."""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"RSS item {item_index}의 URL이 유효하지 않음: {value!r}")
    return value


def parse_google_news_rss(xml: bytes, *, limit: int = 5) -> list[NewsArticle]:
    """Google News RSS XML을 검증·파싱하고 URL 중복을 제거한다."""
    if not isinstance(xml, bytes):
        raise TypeError(f"RSS 응답은 bytes여야 함: {type(xml).__name__}")
    if type(limit) is not int or limit <= 0:
        raise ValueError(f"limit은 양의 정수여야 함: {limit!r}")

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ValueError("RSS XML을 파싱할 수 없음") from exc

    articles: list[NewsArticle] = []
    seen_urls: set[str] = set()
    for index, item in enumerate(root.iter(), start=1):
        if _local_name(item.tag) != "item":
            continue
        title = _child_text(item, "title")
        url = _child_text(item, "link")
        if title is None:
            raise ValueError(f"RSS item {index}에 title이 없음")
        if url is None:
            raise ValueError(f"RSS item {index}에 link가 없음")
        url = _validate_url(url, item_index=index)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        articles.append(
            NewsArticle(
                title=title,
                url=url,
                source=_child_text(item, "source"),
                published_at=_parse_published_at(_child_text(item, "pubDate")),
            )
        )
        if len(articles) == limit:
            break
    return articles


class NewsContextProvider:
    """검색어 하나를 Google News RSS로 조회하는 뉴스 문맥 Provider."""

    def __init__(
        self,
        http_client: HttpClient | None = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError(f"timeout은 양수여야 함: {timeout!r}")
        self._http_client = http_client or requests.Session()
        self._timeout = timeout

    def search(self, keyword: str, limit: int = 5) -> list[NewsArticle]:
        """검색어의 최신 뉴스 문맥을 조회한다."""
        if not isinstance(keyword, str):
            raise TypeError(f"keyword는 문자열이어야 함: {type(keyword).__name__}")
        normalized_keyword = keyword.strip()
        if not normalized_keyword:
            raise ValueError("keyword가 비어 있음")
        if type(limit) is not int or limit <= 0:
            raise ValueError(f"limit은 양의 정수여야 함: {limit!r}")

        query = urlencode(
            {
                "q": normalized_keyword,
                "hl": "ko",
                "gl": "KR",
                "ceid": "KR:ko",
            }
        )
        response = self._http_client.get(f"{GOOGLE_NEWS_RSS_URL}?{query}", timeout=self._timeout)
        response.raise_for_status()
        return parse_google_news_rss(response.content, limit=limit)
