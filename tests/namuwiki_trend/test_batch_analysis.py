"""Namuwiki Batch 분석 계약 테스트."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from namuwiki_trend.enricher import TrendEnricher
from namuwiki_trend.gemini_reason_generator import (
    BatchMappingError,
    BatchResponseError,
    GeminiReasonGenerator,
    build_batch_reason_prompt,
    parse_batch_reason_response,
)
from namuwiki_trend.models import NewsArticle, TrendInsight, TrendItem


def _trend(rank: int, keyword: str) -> TrendItem:
    return TrendItem(rank=rank, keyword=keyword, href=f"/Go?q={keyword}")


def _article(keyword: str) -> NewsArticle:
    return NewsArticle(
        title=f"{keyword} 관련 기사",
        url=f"https://news.example/{keyword}",
        source="테스트뉴스",
        published_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )


def _items() -> list[tuple[TrendItem, list[NewsArticle]]]:
    return [
        (_trend(2, "두번째"), [_article("두번째")]),
        (_trend(1, "첫번째"), [_article("첫번째")]),
    ]


class FakeRuntime:
    """Batch Runtime 호출을 기록하는 Fake."""

    def __init__(self, text: str, *, finish_reason=None, output_tokens=None) -> None:
        self.text = text
        self.finish_reason = finish_reason
        self.output_tokens = output_tokens
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            text=self.text,
            finish_reason=self.finish_reason,
            output_tokens=self.output_tokens,
        )


def _response(items: list[dict[str, object]]) -> str:
    return json.dumps({"items": items}, ensure_ascii=False)


def test_batch_prompt_contains_all_identifiers_and_json_contract() -> None:
    prompt = build_batch_reason_prompt(_items())

    assert "rank: 2" in prompt
    assert "keyword: 두번째" in prompt
    assert "rank: 1" in prompt
    assert "keyword: 첫번째" in prompt
    assert "정확한 JSON 객체 하나" in prompt
    assert "2~3문장" in prompt
    assert "https://news.example" not in prompt


def test_batch_generator_calls_runtime_once_and_maps_response() -> None:
    items = _items()
    runtime = FakeRuntime(
        _response(
            [
                {"rank": 1, "keyword": "첫번째", "reason": " 첫번째 이유 "},
                {"rank": 2, "keyword": "두번째", "reason": "두번째 이유"},
            ]
        )
    )
    generator = GeminiReasonGenerator(runtime=runtime, profile="test")

    result = generator.generate_reasons(items)

    assert result == {(1, "첫번째"): "첫번째 이유", (2, "두번째"): "두번째 이유"}
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["max_output_tokens"] == 4096
    response_format = runtime.calls[0]["response_format"]
    assert response_format.response_mime_type == "application/json"
    assert response_format.response_schema["required"] == ["items"]


def test_batch_parser_accepts_one_json_code_fence() -> None:
    items = _items()
    response = "```json\n" + _response(
        [
            {"rank": 1, "keyword": "첫번째", "reason": "첫번째 이유"},
            {"rank": 2, "keyword": "두번째", "reason": "두번째 이유"},
        ]
    ) + "\n```"

    result = parse_batch_reason_response(response, items)

    assert len(result) == 2


@pytest.mark.parametrize(
    "response",
    [
        '설명입니다. {"items": []}',
        '{"items": []} 설명입니다.',
    ],
)
def test_batch_parser_rejects_text_around_json(response: str) -> None:
    with pytest.raises(BatchResponseError, match="malformed_json"):
        parse_batch_reason_response(response, _items())


@pytest.mark.parametrize(
    "response",
    [
        '{"items": [{"rank": 1, "keyword": "첫번째", "reason": "이유"}',
        '{"items": [{"rank": 1, "keyword": "첫번째", "reason": "이유}]',
        '{"items": [{"rank": 1, "keyword": "첫번째", "reason": "이유"}',
    ],
)
def test_batch_parser_classifies_truncated_json(response: str) -> None:
    with pytest.raises(BatchResponseError, match="truncated_json"):
        parse_batch_reason_response(response, _items())


def test_batch_parser_classifies_max_tokens_separately() -> None:
    with pytest.raises(BatchResponseError, match="truncated_json"):
        parse_batch_reason_response(
            '{"items": [{"rank": 1, "keyword": "첫번째", "reason": "이유"}',
            _items(),
            finish_reason="MAX_TOKENS",
            output_tokens=4096,
        )


def test_batch_parser_accepts_ten_long_reasons() -> None:
    items = [
        (_trend(rank, f"검색어-{rank}"), [_article(f"검색어-{rank}")])
        for rank in range(1, 11)
    ]
    response = _response(
        [
            {"rank": trend.rank, "keyword": trend.keyword, "reason": "가" * 300}
            for trend, _ in items
        ]
    )

    result = parse_batch_reason_response(response, items)

    assert len(result) == 10


@pytest.mark.parametrize(
    ("item", "error", "message"),
    [
        ({"rank": True, "keyword": "첫번째", "reason": "이유"}, BatchResponseError, "positive"),
        ({"rank": 9, "keyword": "첫번째", "reason": "이유"}, BatchMappingError, "unknown_rank"),
        ({"rank": 1, "keyword": "없는말", "reason": "이유"}, BatchMappingError, "unknown_keyword"),
        ({"rank": 2, "keyword": "첫번째", "reason": "이유"}, BatchMappingError, "pair_mismatch"),
        ({"rank": 1, "keyword": "첫번째", "reason": ""}, BatchResponseError, "non_empty"),
        (
            {"rank": 1, "keyword": "첫번째", "reason": "이유", "extra": 1},
            BatchResponseError,
            "unexpected",
        ),
    ],
)
def test_batch_parser_rejects_invalid_item(
    item: dict[str, object], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        parse_batch_reason_response(_response([item]), _items())


def test_batch_parser_rejects_missing_duplicate_and_malformed_items() -> None:
    items = _items()
    one = {"rank": 1, "keyword": "첫번째", "reason": "이유"}
    with pytest.raises(BatchMappingError, match="missing_item"):
        parse_batch_reason_response(_response([one]), items)
    with pytest.raises(BatchMappingError, match="duplicate_item"):
        parse_batch_reason_response(_response([one, one]), items)
    with pytest.raises(BatchResponseError, match="malformed_json"):
        parse_batch_reason_response("{broken", items)


class FakeNewsProvider:
    """검색어별 뉴스 결과를 반환하는 Fake."""

    def __init__(self, articles: dict[str, list[NewsArticle]]) -> None:
        self.articles = articles
        self.calls: list[str] = []

    def search(self, keyword: str, limit: int) -> list[NewsArticle]:
        self.calls.append(keyword)
        return self.articles[keyword]


class FakeBatchGenerator:
    """Batch 생성 호출을 기록하는 Fake."""

    def __init__(self) -> None:
        self.calls: list[list[tuple[TrendItem, list[NewsArticle]]]] = []

    def generate_reasons(self, items):
        self.calls.append(list(items))
        return {(trend.rank, trend.keyword): f"{trend.keyword} 이유" for trend, _ in items}


def test_enricher_calls_batch_once_and_restores_rank_order() -> None:
    trends = [_trend(2, "두번째"), _trend(1, "첫번째"), _trend(3, "뉴스없음")]
    news = FakeNewsProvider(
        {"두번째": [_article("두번째")], "첫번째": [_article("첫번째")], "뉴스없음": []}
    )
    generator = FakeBatchGenerator()

    result = TrendEnricher(news, generator).enrich_all(trends)

    assert [item.trend.rank for item in result] == [1, 2, 3]
    assert [item.reason for item in result] == [
        "첫번째 이유",
        "두번째 이유",
        "제공된 기사만으로는 정확한 이유를 확인하기 어렵다.",
    ]
    assert len(generator.calls) == 1
    assert [trend.keyword for trend, _ in generator.calls[0]] == ["두번째", "첫번째"]


def test_enricher_does_not_call_batch_when_all_news_are_empty() -> None:
    trend = _trend(1, "뉴스없음")
    news = FakeNewsProvider({"뉴스없음": []})
    generator = FakeBatchGenerator()

    result = TrendEnricher(news, generator).enrich_all([trend])

    assert isinstance(result[0], TrendInsight)
    assert generator.calls == []
