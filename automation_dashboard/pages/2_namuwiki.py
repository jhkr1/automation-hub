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
from automation_dashboard.ui.components import (
    apply_dashboard_theme,
    render_chart_card,
    render_empty_state,
    render_insight_card,
    render_metadata_card,
    render_page_hero,
    render_section_title,
    render_selection_panel,
    render_table_card,
)
from automation_dashboard.ui.formatting import (
    format_integer,
    format_kst_datetime,
)
from automation_dashboard.ui.layout import render_sidebar_context
from automation_dashboard.ui.states import render_database_error

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
    render_section_title("Top Keyword", "저장된 Insight 중 첫 번째 순위의 요약입니다.")
    if model.status in {InsightStatus.NO_DATA, InsightStatus.PLANNED}:
        render_empty_state(model.message or "분석 결과가 없습니다.")
        return
    if model.status in {InsightStatus.INVALID_ARTIFACT, InsightStatus.UNAVAILABLE}:
        st.error(model.message or "LLM Insight artifact를 읽을 수 없습니다.")
        return
    if not model.rows:
        render_empty_state("저장된 LLM Insight item이 없습니다.")
        return

    selected_keyword = render_selection_panel(
        "Insight detail",
        options=[row.keyword for row in model.rows],
        format_func=str,
        key="namuwiki-insight-keyword",
    )
    if selected_keyword is None:
        render_empty_state("선택 가능한 Insight가 없습니다.")
        return
    selected = next(row for row in model.rows if row.keyword == selected_keyword)
    render_insight_card(
        status=selected.status.value,
        headline=f"{selected.keyword} · Rank {selected.rank}",
        summary=selected.reason,
        evidence=f"{format_integer(selected.article_count)} articles",
        generated_at=selected.generated_at_kst,
    )
    render_table_card(
        "Insight Details",
        pd.DataFrame(_insight_rows(model.rows)),
        description="저장된 Insight metadata를 표시합니다.",
    )


def main() -> None:
    """Render the Namuwiki read-only snapshot view."""
    apply_dashboard_theme()
    render_sidebar_context()
    try:
        latest_snapshot = _load_latest_snapshot()
        summary = _load_snapshot_summary()
        statistics = _load_keyword_statistics()
        insights = _load_insights()
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_page_hero(
            "Namuwiki Trends",
            "저장된 Top 10 Snapshot을 조회하는 Read-only 화면입니다.",
            status="Unavailable",
        )
        render_database_error()
        return

    data_status = "Healthy" if summary.latest_collected_at is not None else "No Data"
    render_page_hero(
        "Namuwiki Trends",
        "저장된 Top 10 Snapshot을 조회하는 Read-only 화면입니다.",
        primary_entity=(latest_snapshot[0].keyword if latest_snapshot else None),
        status=data_status,
        last_updated=summary.latest_collected_at,
    )
    _render_insights(insights)
    if not latest_snapshot:
        render_empty_state(
            "저장된 Namuwiki Snapshot이 없습니다. 먼저 snapshot job 상태를 확인하세요."
        )
        return

    render_section_title("Top 10", "가장 최근 저장된 순위입니다.")
    render_table_card(
        "Latest Ranking",
        pd.DataFrame(_latest_rows(latest_snapshot)),
        description=(
            f"{format_integer(len(latest_snapshot))} rows · "
            f"{format_integer(summary.total_snapshot_count)} stored batches"
        ),
    )

    selected_keyword = render_selection_panel(
        "Keyword",
        [row.keyword for row in statistics],
    )
    if selected_keyword is None:
        render_empty_state("선택 가능한 검색어가 없습니다.")
        return
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
    render_section_title("History", "선택한 검색어의 저장된 순위 기록입니다.")
    if len(history) < 2:
        render_empty_state("이 검색어는 한 번만 저장되어 순위 추이를 표시할 수 없습니다.")
    else:
        chart_frame = pd.DataFrame(
            {
                "Collected At": [point.collected_at for point in history],
                "Rank": [point.rank_position for point in history],
            }
        )
        figure = px.line(chart_frame, x="Collected At", y="Rank")
        figure.update_traces(hovertemplate="Time: %{x|%Y-%m-%d %H:%M}<br>Rank: %{y}<extra></extra>")
        figure.update_yaxes(autorange="reversed", dtick=1)
        render_chart_card(
            f"{selected_keyword} Rank History",
            figure,
            x_title="Collected At (KST)",
            y_title="Rank",
        )

    render_section_title(
        "Statistics",
        f"등장 횟수, 최고 순위, 최근 등장 순서로 정렬된 상위 {STATISTICS_LIMIT}개입니다.",
    )
    render_table_card(
        "Keyword Statistics",
        pd.DataFrame(_statistics_rows(statistics[:STATISTICS_LIMIT])),
    )

    render_section_title("Metadata")
    render_metadata_card(
        "Snapshot Metadata",
        {
            "Selected Keyword": selected_keyword,
            "Current Rank": current_rank,
            "Occurrences": format_integer(selected_summary.appearance_count),
            "First Seen": format_kst_datetime(selected_summary.first_seen_at),
            "Last Seen": format_kst_datetime(selected_summary.last_seen_at),
            "Latest Batch": format_integer(len(latest_snapshot)),
            "Today's Collections": format_integer(summary.today_snapshot_count),
            "Stored Keywords": format_integer(summary.stored_keyword_count),
        },
    )


if __name__ == "__main__":
    main()
