"""Read-only Google Finance snapshot dashboard page."""

from decimal import Decimal

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

HISTORY_LIMIT = 50


def _format_price(value: Decimal, currency: str) -> str:
    """Format a persisted Decimal price without changing its stored value."""
    return f"{value:,.2f} {currency}"


def _format_time(value: object) -> str:
    """Format an already localized timestamp for stable dashboard display."""
    return value.strftime("%Y-%m-%d %H:%M:%S %Z")


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
    """Map latest quote DTOs to UI values without exposing ORM objects."""
    return [
        {
            "Symbol": quote.symbol,
            "Name": quote.name,
            "Latest Price": _format_price(quote.current_price, quote.currency),
            "Currency": quote.currency,
            "Google Finance Change %": f"{quote.change_percent:.2f}%",
            "Latest Collected At": _format_time(quote.collected_at),
            "Snapshot Count": quote.snapshot_count,
        }
        for quote in quotes
    ]


def _history_table_rows(history: list[PricePoint]) -> list[dict[str, object]]:
    """Map historical DTOs to the recent snapshot table contract."""
    return [
        {
            "Collected At (KST)": _format_time(point.collected_at),
            "Current Price": _format_price(point.current_price, point.currency),
            "Google Finance Change %": f"{point.change_percent:.2f}%",
        }
        for point in reversed(history)
    ]


def _show_database_error() -> None:
    """Display a safe failure message without rendering provider or connection details."""
    st.error("데이터베이스 연결에 실패했습니다. Operations 로그와 DATABASE_URL 설정을 확인하세요.")


def main() -> None:
    """Render the Google Finance read-only snapshot view."""
    st.title("Google Finance")
    st.caption("저장된 Snapshot만 조회합니다. 수집·분석·저장 작업은 수행하지 않습니다.")

    try:
        quotes = _load_latest_quotes()
    except (DashboardConfigurationError, DashboardDatabaseError):
        _show_database_error()
        return

    if not quotes:
        st.info(
            "저장된 Google Finance Snapshot이 없습니다. "
            "먼저 collect job이 정상 실행됐는지 확인하세요."
        )
        return

    latest_collected_at = max(quote.collected_at for quote in quotes)
    total_snapshot_count = sum(quote.snapshot_count for quote in quotes)
    overview_columns = st.columns(3)
    overview_columns[0].metric("조회된 종목 수", len(quotes))
    overview_columns[1].metric("전체 Snapshot 수", total_snapshot_count)
    overview_columns[2].metric("마지막 전체 수집 시각", _format_time(latest_collected_at))

    st.subheader("최신 가격")
    st.dataframe(pd.DataFrame(_quote_table_rows(quotes)), use_container_width=True, hide_index=True)

    selected_symbol = st.selectbox(
        "종목 선택",
        options=[quote.symbol for quote in quotes],
        format_func=lambda symbol: next(
            quote.name for quote in quotes if quote.symbol == symbol
        )
        + f" ({symbol})",
    )
    selected_quote = next(quote for quote in quotes if quote.symbol == selected_symbol)

    try:
        delta = _load_latest_delta(selected_symbol)
        history = _load_price_history(selected_symbol)
    except (DashboardConfigurationError, DashboardDatabaseError):
        _show_database_error()
        return

    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "Latest Price",
        _format_price(selected_quote.current_price, selected_quote.currency),
    )
    metric_columns[1].metric(
        "Latest Delta",
        "비교 불가" if delta is None else f"{delta.price_delta:+.2f} {delta.currency}",
    )
    metric_columns[2].metric("Latest Change %", f"{selected_quote.change_percent:.2f}%")
    metric_columns[3].metric("Latest Collected At", _format_time(selected_quote.collected_at))

    if not history:
        st.info("선택한 종목의 저장된 Snapshot이 없습니다.")
        return

    st.subheader("가격 추이")
    chart_frame = pd.DataFrame(
        {
            "Collected At (KST)": [point.collected_at for point in history],
            "Current Price": [float(point.current_price) for point in history],
            "Google Finance Change %": [float(point.change_percent) for point in history],
        }
    )
    figure = px.line(
        chart_frame,
        x="Collected At (KST)",
        y="Current Price",
        markers=True,
        hover_data=["Google Finance Change %"],
        title=f"{selected_symbol} price history ({selected_quote.currency})",
    )
    figure.update_yaxes(title_text=f"Price ({selected_quote.currency})")
    st.plotly_chart(figure, use_container_width=True)

    st.subheader(f"최근 {min(len(history), HISTORY_LIMIT)}개 Snapshot")
    st.dataframe(
        pd.DataFrame(_history_table_rows(history)),
        use_container_width=True,
        hide_index=True,
    )


main()
