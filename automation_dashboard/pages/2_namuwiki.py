"""Read-only Namuwiki trend snapshot dashboard page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from automation_dashboard.config import DashboardConfigurationError
from automation_dashboard.queries.namuwiki import (
    KeywordSummary,
    LatestTrendRow,
    SnapshotSummary,
    TrendHistoryPoint,
    list_keyword_history,
    list_keyword_statistics,
    list_latest_snapshot,
    load_snapshot_summary,
)
from automation_dashboard.session import DashboardDatabaseError, dashboard_session


def _format_time(value: object) -> str:
    """Format an already localized timestamp for stable dashboard display."""
    return value.strftime("%Y-%m-%d %H:%M:%S %Z")


@st.cache_data(ttl=60, show_spinner=False)
def _load_latest_snapshot() -> list[LatestTrendRow]:
    """Cache detached latest snapshot DTOs, never database resources."""
    with dashboard_session() as session:
        return list_latest_snapshot(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_keyword_history(keyword: str) -> list[TrendHistoryPoint]:
    """Cache one keyword's detached rank history DTOs."""
    with dashboard_session() as session:
        return list_keyword_history(session, keyword)


@st.cache_data(ttl=60, show_spinner=False)
def _load_keyword_statistics() -> list[KeywordSummary]:
    """Cache detached keyword summary DTOs for a short dashboard interval."""
    with dashboard_session() as session:
        return list_keyword_statistics(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_snapshot_summary() -> SnapshotSummary:
    """Cache detached snapshot KPI values without caching a Session."""
    with dashboard_session() as session:
        return load_snapshot_summary(session)


def _show_database_error() -> None:
    """Display a safe failure message without database connection details."""
    st.error("데이터베이스 연결에 실패했습니다. Operations 로그와 DATABASE_URL 설정을 확인하세요.")


def _latest_rows(rows: list[LatestTrendRow]) -> list[dict[str, object]]:
    """Map persisted trend DTOs to the latest Top 10 table."""
    return [
        {
            "Rank": row.rank_position,
            "Keyword": row.keyword,
            "Collected At (KST)": _format_time(row.collected_at),
        }
        for row in rows
    ]


def _statistics_rows(rows: list[KeywordSummary]) -> list[dict[str, object]]:
    """Map keyword summary DTOs to stable table values."""
    return [
        {
            "Keyword": row.keyword,
            "Appearances": row.appearance_count,
            "Best Rank": row.best_rank,
            "First Seen (KST)": _format_time(row.first_seen_at),
            "Last Seen (KST)": _format_time(row.last_seen_at),
        }
        for row in rows
    ]


def main() -> None:
    """Render the Namuwiki read-only snapshot view."""
    st.title("Namuwiki Dashboard")
    st.caption(
        "저장된 Snapshot만 조회합니다. 수집·enrichment·Gemini 호출·저장 작업은 수행하지 않습니다."
    )

    try:
        latest_snapshot = _load_latest_snapshot()
        summary = _load_snapshot_summary()
        statistics = _load_keyword_statistics()
    except (DashboardConfigurationError, DashboardDatabaseError):
        _show_database_error()
        return

    if not latest_snapshot:
        st.info(
            "저장된 Namuwiki Snapshot이 없습니다. "
            "먼저 snapshot job이 정상 실행됐는지 확인하세요."
        )
        return

    overview_columns = st.columns(4)
    overview_columns[0].metric(
        "Latest Snapshot",
        f"{len(latest_snapshot)} rows",
        help=f"저장된 Snapshot 묶음 수: {summary.total_snapshot_count}",
    )
    overview_columns[1].metric("Today's Snapshots", summary.today_snapshot_count)
    overview_columns[2].metric("Stored Keywords", summary.stored_keyword_count)
    overview_columns[3].metric(
        "Latest Collection",
        "-" if summary.latest_collected_at is None else _format_time(summary.latest_collected_at),
    )

    st.subheader("Latest Snapshot Top 10")
    st.dataframe(
        pd.DataFrame(_latest_rows(latest_snapshot)),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Snapshot 저장 스키마에는 Namuwiki 원본 링크가 포함되지 않아 링크는 표시하지 않습니다."
    )

    selected_keyword = st.selectbox(
        "검색어 선택",
        options=[row.keyword for row in statistics],
    )
    try:
        history = _load_keyword_history(selected_keyword)
    except (DashboardConfigurationError, DashboardDatabaseError):
        _show_database_error()
        return

    if history:
        st.subheader("Rank History")
        chart_frame = pd.DataFrame(
            {
                "Collected At (KST)": [point.collected_at for point in history],
                "Rank": [point.rank_position for point in history],
            }
        )
        figure = px.line(
            chart_frame,
            x="Collected At (KST)",
            y="Rank",
            markers=True,
            title=f"{selected_keyword} rank history",
        )
        figure.update_yaxes(autorange="reversed", dtick=1, title_text="Rank")
        st.plotly_chart(figure, width="stretch")

    st.subheader("Keyword Statistics")
    st.dataframe(
        pd.DataFrame(_statistics_rows(statistics)),
        width="stretch",
        hide_index=True,
    )


main()
