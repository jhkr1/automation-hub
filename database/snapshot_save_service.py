"""수집된 실시간 검색어 스냅샷 저장 서비스."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database.models import TrendSnapshot
from namuwiki_trend.models import TrendItem


class SnapshotSaveService:
    """TrendItem 목록을 하나의 transaction으로 TrendSnapshot에 저장한다."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the service with a session factory and UTC clock."""
        if session_factory is None:
            from database.session import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def save(self, trends: Sequence[TrendItem]) -> list[TrendSnapshot]:
        """Convert and save all trends in one transaction."""
        collected_at = self._clock()
        snapshots = [
            TrendSnapshot(
                collected_at=collected_at,
                rank_position=trend.rank,
                keyword=trend.keyword,
            )
            for trend in trends
        ]

        with self._session_factory.begin() as session:
            session.add_all(snapshots)

        return snapshots
