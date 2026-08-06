"""Tests for the Google Finance JSON insight artifact contract."""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from google_finance import watchlist_main
from google_finance.insight_artifact import (
    JsonGoogleFinanceInsightStorage,
    artifact_path,
    build_insight_artifact,
)
from google_finance.models import StockInsight
from google_finance.movement import MovementDirection, MovementResult
from google_finance.movement_application import MovementUnavailable
from google_finance.watchlist_application import (
    WatchlistAnalysisErrorStage,
    WatchlistAnalysisResult,
    WatchlistAnalysisStatus,
    WatchlistAnalysisUnavailableReason,
)
from llm_runtime.models import KeyProfile

WHEN = datetime(2026, 8, 6, 0, 0, tzinfo=timezone.utc)


def _movement(symbol: str, delta: str = "1.00") -> MovementResult:
    return MovementResult(
        direction=MovementDirection.UP if delta != "0.00" else MovementDirection.UNCHANGED,
        symbol=symbol,
        latest_price=Decimal("101.00"),
        previous_price=Decimal("100.00"),
        price_delta=Decimal(delta),
        latest_collected_at=WHEN,
        previous_collected_at=WHEN,
    )


def _success(symbol: str = "000660:KRX") -> WatchlistAnalysisResult:
    return WatchlistAnalysisResult(
        symbol=symbol,
        status=WatchlistAnalysisStatus.SUCCESS,
        analysis=StockInsight(
            symbol=symbol,
            company_name="SK Hynix Inc",
            currency="KRW",
            current_price=Decimal("1668000.00"),
            change_percent=Decimal("5.77"),
            movement=_movement(symbol),
            summary="최근 두 차례 자동 수집 사이에는 가격이 상승했습니다.",
            news=(),
            generated_at=WHEN,
        ),
    )


def test_artifact_uses_profile_paths_and_preserves_decimal_strings(tmp_path) -> None:
    production = artifact_path(KeyProfile.PRODUCTION, root=tmp_path)
    test = artifact_path(KeyProfile.TEST, root=tmp_path)
    assert production == tmp_path / "google_finance_insights.json"
    assert test == tmp_path / "test" / "google_finance_insights.json"

    artifact = build_insight_artifact(
        [_success()], profile=KeyProfile.PRODUCTION, model="gemini-3.5-flash", clock=lambda: WHEN
    )
    output = JsonGoogleFinanceInsightStorage().save(artifact, production)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["profile"] == "production"
    assert payload["model"] == "gemini-3.5-flash"
    assert payload["generated_at"] == WHEN.isoformat()
    assert payload["items"][0]["price"] == "1668000.00"
    assert payload["items"][0]["google_finance_change_percent"] == "5.77"
    assert "prompt" not in payload and "api_key" not in payload
    assert "news" not in payload["items"][0]
    assert output.stat().st_mode & 0o777 == 0o600


def test_artifact_preserves_watchlist_order_and_non_success_states(tmp_path) -> None:
    results = [
        _success("PLTR:NASDAQ"),
        WatchlistAnalysisResult(
            symbol="NVDA:NASDAQ",
            status=WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE,
            analysis=MovementUnavailable(symbol="NVDA:NASDAQ", snapshot_count=1),
        ),
        WatchlistAnalysisResult(
            symbol="005930:KRX",
            status=WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE,
            unavailable_reason=WatchlistAnalysisUnavailableReason.DAILY_QUOTA_EXHAUSTED,
        ),
        WatchlistAnalysisResult(
            symbol="AAPL:NASDAQ",
            status=WatchlistAnalysisStatus.FAILED,
            error_stage=WatchlistAnalysisErrorStage.ANALYSIS,
            error_message="ANALYSIS failed: RuntimeError",
        ),
    ]
    artifact = build_insight_artifact(
        results, profile=KeyProfile.TEST, model="gemini-3.5-flash", clock=lambda: WHEN
    )

    assert [item.symbol for item in artifact.items] == [
        "PLTR:NASDAQ",
        "NVDA:NASDAQ",
        "005930:KRX",
        "AAPL:NASDAQ",
    ]
    assert [item.status for item in artifact.items] == [
        "SUCCESS",
        "MOVEMENT_UNAVAILABLE",
        "ANALYSIS_UNAVAILABLE",
        "FAILED",
    ]
    assert artifact.items[2].summary is None
    assert artifact.items[3].summary is None


def test_write_failure_preserves_existing_artifact(monkeypatch, tmp_path) -> None:
    path = tmp_path / "google_finance_insights.json"
    path.write_text("old artifact", encoding="utf-8")
    artifact = build_insight_artifact(
        [_success()], profile=KeyProfile.PRODUCTION, model="gemini-3.5-flash", clock=lambda: WHEN
    )

    def fail_replace(*args: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("google_finance.insight_artifact.os.replace", fail_replace)
    with pytest.raises(OSError, match="unable to write"):
        JsonGoogleFinanceInsightStorage().save(artifact, path)

    assert path.read_text(encoding="utf-8") == "old artifact"
    assert list(tmp_path.glob("*.tmp")) == []


def test_fsync_failure_preserves_existing_artifact(monkeypatch, tmp_path) -> None:
    path = tmp_path / "google_finance_insights.json"
    path.write_text("old artifact", encoding="utf-8")
    artifact = build_insight_artifact(
        [_success()], profile=KeyProfile.PRODUCTION, model="gemini-3.5-flash", clock=lambda: WHEN
    )

    def fail_fsync(*args: object) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr("google_finance.insight_artifact.os.fsync", fail_fsync)
    with pytest.raises(OSError, match="unable to write"):
        JsonGoogleFinanceInsightStorage().save(artifact, path)

    assert path.read_text(encoding="utf-8") == "old artifact"
    assert list(tmp_path.glob("*.tmp")) == []


def test_cli_artifact_save_skips_failed_or_quota_results(monkeypatch) -> None:
    calls: list[object] = []

    class FakeStorage:
        def save(self, artifact: object, path: object) -> None:
            calls.append((artifact, path))

    monkeypatch.setattr(watchlist_main, "JsonGoogleFinanceInsightStorage", FakeStorage)
    monkeypatch.setattr(watchlist_main, "build_insight_artifact", lambda *args, **kwargs: object())
    failed = WatchlistAnalysisResult(
        symbol="NVDA:NASDAQ",
        status=WatchlistAnalysisStatus.FAILED,
        error_stage=WatchlistAnalysisErrorStage.ANALYSIS,
        error_message="ANALYSIS failed: RuntimeError",
    )
    unavailable = WatchlistAnalysisResult(
        symbol="PLTR:NASDAQ",
        status=WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE,
        unavailable_reason=WatchlistAnalysisUnavailableReason.DAILY_QUOTA_EXHAUSTED,
    )

    watchlist_main._save_analysis_artifact([failed], KeyProfile.PRODUCTION)
    watchlist_main._save_analysis_artifact([unavailable], KeyProfile.PRODUCTION)

    assert calls == []


def test_cli_artifact_save_accepts_success_and_movement_unavailable(monkeypatch) -> None:
    calls: list[object] = []

    class FakeStorage:
        def save(self, artifact: object, path: object) -> None:
            calls.append((artifact, path))

    monkeypatch.setattr(watchlist_main, "JsonGoogleFinanceInsightStorage", FakeStorage)
    monkeypatch.setattr(watchlist_main, "build_insight_artifact", lambda *args, **kwargs: object())
    monkeypatch.setattr(watchlist_main, "artifact_path", lambda profile: profile.value)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
    movement_unavailable = WatchlistAnalysisResult(
        symbol="NVDA:NASDAQ",
        status=WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE,
        analysis=MovementUnavailable(symbol="NVDA:NASDAQ", snapshot_count=1),
    )

    watchlist_main._save_analysis_artifact(
        [_success(), movement_unavailable], KeyProfile.TEST
    )

    assert len(calls) == 1
    assert calls[0][1] == "test"
