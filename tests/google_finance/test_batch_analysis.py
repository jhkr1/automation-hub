"""Google Finance Watchlist Batch analysis tests."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from google_finance.analysis_application import analyze_stored_quotes_batch
from google_finance.batch_analysis import (
    BATCH_MAX_OUTPUT_TOKENS,
    GOOGLE_FINANCE_RESPONSE_SCHEMA,
    GeminiStockInsightBatchGenerator,
    StockAnalysisBatchItem,
    StockBatchMappingError,
    StockBatchResponseError,
    build_batch_analysis_prompt,
    parse_batch_analysis_response,
)
from google_finance.models import StockNewsArticle, StockPrice
from google_finance.movement import MovementDirection
from google_finance.movement_application import MovementUnavailable
from google_finance.watchlist_application import (
    WatchlistAnalysisStatus,
    WatchlistAnalysisUnavailableReason,
)
from llm_runtime.exceptions import LlmDailyQuotaExceededError
from llm_runtime.models import KeyProfile, LlmJob

EARLIER = datetime(2026, 8, 3, 5, tzinfo=timezone.utc)
LATER = datetime(2026, 8, 3, 6, tzinfo=timezone.utc)


def _quote(
    symbol: str,
    price: str,
    collected_at: datetime,
    *,
    name: str | None = None,
) -> StockPrice:
    return StockPrice(
        symbol=symbol,
        name=name or f"Company {symbol}",
        current_price=Decimal(price),
        previous_close=Decimal("100.00"),
        open_price=Decimal("99.00"),
        change_percent=Decimal("2.00"),
        currency="USD",
        collected_at=collected_at,
    )


def _article(symbol: str) -> StockNewsArticle:
    return StockNewsArticle(
        title=f"{symbol} news",
        url=f"https://news.example/{symbol}",
        source="Example News",
        published_at=LATER,
    )


def _item(symbol: str) -> StockAnalysisBatchItem:
    return StockAnalysisBatchItem(
        symbol=symbol,
        company_name=f"Company {symbol}",
        price=Decimal("101.00"),
        currency="USD",
        snapshot_delta=Decimal("1.00"),
        snapshot_change_percent=Decimal("1.00"),
        snapshot_movement=MovementDirection.UP,
        google_finance_change_percent=Decimal("2.00"),
        articles=(_article(symbol),),
    )


def _response(symbols: list[str], summary: str = "뉴스에 근거한 가능한 배경입니다.") -> str:
    return json.dumps(
        {"items": [{"symbol": symbol, "summary": summary} for symbol in symbols]},
        ensure_ascii=False,
    )


class FakeRuntime:
    def __init__(self, text: str = "", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            text=self.text,
            finish_reason=None,
            output_tokens=100,
        )


class FakeStorage:
    def __init__(self, snapshots: dict[str, list[StockPrice]]) -> None:
        self.snapshots = snapshots
        self.calls: list[str] = []

    def get_latest_two(self, symbol: str) -> list[StockPrice]:
        self.calls.append(symbol)
        return self.snapshots.get(symbol, [])


class FakeNewsProvider:
    def __init__(self, articles: dict[str, list[StockNewsArticle]]) -> None:
        self.articles = articles
        self.calls: list[str] = []

    def search(self, company_name: str, limit: int = 5) -> list[StockNewsArticle]:
        self.calls.append(company_name)
        return self.articles.get(company_name, [])[:limit]


class FakeBatchGenerator:
    def __init__(
        self,
        summaries: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.summaries = summaries or {}
        self.error = error
        self.calls: list[list[StockAnalysisBatchItem]] = []

    def generate_summaries(self, items: list[StockAnalysisBatchItem]) -> dict[str, str]:
        self.calls.append(items)
        if self.error is not None:
            raise self.error
        return self.summaries


def test_prompt_distinguishes_snapshot_and_google_finance_changes() -> None:
    prompt = build_batch_analysis_prompt([_item("NVDA:NASDAQ")])

    assert "NVDA:NASDAQ" in prompt
    assert "Snapshot change_percent" in prompt
    assert "Google Finance change_percent" in prompt
    assert "같은 의미로" in prompt
    assert "최근 두 차례 자동 수집 시점 사이에는" in prompt
    assert "오늘 또는 전일 대비" in prompt
    assert "매수" in prompt and "매도" in prompt


def test_batch_generator_calls_runtime_once_with_structured_schema() -> None:
    runtime = FakeRuntime(_response(["NVDA:NASDAQ", "PLTR:NASDAQ"]))
    generator = GeminiStockInsightBatchGenerator(runtime=runtime, profile=KeyProfile.TEST)

    result = generator.generate_summaries([_item("NVDA:NASDAQ"), _item("PLTR:NASDAQ")])

    assert result == {
        "NVDA:NASDAQ": "뉴스에 근거한 가능한 배경입니다.",
        "PLTR:NASDAQ": "뉴스에 근거한 가능한 배경입니다.",
    }
    assert len(runtime.calls) == 1
    call = runtime.calls[0]
    assert call["job"] is LlmJob.GOOGLE_FINANCE
    assert call["max_output_tokens"] == BATCH_MAX_OUTPUT_TOKENS
    response_format = call["response_format"]
    assert response_format.response_mime_type == "application/json"
    assert response_format.response_schema == GOOGLE_FINANCE_RESPONSE_SCHEMA


def test_one_eligible_symbol_still_uses_one_batch_call() -> None:
    runtime = FakeRuntime(_response(["NVDA:NASDAQ"]))
    generator = GeminiStockInsightBatchGenerator(runtime=runtime, profile=KeyProfile.TEST)

    result = generator.generate_summaries([_item("NVDA:NASDAQ")])

    assert result["NVDA:NASDAQ"]
    assert len(runtime.calls) == 1


def test_batch_application_restores_watchlist_order_and_calls_once() -> None:
    symbols = ["PLTR:NASDAQ", "NVDA:NASDAQ", "005930:KRX"]
    storage = FakeStorage(
        {
            "PLTR:NASDAQ": [
                _quote("PLTR:NASDAQ", "101", LATER),
                _quote("PLTR:NASDAQ", "100", EARLIER),
            ],
            "NVDA:NASDAQ": [
                _quote("NVDA:NASDAQ", "101", LATER),
                _quote("NVDA:NASDAQ", "100", EARLIER),
            ],
            "005930:KRX": [_quote("005930:KRX", "101", LATER)],
        }
    )
    news = FakeNewsProvider(
        {
            "Company PLTR:NASDAQ": [_article("PLTR:NASDAQ")],
            "Company NVDA:NASDAQ": [],
        }
    )
    batch = FakeBatchGenerator({"PLTR:NASDAQ": "PLTR 배경입니다."})

    results = analyze_stored_quotes_batch(storage, news, batch, symbols)

    assert [result.symbol for result in results] == symbols
    assert results[0].status is WatchlistAnalysisStatus.SUCCESS
    assert results[0].analysis.summary == "PLTR 배경입니다."
    assert results[1].status is WatchlistAnalysisStatus.SUCCESS
    assert results[2].status is WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE
    assert isinstance(results[2].analysis, MovementUnavailable)
    assert len(batch.calls) == 1
    assert [item.symbol for item in batch.calls[0]] == ["PLTR:NASDAQ"]


def test_no_eligible_symbol_means_no_batch_call() -> None:
    storage = FakeStorage({"NVDA:NASDAQ": [_quote("NVDA:NASDAQ", "101", LATER)]})
    batch = FakeBatchGenerator()

    results = analyze_stored_quotes_batch(
        storage,
        FakeNewsProvider({}),
        batch,
        ["NVDA:NASDAQ"],
    )

    assert len(batch.calls) == 0
    assert results[0].status is WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE


def test_batch_failure_does_not_fallback_to_individual_calls() -> None:
    symbols = ["NVDA:NASDAQ", "PLTR:NASDAQ"]
    storage = FakeStorage(
        {
            symbol: [_quote(symbol, "101", LATER), _quote(symbol, "100", EARLIER)]
            for symbol in symbols
        }
    )
    news = FakeNewsProvider({f"Company {symbol}": [_article(symbol)] for symbol in symbols})
    batch = FakeBatchGenerator(error=RuntimeError("provider unavailable"))

    results = analyze_stored_quotes_batch(storage, news, batch, symbols)

    assert len(batch.calls) == 1
    assert all(result.status is WatchlistAnalysisStatus.FAILED for result in results)


def test_daily_quota_maps_all_batch_items_without_fallback() -> None:
    symbols = ["NVDA:NASDAQ", "PLTR:NASDAQ"]
    storage = FakeStorage(
        {
            symbol: [_quote(symbol, "101", LATER), _quote(symbol, "100", EARLIER)]
            for symbol in symbols
        }
    )
    news = FakeNewsProvider({f"Company {symbol}": [_article(symbol)] for symbol in symbols})
    batch = FakeBatchGenerator(error=LlmDailyQuotaExceededError("daily quota"))

    results = analyze_stored_quotes_batch(storage, news, batch, symbols)

    assert len(batch.calls) == 1
    assert all(result.status is WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE for result in results)
    assert all(
        result.unavailable_reason is WatchlistAnalysisUnavailableReason.DAILY_QUOTA_EXHAUSTED
        for result in results
    )


@pytest.mark.parametrize(
    ("response", "error_type", "message"),
    [
        (
            '{"items": [{"symbol": "UNKNOWN:NASDAQ", "summary": "요약"}]}',
            StockBatchMappingError,
            "unknown_symbol",
        ),
        (
            '{"items": [{"symbol": "NVDA:NASDAQ", "summary": "요약"}, '
            '{"symbol": "NVDA:NASDAQ", "summary": "중복"}]}',
            StockBatchMappingError,
            "duplicate_symbol",
        ),
        ('{"items": []}', StockBatchMappingError, "missing_symbol"),
        (
            '{"items": [{"symbol": "NVDA:NASDAQ", "summary": ""}]}',
            StockBatchResponseError,
            "non_empty",
        ),
    ],
)
def test_parser_rejects_invalid_mapping_and_summary(
    response: str,
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        parse_batch_analysis_response(response, ["NVDA:NASDAQ"])


def test_parser_rejects_summary_over_300_characters() -> None:
    response = json.dumps(
        {"items": [{"symbol": "NVDA:NASDAQ", "summary": "가" * 301}]}
    )

    with pytest.raises(StockBatchResponseError, match="summary_too_long"):
        parse_batch_analysis_response(response, ["NVDA:NASDAQ"])


def test_parser_accepts_one_json_code_fence_and_rejects_text_around_json() -> None:
    response = "```json\n" + _response(["NVDA:NASDAQ"]) + "\n```"
    assert parse_batch_analysis_response(response, ["NVDA:NASDAQ"])["NVDA:NASDAQ"]

    with pytest.raises(StockBatchResponseError, match="malformed_json"):
        parse_batch_analysis_response("설명 {\"items\": []}", ["NVDA:NASDAQ"])


@pytest.mark.parametrize(
    "response",
    [
        '{"items": [{"symbol": "NVDA:NASDAQ", "summary": "요약"}',
        '{"items": [{"symbol": "NVDA:NASDAQ", "summary": "요약}]',
    ],
)
def test_parser_classifies_truncated_json(response: str) -> None:
    with pytest.raises(StockBatchResponseError, match="truncated_json"):
        parse_batch_analysis_response(response, ["NVDA:NASDAQ"])


def test_parser_classifies_max_tokens_without_repairing_json() -> None:
    with pytest.raises(StockBatchResponseError, match="truncated_json"):
        parse_batch_analysis_response(
            '{"items": [',
            ["NVDA:NASDAQ"],
            finish_reason="MAX_TOKENS",
            output_tokens=4096,
        )
