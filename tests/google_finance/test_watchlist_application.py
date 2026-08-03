"""Google Finance Watchlist application tests."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from google_finance.analysis_application import GeminiAnalysisUnavailableError
from google_finance.models import StockInsight, StockPrice
from google_finance.movement import MovementDetectionError, MovementDirection, MovementResult
from google_finance.movement_application import MovementUnavailable
from google_finance.watchlist_application import (
    WatchlistAnalysisErrorStage,
    WatchlistAnalysisResult,
    WatchlistAnalysisStatus,
    WatchlistAnalysisUnavailableReason,
    WatchlistCollectErrorStage,
    WatchlistCollectResult,
    WatchlistCollectStatus,
    analyze_watchlist,
    collect_watchlist,
)

EARLIER = datetime(2026, 7, 30, 5, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 30, 6, tzinfo=timezone.utc)
SYMBOLS = ("NVDA:NASDAQ", "PLTR:NASDAQ", "005930:KRX", "000660:KRX")


def _stock_price(symbol: str, price: str = "101.00") -> StockPrice:
    return StockPrice(
        symbol=symbol,
        name=symbol,
        current_price=Decimal(price),
        previous_close=Decimal("100.00"),
        open_price=Decimal("100.50"),
        change_percent=Decimal("1.00"),
        currency="USD",
        collected_at=LATER,
    )


def _movement(symbol: str = "NVDA:NASDAQ") -> MovementResult:
    return MovementResult(
        direction=MovementDirection.UP,
        symbol=symbol,
        latest_price=Decimal("101.00"),
        previous_price=Decimal("100.00"),
        price_delta=Decimal("1.00"),
        latest_collected_at=LATER,
        previous_collected_at=EARLIER,
    )


def _insight(symbol: str = "NVDA:NASDAQ", *, news: tuple = ()) -> StockInsight:
    return StockInsight(
        symbol=symbol,
        company_name=symbol,
        currency="USD",
        current_price=Decimal("101.00"),
        change_percent=Decimal("1.00"),
        movement=_movement(symbol),
        summary="근거를 바탕으로 요약했습니다.",
        news=news,
    )


def test_collect_watchlist_runs_all_symbols_in_input_order_and_saves_successes() -> None:
    collected: list[str] = []
    saved: list[str] = []

    def collect_one(symbol: str) -> StockPrice:
        collected.append(symbol)
        return _stock_price(symbol)

    def save_one(stock_price: StockPrice) -> None:
        saved.append(stock_price.symbol)

    results = collect_watchlist(SYMBOLS, collect_one, save_one)

    assert collected == list(SYMBOLS)
    assert saved == list(SYMBOLS)
    assert [result.symbol for result in results] == list(SYMBOLS)
    assert all(result.status is WatchlistCollectStatus.SUCCESS for result in results)


def test_collect_watchlist_continues_after_collection_failure() -> None:
    called: list[str] = []

    def collect_one(symbol: str) -> StockPrice:
        called.append(symbol)
        if symbol == "PLTR:NASDAQ":
            raise RuntimeError("secret-token collection failure")
        return _stock_price(symbol)

    results = collect_watchlist(SYMBOLS, collect_one, lambda stock_price: None)

    assert called == list(SYMBOLS)
    failed = results[1]
    assert failed.status is WatchlistCollectStatus.FAILED
    assert failed.error_stage is WatchlistCollectErrorStage.COLLECTION
    assert failed.error_message == "COLLECTION failed: RuntimeError"
    assert "secret-token" not in failed.error_message
    assert "Traceback" not in failed.error_message
    assert results[0].stock_price is not None
    assert results[2].stock_price is not None


def test_collect_watchlist_continues_after_storage_failure() -> None:
    saved: list[str] = []

    def save_one(stock_price: StockPrice) -> None:
        if stock_price.symbol == "PLTR:NASDAQ":
            raise RuntimeError("database password=secret")
        saved.append(stock_price.symbol)

    results = collect_watchlist(SYMBOLS, lambda symbol: _stock_price(symbol), save_one)

    assert saved == ["NVDA:NASDAQ", "005930:KRX", "000660:KRX"]
    assert results[1].error_stage is WatchlistCollectErrorStage.STORAGE
    assert results[1].stock_price is not None
    assert results[1].stock_price.symbol == "PLTR:NASDAQ"
    assert "secret" not in (results[1].error_message or "")


def test_collect_watchlist_returns_all_failures_without_stopping() -> None:
    called: list[str] = []

    def collect_one(symbol: str) -> StockPrice:
        called.append(symbol)
        raise RuntimeError("failed")

    results = collect_watchlist(SYMBOLS, collect_one, lambda stock_price: None)

    assert called == list(SYMBOLS)
    assert len(results) == len(SYMBOLS)
    assert all(result.status is WatchlistCollectStatus.FAILED for result in results)


def test_collect_watchlist_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="symbols must not be empty"):
        collect_watchlist([], lambda symbol: _stock_price(symbol), lambda stock_price: None)


def test_collect_result_is_immutable_and_rejects_invalid_combinations() -> None:
    result = WatchlistCollectResult(
        symbol="NVDA:NASDAQ",
        status=WatchlistCollectStatus.SUCCESS,
        stock_price=_stock_price("NVDA:NASDAQ"),
    )

    with pytest.raises(FrozenInstanceError):
        result.symbol = "PLTR:NASDAQ"  # type: ignore[misc]
    with pytest.raises(ValueError, match="successful collection"):
        WatchlistCollectResult(symbol="NVDA:NASDAQ", status=WatchlistCollectStatus.SUCCESS)


def test_analyze_watchlist_preserves_order_and_existing_insight_objects() -> None:
    insights = {symbol: _insight(symbol) for symbol in SYMBOLS}
    called: list[str] = []

    def analyze_one(symbol: str) -> StockInsight:
        called.append(symbol)
        return insights[symbol]

    results = analyze_watchlist(SYMBOLS, analyze_one)

    assert called == list(SYMBOLS)
    assert [result.symbol for result in results] == list(SYMBOLS)
    assert [result.analysis for result in results] == [insights[symbol] for symbol in SYMBOLS]
    assert all(result.status is WatchlistAnalysisStatus.SUCCESS for result in results)
    assert all(result.analysis is insights[symbol] for result, symbol in zip(results, SYMBOLS))


def test_analyze_watchlist_keeps_movement_unavailable_as_normal_result() -> None:
    unavailable = MovementUnavailable(symbol="PLTR:NASDAQ", snapshot_count=1)

    results = analyze_watchlist(
        SYMBOLS[:2],
        lambda symbol: unavailable if symbol == "PLTR:NASDAQ" else _insight(symbol),
    )

    assert results[0].status is WatchlistAnalysisStatus.SUCCESS
    assert results[1].status is WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE
    assert results[1].analysis is unavailable


def test_analyze_watchlist_treats_empty_news_insight_as_success() -> None:
    insight = _insight("NVDA:NASDAQ", news=())

    results = analyze_watchlist(("NVDA:NASDAQ",), lambda symbol: insight)

    assert results[0].status is WatchlistAnalysisStatus.SUCCESS
    assert results[0].analysis is insight


def test_analyze_watchlist_stops_after_daily_quota_and_preserves_first_context() -> None:
    calls: list[str] = []

    def analyze_one(symbol: str) -> StockInsight:
        calls.append(symbol)
        if symbol == "NVDA:NASDAQ":
            raise GeminiAnalysisUnavailableError(_movement(symbol), news_count=5)
        return _insight(symbol)

    results = analyze_watchlist(SYMBOLS, analyze_one)

    assert calls == ["NVDA:NASDAQ"]
    assert all(
        result.status is WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE for result in results
    )
    assert all(
        result.unavailable_reason is WatchlistAnalysisUnavailableReason.DAILY_QUOTA_EXHAUSTED
        for result in results
    )
    assert results[0].movement == _movement("NVDA:NASDAQ")
    assert results[0].news_count == 5
    assert results[1].movement is None
    assert results[1].news_count is None


def test_analyze_watchlist_continues_after_analysis_failure() -> None:
    called: list[str] = []

    def analyze_one(symbol: str) -> StockInsight:
        called.append(symbol)
        if symbol == "PLTR:NASDAQ":
            raise RuntimeError("provider api-key=secret")
        return _insight(symbol)

    results = analyze_watchlist(SYMBOLS, analyze_one)

    assert called == list(SYMBOLS)
    assert results[1].status is WatchlistAnalysisStatus.FAILED
    assert results[1].error_stage is WatchlistAnalysisErrorStage.ANALYSIS
    assert results[1].analysis is None
    assert results[1].error_message == "ANALYSIS failed: RuntimeError"
    assert "secret" not in results[1].error_message
    assert results[2].analysis is not None


def test_analyze_watchlist_classifies_movement_contract_error() -> None:
    def analyze_one(symbol: str) -> StockInsight:
        if symbol == "PLTR:NASDAQ":
            raise MovementDetectionError("symbols must match")
        return _insight(symbol)

    results = analyze_watchlist(SYMBOLS[:2], analyze_one)

    assert results[1].status is WatchlistAnalysisStatus.FAILED
    assert results[1].error_stage is WatchlistAnalysisErrorStage.MOVEMENT
    assert results[0].status is WatchlistAnalysisStatus.SUCCESS


def test_analyze_watchlist_returns_all_failures_without_stopping() -> None:
    called: list[str] = []

    def analyze_one(symbol: str) -> StockInsight:
        called.append(symbol)
        raise RuntimeError("failed")

    results = analyze_watchlist(SYMBOLS, analyze_one)

    assert called == list(SYMBOLS)
    assert len(results) == len(SYMBOLS)
    assert all(result.status is WatchlistAnalysisStatus.FAILED for result in results)


def test_analyze_watchlist_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="symbols must not be empty"):
        analyze_watchlist([], lambda symbol: _insight(symbol))


def test_analysis_result_is_immutable_and_rejects_invalid_combinations() -> None:
    result = WatchlistAnalysisResult(
        symbol="NVDA:NASDAQ",
        status=WatchlistAnalysisStatus.SUCCESS,
        analysis=_insight(),
    )

    with pytest.raises(FrozenInstanceError):
        result.symbol = "PLTR:NASDAQ"  # type: ignore[misc]
    with pytest.raises(ValueError, match="successful analysis"):
        WatchlistAnalysisResult(symbol="NVDA:NASDAQ", status=WatchlistAnalysisStatus.SUCCESS)
