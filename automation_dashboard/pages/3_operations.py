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
from automation_dashboard.readers.llm_usage import LlmUsageReadModel, read_llm_usage
from automation_dashboard.readers.namuwiki_insights import InsightStatus
from automation_dashboard.session import DashboardDatabaseError, dashboard_session
from automation_dashboard.ui.components import (
    apply_dashboard_theme,
    render_empty_state,
    render_metadata_card,
    render_metric_card,
    render_page_hero,
    render_section_title,
    render_table_card,
    render_timeline_card,
)
from automation_dashboard.ui.formatting import (
    format_file_size,
    format_integer,
    format_kst_datetime,
    format_repository_location,
)
from automation_dashboard.ui.layout import render_sidebar_context
from automation_dashboard.ui.states import (
    GOOGLE_FRESHNESS_THRESHOLD,
    NAMUWIKI_FRESHNESS_THRESHOLD,
    availability_state,
    freshness_state,
    render_database_error,
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


@st.cache_data(ttl=60, show_spinner=False)
def _load_llm_usage() -> LlmUsageReadModel:
    """Cache safe quota ledger metadata without caching file handles."""
    return read_llm_usage()


def _render_llm_usage(model: LlmUsageReadModel) -> None:
    """Render quota counts only; keys, prompts, and responses never enter the UI."""
    render_section_title(
        "LLM Runtime",
        "Quota ledger의 읽기 전용 상태입니다. Provider 호출과 ledger 변경은 수행하지 않습니다.",
    )
    usage_columns = st.columns(3)
    with usage_columns[0]:
        render_metric_card("Ledger Status", model.status.value)
    with usage_columns[1]:
        render_metric_card("Retry Count", format_integer(model.retry_count))
    with usage_columns[2]:
        render_metric_card("Last Request", format_kst_datetime(model.last_request_at_kst))
    if model.status in {InsightStatus.NO_DATA, InsightStatus.UNAVAILABLE}:
        render_empty_state(model.message or "LLM usage 정보가 없습니다.")
        return
    if not model.profiles:
        render_empty_state("오늘 LLM 요청 기록이 없습니다.")
        return
    render_table_card(
        "Profile Usage",
        pd.DataFrame(
            [
                {
                    "Project Profile": profile.project_profile,
                    "Requests Today": profile.requests_today,
                }
                for profile in model.profiles
            ]
        ),
    )


def main() -> None:
    """Render the read-only operations overview without starting any automation."""
    apply_dashboard_theme()
    render_sidebar_context()
    try:
        database = _load_database_summary()
        snapshots = _load_snapshot_summary()
        alembic = _load_alembic_status()
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_page_hero(
            "Operations",
            "현재 시스템 상태를 조회하는 Read-only 페이지입니다.",
            status="Unavailable",
        )
        render_database_error()
        return
    logs = _load_log_summary()
    runtime = _load_runtime_info()
    llm_usage = _load_llm_usage()

    latest_times = [
        value
        for value in (
            snapshots.latest_google_collected_at,
            snapshots.latest_namuwiki_collected_at,
        )
        if value is not None
    ]
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
    render_page_hero(
        "Operations",
        "현재 시스템 상태를 조회하는 Read-only 페이지입니다.",
        status=database_status.label,
        last_updated=max(latest_times) if latest_times else None,
    )
    render_section_title("System Health", "저장소와 최신 Package 상태입니다.")
    status_columns = st.columns(4)
    for column, label, state in (
        (status_columns[0], "Database", database_status),
        (status_columns[1], "Alembic", migration_status),
        (status_columns[2], "Google Latest", google_status),
        (status_columns[3], "Namuwiki Latest", namuwiki_status),
    ):
        with column:
            render_metric_card(label, state.label, detail=state.detail)

    render_section_title("Runtime", "현재 Dashboard 프로세스의 로컬 실행 정보입니다.")
    render_metadata_card(
        "Runtime Details",
        {
            "Python": runtime.python_version,
            "Streamlit": runtime.streamlit_version,
            "Timezone": runtime.timezone,
            "Working Directory": format_repository_location(runtime.working_directory),
        },
    )
    _render_llm_usage(llm_usage)

    render_section_title("Storage", "저장된 Snapshot 행과 현재 KST 날짜의 수집 행입니다.")
    storage_columns = st.columns(4)
    storage_cards = (
        ("Google Snapshots", format_integer(snapshots.google_snapshot_count)),
        ("Namuwiki Snapshots", format_integer(snapshots.namuwiki_snapshot_count)),
        (
            "Today's Collections",
            format_integer(
                snapshots.google_today_snapshot_count + snapshots.namuwiki_today_snapshot_count
            ),
        ),
        ("Database Size", format_file_size(database.size_bytes)),
    )
    for column, (label, value) in zip(storage_columns, storage_cards, strict=True):
        with column:
            render_metric_card(label, value)

    render_section_title("Recent Activity", "가장 최근에 저장된 각 Package의 Snapshot입니다.")
    activity_items = []
    if snapshots.latest_google_collected_at is not None:
        activity_items.append(
            {
                "timestamp": format_kst_datetime(snapshots.latest_google_collected_at),
                "label": "Google Finance",
                "detail": snapshots.latest_google_symbol or "Latest snapshot",
                "sort_at": snapshots.latest_google_collected_at,
            }
        )
    if snapshots.latest_namuwiki_collected_at is not None:
        activity_items.append(
            {
                "timestamp": format_kst_datetime(snapshots.latest_namuwiki_collected_at),
                "label": "Namuwiki",
                "detail": snapshots.latest_namuwiki_keyword or "Latest snapshot",
                "sort_at": snapshots.latest_namuwiki_collected_at,
            }
        )
    activity_items.sort(key=lambda item: item["sort_at"], reverse=True)
    render_timeline_card(
        "Latest Activity",
        [
            {key: value for key, value in item.items() if key != "sort_at"}
            for item in activity_items
        ],
        empty_message="저장된 Snapshot이 없습니다.",
    )

    render_section_title("Logs", "Wrapper 로그의 파일 메타데이터만 표시합니다.")
    if not logs.files:
        render_empty_state("아직 생성된 로그가 없습니다.")
    else:
        render_table_card(
            "Wrapper Logs",
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
        )

    render_section_title("Migration", "Repository migration head와 적용된 버전을 비교합니다.")
    if alembic.current_head is None or alembic.applied_version is None:
        render_empty_state("Migration 정보를 확인할 수 없습니다.")
    else:
        render_metadata_card(
            "Migration Details",
            {
                "Status": migration_status.label,
                "Applied Version": alembic.applied_version,
                "Repository Head": alembic.current_head,
            },
        )


if __name__ == "__main__":
    main()
