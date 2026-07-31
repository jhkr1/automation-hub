"""Application tests for stored Google Finance snapshot movement lookup."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from google_finance.models import StockPrice
from google_finance.movement import MovementDetectionError, MovementDirection, MovementResult
from google_finance.movement_application import MovementUnavailable, lookup_movement

EARLIER = datetime(2026, 7, 31, 1, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)


def _stock_price(
    *,
    current_price: str,
    symbol: str = "AAPL:NASDAQ",
    collected_at: datetime = LATER,
) -> StockPrice:
    """Create a validated quote for application tests."""
    return StockPrice(
        symbol=symbol,
        name="Apple Inc",
        current_price=Decimal(current_price),
        previous_close=Decimal("99.00"),
        open_price=Decimal("99.50"),
        change_percent=Decimal("0.00"),
        currency="USD",
        collected_at=collected_at,
    )


class FakeStorage:
    """Minimal storage fake for the application boundary."""

    def __init__(self, snapshots: list[StockPrice] | Exception) -> None:
        self.snapshots = snapshots
        self.symbols: list[str] = []

    def get_latest_two(self, symbol: str) -> list[StockPrice]:
        """Record the canonical symbol and return snapshots or raise."""
        self.symbols.append(symbol)
        if isinstance(self.snapshots, Exception):
            raise self.snapshots
        return self.snapshots


def test_lookup_movement_passes_newest_then_previous_to_domain() -> None:
    latest = _stock_price(current_price="101.00")
    previous = _stock_price(current_price="100.00", collected_at=EARLIER)
    storage = FakeStorage([latest, previous])

    result = lookup_movement(storage, " aapl:nasdaq ")

    assert isinstance(result, MovementResult)
    assert result.direction is MovementDirection.UP
    assert result.price_delta == Decimal("1.00")
    assert storage.symbols == ["AAPL:NASDAQ"]


@pytest.mark.parametrize("snapshots", [[], [_stock_price(current_price="100.00")]])
def test_lookup_movement_returns_unavailable_for_fewer_than_two_snapshots(
    snapshots: list[StockPrice],
) -> None:
    storage = FakeStorage(snapshots)

    result = lookup_movement(storage, "AAPL:NASDAQ")

    assert result == MovementUnavailable(symbol="AAPL:NASDAQ", snapshot_count=len(snapshots))


def test_lookup_movement_does_not_hide_storage_error() -> None:
    expected = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError) as raised:
        lookup_movement(FakeStorage(expected), "AAPL:NASDAQ")

    assert raised.value is expected


def test_lookup_movement_does_not_hide_domain_contract_error() -> None:
    latest = _stock_price(current_price="101.00", symbol="AAPL:NASDAQ")
    previous = _stock_price(
        current_price="100.00",
        symbol="MSFT:NASDAQ",
        collected_at=EARLIER,
    )

    with pytest.raises(MovementDetectionError):
        lookup_movement(FakeStorage([latest, previous]), "AAPL:NASDAQ")


def test_lookup_movement_preserves_other_symbol_validation() -> None:
    latest = _stock_price(current_price="101.00", symbol="AAPL:NASDAQ")
    previous = _stock_price(
        current_price="100.00",
        symbol="OTHER:NASDAQ",
        collected_at=EARLIER,
    )

    with pytest.raises(MovementDetectionError, match="symbols must match"):
        lookup_movement(FakeStorage([latest, previous]), "AAPL:NASDAQ")
