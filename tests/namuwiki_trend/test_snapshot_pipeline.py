import pytest

from namuwiki_trend.models import TrendItem
from namuwiki_trend.snapshot_pipeline import SnapshotCollectionPipeline


class FakeCollector:
    def __init__(self, trends: list[TrendItem]) -> None:
        self.trends = trends
        self.calls = 0

    def __call__(self) -> list[TrendItem]:
        self.calls += 1
        return self.trends


class FakeSaveService:
    def __init__(self, result: list[object]) -> None:
        self.result = result
        self.calls: list[list[TrendItem]] = []

    def save(self, trends: list[TrendItem]) -> list[object]:
        self.calls.append(trends)
        return self.result


def test_pipeline_collects_saves_and_returns_result() -> None:
    trends = [TrendItem(rank=1, keyword="first", href="/first")]
    collector = FakeCollector(trends)
    saver = FakeSaveService([object()])

    result = SnapshotCollectionPipeline(collector, saver).run()

    assert collector.calls == 1
    assert saver.calls == [trends]
    assert result == saver.result


def test_pipeline_returns_empty_without_calling_save_service() -> None:
    collector = FakeCollector([])
    saver = FakeSaveService([object()])

    result = SnapshotCollectionPipeline(collector, saver).run()

    assert result == []
    assert collector.calls == 1
    assert saver.calls == []


def test_pipeline_propagates_collector_error() -> None:
    expected = RuntimeError("collector failure")

    def collector() -> list[TrendItem]:
        raise expected

    saver = FakeSaveService([])

    with pytest.raises(RuntimeError) as raised:
        SnapshotCollectionPipeline(collector, saver).run()

    assert raised.value is expected
    assert saver.calls == []


def test_pipeline_propagates_save_error() -> None:
    expected = RuntimeError("save failure")
    trends = [TrendItem(rank=1, keyword="first", href="/first")]

    class FailingSaveService:
        def save(self, received: list[TrendItem]) -> list[object]:
            raise expected

    with pytest.raises(RuntimeError) as raised:
        SnapshotCollectionPipeline(FakeCollector(trends), FailingSaveService()).run()

    assert raised.value is expected
