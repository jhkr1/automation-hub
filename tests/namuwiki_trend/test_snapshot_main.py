from datetime import datetime, timezone

import pytest

from database.models import TrendSnapshot
from namuwiki_trend import snapshot_main


class FakePipeline:
    def __init__(self, result: list[object] | None = None, error: Exception | None = None) -> None:
        self.result = result or []
        self.error = error
        self.calls = 0

    def run(self) -> list[object]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def test_main_prints_saved_row_count(monkeypatch, capsys) -> None:
    collected_at = datetime(2026, 7, 30, 3, 45, 31)
    pipeline = FakePipeline(
        [
            TrendSnapshot(
                collected_at=collected_at.replace(tzinfo=timezone.utc),
                rank_position=1,
                keyword="example",
            )
            for _ in range(10)
        ]
    )
    monkeypatch.setattr(snapshot_main, "build_snapshot_pipeline", lambda: pipeline)

    snapshot_main.main()

    assert pipeline.calls == 1
    assert capsys.readouterr().out == (
        "Snapshot collection completed: 10 rows saved.\n"
        "Collected at: 2026-07-30 03:45:31 UTC\n"
        "Collected at: 2026-07-30 12:45:31 KST\n"
    )


def test_main_converts_utc_to_kst_across_date_boundary(monkeypatch, capsys) -> None:
    snapshot = TrendSnapshot(
        collected_at=datetime(2026, 7, 29, 16, 30, tzinfo=timezone.utc),
        rank_position=1,
        keyword="example",
    )
    pipeline = FakePipeline([snapshot])
    monkeypatch.setattr(snapshot_main, "build_snapshot_pipeline", lambda: pipeline)

    snapshot_main.main()

    output = capsys.readouterr().out
    assert "Collected at: 2026-07-29 16:30:00 UTC" in output
    assert "Collected at: 2026-07-30 01:30:00 KST" in output


def test_main_prints_empty_result(monkeypatch, capsys) -> None:
    pipeline = FakePipeline([])
    monkeypatch.setattr(snapshot_main, "build_snapshot_pipeline", lambda: pipeline)

    snapshot_main.main()

    assert pipeline.calls == 1
    assert capsys.readouterr().out == "Snapshot collection completed: no trends collected.\n"


def test_main_propagates_pipeline_error_without_success_message(monkeypatch, capsys) -> None:
    expected = RuntimeError("snapshot failure")
    pipeline = FakePipeline(error=expected)
    monkeypatch.setattr(snapshot_main, "build_snapshot_pipeline", lambda: pipeline)

    with pytest.raises(RuntimeError) as raised:
        snapshot_main.main()

    assert raised.value is expected
    assert capsys.readouterr().out == ""
