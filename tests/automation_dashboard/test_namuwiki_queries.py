"""Unit contracts for read-only Namuwiki dashboard queries."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from automation_dashboard.queries.namuwiki import (
    list_keyword_history,
    list_keyword_statistics,
    list_latest_snapshot,
    load_snapshot_summary,
)
from database.models import TrendSnapshot


@pytest.fixture
def session() -> Session:
    """Create an isolated SQLite TrendSnapshot table without MySQL."""
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def register_mysql_compatibility_functions(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function("CHAR_LENGTH", 1, len)

    TrendSnapshot.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as database_session:
        yield database_session
    engine.dispose()


def _snapshot(
    identifier: int,
    collected_at: datetime,
    rank_position: int,
    keyword: str,
) -> TrendSnapshot:
    """Create a deterministic persisted trend row for query tests."""
    snapshot = TrendSnapshot(
        collected_at=collected_at,
        rank_position=rank_position,
        keyword=keyword,
    )
    snapshot.id = identifier
    return snapshot


def test_empty_snapshot_queries_return_safe_empty_results(session: Session) -> None:
    """The dashboard can render an empty state without a stored snapshot."""
    assert list_latest_snapshot(session) == []
    assert list_keyword_statistics(session) == []
    assert list_keyword_history(session, "없는 검색어") == []

    summary = load_snapshot_summary(session, today=date(2025, 1, 1))

    assert summary.total_snapshot_count == 0
    assert summary.today_snapshot_count == 0
    assert summary.stored_keyword_count == 0
    assert summary.latest_collected_at is None


def test_latest_snapshot_uses_latest_collection_and_rank_order_with_kst(
    session: Session,
) -> None:
    """The latest cohort is ordered by rank and localized from UTC to KST."""
    older = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    latest = datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            _snapshot(1, older, 1, "이전"),
            _snapshot(2, latest, 2, "두 번째"),
            _snapshot(3, latest, 1, "첫 번째"),
        ]
    )
    session.commit()

    result = list_latest_snapshot(session)

    assert [(row.rank_position, row.keyword) for row in result] == [
        (1, "첫 번째"),
        (2, "두 번째"),
    ]
    assert result[0].collected_at.isoformat() == "2025-01-01T10:00:00+09:00"


def test_keyword_history_is_chronological_and_preserves_same_time_id_order(
    session: Session,
) -> None:
    """One keyword history is deterministic even when collection times tie."""
    collected_at = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            _snapshot(3, collected_at, 3, "Python"),
            _snapshot(2, collected_at, 2, "Python"),
            _snapshot(1, collected_at.replace(hour=1), 1, "Other"),
        ]
    )
    session.commit()

    result = list_keyword_history(session, " Python ")

    assert [row.rank_position for row in result] == [2, 3]
    assert all(row.collected_at.tzname() == "KST" for row in result)


def test_keyword_statistics_aggregate_counts_ranks_and_seen_times(session: Session) -> None:
    """Statistics retain the expected aggregation and display sort contracts."""
    first = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    later = datetime(2025, 1, 1, 2, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            _snapshot(1, first, 4, "Python"),
            _snapshot(2, later, 1, "Python"),
            _snapshot(3, first, 2, "Database"),
        ]
    )
    session.commit()

    result = list_keyword_statistics(session)

    assert [row.keyword for row in result] == ["Python", "Database"]
    assert result[0].appearance_count == 2
    assert result[0].best_rank == 1
    assert result[0].first_seen_at.isoformat() == "2025-01-01T09:00:00+09:00"
    assert result[0].last_seen_at.isoformat() == "2025-01-01T11:00:00+09:00"


def test_snapshot_summary_counts_distinct_collections_for_the_kst_day(session: Session) -> None:
    """A snapshot is a collection cohort, not each individual Top 10 row."""
    previous_kst_day_utc = datetime(2025, 1, 1, 14, 30, tzinfo=timezone.utc)
    next_kst_day_utc = datetime(2025, 1, 1, 16, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            _snapshot(1, previous_kst_day_utc, 1, "Python"),
            _snapshot(2, previous_kst_day_utc, 2, "Database"),
            _snapshot(3, next_kst_day_utc, 1, "Python"),
        ]
    )
    session.commit()

    summary = load_snapshot_summary(session, today=date(2025, 1, 2))

    assert summary.total_snapshot_count == 2
    assert summary.today_snapshot_count == 1
    assert summary.stored_keyword_count == 2
    assert summary.latest_collected_at.isoformat() == "2025-01-02T01:00:00+09:00"
