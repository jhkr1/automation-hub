"""Read-only Google Finance snapshot queries for the dashboard."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from google_finance.db_models import StockQuoteSnapshot

SEOUL_TZ = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class LatestQuoteRow:
    """One latest persisted quote and its total snapshot count."""

    symbol: str
    name: str
    currency: str
    current_price: Decimal
    change_percent: Decimal
    collected_at: datetime
    snapshot_count: int


@dataclass(frozen=True)
class PricePoint:
    """One historical price point prepared for dashboard rendering."""

    collected_at: datetime
    current_price: Decimal
    change_percent: Decimal
    currency: str


@dataclass(frozen=True)
class SnapshotDelta:
    """A deterministic comparison of the latest two quote snapshots."""

    latest_price: Decimal
    previous_price: Decimal
    price_delta: Decimal
    absolute_delta: Decimal
    latest_collected_at: datetime
    previous_collected_at: datetime
    currency: str


def to_seoul_time(value: datetime) -> datetime:
    """Interpret naive database datetimes as UTC and return an aware Seoul time."""
    if not isinstance(value, datetime):
        raise TypeError("value must be a datetime")
    utc_value = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return utc_value.astimezone(SEOUL_TZ)


def _normalize_symbol(symbol: str) -> str:
    """Normalize a dashboard symbol parameter for the persisted canonical form."""
    if not isinstance(symbol, str):
        raise TypeError("symbol must be a string")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty")
    return normalized


def _as_utc_naive(value: datetime) -> datetime:
    """Convert a dashboard time filter to the database's naive UTC representation."""
    if not isinstance(value, datetime):
        raise TypeError("time filters must be datetimes")
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def list_latest_quotes(session: Session) -> list[LatestQuoteRow]:
    """Return one latest snapshot per symbol, sorted by canonical symbol."""
    latest = aliased(StockQuoteSnapshot)
    newer = aliased(StockQuoteSnapshot)
    snapshot_count = (
        select(func.count(StockQuoteSnapshot.id))
        .where(StockQuoteSnapshot.symbol == latest.symbol)
        .correlate(latest)
        .scalar_subquery()
    )
    statement = (
        select(
            latest.symbol,
            latest.name,
            latest.currency,
            latest.current_price,
            latest.change_percent,
            latest.collected_at,
            snapshot_count.label("snapshot_count"),
        )
        .where(
            ~exists(
                select(1).where(
                    and_(
                        newer.symbol == latest.symbol,
                        or_(
                            newer.collected_at > latest.collected_at,
                            and_(
                                newer.collected_at == latest.collected_at,
                                newer.id > latest.id,
                            ),
                        ),
                    )
                )
            )
        )
        .order_by(latest.symbol.asc())
    )
    rows = session.execute(statement).all()
    return [
        LatestQuoteRow(
            symbol=row.symbol,
            name=row.name,
            currency=row.currency,
            current_price=Decimal(row.current_price),
            change_percent=Decimal(row.change_percent),
            collected_at=to_seoul_time(row.collected_at),
            snapshot_count=int(row.snapshot_count),
        )
        for row in rows
    ]


def load_price_history(
    session: Session,
    symbol: str,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    *,
    limit: int = 50,
) -> list[PricePoint]:
    """Return the newest bounded history in ascending time and id order."""
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    normalized_symbol = _normalize_symbol(symbol)
    filters = [StockQuoteSnapshot.symbol == normalized_symbol]
    if start_at is not None:
        filters.append(StockQuoteSnapshot.collected_at >= _as_utc_naive(start_at))
    if end_at is not None:
        filters.append(StockQuoteSnapshot.collected_at <= _as_utc_naive(end_at))

    newest_first = (
        select(
            StockQuoteSnapshot.id,
            StockQuoteSnapshot.collected_at,
            StockQuoteSnapshot.current_price,
            StockQuoteSnapshot.change_percent,
            StockQuoteSnapshot.currency,
        )
        .where(*filters)
        .order_by(StockQuoteSnapshot.collected_at.desc(), StockQuoteSnapshot.id.desc())
        .limit(limit)
        .subquery()
    )
    statement = select(
        newest_first.c.collected_at,
        newest_first.c.current_price,
        newest_first.c.change_percent,
        newest_first.c.currency,
    ).order_by(newest_first.c.collected_at.asc(), newest_first.c.id.asc())
    rows = session.execute(statement).all()
    return [
        PricePoint(
            collected_at=to_seoul_time(row.collected_at),
            current_price=Decimal(row.current_price),
            change_percent=Decimal(row.change_percent),
            currency=row.currency,
        )
        for row in rows
    ]


def load_latest_delta(session: Session, symbol: str) -> SnapshotDelta | None:
    """Return the latest two-snapshot delta, or ``None`` when comparison is unavailable."""
    normalized_symbol = _normalize_symbol(symbol)
    statement = (
        select(
            StockQuoteSnapshot.current_price,
            StockQuoteSnapshot.collected_at,
            StockQuoteSnapshot.currency,
        )
        .where(StockQuoteSnapshot.symbol == normalized_symbol)
        .order_by(StockQuoteSnapshot.collected_at.desc(), StockQuoteSnapshot.id.desc())
        .limit(2)
    )
    rows = session.execute(statement).all()
    if len(rows) < 2:
        return None

    latest, previous = rows
    latest_price = Decimal(latest.current_price)
    previous_price = Decimal(previous.current_price)
    price_delta = latest_price - previous_price
    return SnapshotDelta(
        latest_price=latest_price,
        previous_price=previous_price,
        price_delta=price_delta,
        absolute_delta=abs(price_delta),
        latest_collected_at=to_seoul_time(latest.collected_at),
        previous_collected_at=to_seoul_time(previous.collected_at),
        currency=latest.currency,
    )
