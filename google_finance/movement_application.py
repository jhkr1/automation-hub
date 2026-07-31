"""Application flow for comparing stored Google Finance snapshots."""

from dataclasses import dataclass

from google_finance.collector import validate_symbol
from google_finance.movement import MovementResult, detect_movement
from google_finance.storage import StockQuoteStorage


@dataclass(frozen=True)
class MovementUnavailable:
    """A normal application result when fewer than two snapshots exist."""

    symbol: str
    snapshot_count: int


def lookup_movement(
    storage: StockQuoteStorage,
    symbol: str,
) -> MovementResult | MovementUnavailable:
    """Look up two stored snapshots and compare them when possible."""
    normalized_symbol = validate_symbol(symbol)
    snapshots = storage.get_latest_two(normalized_symbol)
    if len(snapshots) < 2:
        return MovementUnavailable(
            symbol=normalized_symbol,
            snapshot_count=len(snapshots),
        )

    return detect_movement(latest=snapshots[0], previous=snapshots[1])
