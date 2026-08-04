"""Read-only operational status dashboard page."""

from datetime import datetime

import pandas as pd
import streamlit as st

from automation_dashboard.config import DashboardConfigurationError
from automation_dashboard.queries.operations import (
    AlembicStatus,
    DatabaseSummary,
    LogSummary,
    OperationsSnapshotSummary,
    RuntimeInfo,
    load_alembic_status,
    load_database_summary,
    load_log_summary,
    load_runtime_info,
    load_snapshot_summary,
)
from automation_dashboard.session import DashboardDatabaseError, dashboard_session


def _format_time(value: datetime | None) -> str:
    """Format an already localized timestamp or a safe empty display value."""
    return "-" if value is None else value.strftime("%Y-%m-%d %H:%M:%S %Z")


def _format_size(value: int | None) -> str:
    """Render an optional byte count without reading additional data."""
    if value is None:
        return "확인 불가"
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


@st.cache_data(ttl=60, show_spinner=False)
def _load_database_summary() -> DatabaseSummary:
    """Cache detached database status DTOs, never Sessions or engines."""
    with dashboard_session() as session:
        return load_database_summary(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_snapshot_summary() -> OperationsSnapshotSummary:
    """Cache detached snapshot totals and recent activity DTOs."""
    with dashboard_session() as session:
        return load_snapshot_summary(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_alembic_status() -> AlembicStatus:
    """Cache detached migration status DTOs while keeping the Session short-lived."""
    with dashboard_session() as session:
        return load_alembic_status(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_log_summary() -> LogSummary:
    """Cache detached file metadata for a short display interval."""
    return load_log_summary()


@st.cache_data(ttl=60, show_spinner=False)
def _load_runtime_info() -> RuntimeInfo:
    """Cache detached local process metadata without caching database resources."""
    return load_runtime_info()


def _show_database_error() -> None:
    """Display a safe database error without exposing connection details."""
    st.error("데이터베이스 연결에 실패했습니다. Operations 로그와 DATABASE_URL 설정을 확인하세요.")


def main() -> None:
    """Render the read-only operations overview without starting any automation."""
    st.title("Operations Dashboard")
    st.caption(
        "현재 저장 데이터와 로컬 파일 메타데이터만 조회합니다. "
        "실행·저장·cron 제어는 수행하지 않습니다."
    )

    try:
        database = _load_database_summary()
        snapshots = _load_snapshot_summary()
        alembic = _load_alembic_status()
    except (DashboardConfigurationError, DashboardDatabaseError):
        _show_database_error()
        return
    logs = _load_log_summary()
    runtime = _load_runtime_info()

    kpi_columns = st.columns(6)
    kpi_columns[0].metric("Google Snapshot Count", snapshots.google_snapshot_count)
    kpi_columns[1].metric("Namuwiki Snapshot Count", snapshots.namuwiki_snapshot_count)
    kpi_columns[2].metric(
        "Latest Google Collect",
        _format_time(snapshots.latest_google_collected_at),
    )
    kpi_columns[3].metric(
        "Latest Namuwiki Snapshot", _format_time(snapshots.latest_namuwiki_collected_at)
    )
    kpi_columns[4].metric("Database Status", database.status)
    kpi_columns[5].metric("Alembic Version", alembic.applied_version or "확인 불가")

    st.subheader("Storage")
    storage_columns = st.columns(3)
    storage_columns[0].metric(
        "Google Snapshots Today",
        snapshots.google_today_snapshot_count,
        help=f"Total: {snapshots.google_snapshot_count}",
    )
    storage_columns[1].metric(
        "Namuwiki Snapshots Today",
        snapshots.namuwiki_today_snapshot_count,
        help=f"Total: {snapshots.namuwiki_snapshot_count}",
    )
    storage_columns[2].metric("Database Size", _format_size(database.size_bytes))

    st.subheader("Log Status")
    if not logs.files:
        st.info("아직 생성된 로그가 없습니다.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Log File": item.name,
                        "Last Modified (KST)": _format_time(item.modified_at),
                        "Size": _format_size(item.size_bytes),
                    }
                    for item in logs.files
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Migration")
    if alembic.current_head is None or alembic.applied_version is None:
        st.info("Migration 정보를 확인할 수 없습니다.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Current Alembic Head": alembic.current_head,
                        "Applied Version": alembic.applied_version,
                        "In Sync": "Yes" if alembic.is_in_sync else "No",
                    }
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    st.subheader("System")
    st.dataframe(
        pd.DataFrame(
            [
                {"Item": "Python Version", "Value": runtime.python_version},
                {"Item": "Timezone", "Value": runtime.timezone},
                {"Item": "Working Directory", "Value": str(runtime.working_directory)},
                {"Item": "Streamlit Version", "Value": runtime.streamlit_version},
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    st.subheader("Recent Activity")
    if (
        snapshots.latest_google_collected_at is None
        and snapshots.latest_namuwiki_collected_at is None
    ):
        st.info("저장된 Snapshot이 없습니다.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Source": "Google Finance",
                    "Latest Stored At (KST)": _format_time(snapshots.latest_google_collected_at),
                    "Symbol / Keyword": snapshots.latest_google_symbol or "-",
                },
                {
                    "Source": "Namuwiki",
                    "Latest Stored At (KST)": _format_time(snapshots.latest_namuwiki_collected_at),
                    "Symbol / Keyword": snapshots.latest_namuwiki_keyword or "-",
                },
            ]
        ),
        width="stretch",
        hide_index=True,
    )


main()
