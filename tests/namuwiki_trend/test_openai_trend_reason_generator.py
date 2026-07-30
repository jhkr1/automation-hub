from datetime import datetime, timezone

import pytest

from database.daily_trend_query import DailyTrendRank
from namuwiki_trend.daily_trend_news_service import DailyTrendNews
from namuwiki_trend.models import NewsArticle, TrendReason
from namuwiki_trend.openai_trend_reason_generator import (
    INSUFFICIENT_EVIDENCE_REASON,
    OpenAITrendReasonGenerator,
)


def _item(articles: tuple[NewsArticle, ...] = ()) -> DailyTrendNews:
    return DailyTrendNews(DailyTrendRank("손흥민", 3, 1, 1.5, 28), articles)


class FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class FakeResponses:
    def __init__(self, client: "FakeClient") -> None:
        self.client = client

    def create(self, **kwargs: object) -> FakeResponse:
        self.client.calls.append(kwargs)
        if self.client.error:
            raise self.client.error
        return FakeResponse(self.client.output_text)


class FakeClient:
    def __init__(self, output_text: str, error: Exception | None = None) -> None:
        self.output_text = output_text
        self.error = error
        self.calls: list[dict[str, object]] = []
        self.responses = FakeResponses(self)


def _article() -> NewsArticle:
    return NewsArticle(
        "손흥민 관련 기사",
        "https://news.example/1",
        "뉴스 출처",
        datetime(2026, 7, 30, 1, tzinfo=timezone.utc),
    )


def _response(url: str = "https://news.example/1") -> str:
    return (
        '{"keyword":"손흥민","reason":"공통 뉴스 사건이 확인됩니다.",'
        f'"confidence":"medium","supporting_articles":["{url}"]}}'
    )


def test_generate_sends_prompt_model_and_structured_schema() -> None:
    client = FakeClient(_response())

    result = OpenAITrendReasonGenerator(client, model="test-model").generate(_item((_article(),)))

    assert result == TrendReason(
        "손흥민",
        "공통 뉴스 사건이 확인됩니다.",
        "medium",
        ("https://news.example/1",),
    )
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request["model"] == "test-model"
    assert "손흥민" in request["input"]
    response_format = request["text"]["format"]  # type: ignore[index]
    assert response_format["type"] == "json_schema"  # type: ignore[index]


def test_prompt_contains_article_metadata_and_never_api_key() -> None:
    client = FakeClient(_response())

    OpenAITrendReasonGenerator(client, model="test-model").generate(_item((_article(),)))

    prompt = client.calls[0]["input"]
    assert "손흥민 관련 기사" in prompt
    assert "뉴스 출처" in prompt
    assert "2026-07-30T01:00:00+00:00" in prompt
    assert "https://news.example/1" in prompt
    assert "OPENAI_API_KEY" not in prompt


def test_empty_articles_return_fallback_without_api_call() -> None:
    client = FakeClient(_response())

    result = OpenAITrendReasonGenerator(client).generate(_item())

    assert result.reason == INSUFFICIENT_EVIDENCE_REASON
    assert result.confidence == "low"
    assert result.supporting_articles == ()
    assert client.calls == []


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ("not json", "JSON"),
        ('{"keyword":"손흥민"}', "reason"),
        (
            '{"keyword":"다른 검색어","reason":"이유","confidence":"low",'
            '"supporting_articles":[]}',
            "keyword",
        ),
        (
            '{"keyword":"손흥민","reason":"이유","confidence":"unknown",'
            '"supporting_articles":[]}',
            "confidence",
        ),
        (
            '{"keyword":"손흥민","reason":"이유","confidence":"low",'
            '"supporting_articles":["https://other.example"]}',
            "subset",
        ),
    ],
)
def test_invalid_responses_are_rejected(response: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        OpenAITrendReasonGenerator(FakeClient(response)).generate(_item((_article(),)))


def test_reason_length_and_supporting_type_are_validated() -> None:
    long_reason = (
        '{"keyword":"손흥민","reason":"'
        + "가" * 301
        + '","confidence":"low","supporting_articles":[]}'
    )
    bad_type = '{"keyword":"손흥민","reason":"이유","confidence":"low","supporting_articles":"url"}'

    with pytest.raises(ValueError, match="300자"):
        OpenAITrendReasonGenerator(FakeClient(long_reason)).generate(_item((_article(),)))
    with pytest.raises(ValueError, match="subset"):
        OpenAITrendReasonGenerator(FakeClient(bad_type)).generate(_item((_article(),)))


def test_client_error_is_propagated() -> None:
    expected = RuntimeError("rate limit")

    with pytest.raises(RuntimeError) as raised:
        OpenAITrendReasonGenerator(FakeClient(_response(), expected)).generate(_item((_article(),)))

    assert raised.value is expected


def test_input_object_is_not_mutated() -> None:
    item = _item((_article(),))
    OpenAITrendReasonGenerator(FakeClient(_response())).generate(item)

    assert item.articles[0].url == "https://news.example/1"
