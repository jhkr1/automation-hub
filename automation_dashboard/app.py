"""Streamlit entry point for the read-only automation dashboard."""

import streamlit as st

from automation_dashboard.config import DashboardConfigurationError
from automation_dashboard.queries.operations import (
    DatabaseSummary,
    OperationsSnapshotSummary,
    load_database_summary,
    load_snapshot_summary,
)
from automation_dashboard.session import DashboardDatabaseError, dashboard_session
from automation_dashboard.ui.formatting import format_kst_datetime
from automation_dashboard.ui.layout import render_page_header, render_sidebar_context
from automation_dashboard.ui.states import (
    GOOGLE_FRESHNESS_THRESHOLD,
    NAMUWIKI_FRESHNESS_THRESHOLD,
    availability_state,
    freshness_state,
    render_database_error,
)


@st.cache_data(ttl=60, show_spinner=False)
def _load_database_summary() -> DatabaseSummary:
    """Cache detached home database status without caching Sessions or engines."""
    with dashboard_session() as session:
        return load_database_summary(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_snapshot_summary() -> OperationsSnapshotSummary:
    """Cache detached home snapshot status without running an automation job."""
    with dashboard_session() as session:
        return load_snapshot_summary(session)


def main() -> None:
    """Render the Dashboard landing page without invoking automations."""
    st.set_page_config(
        page_title="Automation Hub Dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render_sidebar_context()

    try:
        database = _load_database_summary()
        snapshots = _load_snapshot_summary()
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_page_header(
            "Automation Hub Dashboard",
            "Google Finance Snapshot, Namuwiki Trend, Operations 상태를 조회하는 "
            "Read-only 운영 Dashboard입니다.",
        )
        render_database_error()
        return

    latest_times = [
        value
        for value in (
            snapshots.latest_google_collected_at,
            snapshots.latest_namuwiki_collected_at,
        )
        if value is not None
    ]
    render_page_header(
        "Automation Hub Dashboard",
        "Google Finance Snapshot, Namuwiki Trend, Operations 상태를 조회하는 "
        "Read-only 운영 Dashboard입니다.",
        last_updated=max(latest_times) if latest_times else None,
    )
    st.info(
        "이 화면은 저장된 데이터와 상태만 조회합니다. "
        "자동화 실행, cron 제어, Gemini 호출, 데이터 저장은 수행하지 않습니다."
    )

    database_status = availability_state(database.status == "Connected")
    google_status = freshness_state(
        snapshots.latest_google_collected_at,
        threshold=GOOGLE_FRESHNESS_THRESHOLD,
    )
    namuwiki_status = freshness_state(
        snapshots.latest_namuwiki_collected_at,
        threshold=NAMUWIKI_FRESHNESS_THRESHOLD,
    )
    status_columns = st.columns(3)
    status_columns[0].metric(
        "Database",
        database_status.label,
        database_status.detail,
        delta_color="off",
    )
    status_columns[1].metric(
        "Latest Google Data",
        google_status.label,
        google_status.detail,
        delta_color="off",
    )
    status_columns[2].metric(
        "Latest Namuwiki Data",
        namuwiki_status.label,
        namuwiki_status.detail,
        delta_color="off",
    )

    st.subheader("Dashboard Pages")
    st.caption("목적에 맞는 화면을 선택하세요. 모든 화면은 저장된 데이터만 조회합니다.")
    navigation_columns = st.columns(3)
    with navigation_columns[0]:
        st.page_link("pages/1_google_finance.py", label="Google Finance", width="stretch")
    with navigation_columns[1]:
        st.page_link("pages/2_namuwiki.py", label="Namuwiki Trends", width="stretch")
    with navigation_columns[2]:
        st.page_link("pages/3_operations.py", label="Operations", width="stretch")

    if latest_times:
        st.caption(f"최근 저장 데이터: {format_kst_datetime(max(latest_times))}")


if __name__ == "__main__":
    main()
