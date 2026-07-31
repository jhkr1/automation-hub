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
    from google_finance.storage import StockQuoteStorage

    symbol = "INTEGRATION:TEST"
    single_symbol = "INTEGRATION:SINGLE"
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

        latest = storage.get_latest("integration:test")
        assert latest is not None
        assert latest.current_price == Decimal("13.00000001")

        latest_two = storage.get_latest_two(symbol)
        assert [item.collected_at.hour for item in latest_two] == [3, 2]
        assert [item.current_price for item in latest_two] == [
            Decimal("13.00000001"),
            Decimal("12.00000001"),
        ]
        assert len(storage.get_latest_two(single_symbol)) == 1
        assert storage.get_latest("MISSING:TEST") is None
    finally:
        with SessionLocal.begin() as session:
            session.execute(
                delete(StockQuoteSnapshot).where(
                    StockQuoteSnapshot.symbol.in_([symbol, "OTHER:TEST", single_symbol])
                )
            )
