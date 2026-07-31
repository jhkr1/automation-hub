"""Optional MySQL integration tests for Google Finance snapshots."""

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="set RUN_DB_INTEGRATION=1 to run against MySQL",
)


def test_google_finance_snapshot_schema_and_round_trip() -> None:
    """Verify the migrated table, append behavior, and latest-two query contract."""
    from sqlalchemy import delete, inspect

    from database.engine import engine
    from database.session import SessionLocal
    from google_finance.db_models import StockQuoteSnapshot
    from google_finance.models import StockPrice
    from google_finance.movement import MovementDirection
    from google_finance.movement_application import MovementUnavailable, lookup_movement
    from google_finance.storage import StockQuoteStorage

    symbol = "INTEGRATION:TEST"
    single_symbol = "INTEGRATION:SINGLE"
    same_timestamp_symbol = "INTEGRATION:SAME-TIME"
    inspector = inspect(engine)
    assert "stock_quote_snapshots" in inspector.get_table_names()
    assert "ix_stock_quote_snapshots_symbol_collected_at" in {
        index["name"] for index in inspector.get_indexes("stock_quote_snapshots")
    }

    def quote(hour: int, *, quote_symbol: str = symbol, price: str = "10.00000001") -> StockPrice:
        return StockPrice(
            symbol=quote_symbol,
            name="Integration Test",
            current_price=Decimal(price),
            previous_close=Decimal("9.00000001"),
            open_price=Decimal("9.50000001"),
            change_percent=Decimal("11.11111111"),
            currency="USD",
            collected_at=datetime(2099, 1, 1, hour, tzinfo=timezone.utc),
        )

    try:
        storage = StockQuoteStorage()
        storage.save(quote(1, quote_symbol=symbol.lower(), price="10.00000001"))
        storage.save(quote(2, price="11.00000001"))
        storage.save(quote(2, price="12.00000001"))
        storage.save(quote(3, price="13.00000001"))
        storage.save(quote(4, quote_symbol="OTHER:TEST", price="99.00000001"))
        storage.save(quote(5, quote_symbol=single_symbol, price="7.00000001"))
        storage.save(quote(6, quote_symbol=same_timestamp_symbol, price="20.00000001"))
        storage.save(quote(6, quote_symbol=same_timestamp_symbol, price="21.00000001"))

        latest = storage.get_latest("integration:test")
        assert latest is not None
        assert latest.current_price == Decimal("13.00000001")

        latest_two = storage.get_latest_two(symbol)
        assert [item.collected_at.hour for item in latest_two] == [3, 2]
        assert [item.current_price for item in latest_two] == [
            Decimal("13.00000001"),
            Decimal("12.00000001"),
        ]
        movement = lookup_movement(storage, "integration:test")
        assert movement.direction is MovementDirection.UP
        assert movement.price_delta == Decimal("1.00000000")

        same_timestamp = storage.get_latest_two(same_timestamp_symbol)
        assert [item.current_price for item in same_timestamp] == [
            Decimal("21.00000001"),
            Decimal("20.00000001"),
        ]
        same_timestamp_movement = lookup_movement(storage, same_timestamp_symbol)
        assert same_timestamp_movement.direction is MovementDirection.UP
        assert same_timestamp_movement.price_delta == Decimal("1.00000000")

        assert len(storage.get_latest_two(single_symbol)) == 1
        assert lookup_movement(storage, single_symbol) == MovementUnavailable(
            symbol=single_symbol,
            snapshot_count=1,
        )
        assert storage.get_latest("MISSING:TEST") is None
        assert lookup_movement(storage, "MISSING:TEST") == MovementUnavailable(
            symbol="MISSING:TEST",
            snapshot_count=0,
        )
    finally:
        with SessionLocal.begin() as session:
            session.execute(
                delete(StockQuoteSnapshot).where(
                    StockQuoteSnapshot.symbol.in_(
                        [symbol, "OTHER:TEST", single_symbol, same_timestamp_symbol]
                    )
                )
            )
