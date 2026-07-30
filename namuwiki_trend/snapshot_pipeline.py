"""Collector와 TrendSnapshot 저장을 연결하는 Application Pipeline."""

from collections.abc import Callable

from database.models import TrendSnapshot
from database.snapshot_save_service import SnapshotSaveService
from namuwiki_trend.models import TrendItem


class SnapshotCollectionPipeline:
    """Collector 결과를 SnapshotSaveService에 전달하는 orchestration 계층."""

    def __init__(
        self,
        collector: Callable[[], list[TrendItem]],
        save_service: SnapshotSaveService,
    ) -> None:
        """Initialize the pipeline with its externally created collaborators."""
        self._collector = collector
        self._save_service = save_service

    def run(self) -> list[TrendSnapshot]:
        """Collect trends and save them as one snapshot batch."""
        trends = self._collector()
        if not trends:
            return []
        return self._save_service.save(trends)
