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
from automation_dashboard.readers.namuwiki_insights import (
    InsightStatus,
    NamuwikiInsightReadModel,
    NamuwikiInsightRow,
    read_namuwiki_insights,
)
from automation_dashboard.session import DashboardDatabaseError, dashboard_session
from automation_dashboard.ui.formatting import (
    format_duration,
    format_integer,
    format_kst_datetime,
)
from automation_dashboard.ui.layout import (
    configure_chart,
    render_information_card,
    render_page_header,
    render_section_header,
    render_sidebar_context,
)
from automation_dashboard.ui.states import render_database_error, render_empty_state

STATISTICS_LIMIT = 20


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


@st.cache_data(ttl=60, show_spinner=False)
def _load_insights() -> NamuwikiInsightReadModel:
    """Cache detached artifact data without modifying the production file."""
    return read_namuwiki_insights()


def _latest_rows(rows: list[LatestTrendRow]) -> list[dict[str, object]]:
    """Map persisted trend DTOs to the focused latest Top 10 table."""
    return [{"Rank": row.rank_position, "Keyword": row.keyword} for row in rows]


def _statistics_rows(rows: list[KeywordSummary]) -> list[dict[str, object]]:
    """Map keyword summary DTOs to consistent display columns."""
    return [
        {
            "Keyword": row.keyword,
            "Appearances": row.appearance_count,
            "Best Rank": row.best_rank,
            "First Seen": format_kst_datetime(row.first_seen_at),
            "Last Seen": format_kst_datetime(row.last_seen_at),
        }
        for row in rows
    ]


def _insight_rows(rows: tuple[NamuwikiInsightRow, ...]) -> list[dict[str, object]]:
    """Map artifact DTOs to concise table values."""
    return [
        {
            "Rank": row.rank,
            "Keyword": row.keyword,
            "Reason": row.reason,
            "Articles": row.article_count,
            "Generated At": format_kst_datetime(row.generated_at_kst),
        }
        for row in rows
    ]


def _render_insights(model: NamuwikiInsightReadModel) -> None:
    """Render artifact status and insight details without calling Gemini."""
    render_section_header(
        "LLM Trend Insights",
        "저장된 Namuwiki artifact만 조회합니다. Dashboard는 Gemini를 호출하지 않습니다.",
    )
    kpi_columns = st.columns(4)
    kpi_columns[0].metric("Status", model.status.value)
    kpi_columns[1].metric(
        "Generated At",
        format_kst_datetime(model.generated_at_kst),
    )
    kpi_columns[2].metric("Insight Items", format_integer(len(model.rows)))
    kpi_columns[3].metric("Data Age", format_duration(model.age))

    if model.status in {InsightStatus.NO_DATA, InsightStatus.PLANNED}:
        render_empty_state(model.message or "분석 결과가 없습니다.")
        return
    if model.status in {InsightStatus.INVALID_ARTIFACT, InsightStatus.UNAVAILABLE}:
        st.error(model.message or "LLM Insight artifact를 읽을 수 없습니다.")
        return
    if not model.rows:
        render_empty_state("저장된 LLM Insight item이 없습니다.")
        return

    selected_keyword = st.selectbox(
        "Insight 검색어 선택",
        options=[row.keyword for row in model.rows],
        key="namuwiki-insight-keyword",
    )
    selected = next(row for row in model.rows if row.keyword == selected_keyword)
    render_information_card(
        "Selected Insight",
        primary=("Keyword", selected.keyword),
        details=(
            ("Rank", str(selected.rank)),
            ("Articles", format_integer(selected.article_count)),
            ("Generated At", format_kst_datetime(selected.generated_at_kst)),
            ("Status", selected.status.value),
        ),
    )
    st.write(selected.reason)
    st.dataframe(
        pd.DataFrame(_insight_rows(model.rows)),
        width="stretch",
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "Keyword": st.column_config.TextColumn(width="medium"),
            "Reason": st.column_config.TextColumn(width="large"),
            "Articles": st.column_config.NumberColumn(width="small"),
            "Generated At": st.column_config.TextColumn(width="medium"),
        },
    )


def main() -> None:
    """Render the Namuwiki read-only snapshot view."""
    render_sidebar_context()
    try:
        latest_snapshot = _load_latest_snapshot()
        summary = _load_snapshot_summary()
        statistics = _load_keyword_statistics()
        insights = _load_insights()
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_page_header("Namuwiki Trends", "저장된 Top 10 Snapshot을 조회합니다.")
        render_database_error()
        return

    render_page_header(
        "Namuwiki Trends",
        "저장된 Top 10 Snapshot을 조회합니다. "
        "수집·enrichment·Gemini 호출·저장 작업은 수행하지 않습니다.",
        last_updated=summary.latest_collected_at,
    )
    _render_insights(insights)
    if not latest_snapshot:
        render_empty_state(
            "저장된 Namuwiki Snapshot이 없습니다. 먼저 snapshot job 상태를 확인하세요."
        )
        return

    overview_columns = st.columns(4)
    overview_columns[0].metric(
        "Latest Batch",
        f"{format_integer(len(latest_snapshot))} rows",
        help=f"저장된 Snapshot 묶음 수: {format_integer(summary.total_snapshot_count)}",
    )
    overview_columns[1].metric("Today's Collections", format_integer(summary.today_snapshot_count))
    overview_columns[2].metric("Unique Keywords", format_integer(summary.stored_keyword_count))
    overview_columns[3].metric("Stored Batches", format_integer(summary.total_snapshot_count))

    render_section_header("Latest Top 10", "가장 최근 저장된 순위입니다.")
    st.dataframe(
        pd.DataFrame(_latest_rows(latest_snapshot)),
        width="stretch",
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "Keyword": st.column_config.TextColumn(width="large"),
        },
    )

    selected_keyword = st.selectbox("검색어 선택", options=[row.keyword for row in statistics])
    selected_summary = next(row for row in statistics if row.keyword == selected_keyword)
    try:
        history = _load_keyword_history(selected_keyword)
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_database_error()
        return

    current_rank = next(
        (str(row.rank_position) for row in latest_snapshot if row.keyword == selected_keyword),
        "—",
    )
    render_section_header("Keyword Analysis", "선택한 검색어의 저장된 순위 기록입니다.")
    render_information_card(
        "Keyword Details",
        primary=("Keyword", selected_keyword),
        details=(
            ("Current Rank", current_rank),
            ("Occurrences", format_integer(selected_summary.appearance_count)),
            ("First Seen", format_kst_datetime(selected_summary.first_seen_at)),
            ("Last Seen", format_kst_datetime(selected_summary.last_seen_at)),
        ),
    )

    render_section_header("Rank History", "1위가 위에 표시됩니다.")
    if len(history) < 2:
        render_empty_state("이 검색어는 한 번만 저장되어 순위 추이를 표시할 수 없습니다.")
    else:
        chart_frame = pd.DataFrame(
            {
                "Collected At": [point.collected_at for point in history],
                "Rank": [point.rank_position for point in history],
            }
        )
        figure = px.line(
            chart_frame,
            x="Collected At",
            y="Rank",
            title=f"{selected_keyword} Rank History",
        )
        figure.update_traces(hovertemplate="Time: %{x|%Y-%m-%d %H:%M}<br>Rank: %{y}<extra></extra>")
        figure.update_yaxes(autorange="reversed", dtick=1)
        st.plotly_chart(
            configure_chart(figure, x_title="Collected At (KST)", y_title="Rank"),
            width="stretch",
        )

    render_section_header(
        "Keyword Statistics",
        f"등장 횟수, 최고 순위, 최근 등장 순서로 정렬된 상위 {STATISTICS_LIMIT}개입니다.",
    )
    st.dataframe(
        pd.DataFrame(_statistics_rows(statistics[:STATISTICS_LIMIT])),
        width="stretch",
        hide_index=True,
        column_config={
            "Keyword": st.column_config.TextColumn(width="large"),
            "Appearances": st.column_config.NumberColumn(width="small"),
            "Best Rank": st.column_config.NumberColumn(width="small"),
            "First Seen": st.column_config.TextColumn(width="medium"),
            "Last Seen": st.column_config.TextColumn(width="medium"),
        },
    )


if __name__ == "__main__":
    main()
