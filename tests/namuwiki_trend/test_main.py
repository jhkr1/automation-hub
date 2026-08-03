"""Application Entry Point의 네트워크 비의존 테스트."""

from pathlib import Path

import pytest

from namuwiki_trend.main import build_pipeline, collect_trends, main, run_application
from namuwiki_trend.models import TrendInsight, TrendItem


def _insight(rank: int) -> TrendInsight:
    """테스트용 TrendInsight를 만든다."""
    trend = TrendItem(rank=rank, keyword=f"keyword-{rank}", href=f"/Go?q={rank}")
    return TrendInsight(trend=trend, reason=f"reason-{rank}", articles=())


class FakePipeline:
    """Pipeline 실행을 기록하는 Fake."""

    def __init__(self, insights: list[TrendInsight]) -> None:
        self.insights = insights
        self.calls = 0

    def run(self) -> list[TrendInsight]:
        """Fake Insight 목록을 반환한다."""
        self.calls += 1
        return self.insights


class FakeStorage:
    """저장 호출과 전달된 데이터를 기록하는 Fake."""

    def __init__(self, result: Path) -> None:
        self.result = result
        self.calls: list[tuple[list[TrendInsight], str | Path]] = []

    def save(self, insights: list[TrendInsight], path: str | Path) -> Path:
        """전달된 Insight와 경로를 기록한다."""
        self.calls.append((insights, path))
        return self.result


def test_run_application_runs_pipeline_and_saves_results(tmp_path: Path) -> None:
    """Pipeline 결과를 그대로 Storage에 전달하고 저장 경로를 반환한다."""
    insights = [_insight(1), _insight(2)]
    pipeline = FakePipeline(insights)
    storage = FakeStorage(tmp_path / "insights.json")
    output_path = tmp_path / "nested" / "insights.json"

    result = run_application(pipeline, storage, output_path)

    assert result == storage.result
    assert pipeline.calls == 1
    assert storage.calls == [(insights, output_path)]


def test_build_pipeline_composes_runtime_dependencies(monkeypatch) -> None:
    """Composition Root가 운영 의존성을 생성자 주입으로 연결한다."""
    created: dict[str, object] = {}

    class FakeNewsProvider:
        def __init__(self) -> None:
            created["news_provider"] = self

    class FakeReasonGenerator:
        def __init__(self) -> None:
            created["reason_generator"] = self

    class FakeEnricher:
        def __init__(self, news_provider: object, reason_generator: object) -> None:
            created["enricher"] = self
            created["enricher_args"] = (news_provider, reason_generator)

    class FakePipeline:
        def __init__(self, collector: object, enricher: object) -> None:
            created["pipeline_args"] = (collector, enricher)

    monkeypatch.setattr("namuwiki_trend.main.NewsContextProvider", FakeNewsProvider)
    monkeypatch.setattr("namuwiki_trend.main.GeminiReasonGenerator", FakeReasonGenerator)
    monkeypatch.setattr("namuwiki_trend.main.TrendEnricher", FakeEnricher)
    monkeypatch.setattr("namuwiki_trend.main.TrendPipeline", FakePipeline)

    result = build_pipeline()

    assert isinstance(result, FakePipeline)
    assert created["enricher_args"] == (
        created["news_provider"],
        created["reason_generator"],
    )
    assert created["pipeline_args"] == (collect_trends, created["enricher"])


def test_run_application_propagates_pipeline_failure() -> None:
    """Pipeline 예외를 Storage 호출 없이 그대로 전달한다."""
    expected = RuntimeError("pipeline failure")

    class FailingPipeline:
        def run(self) -> list[TrendInsight]:
            raise expected

    storage = FakeStorage(Path("unused.json"))

    with pytest.raises(RuntimeError) as raised:
        run_application(FailingPipeline(), storage)

    assert raised.value is expected
    assert storage.calls == []


def test_main_returns_zero_when_application_succeeds(monkeypatch, capsys) -> None:
    """Application 성공 시 zero 종료 코드를 반환한다."""
    output_path = Path("output/trend_insights.json")
    monkeypatch.setattr("namuwiki_trend.main.run_application", lambda *args: output_path)
    monkeypatch.setattr("namuwiki_trend.main.build_pipeline", lambda: object())
    monkeypatch.setattr("namuwiki_trend.main.JsonTrendInsightStorage", lambda: object())

    assert main() == 0
    captured = capsys.readouterr()
    assert "결과 저장 완료" in captured.out
    assert captured.err == ""


def test_main_returns_one_when_application_fails(monkeypatch, capsys) -> None:
    """Application 실패 시 오류를 출력하고 non-zero 종료 코드를 반환한다."""
    expected = RuntimeError("application failure")

    def fail(*args: object) -> Path:
        raise expected

    monkeypatch.setattr("namuwiki_trend.main.run_application", fail)
    monkeypatch.setattr("namuwiki_trend.main.build_pipeline", lambda: object())
    monkeypatch.setattr("namuwiki_trend.main.JsonTrendInsightStorage", lambda: object())

    assert main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "실행 실패" in captured.err
