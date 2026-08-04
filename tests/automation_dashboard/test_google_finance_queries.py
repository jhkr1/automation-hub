"""Query contracts for the read-only Google Finance dashboard."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from automation_dashboard.queries.google_finance import (
    list_latest_quotes,
    load_latest_delta,
    load_price_history,
    to_seoul_time,
)
from google_finance.db_models import StockQuoteSnapshot


@pytest.fixture
def session() -> Session:
    """Create an isolated SQLAlchemy table without requiring MySQL."""
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def register_mysql_compatibility_functions(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function("CHAR_LENGTH", 1, len)

    StockQuoteSnapshot.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    active_session = factory()
    try:
        yield active_session
    finally:
        active_session.close()
        engine.dispose()


def _snapshot(
    identifier: int,
    *,
    symbol: str,
    collected_at: datetime,
    current_price: str,
    change_percent: str = "1.00",
) -> StockQuoteSnapshot:
    """Build a deterministic persisted quote row for query tests."""
    return StockQuoteSnapshot(
        id=identifier,
        symbol=symbol,
        name=f"{symbol} Company",
        currency="USD",
        current_price=Decimal(current_price),
        previous_close=Decimal("9.00"),
        open_price=Decimal("9.50"),
        change_percent=Decimal(change_percent),
        collected_at=collected_at,
        created_at=collected_at,
    )


def _save(session: Session, *snapshots: StockQuoteSnapshot) -> None:
    """Persist deterministic snapshot rows for one test."""
    session.add_all(snapshots)
    session.commit()


def test_list_latest_quotes_uses_id_tie_break_and_counts_all_snapshots(session: Session) -> None:
    """One row per symbol uses collected_at DESC then id DESC exactly."""
    same_time = datetime(2026, 8, 1, 1, 0)
    _save(
        session,
        _snapshot(1, symbol="BETA:NASDAQ", collected_at=datetime(2026, 8, 1), current_price="10"),
        _snapshot(2, symbol="ALPHA:NASDAQ", collected_at=same_time, current_price="20"),
        _snapshot(3, symbol="ALPHA:NASDAQ", collected_at=same_time, current_price="21"),
    )

    result = list_latest_quotes(session)

    assert [row.symbol for row in result] == ["ALPHA:NASDAQ", "BETA:NASDAQ"]
    assert result[0].current_price == Decimal("21")
    assert result[0].snapshot_count == 2
    assert result[0].collected_at == datetime(
        2026,
        8,
        1,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Seoul"),
    )


def test_load_price_history_returns_the_newest_limit_in_ascending_order(session: Session) -> None:
    """The latest bounded rows are rendered from oldest to newest for charts."""
    _save(
        session,
        _snapshot(
            1,
            symbol="ALPHA:NASDAQ",
            collected_at=datetime(2026, 8, 1),
            current_price="10",
        ),
        _snapshot(
            2,
            symbol="ALPHA:NASDAQ",
            collected_at=datetime(2026, 8, 1, 1),
            current_price="11",
        ),
        _snapshot(
            3,
            symbol="ALPHA:NASDAQ",
            collected_at=datetime(2026, 8, 1, 2),
            current_price="12",
        ),
    )

    history = load_price_history(session, "alpha:nasdaq", limit=2)

    assert [point.current_price for point in history] == [Decimal("11"), Decimal("12")]
    assert history[0].collected_at < history[1].collected_at


def test_load_latest_delta_uses_the_previous_row_after_id_tie_break(session: Session) -> None:
    """The latest two rows preserve the storage ordering contract."""
    same_time = datetime(2026, 8, 1, 1)
    _save(
        session,
        _snapshot(1, symbol="ALPHA:NASDAQ", collected_at=datetime(2026, 8, 1), current_price="10"),
        _snapshot(2, symbol="ALPHA:NASDAQ", collected_at=same_time, current_price="11"),
        _snapshot(3, symbol="ALPHA:NASDAQ", collected_at=same_time, current_price="13"),
    )

    delta = load_latest_delta(session, "ALPHA:NASDAQ")

    assert delta is not None
    assert delta.latest_price == Decimal("13")
    assert delta.previous_price == Decimal("11")
    assert delta.price_delta == Decimal("2")
    assert delta.absolute_delta == Decimal("2")


def test_queries_return_safe_empty_results_for_zero_or_one_snapshot(session: Session) -> None:
    """Dashboard callers receive empty values instead of snapshot comparison errors."""
    assert list_latest_quotes(session) == []
    assert load_price_history(session, "MISSING:NASDAQ") == []
    assert load_latest_delta(session, "MISSING:NASDAQ") is None

    _save(
        session,
        _snapshot(1, symbol="ALPHA:NASDAQ", collected_at=datetime(2026, 8, 1), current_price="10"),
    )

    assert load_latest_delta(session, "ALPHA:NASDAQ") is None


def test_to_seoul_time_treats_naive_database_datetimes_as_utc() -> None:
    """Naive persisted UTC is never interpreted directly as Korea time."""
    assert to_seoul_time(datetime(2026, 8, 1, 0, 0)) == datetime(
        2026,
        8,
        1,
        9,
        0,
        tzinfo=to_seoul_time(datetime(2026, 8, 1)).tzinfo,
    )
