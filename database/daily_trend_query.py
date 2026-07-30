"""일일 실시간 검색어 집계 조회 서비스."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from database.models import TrendSnapshot


@dataclass(frozen=True)
class DailyTrendRank:
    """특정 KST 날짜의 keyword별 집계 결과."""

    keyword: str
    appearance_count: int
    best_rank: int
    average_rank: float
    rank_score: int


class DailyTrendQueryService:
    """TrendSnapshot을 KST 집계 날짜별 Daily Top N으로 조회한다."""

    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        """Initialize the query service with an optional session factory."""
        if session_factory is None:
            from database.session import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory

    def query(self, target_date: date, limit: int = 10) -> list[DailyTrendRank]:
        """Return ranked keyword aggregates for a Seoul calendar date."""
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        appearance_count = func.count(TrendSnapshot.id).label("appearance_count")
        best_rank = func.min(TrendSnapshot.rank_position).label("best_rank")
        average_rank = func.avg(TrendSnapshot.rank_position).label("average_rank")
        rank_score = func.sum(11 - TrendSnapshot.rank_position).label("rank_score")
        statement: Select[tuple[object, ...]] = (
            select(
                TrendSnapshot.keyword,
                appearance_count,
                best_rank,
                average_rank,
                rank_score,
            )
            .where(TrendSnapshot.collection_date == target_date)
            .group_by(TrendSnapshot.keyword)
            .order_by(
                rank_score.desc(),
                appearance_count.desc(),
                best_rank.asc(),
                average_rank.asc(),
                TrendSnapshot.keyword.asc(),
            )
            .limit(limit)
        )

        with self._session_factory() as session:
            rows = session.execute(statement).all()

        return [
            DailyTrendRank(
                keyword=row.keyword,
                appearance_count=int(row.appearance_count),
                best_rank=int(row.best_rank),
                average_rank=float(row.average_rank),
                rank_score=int(row.rank_score),
            )
            for row in rows
        ]
