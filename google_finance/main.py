"""Command-line entry point for one Google Finance quote."""

import argparse
import sys
from decimal import Decimal

from google_finance.collector import collect_stock_quote
from google_finance.config import Settings
from google_finance.models import StockPrice
from google_finance.pipeline import StockPricePipeline


def _build_parser() -> argparse.ArgumentParser:
    """Build the single-symbol command-line parser."""
    parser = argparse.ArgumentParser(description="Display one Google Finance quote.")
    parser.add_argument("symbol", help="exchange-qualified symbol, for example AAPL:NASDAQ")
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


def main(argv: list[str] | None = None) -> int:
    """Collect one quote and return a process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        settings = Settings()
        _print_stock_price(build_pipeline(settings).run(args.symbol))
    except Exception as exc:  # noqa: BLE001 - process boundary converts failure to exit code
        print(f"[google_finance] 실행 실패: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
