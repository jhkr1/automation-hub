"""Application orchestration for one Google Finance quote."""

from collections.abc import Callable

from google_finance.extraction import parse_stock_quote
from google_finance.models import RawStockQuote, StockPrice

RawQuoteCollector = Callable[[str], RawStockQuote]


class StockPricePipeline:
    """Connect a raw quote collector to the StockPrice model conversion."""

    def __init__(self, collector: RawQuoteCollector) -> None:
        """Initialize the pipeline with an externally created collector."""
        self._collector = collector

    def run(self, symbol: str) -> StockPrice:
        """Collect and normalize one exchange-qualified symbol."""
        return parse_stock_quote(self._collector(symbol))
