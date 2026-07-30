"""Google Finance extraction contract tests."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from google_finance.collector import RawStockQuote
from google_finance.extraction import parse_currency, parse_percent, parse_price, parse_stock_quote

COLLECTED_AT = datetime(2026, 7, 30, 6, 0, tzinfo=timezone.utc)


def _raw_quote(**overrides: str) -> RawStockQuote:
    """Create a valid raw quote fixture."""
    values = {
        "symbol": "AAPL:NASDAQ",
        "name_text": "Apple Inc",
        "current_price_text": "$338.19",
        "currency_text": "Closed: Jul 29, 4:00 PM UTC-4 · USD",
        "previous_close_text": "Prev. close $340.08",
        "open_price_text": "Open\n$339.73",
        "change_percent_text": "-0.56%",
    }
    values.update(overrides)
    return RawStockQuote(**values)


def test_parse_stock_quote_converts_usd_values_and_uses_utc_clock() -> None:
    """A valid raw quote becomes a StockPrice with the injected UTC timestamp."""
    result = parse_stock_quote(_raw_quote(), clock=lambda: COLLECTED_AT)

    assert result.symbol == "AAPL:NASDAQ"
    assert result.name == "Apple Inc"
    assert result.current_price == Decimal("338.19")
    assert result.previous_close == Decimal("340.08")
    assert result.open_price == Decimal("339.73")
    assert result.change_percent == Decimal("-0.56")
    assert result.currency == "USD"
    assert result.collected_at == COLLECTED_AT


def test_parse_stock_quote_supports_jpy_and_grouped_numbers() -> None:
    """Currency symbols and thousands separators are normalized."""
    raw = _raw_quote(
        symbol="7203:TYO",
        name_text="Toyota Motor Corp",
        current_price_text="¥3,224.00",
        currency_text="Jul 30, 3:30 PM UTC+9 · JPY",
        previous_close_text="Prev. close ¥3,200.00",
        open_price_text="Open\n¥3,210.00",
        change_percent_text="+0.75%",
    )

    result = parse_stock_quote(raw, clock=lambda: COLLECTED_AT)

    assert result.current_price == Decimal("3224.00")
    assert result.previous_close == Decimal("3200.00")
    assert result.open_price == Decimal("3210.00")
    assert result.change_percent == Decimal("0.75")
    assert result.currency == "JPY"


@pytest.mark.parametrize("value", ["", "N/A", "$bad", "$1,2.3", "-"])
def test_parse_price_rejects_invalid_values(value: str) -> None:
    """Unavailable and malformed prices are rejected."""
    with pytest.raises((TypeError, ValueError)):
        parse_price(value, "current_price")


@pytest.mark.parametrize("value", ["", "N/A", "1.2", "abc%", "+%"])
def test_parse_percent_rejects_invalid_values(value: str) -> None:
    """Unavailable and malformed percentages are rejected."""
    with pytest.raises(ValueError):
        parse_percent(value)


def test_parse_currency_requires_one_explicit_currency_code() -> None:
    """Currency is taken from an explicit code rather than a price symbol."""
    assert parse_currency("Closed · USD") == "USD"
    assert parse_currency("Closed:\u202fJul 29 · \u00a0 USD") == "USD"

    with pytest.raises(ValueError):
        parse_currency("Closed · USD · JPY")

    with pytest.raises(ValueError):
        parse_currency("Closed $338.19")


def test_parse_stock_quote_requires_timezone_aware_clock() -> None:
    """A naive collection timestamp cannot enter the model contract."""
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_stock_quote(_raw_quote(), clock=lambda: datetime(2026, 7, 30, 6, 0))
