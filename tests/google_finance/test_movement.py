"""Pure Google Finance snapshot movement tests."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from google_finance.models import StockPrice
from google_finance.movement import (
    MovementDetectionError,
    MovementDirection,
    MovementResult,
    detect_movement,
)

EARLIER = datetime(2026, 7, 31, 1, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)


def _stock_price(
    *,
    current_price: str = "100.00",
    symbol: str = "AAPL:NASDAQ",
    collected_at: datetime = LATER,
) -> StockPrice:
    """Create a validated quote for movement tests."""
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


def test_detect_movement_returns_up_and_exact_delta() -> None:
    result = detect_movement(
        _stock_price(current_price="100.30"),
        _stock_price(current_price="100.20", collected_at=EARLIER),
    )

    assert result == MovementResult(
        direction=MovementDirection.UP,
        symbol="AAPL:NASDAQ",
        latest_price=Decimal("100.30"),
        previous_price=Decimal("100.20"),
        price_delta=Decimal("0.10"),
        latest_collected_at=LATER,
        previous_collected_at=EARLIER,
    )


def test_detect_movement_returns_down() -> None:
    result = detect_movement(
        _stock_price(current_price="99.90"),
        _stock_price(current_price="100.00", collected_at=EARLIER),
    )

    assert result.direction is MovementDirection.DOWN
    assert result.price_delta == Decimal("-0.10")


def test_detect_movement_returns_unchanged_for_equal_prices() -> None:
    result = detect_movement(
        _stock_price(current_price="100.00"),
        _stock_price(current_price="100.00", collected_at=EARLIER),
    )

    assert result.direction is MovementDirection.UNCHANGED
    assert result.price_delta == Decimal("0.00")


def test_detect_movement_preserves_decimal_precision() -> None:
    result = detect_movement(
        _stock_price(current_price="100.00000001"),
        _stock_price(current_price="100.00000000", collected_at=EARLIER),
    )

    assert result.price_delta == Decimal("0.00000001")
    assert isinstance(result.price_delta, Decimal)


def test_detect_movement_rejects_different_symbols() -> None:
    with pytest.raises(MovementDetectionError, match="symbols must match"):
        detect_movement(
            _stock_price(symbol="AAPL:NASDAQ"),
            _stock_price(symbol="MSFT:NASDAQ", collected_at=EARLIER),
        )


def test_detect_movement_rejects_latest_before_previous() -> None:
    with pytest.raises(MovementDetectionError, match="must not be earlier"):
        detect_movement(
            _stock_price(collected_at=EARLIER),
            _stock_price(collected_at=LATER),
        )


def test_detect_movement_allows_equal_collected_at() -> None:
    timestamp = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)

    result = detect_movement(
        _stock_price(current_price="101.00", collected_at=timestamp),
        _stock_price(current_price="100.00", collected_at=timestamp),
    )

    assert result.direction is MovementDirection.UP
    assert result.latest_collected_at == timestamp
    assert result.previous_collected_at == timestamp


def test_detect_movement_does_not_mutate_input_models() -> None:
    latest = _stock_price(current_price="101.00")
    previous = _stock_price(current_price="100.00", collected_at=EARLIER)
    latest_before = replace(latest)
    previous_before = replace(previous)

    detect_movement(latest, previous)

    assert latest == latest_before
    assert previous == previous_before
