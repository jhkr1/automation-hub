"""Consistent display formatting for dashboard DTO values."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from automation_dashboard.queries.google_finance import SEOUL_TZ

MISSING_VALUE = "—"


def _decimal_text(value: Decimal) -> str:
    """Format a Decimal with grouping while retaining meaningful precision."""
    text = format(value, "f")
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    integer, separator, fraction = text.partition(".")
    grouped_integer = f"{int(integer):,}"
    trimmed_fraction = fraction.rstrip("0") if separator else ""
    formatted = grouped_integer if not trimmed_fraction else f"{grouped_integer}.{trimmed_fraction}"
    return f"-{formatted}" if negative and formatted != "0" else formatted


def format_integer(value: int | None) -> str:
    """Return a grouped integer or the shared unavailable marker."""
    return MISSING_VALUE if value is None else f"{value:,}"


def format_price(value: Decimal | None, currency: str | None) -> str:
    """Format a persisted price without converting Decimal through float."""
    if value is None or not currency:
        return MISSING_VALUE
    return f"{_decimal_text(value)} {currency}"


def format_signed_price(value: Decimal | None, currency: str | None) -> str:
    """Format a price delta with an explicit sign for non-zero values."""
    if value is None or not currency:
        return MISSING_VALUE
    if value > 0:
        return f"+{_decimal_text(value)} {currency}"
    return format_price(value, currency)


def format_percent(value: Decimal | None) -> str:
    """Format a percentage with a plus sign only when it is positive."""
    if value is None:
        return MISSING_VALUE
    formatted = _decimal_text(value)
    if value > 0:
        formatted = f"+{formatted}"
    return f"{formatted}%"


def format_kst_datetime(value: datetime | None) -> str:
    """Render UTC-naive or aware timestamps as a concise Seoul display value."""
    if value is None:
        return MISSING_VALUE
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return utc_value.astimezone(SEOUL_TZ).strftime("%Y-%m-%d %H:%M KST")


def format_duration(value: timedelta | None) -> str:
    """Render an elapsed duration in concise Korean display units."""
    if value is None:
        return MISSING_VALUE
    total_seconds = max(0, int(value.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}시간 {minutes}분"
    if minutes:
        return f"{minutes}분 {seconds}초"
    return f"{seconds}초"


def format_file_size(value: int | None) -> str:
    """Render a byte count as a compact binary file size."""
    if value is None:
        return MISSING_VALUE
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def format_repository_location(value: Path) -> str:
    """Show a repository name instead of exposing an absolute local path."""
    return value.name or MISSING_VALUE
