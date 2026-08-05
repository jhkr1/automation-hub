"""TrendItem 목록을 TrendInsight 목록으로 변환하는 Batch Application Layer."""

from collections.abc import Callable
from typing import Protocol

from namuwiki_trend.models import TrendInsight, TrendItem

TrendCollector = Callable[[], list[TrendItem]]


class TrendEnricherProtocol(Protocol):
    """Batch Orchestrator가 사용하는 Enricher의 최소 계약."""

    def enrich(self, trend: TrendItem) -> TrendInsight:
        """TrendItem 하나를 TrendInsight로 보강한다."""


class TrendPipeline:
    """Collector와 TrendEnricher를 연결하는 순차 Batch Orchestrator."""

    def __init__(
        self,
        collector: TrendCollector,
        enricher: TrendEnricherProtocol,
    ) -> None:
        self._collector = collector
        self._enricher = enricher

    def run(self) -> list[TrendInsight]:
        """Collector 결과를 입력 순서대로 enrichment하여 반환한다."""
        trends = self._collector()
        enrich_all = getattr(self._enricher, "enrich_all", None)
        if callable(enrich_all):
            return enrich_all(trends)
        return [self._enricher.enrich(trend) for trend in trends]
