"""Read-only operational status dashboard page."""

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
from automation_dashboard.ui.formatting import (
    format_file_size,
    format_integer,
    format_kst_datetime,
    format_repository_location,
)
from automation_dashboard.ui.layout import (
    render_page_header,
    render_section_header,
    render_sidebar_context,
)
from automation_dashboard.ui.states import (
    GOOGLE_FRESHNESS_THRESHOLD,
    NAMUWIKI_FRESHNESS_THRESHOLD,
    availability_state,
    freshness_state,
    render_database_error,
    render_empty_state,
)


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


def main() -> None:
    """Render the read-only operations overview without starting any automation."""
    render_sidebar_context()
    try:
        database = _load_database_summary()
        snapshots = _load_snapshot_summary()
        alembic = _load_alembic_status()
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_page_header("Operations", "현재 시스템 상태를 조회하는 Read-only 페이지입니다.")
        render_database_error()
        return
    logs = _load_log_summary()
    runtime = _load_runtime_info()

    latest_times = [
        value
        for value in (
            snapshots.latest_google_collected_at,
            snapshots.latest_namuwiki_collected_at,
        )
        if value is not None
    ]
    render_page_header(
        "Operations",
        "현재 시스템 상태를 조회하는 Read-only 페이지입니다. "
        "실행·저장·cron 제어는 수행하지 않습니다.",
        last_updated=max(latest_times) if latest_times else None,
    )

    database_status = availability_state(database.status == "Connected")
    migration_status = availability_state(alembic.is_in_sync)
    google_status = freshness_state(
        snapshots.latest_google_collected_at,
        threshold=GOOGLE_FRESHNESS_THRESHOLD,
    )
    namuwiki_status = freshness_state(
        snapshots.latest_namuwiki_collected_at,
        threshold=NAMUWIKI_FRESHNESS_THRESHOLD,
    )
    status_columns = st.columns(4)
    for column, label, state in (
        (status_columns[0], "Database", database_status),
        (status_columns[1], "Alembic", migration_status),
        (status_columns[2], "Google Latest", google_status),
        (status_columns[3], "Namuwiki Latest", namuwiki_status),
    ):
        column.metric(label, state.label, state.detail, delta_color="off")

    render_section_header("Storage", "저장된 Snapshot 행과 현재 KST 날짜의 수집 행입니다.")
    storage_columns = st.columns(4)
    storage_columns[0].metric(
        "Google Snapshot Rows",
        format_integer(snapshots.google_snapshot_count),
    )
    storage_columns[1].metric(
        "Namuwiki Snapshot Rows",
        format_integer(snapshots.namuwiki_snapshot_count),
    )
    storage_columns[2].metric(
        "Today's Collections",
        format_integer(
            snapshots.google_today_snapshot_count + snapshots.namuwiki_today_snapshot_count
        ),
    )
    storage_columns[3].metric("Database Size", format_file_size(database.size_bytes))

    render_section_header("Logs", "Wrapper 로그의 파일 메타데이터만 표시합니다.")
    if not logs.files:
        render_empty_state("아직 생성된 로그가 없습니다.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "File": item.name,
                        "Status": "Available",
                        "Updated": format_kst_datetime(item.modified_at),
                        "Size": format_file_size(item.size_bytes),
                    }
                    for item in logs.files
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    render_section_header("Migration", "Repository migration head와 적용된 버전을 비교합니다.")
    if alembic.current_head is None or alembic.applied_version is None:
        render_empty_state("Migration 정보를 확인할 수 없습니다.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Applied Version": alembic.applied_version,
                        "Repository Head": alembic.current_head,
                        "Status": migration_status.label,
                    }
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    render_section_header("Runtime", "현재 Streamlit 프로세스의 로컬 실행 정보입니다.")
    st.dataframe(
        pd.DataFrame(
            [
                {"Item": "Python Version", "Value": runtime.python_version},
                {"Item": "Streamlit Version", "Value": runtime.streamlit_version},
                {"Item": "Timezone", "Value": runtime.timezone},
                {
                    "Item": "Working Directory",
                    "Value": format_repository_location(runtime.working_directory),
                },
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    render_section_header("Recent Activity", "가장 최근에 저장된 각 Package의 Snapshot입니다.")
    if not latest_times:
        render_empty_state("저장된 Snapshot이 없습니다.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Source": "Google Finance",
                    "Stored At": format_kst_datetime(snapshots.latest_google_collected_at),
                    "Symbol / Keyword": snapshots.latest_google_symbol or "—",
                },
                {
                    "Source": "Namuwiki",
                    "Stored At": format_kst_datetime(snapshots.latest_namuwiki_collected_at),
                    "Symbol / Keyword": snapshots.latest_namuwiki_keyword or "—",
                },
            ]
        ),
        width="stretch",
        hide_index=True,
    )


if __name__ == "__main__":
    main()
