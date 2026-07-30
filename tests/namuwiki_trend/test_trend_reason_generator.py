from datetime import datetime, timezone

import pytest

from database.daily_trend_query import DailyTrendRank
from namuwiki_trend.daily_trend_news_service import DailyTrendNews
from namuwiki_trend.models import NewsArticle, TrendReason
from namuwiki_trend.trend_reason_generator import (
    INSUFFICIENT_EVIDENCE_REASON,
    TrendReasonGenerator,
    build_trend_reason_prompt,
)


def _item(articles: tuple[NewsArticle, ...] = ()) -> DailyTrendNews:
    return DailyTrendNews(
        trend=DailyTrendRank("손흥민", 3, 1, 1.5, 28),
        articles=articles,
    )


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    def __init__(self, client: "FakeClient") -> None:
        self.client = client

    def generate_content(self, *, model: str, contents: str) -> FakeResponse:
        self.client.calls.append((model, contents))
        if self.client.error:
            raise self.client.error
        return FakeResponse(self.client.text)


class FakeClient:
    def __init__(self, text: str = "", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[tuple[str, str]] = []
        self.models = FakeModels(self)


def _article(title: str = "손흥민 관련 최신 뉴스") -> NewsArticle:
    return NewsArticle(
        title=title,
        url="https://news.example/article-1",
        source="뉴스 출처",
        published_at=datetime(2026, 7, 30, 1, tzinfo=timezone.utc),
    )


def _response(keyword: str = "손흥민") -> str:
    return (
        '{"keyword":"'
        + keyword
        + '","reason":"관련 기사에서 공통 사건이 확인됩니다.",'
        '"confidence":"medium","supporting_articles":["https://news.example/article-1"]}'
    )


def test_prompt_contains_trend_news_metadata_and_url() -> None:
    prompt = build_trend_reason_prompt(_item((_article(),)))

    assert "손흥민" in prompt
    assert "등장 횟수: 3" in prompt
    assert "손흥민 관련 최신 뉴스" in prompt
    assert "뉴스 출처" in prompt
    assert "2026-07-30T01:00:00+00:00" in prompt
    assert "https://news.example/article-1" in prompt
    assert "JSON 객체만 출력한다" in prompt


def test_generate_parses_structured_response_and_calls_once() -> None:
    client = FakeClient(_response())

    result = TrendReasonGenerator(client).generate(_item((_article(),)))

    assert result == TrendReason(
        "손흥민",
        "관련 기사에서 공통 사건이 확인됩니다.",
        "medium",
        ("https://news.example/article-1",),
    )
    assert len(client.calls) == 1


def test_empty_articles_return_insufficient_evidence_without_call() -> None:
    client = FakeClient(_response())

    result = TrendReasonGenerator(client).generate(_item())

    assert result.reason == INSUFFICIENT_EVIDENCE_REASON
    assert result.confidence == "low"
    assert result.supporting_articles == ()
    assert client.calls == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "JSON"),
        ('{"keyword":"손흥민"}', "reason"),
        (
            '{"keyword":"손흥민","reason":"이유","confidence":"unknown",'
            '"supporting_articles":[]}',
            "confidence",
        ),
        (
            '{"keyword":"손흥민","reason":"이유","confidence":"low",'
            '"supporting_articles":"url"}',
            "supporting_articles",
        ),
    ],
)
def test_generate_rejects_malformed_or_invalid_response(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TrendReasonGenerator(FakeClient(text)).generate(_item((_article(),)))


def test_generate_rejects_keyword_mismatch_and_long_reason() -> None:
    mismatch = _response("다른 검색어")
    long_reason = (
        '{"keyword":"손흥민","reason":"'
        + "가" * 301
        + '","confidence":"low","supporting_articles":[]}'
    )

    with pytest.raises(ValueError, match="keyword"):
        TrendReasonGenerator(FakeClient(mismatch)).generate(_item((_article(),)))
    with pytest.raises(ValueError, match="300자"):
        TrendReasonGenerator(FakeClient(long_reason)).generate(_item((_article(),)))


def test_generate_propagates_client_exception() -> None:
    expected = RuntimeError("client failed")

    with pytest.raises(RuntimeError) as raised:
        TrendReasonGenerator(FakeClient(error=expected)).generate(_item((_article(),)))

    assert raised.value is expected


def test_input_articles_are_not_mutated() -> None:
    articles = (_article(),)
    item = _item(articles)
    TrendReasonGenerator(FakeClient(_response())).generate(item)

    assert item.articles == articles
