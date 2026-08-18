"""Read-only operator-focused status dashboard page."""

from datetime import datetime

import streamlit as st

from automation_dashboard.config import DashboardConfigurationError
from automation_dashboard.queries.operations import (
    AlembicStatus,
    DatabaseSummary,
    OperationsSnapshotSummary,
    load_alembic_status,
    load_database_summary,
    load_snapshot_summary,
)
from automation_dashboard.session import DashboardDatabaseError, dashboard_session
from automation_dashboard.ui.components import (
    apply_dashboard_theme,
    render_metadata_card,
    render_metric_card,
    render_page_hero,
    render_section_title,
    render_status_badge,
)
from automation_dashboard.ui.formatting import format_integer, format_kst_datetime
from automation_dashboard.ui.layout import render_sidebar_context
from automation_dashboard.ui.states import (
    GOOGLE_FRESHNESS_THRESHOLD,
    NAMUWIKI_FRESHNESS_THRESHOLD,
    DisplayState,
    availability_state,
    bus_monitor_state,
    freshness_state,
    render_database_error,
    status_presentation,
)


@st.cache_data(ttl=60, show_spinner=False)
def _load_database_summary() -> DatabaseSummary:
    """Cache detached database connectivity data for the operator view."""
    with dashboard_session() as session:
        return load_database_summary(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_snapshot_summary() -> OperationsSnapshotSummary:
    """Cache detached latest collection data for the three monitored jobs."""
    with dashboard_session() as session:
        return load_snapshot_summary(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_alembic_status() -> AlembicStatus:
    """Cache migration metadata for the collapsed operational-detail section."""
    with dashboard_session() as session:
        return load_alembic_status(session)


def _render_job_card(name: str, state: DisplayState, collected_at: datetime | None) -> None:
    """Render one concise job-health card without exposing internal implementation IDs."""
    with st.container(border=True):
        st.subheader(name)
        render_status_badge(state.label)
        st.caption("마지막 적재")
        st.write(format_kst_datetime(collected_at))
        st.caption(state.detail)


def main() -> None:
    """Render the operator's quick health assessment without starting any job."""
    apply_dashboard_theme()
    render_sidebar_context()
    try:
        database = _load_database_summary()
        snapshots = _load_snapshot_summary()
        alembic = _load_alembic_status()
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_page_hero(
            "Operations",
            "각 자동화 Job의 최근 적재 상태를 빠르게 확인합니다.",
            status="Unavailable",
        )
        render_database_error()
        return

    database_state = availability_state(database.status == "Connected")
    google_state = freshness_state(
        snapshots.latest_google_collected_at,
        threshold=GOOGLE_FRESHNESS_THRESHOLD,
    )
    namuwiki_state = freshness_state(
        snapshots.latest_namuwiki_collected_at,
        threshold=NAMUWIKI_FRESHNESS_THRESHOLD,
    )
    bus_state = bus_monitor_state(
        snapshots.latest_bus_route_status,
        snapshots.latest_bus_realtime_status,
    )
    jobs = (
        ("Google Finance", google_state, snapshots.latest_google_collected_at),
        ("Namuwiki", namuwiki_state, snapshots.latest_namuwiki_collected_at),
        ("Bus Monitor", bus_state, snapshots.latest_bus_collected_at),
    )
    latest_times = [collected_at for _, _, collected_at in jobs if collected_at is not None]
    tones = [status_presentation(state.label).tone for _, state, _ in jobs]
    healthy_count = tones.count("success")
    warning_count = tones.count("warning") + tones.count("neutral")
    failed_count = tones.count("error")
    overall_status = "Healthy" if warning_count == 0 and failed_count == 0 else "Attention Needed"

    render_page_hero(
        "Operations",
        "각 자동화 Job의 최근 적재 상태를 빠르게 확인합니다.",
        status=overall_status,
        last_updated=max(latest_times) if latest_times else None,
    )
    render_section_title("Automation Status", "정상 여부와 마지막 적재시각을 먼저 확인합니다.")
    summary_columns = st.columns(4)
    summary_items = (
        ("정상 Job", str(healthy_count)),
        ("주의 필요", str(warning_count)),
        ("실패", str(failed_count)),
        ("최근 확인", format_kst_datetime(max(latest_times) if latest_times else None)),
    )
    for column, (label, value) in zip(summary_columns, summary_items, strict=True):
        with column:
            render_metric_card(label, value)

    render_section_title("Job Status", "Job별 상태와 다음 확인 지점을 표시합니다.")
    job_columns = st.columns(3)
    for column, (name, state, collected_at) in zip(job_columns, jobs, strict=True):
        with column:
            _render_job_card(name, state, collected_at)

    with st.expander("운영 상세 정보"):
        migration_state = availability_state(alembic.is_in_sync)
        render_metadata_card(
            "Storage Summary",
            {
                "Google Finance Snapshots": format_integer(snapshots.google_snapshot_count),
                "Namuwiki Snapshots": format_integer(snapshots.namuwiki_snapshot_count),
                "Bus Monitor Snapshots": format_integer(snapshots.bus_snapshot_count),
                "Today's Collections": format_integer(
                    snapshots.google_today_snapshot_count
                    + snapshots.namuwiki_today_snapshot_count
                    + snapshots.bus_today_snapshot_count
                ),
            },
        )
        render_metadata_card(
            "System Details",
            {
                "Database": database_state.detail,
                "Migration": status_presentation(migration_state.label).label,
                "Migration Detail": migration_state.detail,
            },
        )


if __name__ == "__main__":
    main()
