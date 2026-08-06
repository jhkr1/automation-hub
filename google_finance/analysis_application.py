"""Application flow for analyzing stored Google Finance movement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from google_finance.analysis_generator import INSUFFICIENT_EVIDENCE_REASON
from google_finance.batch_analysis import StockAnalysisBatchItem
from google_finance.collector import validate_symbol
from google_finance.models import StockInsight, StockNewsArticle, StockPrice
from google_finance.movement import MovementResult, detect_movement
from google_finance.movement_application import MovementUnavailable
from google_finance.storage import StockQuoteStorage
from llm_runtime.exceptions import LlmDailyQuotaExceededError

if TYPE_CHECKING:
    from google_finance.watchlist_application import WatchlistAnalysisResult


class StockNewsProvider(Protocol):
    """News search contract required by the analysis application."""

    def search(self, company_name: str, limit: int = 5) -> list[StockNewsArticle]:
        """Return recent news for one company."""


class StockAnalysisGenerator(Protocol):
    """Summary generation contract required by the analysis application."""

    def generate_summary(
        self,
        stock_price: StockPrice,
        movement: MovementResult,
        articles: list[StockNewsArticle],
    ) -> str:
        """Generate a summary from validated quote, movement, and news."""


class StockAnalysisBatchGenerator(Protocol):
    """Batch summary generation contract owned by Google Finance."""

    def generate_summaries(
        self,
        items: list[StockAnalysisBatchItem],
    ) -> dict[str, str]:
        """Generate one strictly mapped summary per eligible symbol."""


class GeminiAnalysisUnavailableError(RuntimeError):
    """Preserve analysis context when Gemini daily quota is exhausted."""

    def __init__(self, movement: MovementResult, news_count: int) -> None:
        self.movement = movement
        self.news_count = news_count
        super().__init__("Gemini analysis unavailable: daily quota exhausted")


def analyze_stored_quote(
    storage: StockQuoteStorage,
    news_provider: StockNewsProvider,
    generator: StockAnalysisGenerator,
    symbol: str,
    *,
    news_limit: int = 5,
) -> StockInsight | MovementUnavailable:
    """Analyze the latest two stored snapshots for one symbol."""
    normalized_symbol = validate_symbol(symbol)
    snapshots = storage.get_latest_two(normalized_symbol)
    if len(snapshots) < 2:
        return MovementUnavailable(symbol=normalized_symbol, snapshot_count=len(snapshots))

    latest = snapshots[0]
    previous = snapshots[1]
    movement = detect_movement(latest=latest, previous=previous)
    articles = news_provider.search(latest.name, limit=news_limit)
    if articles:
        try:
            summary = generator.generate_summary(latest, movement, articles)
        except LlmDailyQuotaExceededError as exc:
            raise GeminiAnalysisUnavailableError(movement, len(articles)) from exc
    else:
        summary = INSUFFICIENT_EVIDENCE_REASON
    return StockInsight(
        symbol=latest.symbol,
        company_name=latest.name,
        currency=latest.currency,
        current_price=latest.current_price,
        change_percent=latest.change_percent,
        movement=movement,
        summary=summary,
        news=tuple(articles),
        generated_at=datetime.now(timezone.utc),
    )


@dataclass(frozen=True)
class _PreparedBatchAnalysis:
    """Prepared context retained until the single Batch call completes."""

    item: StockAnalysisBatchItem
    stock_price: StockPrice
    movement: MovementResult
    articles: tuple[StockNewsArticle, ...]


def _snapshot_change_percent(movement: MovementResult) -> Decimal | None:
    """Calculate the change between two snapshots when the base is non-zero."""
    if movement.previous_price == 0:
        return None
    return movement.price_delta / movement.previous_price * Decimal("100")


def _build_insight(
    prepared: _PreparedBatchAnalysis,
    summary: str,
) -> StockInsight:
    """Build the existing user-facing insight DTO from Batch context."""
    stock_price = prepared.stock_price
    return StockInsight(
        symbol=stock_price.symbol,
        company_name=stock_price.name,
        currency=stock_price.currency,
        current_price=stock_price.current_price,
        change_percent=stock_price.change_percent,
        movement=prepared.movement,
        summary=summary,
        news=prepared.articles,
        generated_at=datetime.now(timezone.utc),
    )


def analyze_stored_quotes_batch(
    storage: StockQuoteStorage,
    news_provider: StockNewsProvider,
    batch_generator: StockAnalysisBatchGenerator,
    symbols: list[str] | tuple[str, ...],
    *,
    news_limit: int = 5,
) -> list["WatchlistAnalysisResult"]:
    """Analyze eligible Watchlist symbols with at most one Batch Runtime call.

    Symbols without two snapshots or news never enter the Batch. A Batch failure
    is applied to every eligible symbol and never triggers individual fallback
    calls.
    """
    from google_finance.watchlist_application import (
        WatchlistAnalysisErrorStage,
        WatchlistAnalysisResult,
        WatchlistAnalysisStatus,
        WatchlistAnalysisUnavailableReason,
    )

    prepared: list[_PreparedBatchAnalysis] = []
    results: dict[str, object] = {}
    ordered_symbols: list[str] = []
    for raw_symbol in symbols:
        symbol = validate_symbol(raw_symbol)
        if symbol in ordered_symbols:
            raise ValueError("Watchlist symbols must be unique")
        ordered_symbols.append(symbol)
        try:
            snapshots = storage.get_latest_two(symbol)
            if len(snapshots) < 2:
                results[symbol] = WatchlistAnalysisResult(
                    symbol=symbol,
                    status=WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE,
                    analysis=MovementUnavailable(symbol=symbol, snapshot_count=len(snapshots)),
                )
                continue
            latest, previous = snapshots[0], snapshots[1]
            movement = detect_movement(latest=latest, previous=previous)
            articles = tuple(news_provider.search(latest.name, limit=news_limit))
            if not articles:
                results[symbol] = WatchlistAnalysisResult(
                    symbol=symbol,
                    status=WatchlistAnalysisStatus.SUCCESS,
                    analysis=StockInsight(
                        symbol=latest.symbol,
                        company_name=latest.name,
                        currency=latest.currency,
                        current_price=latest.current_price,
                        change_percent=latest.change_percent,
                        movement=movement,
                        summary=INSUFFICIENT_EVIDENCE_REASON,
                        news=(),
                        generated_at=datetime.now(timezone.utc),
                    ),
                )
                continue
            prepared.append(
                _PreparedBatchAnalysis(
                    item=StockAnalysisBatchItem(
                        symbol=latest.symbol,
                        company_name=latest.name,
                        price=latest.current_price,
                        currency=latest.currency,
                        snapshot_delta=movement.price_delta,
                        snapshot_change_percent=_snapshot_change_percent(movement),
                        snapshot_movement=movement.direction,
                        google_finance_change_percent=latest.change_percent,
                        articles=articles,
                    ),
                    stock_price=latest,
                    movement=movement,
                    articles=articles,
                )
            )
        except Exception as exc:  # noqa: BLE001 - isolate one symbol at the application boundary
            results[symbol] = WatchlistAnalysisResult(
                symbol=symbol,
                status=WatchlistAnalysisStatus.FAILED,
                error_stage=WatchlistAnalysisErrorStage.ANALYSIS,
                error_message=f"ANALYSIS failed: {type(exc).__name__}",
            )

    if prepared:
        try:
            summaries = batch_generator.generate_summaries([entry.item for entry in prepared])
        except LlmDailyQuotaExceededError:
            for entry in prepared:
                results[entry.item.symbol] = WatchlistAnalysisResult(
                    symbol=entry.item.symbol,
                    status=WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE,
                    unavailable_reason=WatchlistAnalysisUnavailableReason.DAILY_QUOTA_EXHAUSTED,
                    movement=entry.movement,
                    news_count=len(entry.articles),
                )
        except Exception as exc:  # noqa: BLE001 - one Batch failure applies to all eligible symbols
            for entry in prepared:
                results[entry.item.symbol] = WatchlistAnalysisResult(
                    symbol=entry.item.symbol,
                    status=WatchlistAnalysisStatus.FAILED,
                    error_stage=WatchlistAnalysisErrorStage.ANALYSIS,
                    error_message=f"ANALYSIS failed: {type(exc).__name__}",
                )
        else:
            for entry in prepared:
                try:
                    results[entry.item.symbol] = WatchlistAnalysisResult(
                        symbol=entry.item.symbol,
                        status=WatchlistAnalysisStatus.SUCCESS,
                        analysis=_build_insight(entry, summaries[entry.item.symbol]),
                    )
                except Exception as exc:  # noqa: BLE001 - preserve per-symbol output contract
                    results[entry.item.symbol] = WatchlistAnalysisResult(
                        symbol=entry.item.symbol,
                        status=WatchlistAnalysisStatus.FAILED,
                        error_stage=WatchlistAnalysisErrorStage.ANALYSIS,
                        error_message=f"ANALYSIS failed: {type(exc).__name__}",
                    )

    return [results[symbol] for symbol in ordered_symbols]
