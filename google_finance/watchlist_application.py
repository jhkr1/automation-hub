"""Application orchestration for sequential Google Finance Watchlist runs."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from google_finance.models import StockInsight, StockPrice
from google_finance.movement import MovementDetectionError
from google_finance.movement_application import MovementUnavailable


class WatchlistCollectStatus(str, Enum):
    """Possible states for one collection result."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class WatchlistCollectErrorStage(str, Enum):
    """Collection boundaries that can be distinguished safely."""

    COLLECTION = "COLLECTION"
    STORAGE = "STORAGE"


class WatchlistAnalysisStatus(str, Enum):
    """Possible states for one analysis result."""

    SUCCESS = "SUCCESS"
    MOVEMENT_UNAVAILABLE = "MOVEMENT_UNAVAILABLE"
    FAILED = "FAILED"


class WatchlistAnalysisErrorStage(str, Enum):
    """Analysis boundaries exposed by the current single-symbol contract."""

    MOVEMENT = "MOVEMENT"
    ANALYSIS = "ANALYSIS"


@dataclass(frozen=True)
class WatchlistCollectResult:
    """Immutable result for collecting and saving one Watchlist symbol."""

    symbol: str
    status: WatchlistCollectStatus
    stock_price: StockPrice | None = None
    error_stage: WatchlistCollectErrorStage | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Reject combinations that do not describe a valid result state."""
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.status is WatchlistCollectStatus.SUCCESS:
            if self.stock_price is None or self.error_stage is not None or self.error_message:
                raise ValueError("successful collection must contain only stock_price")
        elif self.status is WatchlistCollectStatus.FAILED:
            if self.error_stage is None or not self.error_message:
                raise ValueError("failed collection must contain an error")
            if (
                self.error_stage is WatchlistCollectErrorStage.COLLECTION
                and self.stock_price is not None
            ):
                raise ValueError("collection failure must not contain stock_price")
            if self.error_stage is WatchlistCollectErrorStage.STORAGE and self.stock_price is None:
                raise ValueError("storage failure must preserve stock_price")
        else:
            raise TypeError("unsupported collection status")


@dataclass(frozen=True)
class WatchlistAnalysisResult:
    """Immutable result for analyzing one stored Watchlist symbol."""

    symbol: str
    status: WatchlistAnalysisStatus
    analysis: StockInsight | MovementUnavailable | None = None
    error_stage: WatchlistAnalysisErrorStage | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Reject combinations that do not describe a valid result state."""
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.status is WatchlistAnalysisStatus.SUCCESS:
            if not isinstance(self.analysis, StockInsight):
                raise ValueError("successful analysis must contain StockInsight")
            if self.error_stage is not None or self.error_message:
                raise ValueError("successful analysis must not contain an error")
        elif self.status is WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE:
            if not isinstance(self.analysis, MovementUnavailable):
                raise ValueError("unavailable analysis must contain MovementUnavailable")
            if self.error_stage is not None or self.error_message:
                raise ValueError("unavailable analysis must not contain an error")
        elif self.status is WatchlistAnalysisStatus.FAILED:
            if self.analysis is not None or self.error_stage is None or not self.error_message:
                raise ValueError("failed analysis must contain an error")
        else:
            raise TypeError("unsupported analysis status")


CollectOne = Callable[[str], StockPrice]
SaveOne = Callable[[StockPrice], None]
AnalyzeOne = Callable[[str], StockInsight | MovementUnavailable]


def _require_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Materialize a non-empty, already-canonical Watchlist sequence."""
    materialized = tuple(symbols)
    if not materialized:
        raise ValueError("Watchlist symbols must not be empty")
    if any(not isinstance(symbol, str) or not symbol.strip() for symbol in materialized):
        raise ValueError("Watchlist symbols must contain non-empty strings")
    return materialized


def _safe_error_message(stage: Enum, error: Exception) -> str:
    """Keep only a non-sensitive stage and exception type in batch results."""
    return f"{stage.value} failed: {type(error).__name__}"


def collect_watchlist(
    symbols: Sequence[str],
    collect_one: CollectOne,
    save_one: SaveOne,
) -> list[WatchlistCollectResult]:
    """Collect and save symbols sequentially, isolating each symbol failure."""
    results: list[WatchlistCollectResult] = []
    for symbol in _require_symbols(symbols):
        try:
            stock_price = collect_one(symbol)
        except Exception as exc:  # noqa: BLE001 - isolate one symbol at the application boundary
            results.append(
                WatchlistCollectResult(
                    symbol=symbol,
                    status=WatchlistCollectStatus.FAILED,
                    error_stage=WatchlistCollectErrorStage.COLLECTION,
                    error_message=_safe_error_message(WatchlistCollectErrorStage.COLLECTION, exc),
                )
            )
            continue

        try:
            save_one(stock_price)
        except Exception as exc:  # noqa: BLE001 - isolate one symbol at the application boundary
            results.append(
                WatchlistCollectResult(
                    symbol=symbol,
                    status=WatchlistCollectStatus.FAILED,
                    stock_price=stock_price,
                    error_stage=WatchlistCollectErrorStage.STORAGE,
                    error_message=_safe_error_message(WatchlistCollectErrorStage.STORAGE, exc),
                )
            )
            continue

        results.append(
            WatchlistCollectResult(
                symbol=symbol,
                status=WatchlistCollectStatus.SUCCESS,
                stock_price=stock_price,
            )
        )
    return results


def analyze_watchlist(
    symbols: Sequence[str],
    analyze_one: AnalyzeOne,
) -> list[WatchlistAnalysisResult]:
    """Analyze symbols sequentially through the existing single-symbol application."""
    results: list[WatchlistAnalysisResult] = []
    for symbol in _require_symbols(symbols):
        try:
            analysis = analyze_one(symbol)
        except MovementDetectionError as exc:
            results.append(
                WatchlistAnalysisResult(
                    symbol=symbol,
                    status=WatchlistAnalysisStatus.FAILED,
                    error_stage=WatchlistAnalysisErrorStage.MOVEMENT,
                    error_message=_safe_error_message(WatchlistAnalysisErrorStage.MOVEMENT, exc),
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 - isolate one symbol at the application boundary
            results.append(
                WatchlistAnalysisResult(
                    symbol=symbol,
                    status=WatchlistAnalysisStatus.FAILED,
                    error_stage=WatchlistAnalysisErrorStage.ANALYSIS,
                    error_message=_safe_error_message(WatchlistAnalysisErrorStage.ANALYSIS, exc),
                )
            )
            continue

        if isinstance(analysis, MovementUnavailable):
            results.append(
                WatchlistAnalysisResult(
                    symbol=symbol,
                    status=WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE,
                    analysis=analysis,
                )
            )
        elif isinstance(analysis, StockInsight):
            results.append(
                WatchlistAnalysisResult(
                    symbol=symbol,
                    status=WatchlistAnalysisStatus.SUCCESS,
                    analysis=analysis,
                )
            )
        else:
            results.append(
                WatchlistAnalysisResult(
                    symbol=symbol,
                    status=WatchlistAnalysisStatus.FAILED,
                    error_stage=WatchlistAnalysisErrorStage.ANALYSIS,
                    error_message="ANALYSIS returned an unsupported result",
                )
            )
    return results
