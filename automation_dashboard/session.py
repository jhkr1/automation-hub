"""Short-lived SQLAlchemy Sessions for read-only dashboard queries."""

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from automation_dashboard.config import DashboardConfigurationError, DashboardSettings


class DashboardDatabaseError(RuntimeError):
    """Raised as a safe dashboard-level database failure signal."""


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Build one engine factory without storing Sessions or ORM rows in Streamlit cache."""
    try:
        engine = create_engine(DashboardSettings().selected_database_url, pool_pre_ping=True)
    except SQLAlchemyError as exc:
        raise DashboardDatabaseError("database engine configuration failed") from exc
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def dashboard_session() -> Generator[Session, None, None]:
    """Yield a short-lived Session and normalize SQLAlchemy failures safely."""
    try:
        with get_session_factory()() as session:
            yield session
    except DashboardConfigurationError:
        raise
    except SQLAlchemyError as exc:
        raise DashboardDatabaseError("database query failed") from exc


def probe_database() -> None:
    """Verify connectivity with a read-only scalar query."""
    with dashboard_session() as session:
        session.execute(select(1)).scalar_one()
