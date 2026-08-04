"""Read-only operational status queries for the dashboard."""

import platform
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from importlib.metadata import version
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from automation_dashboard.config import PROJECT_ROOT
from automation_dashboard.queries.google_finance import SEOUL_TZ, to_seoul_time
from database.models import TrendSnapshot
from google_finance.db_models import StockQuoteSnapshot

LOG_DIRECTORY = PROJECT_ROOT / "logs"
ALEMBIC_CONFIG_PATH = PROJECT_ROOT / "alembic.ini"


@dataclass(frozen=True)
class DatabaseSummary:
    """Database connectivity and optional MySQL storage size for display."""

    status: str
    size_bytes: int | None


@dataclass(frozen=True)
class OperationsSnapshotSummary:
    """Persisted snapshot totals and the most recent activity from each package."""

    google_snapshot_count: int
    namuwiki_snapshot_count: int
    google_today_snapshot_count: int
    namuwiki_today_snapshot_count: int
    latest_google_collected_at: datetime | None
    latest_google_symbol: str | None
    latest_namuwiki_collected_at: datetime | None
    latest_namuwiki_keyword: str | None


@dataclass(frozen=True)
class LogFileStatus:
    """One read-only wrapper log file metadata record."""

    name: str
    size_bytes: int
    modified_at: datetime


@dataclass(frozen=True)
class LogSummary:
    """Existing wrapper log metadata without reading log content."""

    log_directory: Path
    files: tuple[LogFileStatus, ...]


@dataclass(frozen=True)
class AlembicStatus:
    """Alembic script head and applied database revision, when readable."""

    current_head: str | None
    applied_version: str | None
    is_in_sync: bool | None


@dataclass(frozen=True)
class RuntimeInfo:
    """Local process metadata used by the operations dashboard."""

    python_version: str
    timezone: str
    working_directory: Path
    streamlit_version: str


def _seoul_day_bounds(target_date: date) -> tuple[datetime, datetime]:
    """Return UTC-naive bounds for one Seoul calendar date in the database."""
    start = datetime.combine(target_date, time.min, tzinfo=SEOUL_TZ)
    end = datetime.combine(target_date, time.max, tzinfo=SEOUL_TZ)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def load_database_summary(session: Session) -> DatabaseSummary:
    """Verify read connectivity and report MySQL table storage when available."""
    session.execute(select(1)).scalar_one()
    if session.bind is None or session.bind.dialect.name != "mysql":
        return DatabaseSummary(status="Connected", size_bytes=None)

    try:
        size_bytes = session.scalar(
            text(
                "SELECT COALESCE(SUM(data_length + index_length), 0) "
                "FROM information_schema.tables WHERE table_schema = DATABASE()"
            )
        )
    except SQLAlchemyError:
        size_bytes = None
    return DatabaseSummary(
        status="Connected",
        size_bytes=None if size_bytes is None else int(size_bytes),
    )


def load_snapshot_summary(
    session: Session,
    *,
    today: date | None = None,
) -> OperationsSnapshotSummary:
    """Return persisted totals and deterministic latest rows without writing data."""
    target_date = today or datetime.now(SEOUL_TZ).date()
    day_start, day_end = _seoul_day_bounds(target_date)
    google_total = session.scalar(select(func.count(StockQuoteSnapshot.id))) or 0
    namuwiki_total = session.scalar(select(func.count(TrendSnapshot.id))) or 0
    google_today = (
        session.scalar(
            select(func.count(StockQuoteSnapshot.id)).where(
                StockQuoteSnapshot.collected_at >= day_start,
                StockQuoteSnapshot.collected_at <= day_end,
            )
        )
        or 0
    )
    namuwiki_today = (
        session.scalar(
            select(func.count(TrendSnapshot.id)).where(TrendSnapshot.collection_date == target_date)
        )
        or 0
    )
    latest_google = session.execute(
        select(StockQuoteSnapshot.collected_at, StockQuoteSnapshot.symbol)
        .order_by(StockQuoteSnapshot.collected_at.desc(), StockQuoteSnapshot.id.desc())
        .limit(1)
    ).one_or_none()
    latest_namuwiki = session.execute(
        select(TrendSnapshot.collected_at, TrendSnapshot.keyword)
        .order_by(TrendSnapshot.collected_at.desc(), TrendSnapshot.id.desc())
        .limit(1)
    ).one_or_none()
    return OperationsSnapshotSummary(
        google_snapshot_count=int(google_total),
        namuwiki_snapshot_count=int(namuwiki_total),
        google_today_snapshot_count=int(google_today),
        namuwiki_today_snapshot_count=int(namuwiki_today),
        latest_google_collected_at=(
            None if latest_google is None else to_seoul_time(latest_google.collected_at)
        ),
        latest_google_symbol=None if latest_google is None else latest_google.symbol,
        latest_namuwiki_collected_at=(
            None if latest_namuwiki is None else to_seoul_time(latest_namuwiki.collected_at)
        ),
        latest_namuwiki_keyword=None if latest_namuwiki is None else latest_namuwiki.keyword,
    )


def load_log_summary(log_directory: Path = LOG_DIRECTORY) -> LogSummary:
    """Return metadata for existing log files without opening their contents."""
    if not log_directory.is_dir():
        return LogSummary(log_directory=log_directory, files=())

    files = tuple(
        LogFileStatus(
            name=path.name,
            size_bytes=path.stat().st_size,
            modified_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(
                SEOUL_TZ
            ),
        )
        for path in sorted(log_directory.glob("*.log"), key=lambda item: item.name)
        if path.is_file()
    )
    return LogSummary(log_directory=log_directory, files=files)


def load_alembic_status(session: Session) -> AlembicStatus:
    """Read the local script head and applied revision without running migrations."""
    try:
        script_directory = ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG_PATH)))
        current_head = script_directory.get_current_head()
    except (OSError, ValueError):
        current_head = None

    try:
        applied_version = session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    except SQLAlchemyError:
        applied_version = None
    normalized_applied_version = None if applied_version is None else str(applied_version)
    is_in_sync = (
        None
        if current_head is None or normalized_applied_version is None
        else current_head == normalized_applied_version
    )
    return AlembicStatus(
        current_head=current_head,
        applied_version=normalized_applied_version,
        is_in_sync=is_in_sync,
    )


def load_runtime_info() -> RuntimeInfo:
    """Return local runtime details without starting an automation job."""
    return RuntimeInfo(
        python_version=platform.python_version(),
        timezone=datetime.now().astimezone().tzname() or "Unknown",
        working_directory=Path.cwd(),
        streamlit_version=version("streamlit"),
    )
