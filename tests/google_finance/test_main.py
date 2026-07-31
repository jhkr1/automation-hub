"""Google Finance CLI tests."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from google_finance.collector import RawStockQuote
from google_finance.main import main
from google_finance.models import StockPrice
from google_finance.movement import MovementDetectionError, MovementDirection, MovementResult
from google_finance.movement_application import MovementUnavailable


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


def _movement_result() -> MovementResult:
    """Create a deterministic movement result for CLI tests."""
    return MovementResult(
        direction=MovementDirection.UP,
        symbol="AAPL:NASDAQ",
        latest_price=Decimal("101.25"),
        previous_price=Decimal("100.10"),
        price_delta=Decimal("1.15"),
        latest_collected_at=datetime(2026, 7, 30, 7, 0, tzinfo=timezone.utc),
        previous_collected_at=datetime(2026, 7, 30, 6, 0, tzinfo=timezone.utc),
    )


class FakeMovementStorage:
    """Minimal storage replacement for movement CLI tests."""


def test_main_show_movement_prints_result_without_collecting(monkeypatch, capsys) -> None:
    """Movement mode reads the application result and skips quote collection."""
    import google_finance.movement_application as movement_application

    monkeypatch.setattr(
        "google_finance.main.build_pipeline",
        lambda settings: (_ for _ in ()).throw(AssertionError("quote collection is not allowed")),
    )
    monkeypatch.setattr(
        movement_application,
        "StockQuoteStorage",
        lambda: FakeMovementStorage(),
    )
    monkeypatch.setattr(
        movement_application,
        "lookup_movement",
        lambda storage, symbol: _movement_result(),
    )

    assert main(["AAPL:NASDAQ", "--show-movement"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Symbol: AAPL:NASDAQ" in captured.out
    assert "Movement: UP" in captured.out
    assert "Previous price: 100.10" in captured.out
    assert "Latest price: 101.25" in captured.out
    assert "Price delta: +1.15" in captured.out
    assert "Previous collected at: 2026-07-30T06:00:00+00:00" in captured.out
    assert "Latest collected at: 2026-07-30T07:00:00+00:00" in captured.out


@pytest.mark.parametrize(
    ("snapshot_count", "expected_message"),
    [
        (0, "0 snapshots found; at least 2 are required."),
        (1, "1 snapshot found; at least 2 are required."),
    ],
)
def test_main_show_movement_prints_unavailable_and_returns_zero(
    monkeypatch,
    capsys,
    snapshot_count: int,
    expected_message: str,
) -> None:
    """Missing comparison history is a normal stdout result."""
    import google_finance.movement_application as movement_application

    monkeypatch.setattr(movement_application, "StockQuoteStorage", lambda: FakeMovementStorage())
    monkeypatch.setattr(
        movement_application,
        "lookup_movement",
        lambda storage, symbol: MovementUnavailable(
            symbol="AAPL:NASDAQ",
            snapshot_count=snapshot_count,
        ),
    )

    assert main(["AAPL:NASDAQ", "--show-movement"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert expected_message in captured.out


@pytest.mark.parametrize(
    "error",
    [RuntimeError("database unavailable"), MovementDetectionError("bad snapshots")],
)
def test_main_show_movement_reports_errors_on_stderr(monkeypatch, capsys, error: Exception) -> None:
    """Database and movement contract errors return non-zero without a traceback."""
    import google_finance.movement_application as movement_application

    monkeypatch.setattr(movement_application, "StockQuoteStorage", lambda: FakeMovementStorage())
    monkeypatch.setattr(
        movement_application,
        "lookup_movement",
        lambda storage, symbol: (_ for _ in ()).throw(error),
    )

    assert main(["AAPL:NASDAQ", "--show-movement"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "실행 실패" in captured.err
    assert "Traceback" not in captured.err


def test_main_rejects_save_db_and_show_movement_together(capsys) -> None:
    """Collection and stored movement modes are mutually exclusive."""
    with pytest.raises(SystemExit) as raised:
        main(["AAPL:NASDAQ", "--save-db", "--show-movement"])

    assert raised.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err
