"""Read-only Namuwiki trend snapshot queries for the dashboard."""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from automation_dashboard.queries.google_finance import SEOUL_TZ, to_seoul_time
from database.models import TrendSnapshot


@dataclass(frozen=True)
class LatestTrendRow:
    """One row from the latest persisted Namuwiki Top 10 snapshot."""

    rank_position: int
    keyword: str
    collected_at: datetime


@dataclass(frozen=True)
class TrendHistoryPoint:
    """One persisted keyword rank at a localized collection time."""

    collected_at: datetime
    rank_position: int


@dataclass(frozen=True)
class KeywordSummary:
    """Aggregated persisted appearance data for one keyword."""

    keyword: str
    appearance_count: int
    best_rank: int
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class SnapshotSummary:
    """Read-only totals prepared for the Namuwiki dashboard KPI row."""

    total_snapshot_count: int
    today_snapshot_count: int
    stored_keyword_count: int
    latest_collected_at: datetime | None


def _normalize_keyword(keyword: str) -> str:
    """Validate a dashboard keyword without changing its persisted spelling."""
    if not isinstance(keyword, str):
        raise TypeError("keyword must be a string")
    normalized = keyword.strip()
    if not normalized:
        raise ValueError("keyword must not be empty")
    return normalized


def list_latest_snapshot(session: Session) -> list[LatestTrendRow]:
    """Return the latest snapshot rows in ascending persisted rank order."""
    latest_collected_at = session.scalar(select(func.max(TrendSnapshot.collected_at)))
    if latest_collected_at is None:
        return []

    statement = (
        select(
            TrendSnapshot.rank_position,
            TrendSnapshot.keyword,
            TrendSnapshot.collected_at,
        )
        .where(TrendSnapshot.collected_at == latest_collected_at)
        .order_by(TrendSnapshot.rank_position.asc(), TrendSnapshot.id.asc())
    )
    return [
        LatestTrendRow(
            rank_position=int(row.rank_position),
            keyword=row.keyword,
            collected_at=to_seoul_time(row.collected_at),
        )
        for row in session.execute(statement).all()
    ]


def list_keyword_history(session: Session, keyword: str) -> list[TrendHistoryPoint]:
    """Return one keyword's rank history in chronological order."""
    normalized_keyword = _normalize_keyword(keyword)
    statement = (
        select(TrendSnapshot.collected_at, TrendSnapshot.rank_position)
        .where(TrendSnapshot.keyword == normalized_keyword)
        .order_by(TrendSnapshot.collected_at.asc(), TrendSnapshot.id.asc())
    )
    return [
        TrendHistoryPoint(
            collected_at=to_seoul_time(row.collected_at),
            rank_position=int(row.rank_position),
        )
        for row in session.execute(statement).all()
    ]


def list_keyword_statistics(session: Session) -> list[KeywordSummary]:
    """Aggregate persisted keyword appearances for the dashboard table."""
    appearance_count = func.count(TrendSnapshot.id).label("appearance_count")
    best_rank = func.min(TrendSnapshot.rank_position).label("best_rank")
    first_seen_at = func.min(TrendSnapshot.collected_at).label("first_seen_at")
    last_seen_at = func.max(TrendSnapshot.collected_at).label("last_seen_at")
    statement = (
        select(
            TrendSnapshot.keyword,
            appearance_count,
            best_rank,
            first_seen_at,
            last_seen_at,
        )
        .group_by(TrendSnapshot.keyword)
        .order_by(
            appearance_count.desc(),
            best_rank.asc(),
            last_seen_at.desc(),
            TrendSnapshot.keyword.asc(),
        )
    )
    return [
        KeywordSummary(
            keyword=row.keyword,
            appearance_count=int(row.appearance_count),
            best_rank=int(row.best_rank),
            first_seen_at=to_seoul_time(row.first_seen_at),
            last_seen_at=to_seoul_time(row.last_seen_at),
        )
        for row in session.execute(statement).all()
    ]


def load_snapshot_summary(
    session: Session,
    *,
    today: date | None = None,
) -> SnapshotSummary:
    """Return stored snapshot, KST-day, keyword, and latest-time totals."""
    target_date = today or datetime.now(SEOUL_TZ).date()
    statement = select(
        func.count(func.distinct(TrendSnapshot.collected_at)).label("total_snapshot_count"),
        func.count(func.distinct(TrendSnapshot.keyword)).label("stored_keyword_count"),
        func.max(TrendSnapshot.collected_at).label("latest_collected_at"),
    )
    today_statement = select(
        func.count(func.distinct(TrendSnapshot.collected_at)).label("today_snapshot_count")
    ).where(TrendSnapshot.collection_date == target_date)
    row = session.execute(statement).one()
    today_snapshot_count = session.scalar(today_statement)
    latest_collected_at = row.latest_collected_at
    return SnapshotSummary(
        total_snapshot_count=int(row.total_snapshot_count),
        today_snapshot_count=int(today_snapshot_count or 0),
        stored_keyword_count=int(row.stored_keyword_count),
        latest_collected_at=(
            None if latest_collected_at is None else to_seoul_time(latest_collected_at)
        ),
    )
