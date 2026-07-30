"""Google Finance CLI tests."""

from datetime import datetime, timezone
from decimal import Decimal

from google_finance.collector import RawStockQuote
from google_finance.main import main
from google_finance.models import StockPrice


def _raw_quote() -> RawStockQuote:
    """Create a CLI fixture."""
    return RawStockQuote(
        symbol="AAPL:NASDAQ",
        name_text="Apple Inc",
        current_price_text="$338.19",
        currency_text="Closed · USD",
        previous_close_text="Prev. close $340.08",
        open_price_text="Open\n$339.73",
        change_percent_text="-0.56%",
    )


def _stock_price() -> StockPrice:
    """Create a parsed CLI fixture."""
    return StockPrice(
        symbol="AAPL:NASDAQ",
        name="Apple Inc",
        current_price=Decimal("338.19"),
        previous_close=Decimal("340.08"),
        open_price=Decimal("339.73"),
        change_percent=Decimal("-0.56"),
        currency="USD",
        collected_at=datetime(2026, 7, 30, 6, 0, tzinfo=timezone.utc),
    )


class FakeSettings:
    """Minimal Settings replacement for CLI tests."""

    google_finance_locale = "en-US"


class FakePipeline:
    """Minimal pipeline replacement for CLI tests."""

    def __init__(self, result: StockPrice | Exception) -> None:
        self.result = result

    def run(self, symbol: str) -> StockPrice:
        """Return a quote or propagate the configured failure."""
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_main_prints_quote_and_returns_zero(monkeypatch, capsys) -> None:
    """Successful CLI execution prints currency and an ISO timestamp."""
    monkeypatch.setattr("google_finance.main.Settings", FakeSettings)
    monkeypatch.setattr(
        "google_finance.main.build_pipeline",
        lambda settings: FakePipeline(_stock_price()),
    )

    assert main(["AAPL:NASDAQ"]) == 0
    output = capsys.readouterr().out
    assert "Symbol: AAPL:NASDAQ" in output
    assert "Current price: 338.19 USD" in output
    assert "Change: -0.56%" in output
    assert "Collected at: 2026-07-30T06:00:00+00:00" in output


def test_main_returns_one_for_collection_failure(monkeypatch, capsys) -> None:
    """CLI failures produce a concise error and non-zero exit code."""
    monkeypatch.setattr("google_finance.main.Settings", FakeSettings)
    monkeypatch.setattr(
        "google_finance.main.build_pipeline",
        lambda settings: FakePipeline(RuntimeError("quote unavailable")),
    )

    assert main(["AAPL:NASDAQ"]) == 1
    assert "실행 실패" in capsys.readouterr().err
