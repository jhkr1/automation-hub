"""Google Finance snapshot model and storage contract tests."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from google_finance.db_models import StockQuoteSnapshot
from google_finance.models import StockPrice
from google_finance.storage import StockQuoteStorage


def _stock_price(*, collected_at: datetime) -> StockPrice:
    """Create a precise quote fixture."""
    return StockPrice(
        symbol="AAPL:NASDAQ",
        name="Apple Inc",
        current_price=Decimal("338.19000001"),
        previous_close=Decimal("340.08000001"),
        open_price=Decimal("339.73000001"),
        change_percent=Decimal("-0.55555555"),
        currency="USD",
        collected_at=collected_at,
    )


class FakeSession:
    """Minimal session fake for storage transaction and query boundaries."""

    def __init__(self, rows: list[StockQuoteSnapshot] | None = None) -> None:
        self.added: list[StockQuoteSnapshot] = []
        self.rows = rows or []

    def add(self, row: StockQuoteSnapshot) -> None:
        self.added.append(row)

    def scalars(self, statement: object) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.rows)

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None


class FakeTransaction:
    """Transaction fake that records commit and rollback behavior."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeSession:
        return self.session

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True


class FakeSessionFactory:
    """Session factory fake supporting both storage operations."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.transaction = FakeTransaction(session)

    def begin(self) -> FakeTransaction:
        return self.transaction

    def __call__(self) -> FakeSession:
        return self.session


def test_snapshot_conversion_preserves_decimal_and_utc() -> None:
    """ORM conversion preserves precision and restores an aware UTC timestamp."""
    collected_at = datetime(2026, 7, 31, 1, 2, 3, 456789, tzinfo=timezone.utc)

    row = StockQuoteSnapshot.from_domain(_stock_price(collected_at=collected_at))
    restored = row.to_domain()

    assert row.collected_at == collected_at.replace(tzinfo=None)
    assert restored.collected_at == collected_at
    assert restored.current_price == Decimal("338.19000001")
    assert restored.change_percent == Decimal("-0.55555555")


def test_storage_save_uses_one_transaction_and_converts_row() -> None:
    """Saving appends one ORM row and commits through the existing transaction API."""
    session = FakeSession()
    factory = FakeSessionFactory(session)
    storage = StockQuoteStorage(factory)

    storage.save(_stock_price(collected_at=datetime(2026, 7, 31, 1, tzinfo=timezone.utc)))

    assert len(session.added) == 1
    assert session.added[0].symbol == "AAPL:NASDAQ"
    assert session.added[0].current_price == Decimal("338.19000001")
    assert factory.transaction.committed is True
    assert factory.transaction.rolled_back is False


def test_storage_canonicalizes_symbol_on_save_and_query() -> None:
    """Storage uses strip-uppercase for both persisted and queried symbols."""
    session = FakeSession()
    factory = FakeSessionFactory(session)
    storage = StockQuoteStorage(factory)

    storage.save(
        replace(
            _stock_price(collected_at=datetime(2026, 7, 31, 1, tzinfo=timezone.utc)),
            symbol=" aapl:nasdaq ",
        )
    )

    assert session.added[0].symbol == "AAPL:NASDAQ"


def test_storage_get_latest_returns_newest_domain_snapshot() -> None:
    """The latest query maps the selected ORM row back to StockPrice."""
    row = StockQuoteSnapshot.from_domain(
        _stock_price(collected_at=datetime(2026, 7, 31, 1, tzinfo=timezone.utc))
    )
    result = StockQuoteStorage(FakeSessionFactory(FakeSession([row]))).get_latest("aapl:nasdaq")

    assert result is not None
    assert result.symbol == "AAPL:NASDAQ"
    assert result.collected_at.tzinfo == timezone.utc


def test_storage_get_latest_two_preserves_newest_first_contract() -> None:
    """The two-row query returns the storage contract order unchanged."""
    rows = [
        StockQuoteSnapshot.from_domain(
            _stock_price(collected_at=datetime(2026, 7, 31, 2, tzinfo=timezone.utc))
        ),
        StockQuoteSnapshot.from_domain(
            _stock_price(collected_at=datetime(2026, 7, 31, 1, tzinfo=timezone.utc))
        ),
    ]

    result = StockQuoteStorage(FakeSessionFactory(FakeSession(rows))).get_latest_two(
        "AAPL:NASDAQ"
    )

    assert [item.collected_at.hour for item in result] == [2, 1]


def test_storage_returns_none_for_missing_latest() -> None:
    """No row for a symbol maps to None."""
    assert StockQuoteStorage(FakeSessionFactory(FakeSession())).get_latest("AAPL:NASDAQ") is None


@pytest.mark.parametrize("symbol", ["", "   "])
def test_storage_rejects_empty_query_symbol(symbol: str) -> None:
    """A query without a symbol cannot accidentally return another symbol."""
    with pytest.raises(ValueError, match="symbol"):
        StockQuoteStorage(FakeSessionFactory(FakeSession())).get_latest(symbol)


def test_snapshot_rejects_decimal_scale_that_database_would_round() -> None:
    """Values beyond DECIMAL scale eight are rejected before persistence."""
    with pytest.raises(ValueError, match="8 decimal places"):
        StockQuoteSnapshot.from_domain(
            replace(
                _stock_price(collected_at=datetime(2026, 7, 31, 1, tzinfo=timezone.utc)),
                current_price=Decimal("338.190000001"),
            )
        )
