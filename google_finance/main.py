"""Command-line entry point for one Google Finance quote."""

import argparse
import sys
from decimal import Decimal

from google_finance.collector import collect_stock_quote
from google_finance.config import Settings
from google_finance.models import StockPrice
from google_finance.movement import MovementResult
from google_finance.pipeline import StockPricePipeline


def _build_parser() -> argparse.ArgumentParser:
    """Build the single-symbol command-line parser."""
    parser = argparse.ArgumentParser(description="Display one Google Finance quote.")
    parser.add_argument("symbol", help="exchange-qualified symbol, for example AAPL:NASDAQ")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--save-db",
        action="store_true",
        help="append the collected quote to the configured MySQL database",
    )
    mode_group.add_argument(
        "--show-movement",
        action="store_true",
        help="show movement between the latest stored snapshots",
    )
    return parser


def _format_price(value: Decimal) -> str:
    """Format a model price without depending on the process locale."""
    return f"{value:.2f}"


def build_pipeline(settings: Settings) -> StockPricePipeline:
    """Compose the production collector and application pipeline."""
    return StockPricePipeline(
        lambda symbol: collect_stock_quote(symbol, locale=settings.google_finance_locale)
    )


def _print_stock_price(stock_price: StockPrice) -> None:
    """Print a stable human-readable quote result."""
    print(f"Symbol: {stock_price.symbol}")
    print(f"Name: {stock_price.name}")
    print(f"Current price: {_format_price(stock_price.current_price)} {stock_price.currency}")
    print(f"Previous close: {_format_price(stock_price.previous_close)} {stock_price.currency}")
    print(f"Open price: {_format_price(stock_price.open_price)} {stock_price.currency}")
    print(f"Change: {stock_price.change_percent:.2f}%")
    print(f"Collected at: {stock_price.collected_at.isoformat()}")


def _print_movement_result(result: MovementResult) -> None:
    """Print a stable human-readable snapshot movement result."""
    print(f"Symbol: {result.symbol}")
    print(f"Movement: {result.direction.value}")
    print(f"Previous price: {_format_price(result.previous_price)}")
    print(f"Latest price: {_format_price(result.latest_price)}")
    print(f"Price delta: {result.price_delta:+.2f}")
    print(f"Previous collected at: {result.previous_collected_at.isoformat()}")
    print(f"Latest collected at: {result.latest_collected_at.isoformat()}")


def _print_movement_unavailable(symbol: str, snapshot_count: int) -> None:
    """Print why a stored movement comparison cannot be performed."""
    noun = "snapshot" if snapshot_count == 1 else "snapshots"
    print(
        f"Symbol: {symbol}\n"
        f"Movement unavailable: {snapshot_count} {noun} found; at least 2 are required."
    )


def _run_movement(symbol: str) -> None:
    """Look up stored snapshots and print their movement without collecting a quote."""
    from google_finance import movement_application

    result = movement_application.lookup_movement(
        movement_application.StockQuoteStorage(),
        symbol,
    )
    if isinstance(result, MovementResult):
        _print_movement_result(result)
    elif isinstance(result, movement_application.MovementUnavailable):
        _print_movement_unavailable(result.symbol, result.snapshot_count)
    else:
        raise TypeError("movement application returned an unsupported result")


def main(argv: list[str] | None = None) -> int:
    """Collect one quote and return a process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        if args.show_movement:
            _run_movement(args.symbol)
            return 0

        settings = Settings()
        stock_price = build_pipeline(settings).run(args.symbol)
        _print_stock_price(stock_price)
        if args.save_db:
            from google_finance.storage import StockQuoteStorage

            StockQuoteStorage().save(stock_price)
            print("Saved quote snapshot to database.")
    except Exception as exc:  # noqa: BLE001 - process boundary converts failure to exit code
        print(f"[google_finance] 실행 실패: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
