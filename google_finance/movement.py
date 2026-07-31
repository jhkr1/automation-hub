"""Pure movement detection for two validated Google Finance snapshots."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from google_finance.models import StockPrice


class MovementDetectionError(ValueError):
    """Raised when snapshots violate the movement comparison contract."""


class MovementDirection(str, Enum):
    """Price direction between the previous and latest snapshot."""

    UP = "UP"
    DOWN = "DOWN"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True)
class MovementResult:
    """Immutable price movement calculated from two snapshots."""

    direction: MovementDirection
    symbol: str
    latest_price: Decimal
    previous_price: Decimal
    price_delta: Decimal
    latest_collected_at: datetime
    previous_collected_at: datetime


def detect_movement(latest: StockPrice, previous: StockPrice) -> MovementResult:
    """Compare two ordered snapshots without applying a threshold."""
    if not isinstance(latest, StockPrice):
        raise TypeError("latest must be a StockPrice")
    if not isinstance(previous, StockPrice):
        raise TypeError("previous must be a StockPrice")
    if latest.symbol != previous.symbol:
        raise MovementDetectionError("latest and previous symbols must match")
    if latest.collected_at < previous.collected_at:
        raise MovementDetectionError("latest collected_at must not be earlier than previous")

    price_delta = latest.current_price - previous.current_price
    if price_delta > 0:
        direction = MovementDirection.UP
    elif price_delta < 0:
        direction = MovementDirection.DOWN
    else:
        direction = MovementDirection.UNCHANGED

    return MovementResult(
        direction=direction,
        symbol=latest.symbol,
        latest_price=latest.current_price,
        previous_price=previous.current_price,
        price_delta=price_delta,
        latest_collected_at=latest.collected_at,
        previous_collected_at=previous.collected_at,
    )
