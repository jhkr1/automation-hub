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


def test_main_does_not_save_to_db_by_default(monkeypatch) -> None:
    """The existing command remains a collector-only execution by default."""
    monkeypatch.setattr("google_finance.main.Settings", FakeSettings)
    monkeypatch.setattr(
        "google_finance.main.build_pipeline",
        lambda settings: FakePipeline(_stock_price()),
    )

    class UnexpectedStorage:
        def __init__(self) -> None:
            raise AssertionError("storage must not be constructed")

    monkeypatch.setattr("google_finance.storage.StockQuoteStorage", UnexpectedStorage)

    assert main(["AAPL:NASDAQ"]) == 0


def test_main_save_db_calls_storage_after_stdout(monkeypatch, capsys) -> None:
    """The explicit option saves the collected domain snapshot."""
    monkeypatch.setattr("google_finance.main.Settings", FakeSettings)
    monkeypatch.setattr(
        "google_finance.main.build_pipeline",
        lambda settings: FakePipeline(_stock_price()),
    )
    saved: list[StockPrice] = []

    class FakeStorage:
        def save(self, stock_price: StockPrice) -> None:
            saved.append(stock_price)

    monkeypatch.setattr("google_finance.storage.StockQuoteStorage", FakeStorage)

    assert main(["AAPL:NASDAQ", "--save-db"]) == 0
    assert saved == [_stock_price()]
    assert "Current price: 338.19 USD" in capsys.readouterr().out


def test_main_save_db_returns_one_when_storage_fails(monkeypatch, capsys) -> None:
    """A database failure is visible on stderr and returns a non-zero code."""
    monkeypatch.setattr("google_finance.main.Settings", FakeSettings)
    monkeypatch.setattr(
        "google_finance.main.build_pipeline",
        lambda settings: FakePipeline(_stock_price()),
    )

    class FailingStorage:
        def save(self, stock_price: StockPrice) -> None:
            raise RuntimeError("database unavailable")

    monkeypatch.setattr("google_finance.storage.StockQuoteStorage", FailingStorage)

    assert main(["AAPL:NASDAQ", "--save-db"]) == 1
    assert "database unavailable" in capsys.readouterr().err
