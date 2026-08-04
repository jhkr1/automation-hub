"""Unit contracts for read-only operations dashboard queries."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from automation_dashboard.queries.operations import (
    load_alembic_status,
    load_database_summary,
    load_log_summary,
    load_runtime_info,
    load_snapshot_summary,
)
from database.models import TrendSnapshot
from google_finance.db_models import StockQuoteSnapshot


@pytest.fixture
def session() -> Session:
    """Create isolated dashboard tables without requiring MySQL."""
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def register_mysql_compatibility_functions(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function("CHAR_LENGTH", 1, len)

    TrendSnapshot.__table__.create(engine)
    StockQuoteSnapshot.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as database_session:
        yield database_session
    engine.dispose()


def _trend(identifier: int, collected_at: datetime, rank: int, keyword: str) -> TrendSnapshot:
    """Create a deterministic Namuwiki snapshot row for read-query tests."""
    row = TrendSnapshot(collected_at=collected_at, rank_position=rank, keyword=keyword)
    row.id = identifier
    return row


def _quote(identifier: int, collected_at: datetime, symbol: str) -> StockQuoteSnapshot:
    """Create a deterministic Google Finance snapshot row for read-query tests."""
    return StockQuoteSnapshot(
        id=identifier,
        symbol=symbol,
        name=symbol,
        currency="USD",
        current_price=Decimal("100"),
        previous_close=Decimal("99"),
        open_price=Decimal("98"),
        change_percent=Decimal("1"),
        collected_at=collected_at.replace(tzinfo=None),
        created_at=collected_at.replace(tzinfo=None),
    )


def test_empty_snapshot_summary_and_database_status_are_safe(session: Session) -> None:
    """No persisted data produces zero counts and a read-only connection signal."""
    summary = load_snapshot_summary(session, today=date(2025, 1, 1))
    database = load_database_summary(session)

    assert summary.google_snapshot_count == 0
    assert summary.namuwiki_snapshot_count == 0
    assert summary.latest_google_collected_at is None
    assert summary.latest_namuwiki_collected_at is None
    assert database.status == "Connected"
    assert database.size_bytes is None


def test_snapshot_summary_counts_rows_and_reports_latest_activity_in_kst(session: Session) -> None:
    """Storage totals and latest rows are deterministic across both snapshot tables."""
    older = datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc)
    latest = datetime(2025, 1, 1, 16, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            _quote(1, older, "NVDA:NASDAQ"),
            _quote(2, latest, "PLTR:NASDAQ"),
            _trend(1, older, 2, "Python"),
            _trend(2, latest, 1, "Database"),
        ]
    )
    session.commit()

    summary = load_snapshot_summary(session, today=date(2025, 1, 2))

    assert summary.google_snapshot_count == 2
    assert summary.namuwiki_snapshot_count == 2
    assert summary.google_today_snapshot_count == 1
    assert summary.namuwiki_today_snapshot_count == 1
    assert summary.latest_google_symbol == "PLTR:NASDAQ"
    assert summary.latest_namuwiki_keyword == "Database"
    assert summary.latest_google_collected_at.isoformat() == "2025-01-02T01:00:00+09:00"


def test_log_summary_uses_fake_directory_metadata_without_reading_content(tmp_path) -> None:
    """Operations log status reads only file names, sizes, and modification times."""
    assert load_log_summary(tmp_path).files == ()

    log_file = tmp_path / "google_finance_wrapper.log"
    log_file.write_text("safe log content", encoding="utf-8")

    summary = load_log_summary(tmp_path)

    assert [item.name for item in summary.files] == ["google_finance_wrapper.log"]
    assert summary.files[0].size_bytes == len("safe log content")
    assert summary.files[0].modified_at.tzname() == "KST"


def test_alembic_status_compares_applied_revision_with_local_script_head(session: Session) -> None:
    """Migration status reads the existing version table without running Alembic."""
    session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)"))
    session.execute(
        text(
            "INSERT INTO alembic_version (version_num) "
            "VALUES ('0003_stock_quote_snapshots')"
        )
    )
    session.commit()

    status = load_alembic_status(session)

    assert status.current_head == "0003_stock_quote_snapshots"
    assert status.applied_version == "0003_stock_quote_snapshots"
    assert status.is_in_sync is True


def test_runtime_info_exposes_local_process_metadata() -> None:
    """Runtime information is available without a Session or external service."""
    runtime = load_runtime_info()

    assert runtime.python_version
    assert runtime.timezone
    assert runtime.working_directory.is_absolute()
    assert runtime.streamlit_version
