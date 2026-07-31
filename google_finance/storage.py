"""MySQL-backed append-only storage for Google Finance quote snapshots."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from google_finance.db_models import StockQuoteSnapshot, _canonical_symbol
from google_finance.models import StockPrice


class StockQuoteStorage:
    """Persist and query Google Finance snapshots without owning domain logic."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        """Initialize with the existing SessionLocal factory when none is supplied."""
        if session_factory is None:
            from database.session import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory

    def save(self, stock_price: StockPrice) -> None:
        """Append one snapshot in a transaction and propagate database errors."""
        row = StockQuoteSnapshot.from_domain(stock_price)
        with self._session_factory.begin() as session:
            session.add(row)

    def get_latest(self, symbol: str) -> StockPrice | None:
        """Return the newest snapshot for a symbol, or ``None`` when absent."""
        rows = self._query_latest(symbol, limit=1)
        return rows[0] if rows else None

    def get_latest_two(self, symbol: str) -> list[StockPrice]:
        """Return ``[newest, previous]`` snapshots for one symbol."""
        return self._query_latest(symbol, limit=2)

    def _query_latest(self, symbol: str, *, limit: int) -> list[StockPrice]:
        """Query only one symbol with deterministic newest-first ordering."""
        normalized_symbol = _canonical_symbol(symbol)

        statement = (
            select(StockQuoteSnapshot)
            .where(StockQuoteSnapshot.symbol == normalized_symbol)
            .order_by(
                StockQuoteSnapshot.collected_at.desc(),
                StockQuoteSnapshot.id.desc(),
            )
            .limit(limit)
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
        return [row.to_domain() for row in rows]
