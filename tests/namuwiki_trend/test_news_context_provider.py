"""뉴스 문맥 Provider의 네트워크 비의존 테스트."""

from datetime import datetime, timedelta, timezone

import pytest
import requests

from namuwiki_trend.news_context_provider import NewsContextProvider, parse_google_news_rss

RSS = '''<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
<item><title>  첫 번째 기사  </title><link>https://news.example/1</link>
<source>연합뉴스</source><pubDate>Wed, 29 Jul 2026 10:00:00 +0900</pubDate></item>
<item><title>두 번째 기사</title><link>https://news.example/2</link></item>
<item><title>중복 기사</title><link>https://news.example/1</link></item>
</channel></rss>'''.encode()


class FakeResponse:
    """requests.Response의 Provider 사용 부분만 흉내 낸다."""

    def __init__(self, content: bytes = RSS, error: Exception | None = None) -> None:
        self.content = content
        self.error = error

    def raise_for_status(self) -> None:
        """설정된 HTTP 예외를 발생시킨다."""
        if self.error:
            raise self.error


class FakeClient:
    """실제 네트워크를 사용하지 않는 HTTP client."""

    def __init__(
        self,
        response: FakeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or FakeResponse(error=error)
        self.calls: list[tuple[str, float]] = []

    def get(self, url: str, *, timeout: float) -> FakeResponse:
        """호출 정보를 저장하고 fake 응답을 반환한다."""
        self.calls.append((url, timeout))
        return self.response


def test_parse_rss_maps_fields_and_deduplicates_urls() -> None:
    """제목·URL·출처·게시 시각을 매핑하고 URL 중복은 첫 항목만 유지한다."""
    articles = parse_google_news_rss(RSS, limit=5)

    assert len(articles) == 2
    assert articles[0].title == "첫 번째 기사"
    assert articles[0].source == "연합뉴스"
    assert articles[0].published_at == datetime(
        2026,
        7,
        29,
        10,
        tzinfo=timezone(timedelta(hours=9)),
    )
    assert articles[1].published_at is None


def test_search_trims_keyword_builds_korean_url_and_limits_results() -> None:
    """검색어를 trim하고 한국어 feed URL과 limit을 사용한다."""
    client = FakeClient()
    articles = NewsContextProvider(client, timeout=3).search("  손흥민  ", limit=1)

    assert len(articles) == 1
    assert "q=%EC%86%90%ED%9D%A5%EB%AF%BC" in client.calls[0][0]
    assert "hl=ko" in client.calls[0][0]
    assert client.calls[0][1] == 3


@pytest.mark.parametrize("keyword", ["", "  ", None])
def test_search_rejects_empty_or_non_string_keyword(keyword: object) -> None:
    """빈 검색어와 문자열이 아닌 검색어를 거부한다."""
    with pytest.raises((TypeError, ValueError)):
        NewsContextProvider(FakeClient()).search(keyword)  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_search_rejects_invalid_limit(limit: object) -> None:
    """양의 정수가 아닌 limit을 거부한다."""
    with pytest.raises(ValueError):
        NewsContextProvider(FakeClient()).search("검색어", limit=limit)  # type: ignore[arg-type]


def test_parser_rejects_missing_required_fields_and_invalid_url() -> None:
    """title·link 누락과 HTTP(S) 절대 URL이 아닌 link를 거부한다."""
    with pytest.raises(ValueError, match="title"):
        parse_google_news_rss(b"<rss><channel><item><link>https://e.test</link></item></channel></rss>")
    with pytest.raises(ValueError, match="link"):
        parse_google_news_rss(
            "<rss><channel><item><title>제목</title></item></channel></rss>".encode()
        )
    with pytest.raises(ValueError, match="URL"):
        parse_google_news_rss(
            "<rss><channel><item><title>제목</title><link>/relative</link></item></channel></rss>".encode()
        )


def test_parser_rejects_invalid_xml_and_returns_empty_result() -> None:
    """잘못된 XML은 실패시키고 item이 없으면 빈 결과를 반환한다."""
    with pytest.raises(ValueError, match="XML"):
        parse_google_news_rss(b"<rss>")
    assert parse_google_news_rss(b"<rss><channel /></rss>") == []


def test_search_propagates_http_exception() -> None:
    """HTTP client의 예외를 원인 그대로 전달한다."""
    expected = requests.HTTPError("fake HTTP failure")

    with pytest.raises(requests.HTTPError) as raised:
        NewsContextProvider(FakeClient(error=expected)).search("검색어")

    assert raised.value is expected
