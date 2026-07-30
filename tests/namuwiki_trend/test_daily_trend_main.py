from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from namuwiki_trend import daily_trend_main


class FakeService:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.calls: list[tuple[object, int]] = []

    def query(self, target_date: object, limit: int) -> list[object]:
        self.calls.append((target_date, limit))
        return self.results


def _result(keyword: str, score: int) -> SimpleNamespace:
    return SimpleNamespace(
        keyword=keyword,
        appearance_count=2,
        best_rank=1,
        average_rank=2.5,
        rank_score=score,
    )


def test_main_passes_explicit_date_and_limit(capsys: pytest.CaptureFixture[str]) -> None:
    service = FakeService([_result("가나다", 18)])

    assert daily_trend_main.main(["--date", "2026-07-30", "--limit", "3"], service) == 0

    assert service.calls == [(datetime(2026, 7, 30).date(), 3)]
    assert "가나다" in capsys.readouterr().out


def test_main_uses_kst_date_when_date_is_omitted(capsys: pytest.CaptureFixture[str]) -> None:
    service = FakeService([])
    now = datetime(2026, 7, 29, 16, 30, tzinfo=timezone.utc)

    daily_trend_main.main([], service, now)

    assert service.calls == [(datetime(2026, 7, 30).date(), 10)]
    assert "No daily trends found for 2026-07-30 KST." in capsys.readouterr().out


def test_main_preserves_service_order_and_formats_average(
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = FakeService([_result("첫 번째", 20), _result("두 번째", 10)])

    daily_trend_main.main(["--date", "2026-07-30"], service)

    output = capsys.readouterr().out
    assert output.index("첫 번째") < output.index("두 번째")
    assert "2.50" in output


def test_main_rejects_invalid_date() -> None:
    with pytest.raises(SystemExit):
        daily_trend_main.main(["--date", "2026/07/30"], FakeService([]))


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_main_rejects_non_positive_limit(limit: str) -> None:
    with pytest.raises(SystemExit):
        daily_trend_main.main(["--limit", limit], FakeService([]))


def test_main_propagates_service_error() -> None:
    class FailingService(FakeService):
        def query(self, target_date: object, limit: int) -> list[object]:
            raise RuntimeError("query failed")

    with pytest.raises(RuntimeError, match="query failed"):
        daily_trend_main.main([], FailingService([]))
