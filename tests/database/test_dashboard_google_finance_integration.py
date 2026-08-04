"""Optional MySQL integration tests for Dashboard Google Finance queries."""

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="set RUN_DB_INTEGRATION=1 to run against MySQL",
)


def test_dashboard_google_finance_queries_use_persisted_snapshot_ordering() -> None:
    """Validate latest, history, and delta contracts on the migrated MySQL table."""
    from sqlalchemy import delete

    from automation_dashboard.queries.google_finance import (
        list_latest_quotes,
        load_latest_delta,
        load_price_history,
    )
    from database.session import SessionLocal
    from google_finance.db_models import StockQuoteSnapshot
    from google_finance.models import StockPrice
    from google_finance.storage import StockQuoteStorage

    symbol = "DASHBOARD:INTEGRATION"

    def quote(hour: int, price: str) -> StockPrice:
        return StockPrice(
            symbol=symbol,
            name="Dashboard Integration",
            current_price=Decimal(price),
            previous_close=Decimal("9.00"),
            open_price=Decimal("9.50"),
            change_percent=Decimal("1.00"),
            currency="USD",
            collected_at=datetime(2099, 1, 1, hour, tzinfo=timezone.utc),
        )

    try:
        storage = StockQuoteStorage()
        storage.save(quote(1, "10.00"))
        storage.save(quote(2, "11.00"))
        storage.save(quote(2, "12.00"))

        with SessionLocal() as session:
            latest = [row for row in list_latest_quotes(session) if row.symbol == symbol]
            history = load_price_history(session, symbol)
            delta = load_latest_delta(session, symbol)

        assert len(latest) == 1
        assert latest[0].current_price == Decimal("12.00000000")
        assert latest[0].snapshot_count == 3
        assert [point.current_price for point in history] == [
            Decimal("10.00000000"),
            Decimal("11.00000000"),
            Decimal("12.00000000"),
        ]
        assert delta is not None
        assert delta.price_delta == Decimal("1.00000000")
    finally:
        with SessionLocal.begin() as session:
            session.execute(delete(StockQuoteSnapshot).where(StockQuoteSnapshot.symbol == symbol))
