"""google_finance 데이터 모델.

파이프라인에서 모듈 간 데이터를 전달하는 데 사용하는
dataclass를 정의한다.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google_finance.movement import MovementResult

MAX_STOCK_INSIGHT_SUMMARY_LENGTH = 400
MAX_STOCK_INSIGHT_SUMMARY_SENTENCES = 2


def count_stock_insight_sentences(summary: str) -> int:
    """Count sentences separated by terminal punctuation and whitespace."""
    normalized = summary.strip()
    if not normalized:
        return 0
    return len(
        [
            part
            for part in re.split(r"(?<=[.!?。！？])\s+", normalized)
            if part.strip()
        ]
    )


@dataclass(frozen=True)
class RawStockQuote:
    """Raw strings collected from one rendered Google Finance quote."""

    symbol: str
    name_text: str
    current_price_text: str
    currency_text: str
    previous_close_text: str
    open_price_text: str
    change_percent_text: str


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def _validate_quote_fields(
    *,
    symbol: str,
    name: str,
    current_price: Decimal,
    previous_close: Decimal,
    open_price: Decimal,
    change_percent: Decimal,
    currency: str,
) -> None:
    """Validate common quote invariants shared by quote models."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must not be empty")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must not be empty")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("currency must not be empty")
    numeric_values = (current_price, previous_close, open_price, change_percent)
    if not all(isinstance(value, Decimal) and value.is_finite() for value in numeric_values):
        raise TypeError("quote numeric fields must be finite Decimal values")
    if any(value < 0 for value in (current_price, previous_close, open_price)):
        raise ValueError("quote prices must be non-negative")


@dataclass
class StockPrice:
    """Google Finance에서 수집한 종목 시세 1건."""

    symbol: str
    name: str
    current_price: Decimal
    previous_close: Decimal
    open_price: Decimal
    change_percent: Decimal
    currency: str
    collected_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        """Validate fields that are required for an unambiguous quote."""
        _validate_quote_fields(
            symbol=self.symbol,
            name=self.name,
            current_price=self.current_price,
            previous_close=self.previous_close,
            open_price=self.open_price,
            change_percent=self.change_percent,
            currency=self.currency,
        )
        if self.collected_at.tzinfo is None or self.collected_at.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")


@dataclass(frozen=True)
class StockNewsArticle:
    """News context article used by Google Finance analysis."""

    title: str
    url: str
    source: str | None = None
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate the fields retained as analysis evidence."""
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("news title must not be empty")
        if not isinstance(self.url, str) or not self.url.strip():
            raise ValueError("news url must not be empty")
        if self.published_at is not None and (
            self.published_at.tzinfo is None or self.published_at.utcoffset() is None
        ):
            raise ValueError("news published_at must be timezone-aware")


@dataclass
class StockReport:
    """최종 결과물. 종목 시세 + LLM 등락 분석을 합친 보고서 1건."""

    symbol: str
    name: str
    current_price: Decimal
    previous_close: Decimal
    open_price: Decimal
    change_percent: Decimal
    reason: str
    collected_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class StockInsight:
    """Immutable user-facing analysis result for one stored quote movement."""

    symbol: str
    company_name: str
    currency: str
    current_price: Decimal
    change_percent: Decimal
    movement: "MovementResult"
    summary: str
    news: tuple[StockNewsArticle, ...]
    generated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        """Validate the output contract without adding analysis rules to the domain."""
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("insight symbol must not be empty")
        if not isinstance(self.company_name, str) or not self.company_name.strip():
            raise ValueError("insight company_name must not be empty")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise ValueError("insight currency must not be empty")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("insight summary must not be empty")
        if len(self.summary.strip()) > MAX_STOCK_INSIGHT_SUMMARY_LENGTH:
            raise ValueError(
                "insight summary must not exceed "
                f"{MAX_STOCK_INSIGHT_SUMMARY_LENGTH} characters"
            )
        if count_stock_insight_sentences(self.summary) > MAX_STOCK_INSIGHT_SUMMARY_SENTENCES:
            raise ValueError(
                "insight summary must not exceed "
                f"{MAX_STOCK_INSIGHT_SUMMARY_SENTENCES} sentences"
            )
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("insight generated_at must be timezone-aware")
        from google_finance.movement import MovementResult

        if not isinstance(self.movement, MovementResult):
            raise TypeError("insight movement must be a MovementResult")
        if not isinstance(self.news, tuple) or not all(
            isinstance(article, StockNewsArticle) for article in self.news
        ):
            raise TypeError("insight news must be a tuple of StockNewsArticle")
