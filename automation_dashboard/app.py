"""Streamlit entry point for the read-only automation dashboard."""

from datetime import datetime

import streamlit as st

from automation_dashboard.config import DashboardConfigurationError
from automation_dashboard.queries.google_finance import SEOUL_TZ
from automation_dashboard.queries.operations import (
    DatabaseSummary,
    OperationsSnapshotSummary,
    load_database_summary,
    load_snapshot_summary,
)
from automation_dashboard.readers.llm_usage import LlmUsageReadModel, read_llm_usage
from automation_dashboard.session import DashboardDatabaseError, dashboard_session
from automation_dashboard.ui.components import (
    apply_dashboard_theme,
    render_attention_banner,
    render_metric_card,
    render_overview_card,
    render_page_hero,
    render_section_title,
    render_status_badge,
    render_timeline_card,
)
from automation_dashboard.ui.formatting import format_integer, format_kst_datetime
from automation_dashboard.ui.layout import render_sidebar_context
from automation_dashboard.ui.states import (
    GOOGLE_FRESHNESS_THRESHOLD,
    NAMUWIKI_FRESHNESS_THRESHOLD,
    availability_state,
    bus_monitor_state,
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


@st.cache_data(ttl=60, show_spinner=False)
def _load_llm_usage() -> LlmUsageReadModel:
    """Cache safe LLM ledger metadata without opening a mutable resource."""
    return read_llm_usage()


def _attention_items(
    database_status: str,
    google_status: str,
    namuwiki_status: str,
    bus_status: str,
    llm_status: str,
) -> list[tuple[str, str]]:
    """Return one concise attention item per unavailable monitored source."""
    items: list[tuple[str, str]] = []
    if database_status != "Healthy":
        items.append(("Database", database_status))
    if google_status in {"Stale", "No Data", "Unavailable"}:
        items.append(("Google Finance", google_status))
    if namuwiki_status in {"Stale", "No Data", "Unavailable"}:
        items.append(("Namuwiki", namuwiki_status))
    if bus_status in {"FAILED", "UNAVAILABLE", "No Data", "Unknown"}:
        items.append(("Bus Monitor", bus_status))
    if llm_status in {"Unavailable", "Invalid Artifact"}:
        items.append(("LLM Runtime", llm_status))
    return items


def _activity_items(
    snapshots: OperationsSnapshotSummary,
    llm_usage: LlmUsageReadModel,
) -> list[dict[str, str]]:
    """Build a recent-activity preview from existing latest timestamps only."""
    events: list[tuple[datetime, dict[str, str]]] = []
    if snapshots.latest_google_collected_at is not None:
        events.append(
            (
                snapshots.latest_google_collected_at,
                {
                    "timestamp": format_kst_datetime(snapshots.latest_google_collected_at),
                    "label": "Google Finance collection",
                    "detail": snapshots.latest_google_symbol or "Latest snapshot",
                },
            )
        )
    if snapshots.latest_namuwiki_collected_at is not None:
        events.append(
            (
                snapshots.latest_namuwiki_collected_at,
                {
                    "timestamp": format_kst_datetime(snapshots.latest_namuwiki_collected_at),
                    "label": "Namuwiki snapshot",
                    "detail": snapshots.latest_namuwiki_keyword or "Latest snapshot",
                },
            )
        )
    if snapshots.latest_bus_collected_at is not None:
        events.append(
            (
                snapshots.latest_bus_collected_at,
                {
                    "timestamp": format_kst_datetime(snapshots.latest_bus_collected_at),
                    "label": "Bus Monitor snapshot",
                    "detail": "Latest route and realtime collection",
                },
            )
        )
    if llm_usage.last_request_at_kst is not None:
        events.append(
            (
                llm_usage.last_request_at_kst,
                {
                    "timestamp": format_kst_datetime(llm_usage.last_request_at_kst),
                    "label": "LLM Runtime request",
                    "detail": (
                        f"{sum(profile.requests_today for profile in llm_usage.profiles)} today"
                    ),
                },
            )
        )
    return [item for _, item in sorted(events, key=lambda event: event[0], reverse=True)]


def main() -> None:
    """Render the Dashboard landing page without invoking automations."""
    apply_dashboard_theme()
    render_sidebar_context()

    try:
        database = _load_database_summary()
        snapshots = _load_snapshot_summary()
        llm_usage = _load_llm_usage()
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_page_hero(
            "Automation Hub",
            "Read-only automation operations dashboard",
            status="Unavailable",
            last_updated=datetime.now(SEOUL_TZ),
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
    llm_status = llm_usage.status.value
    attention = _attention_items(
        database_state.label,
        google_state.label,
        namuwiki_state.label,
        bus_state.label,
        llm_status,
    )
    overall_status = "Healthy" if not attention else "Attention Needed"
    render_page_hero(
        "Automation Hub",
        "Read-only automation operations dashboard",
        status=overall_status,
        last_updated=datetime.now(SEOUL_TZ),
    )

    render_section_title("System Overview", "전체 상태를 빠르게 확인합니다.")
    overview_columns = st.columns(4)
    overview_cards = (
        ("Database", database_state.label, database_state.detail),
        ("Google Finance", google_state.label, google_state.detail),
        ("Namuwiki", namuwiki_state.label, namuwiki_state.detail),
        ("Bus Monitor", bus_state.label, bus_state.detail),
    )
    for column, (label, value, detail) in zip(overview_columns, overview_cards, strict=True):
        with column:
            render_metric_card(label, value, detail=detail)

    render_section_title("Attention Needed")
    if not attention:
        render_status_badge("Healthy", detail="No attention needed")
    else:
        for label, status in attention:
            render_attention_banner(label, f"현재 상태: {status}")

    render_section_title("Package Overview")
    package_columns = st.columns(3)
    with package_columns[0]:
        google_detail = (
            f"Latest: {format_kst_datetime(snapshots.latest_google_collected_at)}"
            if snapshots.latest_google_collected_at
            else "저장된 Snapshot이 없습니다."
        )
        render_overview_card(
            "Google Finance",
            f"{format_integer(snapshots.google_snapshot_count)} snapshots",
            status=google_state.label,
            detail=f"{google_detail} · LLM Insight: Planned",
            link_label="Open Google Finance",
            link_target="pages/1_google_finance.py",
        )
    with package_columns[1]:
        namuwiki_detail = (
            f"Latest: {format_kst_datetime(snapshots.latest_namuwiki_collected_at)}"
            if snapshots.latest_namuwiki_collected_at
            else "저장된 Snapshot이 없습니다."
        )
        render_overview_card(
            "Namuwiki",
            f"{format_integer(snapshots.namuwiki_snapshot_count)} snapshots",
            status=namuwiki_state.label,
            detail=f"{namuwiki_detail} · Keyword: {snapshots.latest_namuwiki_keyword or '—'}",
            link_label="Open Namuwiki",
            link_target="pages/2_namuwiki.py",
        )
    with package_columns[2]:
        bus_detail = (
            f"Latest: {format_kst_datetime(snapshots.latest_bus_collected_at)}"
            if snapshots.latest_bus_collected_at
            else "저장된 Snapshot이 없습니다."
        )
        render_overview_card(
            "Bus Monitor",
            f"{format_integer(snapshots.bus_snapshot_count)} snapshots",
            status=bus_state.label,
            detail=bus_detail,
            link_label="Open Bus Monitor",
            link_target="pages/4_bus_monitor.py",
        )

    render_section_title(
        "LLM Runtime Summary",
        "상세 quota와 profile 정보는 Operations에서 확인합니다.",
    )
    llm_columns = st.columns(4)
    llm_cards = (
        ("Ledger", llm_status),
        (
            "Requests Today",
            format_integer(sum(profile.requests_today for profile in llm_usage.profiles)),
        ),
        ("Retries", format_integer(llm_usage.retry_count)),
        (
            "Last Request",
            format_kst_datetime(llm_usage.last_request_at_kst)
            if llm_usage.last_request_at_kst
            else "—",
        ),
    )
    for column, (label, value) in zip(llm_columns, llm_cards, strict=True):
        with column:
            render_metric_card(label, value)

    render_section_title("Recent Activity")
    render_timeline_card("Latest Activity", _activity_items(snapshots, llm_usage))

    render_section_title("Navigation", "상세 조회 화면으로 이동합니다.")
    navigation_columns = st.columns(4)
    navigation = (
        ("Bus Monitor", "pages/4_bus_monitor.py"),
        ("Google Finance", "pages/1_google_finance.py"),
        ("Namuwiki Trend", "pages/2_namuwiki.py"),
        ("Operations", "pages/3_operations.py"),
    )
    for column, (label, target) in zip(navigation_columns, navigation, strict=True):
        with column:
            st.page_link(target, label=label, width="stretch")


if __name__ == "__main__":
    st.set_page_config(
        page_title="Automation Hub Dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    selected_page = st.navigation(
        [
            st.Page(main, title="Home", default=True),
            st.Page("pages/4_bus_monitor.py", title="Bus Monitor", url_path="bus_monitor"),
            st.Page("pages/1_google_finance.py", title="Google Finance", url_path="google_finance"),
            st.Page("pages/2_namuwiki.py", title="Namuwiki Trend", url_path="namuwiki"),
            st.Page("pages/3_operations.py", title="Operations", url_path="operations"),
        ]
    )
    selected_page.run()
