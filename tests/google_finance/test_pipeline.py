"""Google Finance pipeline tests."""

from datetime import datetime
from decimal import Decimal

import pytest

from google_finance.collector import RawStockQuote
from google_finance.models import StockPrice
from google_finance.pipeline import StockPricePipeline


def _raw_quote() -> RawStockQuote:
    """Create a pipeline fixture."""
    return RawStockQuote(
        symbol="AAPL:NASDAQ",
        name_text="Apple Inc",
        current_price_text="$338.19",
        currency_text="Closed · USD",
        previous_close_text="Prev. close $340.08",
        open_price_text="Open\n$339.73",
        change_percent_text="-0.56%",
    )


def test_pipeline_passes_symbol_and_returns_stock_price() -> None:
    """Pipeline calls the fake collector once and maps its raw result."""
    calls: list[str] = []

    def collect(symbol: str) -> RawStockQuote:
        calls.append(symbol)
        return _raw_quote()

    result = StockPricePipeline(collect).run("AAPL:NASDAQ")

    assert calls == ["AAPL:NASDAQ"]
    assert isinstance(result, StockPrice)
    assert result.currency == "USD"
    assert result.current_price == Decimal("338.19")
    assert result.collected_at.tzinfo is not None


def test_pipeline_propagates_collector_failure() -> None:
    """Pipeline does not hide provider failures."""
    expected = RuntimeError("collector failure")

    def collect(symbol: str) -> RawStockQuote:
        raise expected

    with pytest.raises(RuntimeError) as raised:
        StockPricePipeline(collect).run("AAPL:NASDAQ")

    assert raised.value is expected


def test_stock_price_rejects_empty_currency_and_naive_time() -> None:
    """The model preserves currency and timestamp invariants."""
    with pytest.raises(ValueError):
        StockPrice(
            symbol="AAPL:NASDAQ",
            name="Apple Inc",
            current_price=Decimal("1.0"),
            previous_close=Decimal("1.0"),
            open_price=Decimal("1.0"),
            change_percent=Decimal("0.0"),
            currency="",
        )

    with pytest.raises(ValueError):
        StockPrice(
            symbol="AAPL:NASDAQ",
            name="Apple Inc",
            current_price=Decimal("1.0"),
            previous_close=Decimal("1.0"),
            open_price=Decimal("1.0"),
            change_percent=Decimal("0.0"),
            currency="USD",
            collected_at=datetime(2026, 7, 30, 6, 0),
        )
