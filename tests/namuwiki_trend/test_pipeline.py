"""TrendPipeline의 네트워크 비의존 계약 테스트."""

import pytest

from namuwiki_trend.models import TrendInsight, TrendItem
from namuwiki_trend.pipeline import TrendPipeline


def _trends(count: int = 3) -> list[TrendItem]:
    """테스트용 순위 목록을 만든다."""
    return [
        TrendItem(rank=index, keyword=f"keyword-{index}", href=f"/Go?q={index}")
        for index in range(1, count + 1)
    ]


class FakeCollector:
    """Collector 호출과 반환 목록을 기록하는 Fake Collector."""

    def __init__(
        self,
        trends: list[TrendItem] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.trends = trends if trends is not None else _trends()
        self.error = error
        self.call_count = 0

    def __call__(self) -> list[TrendItem]:
        """호출 횟수를 기록하고 fake 목록 또는 예외를 반환한다."""
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return self.trends


class FakeEnricher:
    """Enricher 호출 순서와 입력을 기록하는 Fake Enricher."""

    def __init__(self, error_at: int | None = None, error: Exception | None = None) -> None:
        self.error_at = error_at
        self.error = error
        self.calls: list[TrendItem] = []

    def enrich(self, trend: TrendItem) -> TrendInsight:
        """호출을 기록하고 TrendInsight 또는 예외를 반환한다."""
        self.calls.append(trend)
        if self.error_at == len(self.calls):
            assert self.error is not None
            raise self.error
        return TrendInsight(trend=trend, reason=f"reason-{trend.rank}", articles=())


def _pipeline(
    trends: list[TrendItem] | None = None,
    *,
    collector_error: Exception | None = None,
    enricher_error_at: int | None = None,
    enricher_error: Exception | None = None,
) -> tuple[TrendPipeline, FakeCollector, FakeEnricher]:
    """테스트용 Pipeline과 Fake 의존성을 만든다."""
    collector = FakeCollector(trends, error=collector_error)
    enricher = FakeEnricher(error_at=enricher_error_at, error=enricher_error)
    return TrendPipeline(collector, enricher), collector, enricher


def test_run_calls_collector_once_and_preserves_order() -> None:
    """Collector를 한 번 호출하고 TrendItem과 결과 순서를 보존한다."""
    pipeline, collector, enricher = _pipeline()

    results = pipeline.run()

    assert collector.call_count == 1
    assert enricher.calls == collector.trends
    assert [result.trend for result in results] == collector.trends
    assert [result.reason for result in results] == ["reason-1", "reason-2", "reason-3"]


def test_run_returns_empty_list_without_calling_enricher() -> None:
    """Collector가 빈 목록을 반환하면 정상적인 빈 결과를 반환한다."""
    pipeline, collector, enricher = _pipeline([])

    assert pipeline.run() == []
    assert collector.call_count == 1
    assert enricher.calls == []


def test_run_propagates_collector_exception_unchanged() -> None:
    """Collector 예외를 wrapping하지 않고 그대로 전달한다."""
    expected = RuntimeError("collector failure")
    pipeline, collector, enricher = _pipeline(collector_error=expected)

    with pytest.raises(RuntimeError) as raised:
        pipeline.run()

    assert raised.value is expected
    assert collector.call_count == 1
    assert enricher.calls == []


def test_run_stops_at_first_enrichment_failure() -> None:
    """첫 enrichment 실패 뒤에는 이후 항목을 처리하지 않는다."""
    expected = ValueError("enrichment failure")
    pipeline, _, enricher = _pipeline(enricher_error_at=1, enricher_error=expected)

    with pytest.raises(ValueError) as raised:
        pipeline.run()

    assert raised.value is expected
    assert enricher.calls == [_trends()[0]]


def test_run_stops_at_middle_enrichment_failure() -> None:
    """중간 enrichment 실패 뒤의 항목은 처리하지 않는다."""
    expected = RuntimeError("middle failure")
    pipeline, _, enricher = _pipeline(enricher_error_at=2, enricher_error=expected)

    with pytest.raises(RuntimeError) as raised:
        pipeline.run()

    assert raised.value is expected
    assert enricher.calls == _trends()[:2]


def test_run_enriches_ten_collector_items_exactly_once() -> None:
    """Collector가 10개를 반환하면 각 항목을 정확히 한 번 처리한다."""
    pipeline, collector, enricher = _pipeline(_trends(10))

    results = pipeline.run()

    assert len(results) == 10
    assert enricher.calls == collector.trends
    assert len(enricher.calls) == 10


def test_run_does_not_mutate_collector_result() -> None:
    """Pipeline은 입력 목록을 정렬하거나 수정하지 않는다."""
    trends = _trends()
    original = trends.copy()
    pipeline, _, _ = _pipeline(trends)

    pipeline.run()

    assert trends == original
