"""Read-only Google Finance snapshot dashboard page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from automation_dashboard.config import DashboardConfigurationError
from automation_dashboard.queries.google_finance import (
    LatestQuoteRow,
    PricePoint,
    SnapshotDelta,
    list_latest_quotes,
    load_latest_delta,
    load_price_history,
)
from automation_dashboard.session import DashboardDatabaseError, dashboard_session
from automation_dashboard.ui.formatting import (
    format_integer,
    format_kst_datetime,
    format_percent,
    format_price,
    format_signed_price,
)
from automation_dashboard.ui.layout import (
    configure_chart,
    render_page_header,
    render_section_header,
    render_sidebar_context,
)
from automation_dashboard.ui.states import render_database_error, render_empty_state

HISTORY_LIMIT = 20


@st.cache_data(ttl=60, show_spinner=False)
def _load_latest_quotes() -> list[LatestQuoteRow]:
    """Cache detached DTOs, never Sessions, engines, ORM rows, or secrets."""
    with dashboard_session() as session:
        return list_latest_quotes(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_price_history(symbol: str) -> list[PricePoint]:
    """Cache one symbol's detached history DTOs for a short dashboard interval."""
    with dashboard_session() as session:
        return load_price_history(session, symbol, limit=HISTORY_LIMIT)


@st.cache_data(ttl=60, show_spinner=False)
def _load_latest_delta(symbol: str) -> SnapshotDelta | None:
    """Cache one symbol's detached two-snapshot comparison."""
    with dashboard_session() as session:
        return load_latest_delta(session, symbol)


def _quote_table_rows(quotes: list[LatestQuoteRow]) -> list[dict[str, object]]:
    """Map latest quote DTOs to concise UI columns without exposing ORM objects."""
    return [
        {
            "Symbol": quote.symbol,
            "Name": quote.name,
            "Price": format_price(quote.current_price, quote.currency),
            "Change %": format_percent(quote.change_percent),
            "Collected At": format_kst_datetime(quote.collected_at),
            "Snapshots": format_integer(quote.snapshot_count),
        }
        for quote in quotes
    ]


def _history_table_rows(history: list[PricePoint]) -> list[dict[str, object]]:
    """Map oldest-to-newest chart data to a separate latest-first table contract."""
    return [
        {
            "Collected At": format_kst_datetime(point.collected_at),
            "Price": format_price(point.current_price, point.currency),
            "Change %": format_percent(point.change_percent),
        }
        for point in reversed(history)
    ]


def _selected_label(symbol: str, quotes: list[LatestQuoteRow]) -> str:
    """Format a symbol option without duplicating table-level column labels."""
    quote = next(quote for quote in quotes if quote.symbol == symbol)
    return f"{quote.name} ({symbol})"


def main() -> None:
    """Render the Google Finance read-only snapshot view."""
    render_sidebar_context()
    try:
        quotes = _load_latest_quotes()
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_page_header("Google Finance", "저장된 가격 Snapshot을 조회합니다.")
        render_database_error()
        return

    latest_collected_at = max((quote.collected_at for quote in quotes), default=None)
    render_page_header(
        "Google Finance",
        "저장된 가격 Snapshot을 조회합니다. 수집·분석·저장 작업은 수행하지 않습니다.",
        last_updated=latest_collected_at,
    )
    if not quotes:
        render_empty_state(
            "저장된 Google Finance Snapshot이 없습니다. 먼저 collect job 상태를 확인하세요."
        )
        return

    render_section_header("Latest Quotes", "종목별 최신 저장 가격입니다.")
    st.dataframe(
        pd.DataFrame(_quote_table_rows(quotes)),
        width="stretch",
        hide_index=True,
    )

    selected_symbol = st.selectbox(
        "종목 선택",
        options=[quote.symbol for quote in quotes],
        format_func=lambda symbol: _selected_label(symbol, quotes),
    )
    selected_quote = next(quote for quote in quotes if quote.symbol == selected_symbol)
    try:
        delta = _load_latest_delta(selected_symbol)
        history = _load_price_history(selected_symbol)
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_database_error()
        return

    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "Latest Price",
        format_price(selected_quote.current_price, selected_quote.currency),
    )
    metric_columns[1].metric(
        "Price Delta",
        format_signed_price(None if delta is None else delta.price_delta, selected_quote.currency),
    )
    metric_columns[2].metric("Change %", format_percent(selected_quote.change_percent))
    metric_columns[3].metric("Last Collected", format_kst_datetime(selected_quote.collected_at))

    render_section_header(
        "Price History",
        "차트는 오래된 순서이고, 아래 표는 최근 수집 시각부터 표시합니다.",
    )
    if len(history) < 2:
        render_empty_state("가격 추이를 표시하려면 선택 종목의 Snapshot이 두 개 이상 필요합니다.")
    else:
        chart_frame = pd.DataFrame(
            {
                "Collected At": [point.collected_at for point in history],
                "Price": [float(point.current_price) for point in history],
            }
        )
        figure = px.line(
            chart_frame,
            x="Collected At",
            y="Price",
            title=f"{selected_symbol} Price History ({selected_quote.currency})",
        )
        figure.update_traces(
            hovertemplate="Time: %{x|%Y-%m-%d %H:%M}<br>Price: %{y}<extra></extra>"
        )
        st.plotly_chart(
            configure_chart(figure, x_title="Collected At (KST)", y_title=selected_quote.currency),
            width="stretch",
        )

    st.dataframe(
        pd.DataFrame(_history_table_rows(history)),
        width="stretch",
        hide_index=True,
    )


if __name__ == "__main__":
    main()
