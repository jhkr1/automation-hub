import os
from datetime import date, datetime, timezone

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="set RUN_DB_INTEGRATION=1 to run against MySQL",
)


def test_migrated_snapshot_schema_and_constraints() -> None:
    from sqlalchemy import inspect

    from database.engine import engine

    inspector = inspect(engine)
    assert "trend_snapshots" in inspector.get_table_names()
    assert "ix_trend_snapshots_collection_date_keyword" in {
        index["name"] for index in inspector.get_indexes("trend_snapshots")
    }
    assert "uq_trend_snapshots_collected_rank" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("trend_snapshots")
    }


def test_duplicate_snapshot_is_rolled_back() -> None:
    from sqlalchemy.exc import IntegrityError

    from database.models import TrendSnapshot
    from database.session import SessionLocal

    collected_at = datetime.now(timezone.utc)
    with SessionLocal() as session:
        try:
            session.add(
                TrendSnapshot(collected_at=collected_at, rank_position=1, keyword="integration")
            )
            session.flush()
            session.add(
                TrendSnapshot(collected_at=collected_at, rank_position=1, keyword="duplicate")
            )
            with pytest.raises(IntegrityError):
                session.flush()
        finally:
            session.rollback()


def test_daily_trend_query_aggregates_by_collection_date() -> None:
    from sqlalchemy import delete

    from database.daily_trend_query import DailyTrendQueryService
    from database.models import TrendSnapshot
    from database.session import SessionLocal

    target_date = date(2099, 1, 1)
    collected_at_values = [
        datetime(2099, 1, 1, hour, 0, tzinfo=timezone.utc) for hour in range(4)
    ]
    snapshots = [
        TrendSnapshot(collected_at=collected_at_values[0], rank_position=1, keyword="가나다"),
        TrendSnapshot(collected_at=collected_at_values[1], rank_position=3, keyword="가나다"),
        TrendSnapshot(collected_at=collected_at_values[2], rank_position=2, keyword="테스트"),
        TrendSnapshot(collected_at=collected_at_values[3], rank_position=10, keyword="테스트"),
    ]

    with SessionLocal() as session:
        try:
            session.add_all(snapshots)
            session.commit()

            result = DailyTrendQueryService().query(target_date, limit=10)

            assert [(item.keyword, item.appearance_count) for item in result] == [
                ("가나다", 2),
                ("테스트", 2),
            ]
            assert result[0].best_rank == 1
            assert result[0].average_rank == 2.0
            assert result[0].rank_score == 18
            assert result[1].best_rank == 2
            assert result[1].average_rank == 6.0
            assert result[1].rank_score == 10
        finally:
            session.execute(
                delete(TrendSnapshot).where(
                    TrendSnapshot.collected_at.in_(
                        [value.replace(tzinfo=None) for value in collected_at_values]
                    )
                )
            )
            session.commit()
