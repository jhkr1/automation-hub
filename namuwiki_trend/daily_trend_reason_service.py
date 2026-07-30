"""Daily Trend News 목록에서 이유를 생성하는 Application Service."""

from collections.abc import Sequence
from typing import Protocol

from namuwiki_trend.daily_trend_news_service import DailyTrendNews
from namuwiki_trend.models import TrendReason


class ReasonGenerator(Protocol):
    """Reason Generator의 최소 공개 계약."""

    def generate(self, item: DailyTrendNews) -> TrendReason:
        """Generate one reason for a DailyTrendNews item."""


class DailyTrendReasonService:
    """DailyTrendNews 순회와 TrendReason 생성 orchestration을 담당한다."""

    def __init__(self, reason_generator: ReasonGenerator) -> None:
        """Initialize the service with an injectable reason generator."""
        self._reason_generator = reason_generator

    def generate(self, items: Sequence[DailyTrendNews]) -> list[TrendReason]:
        """Generate reasons in the same order as the input items."""
        if items is None:
            raise TypeError("items는 Sequence이어야 함")

        reasons: list[TrendReason] = []
        for index, item in enumerate(items):
            if not isinstance(item, DailyTrendNews):
                raise TypeError(f"items[{index}]가 DailyTrendNews가 아님")
            reasons.append(self._reason_generator.generate(item))
        return reasons
