"""Google Finance analysis application tests."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from google_finance.analysis_application import analyze_stored_quote
from google_finance.analysis_generator import INSUFFICIENT_EVIDENCE_REASON
from google_finance.models import (
    MAX_STOCK_INSIGHT_SUMMARY_LENGTH,
    StockInsight,
    StockNewsArticle,
    StockPrice,
)
from google_finance.movement import MovementDirection, MovementResult
from google_finance.movement_application import MovementUnavailable

EARLIER = datetime(2026, 7, 30, 5, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 30, 6, tzinfo=timezone.utc)


def _quote(price: str, collected_at: datetime, symbol: str = "AAPL:NASDAQ") -> StockPrice:
    return StockPrice(
        symbol=symbol,
        name="Apple Inc",
        current_price=Decimal(price),
        previous_close=Decimal("99.00"),
        open_price=Decimal("99.50"),
        change_percent=Decimal("1.20"),
        currency="USD",
        collected_at=collected_at,
    )


class FakeStorage:
    def __init__(self, snapshots: list[StockPrice] | Exception) -> None:
        self.snapshots = snapshots
        self.symbols: list[str] = []

    def get_latest_two(self, symbol: str) -> list[StockPrice]:
        self.symbols.append(symbol)
        if isinstance(self.snapshots, Exception):
            raise self.snapshots
        return self.snapshots


class FakeNewsProvider:
    def __init__(self, articles: list[StockNewsArticle] | Exception) -> None:
        self.articles = articles
        self.calls: list[tuple[str, int]] = []

    def search(self, company_name: str, limit: int = 5) -> list[StockNewsArticle]:
        self.calls.append((company_name, limit))
        if isinstance(self.articles, Exception):
            raise self.articles
        return self.articles


class FakeGenerator:
    def __init__(self, result: str = "뉴스 근거를 요약했습니다.") -> None:
        self.result = result
        self.calls: list[tuple[StockPrice, MovementResult, list[StockNewsArticle]]] = []

    def generate_summary(
        self,
        stock_price: StockPrice,
        movement: MovementResult,
        articles: list[StockNewsArticle],
    ) -> str:
        self.calls.append((stock_price, movement, articles))
        return self.result


def _article() -> StockNewsArticle:
    return StockNewsArticle(title="Apple news", url="https://news.example/apple")


def test_analyze_stored_quote_connects_storage_movement_news_and_generator() -> None:
    storage = FakeStorage([_quote("101.25", LATER), _quote("100.10", EARLIER)])
    news = FakeNewsProvider([_article()])
    generator = FakeGenerator()

    result = analyze_stored_quote(storage, news, generator, " aapl:nasdaq ")

    assert isinstance(result, StockInsight)
    assert result.movement.direction is MovementDirection.UP
    assert result.movement.price_delta == Decimal("1.15")
    assert result.summary == "뉴스 근거를 요약했습니다."
    assert storage.symbols == ["AAPL:NASDAQ"]
    assert news.calls == [("Apple Inc", 5)]
    assert len(generator.calls) == 1
    assert generator.calls[0][1] is result.movement


@pytest.mark.parametrize("snapshots", [[], [_quote("100.00", LATER)]])
def test_analyze_stored_quote_returns_unavailable_without_news_or_generator(
    snapshots: list[StockPrice],
) -> None:
    news = FakeNewsProvider([])
    generator = FakeGenerator()

    result = analyze_stored_quote(FakeStorage(snapshots), news, generator, "AAPL:NASDAQ")

    assert result == MovementUnavailable(symbol="AAPL:NASDAQ", snapshot_count=len(snapshots))
    assert news.calls == []
    assert generator.calls == []


def test_analyze_stored_quote_skips_generator_when_news_is_empty() -> None:
    storage = FakeStorage([_quote("101.00", LATER), _quote("100.00", EARLIER)])
    news = FakeNewsProvider([])
    generator = FakeGenerator()

    result = analyze_stored_quote(storage, news, generator, "AAPL:NASDAQ")

    assert isinstance(result, StockInsight)
    assert result.summary == INSUFFICIENT_EVIDENCE_REASON
    assert generator.calls == []


def test_stock_insight_is_immutable() -> None:
    storage = FakeStorage([_quote("101.00", LATER), _quote("100.00", EARLIER)])
    result = analyze_stored_quote(storage, FakeNewsProvider([]), FakeGenerator(), "AAPL:NASDAQ")

    assert isinstance(result, StockInsight)
    with pytest.raises(FrozenInstanceError):
        result.summary = "changed"  # type: ignore[misc]


def test_stock_insight_accepts_summary_at_contract_limit() -> None:
    movement = MovementResult(
        direction=MovementDirection.UP,
        symbol="AAPL:NASDAQ",
        latest_price=Decimal("101.00"),
        previous_price=Decimal("100.00"),
        price_delta=Decimal("1.00"),
        latest_collected_at=LATER,
        previous_collected_at=EARLIER,
    )
    result = StockInsight(
        symbol="AAPL:NASDAQ",
        company_name="Apple Inc",
        currency="USD",
        current_price=Decimal("101.00"),
        change_percent=Decimal("1.00"),
        movement=movement,
        summary="가" * MAX_STOCK_INSIGHT_SUMMARY_LENGTH,
        news=(),
    )

    assert len(result.summary) == MAX_STOCK_INSIGHT_SUMMARY_LENGTH


def test_stock_insight_rejects_summary_over_contract_limit() -> None:
    movement = MovementResult(
        direction=MovementDirection.UP,
        symbol="AAPL:NASDAQ",
        latest_price=Decimal("101.00"),
        previous_price=Decimal("100.00"),
        price_delta=Decimal("1.00"),
        latest_collected_at=LATER,
        previous_collected_at=EARLIER,
    )

    with pytest.raises(ValueError, match="400 characters"):
        StockInsight(
            symbol="AAPL:NASDAQ",
            company_name="Apple Inc",
            currency="USD",
            current_price=Decimal("101.00"),
            change_percent=Decimal("1.00"),
            movement=movement,
            summary="가" * (MAX_STOCK_INSIGHT_SUMMARY_LENGTH + 1),
            news=(),
        )


def test_stock_insight_rejects_summary_over_sentence_limit() -> None:
    movement = MovementResult(
        direction=MovementDirection.UP,
        symbol="AAPL:NASDAQ",
        latest_price=Decimal("101.00"),
        previous_price=Decimal("100.00"),
        price_delta=Decimal("1.00"),
        latest_collected_at=LATER,
        previous_collected_at=EARLIER,
    )

    with pytest.raises(ValueError, match="2 sentences"):
        StockInsight(
            symbol="AAPL:NASDAQ",
            company_name="Apple Inc",
            currency="USD",
            current_price=Decimal("101.00"),
            change_percent=Decimal("1.00"),
            movement=movement,
            summary="첫 문장. 둘째 문장. 셋째 문장.",
            news=(),
        )


def test_analyze_stored_quote_propagates_storage_and_news_errors() -> None:
    storage_error = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError) as raised:
        analyze_stored_quote(
            FakeStorage(storage_error), FakeNewsProvider([]), FakeGenerator(), "AAPL:NASDAQ"
        )
    assert raised.value is storage_error

    news_error = RuntimeError("news unavailable")
    storage = FakeStorage([_quote("101.00", LATER), _quote("100.00", EARLIER)])
    with pytest.raises(RuntimeError) as raised:
        analyze_stored_quote(
            storage, FakeNewsProvider(news_error), FakeGenerator(), "AAPL:NASDAQ"
        )
    assert raised.value is news_error
