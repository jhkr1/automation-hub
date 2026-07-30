"""Pure normalization and validation for Google Finance quote strings."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from google_finance.models import RawStockQuote, StockPrice

CURRENCY_PATTERN = re.compile(r"[·•][^\S\r\n]*([A-Z]{3})", re.MULTILINE)
NUMBER_PATTERN = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
CURRENCY_NUMBER_PATTERN = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?$")
CURRENCY_SYMBOLS = "$€£¥₩₹"
QuoteClock = Callable[[], datetime]


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def _required_text(value: str, field_name: str) -> str:
    """Return trimmed text or raise a field-specific validation error."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or normalized.upper() == "N/A":
        raise ValueError(f"{field_name} is empty or unavailable")
    return normalized


def parse_price(value: str, field_name: str) -> Decimal:
    """Parse a displayed price without losing decimal precision."""
    normalized = _required_text(value, field_name)
    normalized = re.sub(r"^(?:Prev\.\s*close|Open)\s*", "", normalized, flags=re.IGNORECASE)
    for symbol in CURRENCY_SYMBOLS:
        normalized = normalized.replace(symbol, "")
    normalized = normalized.strip()
    if "," in normalized:
        valid_number = CURRENCY_NUMBER_PATTERN.fullmatch(normalized)
    else:
        valid_number = NUMBER_PATTERN.fullmatch(normalized)
    if not valid_number:
        raise ValueError(f"{field_name} is not a valid price: {value!r}")

    normalized = normalized.replace(",", "")

    try:
        decimal_value = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} is not a valid price: {value!r}") from exc
    if not decimal_value.is_finite() or decimal_value < 0:
        raise ValueError(f"{field_name} is not a valid non-negative price: {value!r}")
    return decimal_value


def parse_percent(value: str) -> Decimal:
    """Parse a signed percentage such as ``-0.56%``."""
    normalized = _required_text(value, "change_percent")
    if not normalized.endswith("%"):
        raise ValueError(f"change_percent is missing percent sign: {value!r}")
    number = normalized[:-1].strip()
    if not NUMBER_PATTERN.fullmatch(number):
        raise ValueError(f"change_percent is not valid: {value!r}")
    try:
        return Decimal(number)
    except InvalidOperation as exc:
        raise ValueError(f"change_percent is not valid: {value!r}") from exc


def parse_currency(value: str) -> str:
    """Extract an explicit three-letter currency code from quote metadata."""
    normalized = _required_text(value, "currency")
    matches = CURRENCY_PATTERN.findall(normalized)
    if not matches:
        raise ValueError("currency code was not found")
    currencies = set(matches)
    if len(currencies) != 1:
        raise ValueError(f"currency metadata is ambiguous: {sorted(currencies)!r}")
    return matches[0]


def parse_stock_quote(
    raw_quote: RawStockQuote,
    *,
    clock: QuoteClock = _utc_now,
) -> StockPrice:
    """Normalize one raw quote and convert it to ``StockPrice``."""
    if not isinstance(raw_quote, RawStockQuote):
        raise TypeError("raw_quote must be a RawStockQuote")
    collected_at = clock()
    if collected_at.tzinfo is None or collected_at.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")

    name = _required_text(raw_quote.name_text, "name")
    return StockPrice(
        symbol=_required_text(raw_quote.symbol, "symbol"),
        name=name,
        current_price=parse_price(raw_quote.current_price_text, "current_price"),
        previous_close=parse_price(raw_quote.previous_close_text, "previous_close"),
        open_price=parse_price(raw_quote.open_price_text, "open_price"),
        change_percent=parse_percent(raw_quote.change_percent_text),
        currency=parse_currency(raw_quote.currency_text),
        collected_at=collected_at,
    )
