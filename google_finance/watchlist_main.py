"""Command-line entry point for sequential Google Finance Watchlist runs."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from google_finance.config import Settings
from google_finance.insight_artifact import (
    JsonGoogleFinanceInsightStorage,
    artifact_path,
    build_insight_artifact,
)
from google_finance.models import StockInsight
from google_finance.movement_application import MovementUnavailable
from google_finance.watchlist_application import (
    WatchlistAnalysisResult,
    WatchlistAnalysisStatus,
    WatchlistCollectResult,
    WatchlistCollectStatus,
    collect_watchlist,
)
from llm_runtime.models import KeyProfile
from llm_runtime.providers.gemini import GeminiProvider
from llm_runtime.quota import LocalFileQuotaLedger
from llm_runtime.runtime import LlmRuntime
from llm_runtime.settings import DEFAULT_GEMINI_MODEL


def _build_parser() -> argparse.ArgumentParser:
    """Build the mutually exclusive Watchlist mode parser."""
    parser = argparse.ArgumentParser(description="Run the configured Google Finance Watchlist.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--collect", action="store_true", help="collect and save all symbols")
    modes.add_argument("--analyze", action="store_true", help="analyze stored snapshots")
    parser.add_argument(
        "--key-profile",
        choices=(KeyProfile.PRODUCTION.value, KeyProfile.TEST.value),
        help="credential profile for --analyze",
    )
    return parser


def _format_price(value: object) -> str:
    """Format a Decimal-like price for stable CLI output."""
    return f"{value:.2f}"


def _run_collect(settings: Settings, symbols: Sequence[str]) -> list[WatchlistCollectResult]:
    """Compose the existing quote pipeline and storage for Watchlist collection."""
    from google_finance.collector import collect_stock_quote
    from google_finance.pipeline import StockPricePipeline
    from google_finance.storage import StockQuoteStorage

    pipeline = StockPricePipeline(
        lambda symbol: collect_stock_quote(symbol, locale=settings.google_finance_locale)
    )
    storage = StockQuoteStorage()
    return collect_watchlist(symbols, pipeline.run, storage.save)


def build_llm_runtime() -> LlmRuntime:
    """Compose the shared Gemini Provider and project-level quota ledger."""
    repository_root = Path(__file__).resolve().parents[1]
    return LlmRuntime(
        provider=GeminiProvider(),
        ledger=LocalFileQuotaLedger(
            repository_root / ".state" / "llm" / "quota-ledger.json"
        ),
    )


def _run_analyze(
    settings: Settings,
    symbols: Sequence[str],
    profile: KeyProfile,
) -> list[WatchlistAnalysisResult]:
    """Compose the Watchlist Batch analysis application and shared Runtime."""
    from google_finance.analysis_application import analyze_stored_quotes_batch
    from google_finance.batch_analysis import GeminiStockInsightBatchGenerator
    from google_finance.news import GoogleFinanceNewsProvider
    from google_finance.storage import StockQuoteStorage

    storage = StockQuoteStorage()
    provider = GoogleFinanceNewsProvider()
    generator = GeminiStockInsightBatchGenerator(
        runtime=build_llm_runtime(),
        profile=profile,
    )
    results = analyze_stored_quotes_batch(storage, provider, generator, list(symbols))
    _save_analysis_artifact(results, profile)
    return results


def _save_analysis_artifact(
    results: list[WatchlistAnalysisResult],
    profile: KeyProfile,
) -> None:
    """Save only a complete result set, preserving the prior artifact on failure."""
    if any(
        result.status
        in {
            WatchlistAnalysisStatus.FAILED,
            WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE,
        }
        for result in results
    ):
        return
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    artifact = build_insight_artifact(results, profile=profile, model=model)
    JsonGoogleFinanceInsightStorage().save(artifact, artifact_path(profile))


def _print_collect_result(result: WatchlistCollectResult) -> None:
    """Print one collection result to the appropriate output stream."""
    if result.status is WatchlistCollectStatus.SUCCESS:
        stock_price = result.stock_price
        assert stock_price is not None
        print(
            f"Symbol: {result.symbol}\n"
            "Status: SUCCESS\n"
            f"Price: {_format_price(stock_price.current_price)} {stock_price.currency}\n"
            f"Collected at: {stock_price.collected_at.isoformat()}\n"
            "Saved: yes"
        )
        return

    collected = "yes" if result.stock_price is not None else "no"
    print(
        f"Symbol: {result.symbol}\n"
        "Status: FAILED\n"
        f"Stage: {result.error_stage.value if result.error_stage else 'UNKNOWN'}\n"
        f"Collected: {collected}\n"
        "Saved: no\n"
        f"Error: {result.error_message or 'unknown error'}",
        file=sys.stderr,
    )


def _print_analysis_result(result: WatchlistAnalysisResult) -> None:
    """Print one analysis result to stdout or stderr according to its status."""
    if result.status is WatchlistAnalysisStatus.FAILED:
        print(
            f"Symbol: {result.symbol}\n"
            "Status: FAILED\n"
            f"Stage: {result.error_stage.value if result.error_stage else 'UNKNOWN'}\n"
            f"Error: {result.error_message or 'unknown error'}",
            file=sys.stderr,
        )
        return

    if result.status is WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE:
        reason = result.unavailable_reason.value if result.unavailable_reason else "UNKNOWN"
        print(
            f"Symbol: {result.symbol}\n"
            "Status: ANALYSIS_UNAVAILABLE\n"
            f"Reason: {reason}\n"
            f"Gemini called: {'yes' if result.movement is not None else 'no'}"
        )
        if result.movement is not None:
            print(f"Movement: {result.movement.direction.value}")
        if result.news_count is not None:
            print(f"News articles: {result.news_count}")
        return

    analysis = result.analysis
    if result.status is WatchlistAnalysisStatus.MOVEMENT_UNAVAILABLE:
        assert isinstance(analysis, MovementUnavailable)
        print(
            f"Symbol: {result.symbol}\n"
            "Status: MOVEMENT_UNAVAILABLE\n"
            f"Snapshot count: {analysis.snapshot_count}"
        )
        return

    assert isinstance(analysis, StockInsight)
    print(
        f"Symbol: {result.symbol}\n"
        "Status: SUCCESS\n"
        f"Company: {analysis.company_name}\n"
        f"Movement: {analysis.movement.direction.value}\n"
        f"Price delta: {analysis.movement.price_delta:+.2f}\n"
        f"Google Finance change: {analysis.change_percent:.2f}%\n"
        f"News count: {len(analysis.news)}\n"
        f"Summary: {analysis.summary}"
    )


def _print_settings_error() -> None:
    """Print a safe settings error without exposing configuration values."""
    print("[google_finance.watchlist] 실행 실패: 설정 오류", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Run the selected Watchlist mode and return its process exit code."""
    args = _build_parser().parse_args(argv)
    if args.collect and args.key_profile is not None:
        _build_parser().error("--key-profile is only valid with --analyze")
    if args.analyze and args.key_profile is None:
        _build_parser().error("--analyze requires --key-profile production|test")
    try:
        settings = Settings()
        symbols = settings.get_symbol_list()
        if args.collect:
            results = _run_collect(settings, symbols)
            for result in results:
                _print_collect_result(result)
            return (
                1
                if any(result.status is WatchlistCollectStatus.FAILED for result in results)
                else 0
            )

        results = _run_analyze(settings, symbols, KeyProfile(args.key_profile))
        for result in results:
            _print_analysis_result(result)
        return (
            1
            if any(
                result.status
                in {
                    WatchlistAnalysisStatus.FAILED,
                    WatchlistAnalysisStatus.ANALYSIS_UNAVAILABLE,
                }
                for result in results
            )
            else 0
        )
    except (ValidationError, ValueError):
        _print_settings_error()
        return 1
    except Exception as exc:  # noqa: BLE001 - process boundary hides external error details
        print(
            f"[google_finance.watchlist] 실행 실패: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
