"""Google Finance persistence models and domain conversion helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from google_finance.models import StockPrice

PRICE_NUMERIC = Numeric(24, 8)
PERCENT_NUMERIC = Numeric(12, 8)
DECIMAL_SCALE = 8


def _canonical_symbol(value: str) -> str:
    """Return the canonical symbol form used by persistence and queries."""
    if not isinstance(value, str):
        raise TypeError("symbol must be a string")
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty")
    return normalized


def _validate_decimal_scale(value: Decimal, field_name: str) -> None:
    """Reject values that the fixed database scale would round implicitly."""
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -DECIMAL_SCALE:
        raise ValueError(f"{field_name} supports at most {DECIMAL_SCALE} decimal places")


def _as_utc_naive(value: datetime, field_name: str) -> datetime:
    """Convert an aware datetime to the project's naive UTC DB representation."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _as_utc_aware(value: datetime, field_name: str) -> datetime:
    """Convert a DB datetime stored as UTC to an aware domain datetime."""
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(timezone.utc)
    return value.replace(tzinfo=timezone.utc)


class StockQuoteSnapshot(Base):
    """Append-only persisted Google Finance quote snapshot."""

    __tablename__ = "stock_quote_snapshots"
    __table_args__ = (
        CheckConstraint(
            "CHAR_LENGTH(TRIM(symbol)) > 0",
            name="ck_stock_quote_snapshots_symbol_nonempty",
        ),
        CheckConstraint(
            "CHAR_LENGTH(TRIM(name)) > 0",
            name="ck_stock_quote_snapshots_name_nonempty",
        ),
        CheckConstraint(
            "CHAR_LENGTH(currency) = 3",
            name="ck_stock_quote_snapshots_currency_length",
        ),
        Index(
            "ix_stock_quote_snapshots_symbol_collected_at",
            "symbol",
            "collected_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    previous_close: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    open_price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    change_percent: Mapped[Decimal] = mapped_column(PERCENT_NUMERIC, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    @classmethod
    def from_domain(cls, stock_price: StockPrice) -> StockQuoteSnapshot:
        """Create a persistence row without adding persistence fields to the domain model."""
        if not isinstance(stock_price, StockPrice):
            raise TypeError("stock_price must be a StockPrice")
        if len(stock_price.currency) != 3 or not stock_price.currency.isascii():
            raise ValueError("currency must be a three-character ASCII code")
        _validate_decimal_scale(stock_price.current_price, "current_price")
        _validate_decimal_scale(stock_price.previous_close, "previous_close")
        _validate_decimal_scale(stock_price.open_price, "open_price")
        _validate_decimal_scale(stock_price.change_percent, "change_percent")

        return cls(
            symbol=_canonical_symbol(stock_price.symbol),
            name=stock_price.name.strip(),
            currency=stock_price.currency.upper(),
            current_price=stock_price.current_price,
            previous_close=stock_price.previous_close,
            open_price=stock_price.open_price,
            change_percent=stock_price.change_percent,
            collected_at=_as_utc_naive(stock_price.collected_at, "collected_at"),
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

    def to_domain(self) -> StockPrice:
        """Convert this persistence row to the existing StockPrice contract."""
        return StockPrice(
            symbol=self.symbol,
            name=self.name,
            current_price=self.current_price,
            previous_close=self.previous_close,
            open_price=self.open_price,
            change_percent=self.change_percent,
            currency=self.currency,
            collected_at=_as_utc_aware(self.collected_at, "collected_at"),
        )
