from datetime import date
from types import SimpleNamespace

import pytest

from database.daily_trend_query import DailyTrendQueryService


class FakeResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class FakeSession:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.executed = []

    def execute(self, statement: object) -> FakeResult:
        self.executed.append(statement)
        return FakeResult(self.rows)

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        pass


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


def test_query_maps_aggregate_metrics_and_preserves_order() -> None:
    rows = [
        SimpleNamespace(
            keyword="가나다",
            appearance_count=3,
            best_rank=1,
            average_rank=2.0,
            rank_score=27,
        ),
        SimpleNamespace(
            keyword="테스트",
            appearance_count=1,
            best_rank=5,
            average_rank=5.0,
            rank_score=6,
        ),
    ]
    session = FakeSession(rows)

    result = DailyTrendQueryService(FakeSessionFactory(session)).query(
        date(2026, 7, 30), limit=10
    )

    assert result == [
        result[0].__class__("가나다", 3, 1, 2.0, 27),
        result[1].__class__("테스트", 1, 5, 5.0, 6),
    ]
    assert len(session.executed) == 1


def test_query_returns_empty_rows() -> None:
    session = FakeSession([])

    result = DailyTrendQueryService(FakeSessionFactory(session)).query(date(2026, 7, 30))

    assert result == []


@pytest.mark.parametrize("limit", [0, -1])
def test_query_rejects_non_positive_limit(limit: int) -> None:
    service = DailyTrendQueryService(FakeSessionFactory(FakeSession([])))

    with pytest.raises(ValueError, match="limit"):
        service.query(date(2026, 7, 30), limit=limit)
