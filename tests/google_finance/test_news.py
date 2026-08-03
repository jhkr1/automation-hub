"""Google Finance news provider tests."""

from datetime import datetime, timezone

import pytest

from google_finance.news import GoogleFinanceNewsProvider, parse_google_news_rss

RSS = b"""\
<rss><channel>
<item><title>Apple first</title><link>https://news.example/1</link>
<source>Example News</source><pubDate>Thu, 30 Jul 2026 06:00:00 GMT</pubDate></item>
<item><title>Apple duplicate</title><link>https://news.example/1</link></item>
<item><title>Apple second</title><link>https://news.example/2</link></item>
</channel></rss>
"""


class FakeResponse:
    """Minimal RSS response fake."""

    def __init__(self, content: bytes) -> None:
        self.content = content
        self.status_checked = False

    def raise_for_status(self) -> None:
        self.status_checked = True


class FakeHttpClient:
    """Minimal HTTP client fake."""

    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, float]] = []

    def get(self, url: str, *, timeout: float) -> FakeResponse:
        self.calls.append((url, timeout))
        return self.response


def test_parse_google_news_rss_deduplicates_raw_urls() -> None:
    articles = parse_google_news_rss(RSS)

    assert [article.title for article in articles] == ["Apple first", "Apple second"]
    assert articles[0].source == "Example News"
    assert articles[0].published_at == datetime(2026, 7, 30, 6, tzinfo=timezone.utc)


def test_news_provider_searches_company_name_and_passes_timeout() -> None:
    response = FakeResponse(RSS)
    client = FakeHttpClient(response)
    provider = GoogleFinanceNewsProvider(client, timeout=3.5)

    articles = provider.search(" Apple Inc ", limit=1)

    assert len(articles) == 1
    assert "q=Apple+Inc" in client.calls[0][0]
    assert client.calls[0][1] == 3.5
    assert response.status_checked


@pytest.mark.parametrize("xml", [b"", b"<rss>"])
def test_parse_google_news_rss_rejects_invalid_xml(xml: bytes) -> None:
    with pytest.raises(ValueError, match="RSS XML"):
        parse_google_news_rss(xml)
