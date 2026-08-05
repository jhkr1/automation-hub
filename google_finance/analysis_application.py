"""Application flow for analyzing stored Google Finance movement."""

from datetime import datetime, timezone
from typing import Protocol

from google_finance.analysis_generator import INSUFFICIENT_EVIDENCE_REASON
from google_finance.collector import validate_symbol
from google_finance.models import StockInsight, StockNewsArticle, StockPrice
from google_finance.movement import MovementResult, detect_movement
from google_finance.movement_application import MovementUnavailable
from google_finance.storage import StockQuoteStorage
from llm_runtime.exceptions import LlmDailyQuotaExceededError


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
