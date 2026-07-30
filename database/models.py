"""데이터베이스 도메인 모델."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from database.base import Base

SEOUL_TZ = ZoneInfo("Asia/Seoul")


class TrendSnapshot(Base):
    """나무위키 실시간 검색어 한 수집 시점의 원본 순위 항목."""

    __tablename__ = "trend_snapshots"
    __table_args__ = (
        UniqueConstraint("collected_at", "rank_position", name="uq_trend_snapshots_collected_rank"),
        CheckConstraint("rank_position BETWEEN 1 AND 10", name="ck_trend_snapshots_rank_range"),
        CheckConstraint(
            "CHAR_LENGTH(TRIM(keyword)) > 0", name="ck_trend_snapshots_keyword_nonempty"
        ),
        Index("ix_trend_snapshots_collection_date_keyword", "collection_date", "keyword"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    collection_date: Mapped[date] = mapped_column(Date, nullable=False)
    rank_position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    # Python에서 aware UTC를 만든 뒤 MySQL DATETIME용 naive UTC로 저장한다.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    def __init__(
        self,
        *,
        collected_at: datetime,
        rank_position: int,
        keyword: str,
        created_at: datetime | None = None,
    ) -> None:
        """Create an append-only snapshot and derive the Seoul aggregation date."""
        collected_at_utc = self._validate_utc_datetime(collected_at, "collected_at")
        self.collected_at = collected_at_utc.replace(tzinfo=None)
        self.collection_date = collected_at_utc.astimezone(SEOUL_TZ).date()
        self.rank_position = self._validate_rank(rank_position)
        self.keyword = self._validate_keyword(keyword)
        created_at_utc = self._validate_utc_datetime(
            created_at if created_at is not None else datetime.now(timezone.utc),
            "created_at",
        )
        self.created_at = created_at_utc.replace(tzinfo=None)

    @staticmethod
    def _validate_utc_datetime(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _validate_rank(value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError("rank_position must be between 1 and 10")
        return value

    @staticmethod
    def _validate_keyword(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("keyword must not be empty")
        return normalized

    @validates("rank_position")
    def validate_rank_position(self, key: str, value: int) -> int:
        return self._validate_rank(value)

    @validates("keyword")
    def validate_keyword(self, key: str, value: str) -> str:
        return self._validate_keyword(value)
