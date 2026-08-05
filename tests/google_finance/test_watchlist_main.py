"""CLI contract tests for the Google Finance Watchlist."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from google_finance import watchlist_main
from google_finance.models import StockInsight, StockPrice
from google_finance.movement import MovementDirection, MovementResult
from google_finance.movement_application import MovementUnavailable
from google_finance.watchlist_application import (
    WatchlistAnalysisErrorStage,
    WatchlistAnalysisResult,
    WatchlistAnalysisStatus,
    WatchlistAnalysisUnavailableReason,
    WatchlistCollectErrorStage,
    WatchlistCollectResult,
    WatchlistCollectStatus,
)

WHEN = datetime(2026, 8, 3, 1, tzinfo=timezone.utc)
SYMBOLS = ["NVDA:NASDAQ", "PLTR:NASDAQ"]


class FakeSettings:
    google_finance_locale = "en-US"
    gemini_api_key = "test-key"

    def get_symbol_list(self) -> list[str]:
        return list(SYMBOLS)


def _stock_price(symbol: str) -> StockPrice:
    return StockPrice(
        symbol=symbol,
        name=f"Company {symbol}",
        current_price=Decimal("101.00"),
        previous_close=Decimal("100.00"),
        open_price=Decimal("100.50"),
        change_percent=Decimal("1.00"),
        currency="USD",
        collected_at=WHEN,
    )


def _insight(symbol: str) -> StockInsight:
    movement = MovementResult(
        direction=MovementDirection.UP,
        symbol=symbol,
        latest_price=Decimal("101.00"),
        previous_price=Decimal("100.00"),
        price_delta=Decimal("1.00"),
        latest_collected_at=WHEN,
        previous_collected_at=datetime(2026, 8, 2, 1, tzinfo=timezone.utc),
    )
    return StockInsight(
        symbol=symbol,
        company_name=f"Company {symbol}",
        currency="USD",
        current_price=Decimal("101.00"),
        change_percent=Decimal("1.00"),
        movement=movement,
        summary="공개 뉴스에 근거한 가능한 배경입니다.",
        news=(),
    )


def _collect_success(symbol: str) -> WatchlistCollectResult:
    return WatchlistCollectResult(
        symbol=symbol,
        status=WatchlistCollectStatus.SUCCESS,
        stock_price=_stock_price(symbol),
    )


def test_parser_requires_exactly_one_mode() -> None:
    with pytest.raises(SystemExit) as no_mode:
        watchlist_main._build_parser().parse_args([])
    assert no_mode.value.code == 2

    with pytest.raises(SystemExit) as both_modes:
        watchlist_main._build_parser().parse_args(["--collect", "--analyze"])
    assert both_modes.value.code == 2

    with pytest.raises(SystemExit) as invalid_profile:
        watchlist_main._build_parser().parse_args(
            ["--analyze", "--key-profile", "invalid"]
        )
    assert invalid_profile.value.code == 2


def test_analyze_requires_profile_and_collect_rejects_profile(monkeypatch) -> None:
    monkeypatch.setattr(watchlist_main, "Settings", FakeSettings)
    with pytest.raises(SystemExit) as missing_profile:
        watchlist_main.main(["--analyze"])
    assert missing_profile.value.code == 2

    with pytest.raises(SystemExit) as collect_profile:
        watchlist_main.main(["--collect", "--key-profile", "test"])
    assert collect_profile.value.code == 2


def test_collect_prints_success_to_stdout_and_returns_zero(monkeypatch, capsys) -> None:
    monkeypatch.setattr(watchlist_main, "Settings", FakeSettings)
    monkeypatch.setattr(
        watchlist_main,
        "_run_collect",
        lambda settings, symbols: [_collect_success(symbol) for symbol in symbols],
    )

    assert watchlist_main.main(["--collect"]) == 0
    output = capsys.readouterr()
    assert "Status: SUCCESS" in output.out
    assert "Price: 101.00 USD" in output.out
    assert "Saved: yes" in output.out
    assert output.err == ""


def test_collect_failure_uses_stderr_and_nonzero_exit(monkeypatch, capsys) -> None:
    monkeypatch.setattr(watchlist_main, "Settings", FakeSettings)
    failure = WatchlistCollectResult(
        symbol="PLTR:NASDAQ",
        status=WatchlistCollectStatus.FAILED,
        error_stage=WatchlistCollectErrorStage.COLLECTION,
        error_message="COLLECTION failed: RuntimeError",
    )
    monkeypatch.setattr(
        watchlist_main,
        "_run_collect",
        lambda settings, symbols: [_collect_success("NVDA:NASDAQ"), failure],
    )

    assert watchlist_main.main(["--collect"]) == 1
    output = capsys.readouterr()
    assert "Status: SUCCESS" in output.out
    assert "Status: FAILED" in output.err
    assert "COLLECTION failed: RuntimeError" in output.err


def test_storage_failure_reports_collected_but_not_saved(monkeypatch, capsys) -> None:
    monkeypatch.setattr(watchlist_main, "Settings", FakeSettings)
    failure = WatchlistCollectResult(
        symbol="NVDA:NASDAQ",
        status=WatchlistCollectStatus.FAILED,
        stock_price=_stock_price("NVDA:NASDAQ"),
        error_stage=WatchlistCollectErrorStage.STORAGE,
        error_message="STORAGE failed: RuntimeError",
    )
    monkeypatch.setattr(watchlist_main, "_run_collect", lambda settings, symbols: [failure])

    assert watchlist_main.main(["--collect"]) == 1
    output = capsys.readouterr()
    assert "Collected: yes" in output.err
    assert "Saved: no" in output.err


def test_analyze_success_prints_contract_to_stdout(monkeypatch, capsys) -> None:
    monkeypatch.setattr(watchlist_main, "Settings", FakeSettings)
    monkeypatch.setattr(
        watchlist_main,
        "_run_analyze",
        lambda settings, symbols, profile: [
            WatchlistAnalysisResult(
                symbol="NVDA:NASDAQ",
                status=WatchlistAnalysisStatus.SUCCESS,
                analysis=_insight("NVDA:NASDAQ"),
            )
        ],
    )

    assert watchlist_main.main(["--analyze", "--key-profile", "test"]) == 0
    output = capsys.readouterr()
    assert "Company: Company NVDA:NASDAQ" in output.out
    assert "Movement: UP" in output.out
    assert "Price delta: +1.00" in output.out
    assert "Google Finance change: 1.00%" in output.out
    assert "News count: 0" in output.out
    assert output.err == ""


def test_analyze_movement_unavailable_is_normal_stdout_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(watchlist_main, "Settings", FakeSettings)
    unavailable = MovementUnavailable(symbol="NVDA:NASDAQ", snapshot_count=1)
    monkeypatch.setattr(
        watchlist_main,
        "_run_analyze",
        lambda settings, symbols, profile: [
            WatchlistAnalysisResult(
                symbol="NVDA:NASDAQ",
                status=WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE,
                analysis=unavailable,
            )
        ],
    )

    assert watchlist_main.main(["--analyze", "--key-profile", "test"]) == 0
    output = capsys.readouterr()
    assert "Status: MOVEMENT_UNAVAILABLE" in output.out
    assert "Snapshot count: 1" in output.out
    assert output.err == ""


def test_analyze_quota_unavailable_is_stdout_but_returns_nonzero(monkeypatch, capsys) -> None:
    monkeypatch.setattr(watchlist_main, "Settings", FakeSettings)
    monkeypatch.setattr(
        watchlist_main,
        "_run_analyze",
        lambda settings, symbols, profile: [
            WatchlistAnalysisResult(
                symbol="NVDA:NASDAQ",
                status=WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE,
                unavailable_reason=WatchlistAnalysisUnavailableReason.DAILY_QUOTA_EXHAUSTED,
                movement=_insight("NVDA:NASDAQ").movement,
                news_count=5,
            ),
            WatchlistAnalysisResult(
                symbol="PLTR:NASDAQ",
                status=WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE,
                unavailable_reason=WatchlistAnalysisUnavailableReason.DAILY_QUOTA_EXHAUSTED,
            ),
        ],
    )

    assert watchlist_main.main(["--analyze", "--key-profile", "test"]) == 1
    output = capsys.readouterr()
    assert output.out.count("Status: ANALYSIS_UNAVAILABLE") == 2
    assert "Reason: DAILY_QUOTA_EXHAUSTED" in output.out
    assert "Gemini called: yes" in output.out
    assert "Gemini called: no" in output.out
    assert output.err == ""


def test_analyze_failure_uses_stderr_and_nonzero_exit(monkeypatch, capsys) -> None:
    monkeypatch.setattr(watchlist_main, "Settings", FakeSettings)
    failure = WatchlistAnalysisResult(
        symbol="PLTR:NASDAQ",
        status=WatchlistAnalysisStatus.FAILED,
        error_stage=WatchlistAnalysisErrorStage.ANALYSIS,
        error_message="ANALYSIS failed: RuntimeError",
    )
    monkeypatch.setattr(
        watchlist_main,
        "_run_analyze",
        lambda settings, symbols, profile: [failure],
    )

    assert watchlist_main.main(["--analyze", "--key-profile", "test"]) == 1
    output = capsys.readouterr()
    assert "Status: FAILED" in output.err
    assert "ANALYSIS failed: RuntimeError" in output.err
    assert output.out == ""


def test_settings_error_is_safe_and_does_not_expose_values(monkeypatch, capsys) -> None:
    class BrokenSettings:
        def __init__(self) -> None:
            raise ValueError("GEMINI_API_KEY=secret DATABASE_URL=password")

    monkeypatch.setattr(watchlist_main, "Settings", BrokenSettings)

    assert watchlist_main.main(["--collect"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "설정 오류" in output.err
    assert "secret" not in output.err
    assert "password" not in output.err
    assert "Traceback" not in output.err


def test_collect_mode_does_not_require_gemini_key(monkeypatch, capsys) -> None:
    class CollectOnlySettings(FakeSettings):
        gemini_api_key = None

    monkeypatch.setattr(watchlist_main, "Settings", CollectOnlySettings)
    monkeypatch.setattr(
        watchlist_main,
        "_run_collect",
        lambda settings, symbols: [_collect_success("NVDA:NASDAQ")],
    )

    assert watchlist_main.main(["--collect"]) == 0
    assert "Status: SUCCESS" in capsys.readouterr().out


def test_cli_delegates_to_watchlist_application(monkeypatch) -> None:
    monkeypatch.setattr(watchlist_main, "Settings", FakeSettings)
    observed: list[tuple[list[str], object, object]] = []

    def fake_collect(symbols, collect_one, save_one):
        observed.append((list(symbols), collect_one, save_one))
        return [_collect_success("NVDA:NASDAQ")]

    monkeypatch.setattr(watchlist_main, "collect_watchlist", fake_collect)
    monkeypatch.setattr(watchlist_main, "_run_collect", lambda settings, symbols: fake_collect(
        symbols, lambda symbol: _stock_price(symbol), lambda price: None
    ))

    assert watchlist_main.main(["--collect"]) == 0
    assert observed[0][0] == SYMBOLS
