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
from automation_dashboard.readers.google_finance_insights import (
    GoogleFinanceInsightReadModel,
    read_google_finance_insights,
)
from automation_dashboard.session import DashboardDatabaseError, dashboard_session
from automation_dashboard.ui.components import (
    apply_dashboard_theme,
    render_attention_banner,
    render_chart_card,
    render_empty_state,
    render_hero_metric,
    render_insight_card,
    render_metadata_card,
    render_page_hero,
    render_section_title,
    render_selection_panel,
    render_table_card,
)
from automation_dashboard.ui.formatting import (
    format_kst_datetime,
    format_percent,
    format_price,
    format_signed_price,
)
from automation_dashboard.ui.layout import (
    render_sidebar_context,
)
from automation_dashboard.ui.states import (
    GOOGLE_FRESHNESS_THRESHOLD,
    freshness_state,
    render_database_error,
)
from google_finance.config import Settings as GoogleFinanceSettings

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


@st.cache_data(ttl=60, show_spinner=False)
def _load_insights() -> GoogleFinanceInsightReadModel:
    """Cache the detached Google Finance artifact read model."""
    return read_google_finance_insights()


@st.cache_data(ttl=60, show_spinner=False)
def _load_watchlist_symbols() -> list[str]:
    """Load the active Watchlist through the package Settings contract."""
    return GoogleFinanceSettings().get_symbol_list()


def _filter_active_quotes(
    quotes: list[LatestQuoteRow],
    active_symbols: list[str],
) -> list[LatestQuoteRow]:
    """Show only current Watchlist symbols, preserving Watchlist order."""
    quotes_by_symbol = {quote.symbol: quote for quote in quotes}
    return [quotes_by_symbol[symbol] for symbol in active_symbols if symbol in quotes_by_symbol]


def _history_table_rows(history: list[PricePoint]) -> list[dict[str, object]]:
    """Map oldest-to-newest chart data to a separate latest-first table contract."""
    return [
        {
            "Collected At": format_kst_datetime(point.collected_at),
            "Price": format_price(point.current_price, point.currency),
            "Currency": point.currency,
            "Change %": format_percent(point.change_percent),
        }
        for point in reversed(history)
    ]


def _selected_label(symbol: str, quotes: list[LatestQuoteRow]) -> str:
    """Format a symbol option without duplicating table-level column labels."""
    quote = next(quote for quote in quotes if quote.symbol == symbol)
    return f"{quote.name} ({symbol})"


def _render_insights(model: GoogleFinanceInsightReadModel, selected_symbol: str) -> None:
    """Render only the exact selected-symbol insight from the artifact."""
    row = model.row_for_symbol(selected_symbol)
    if row is None:
        render_insight_card(
            status="Symbol Not Analyzed",
            headline=f"No Insight for Selected Symbol · {selected_symbol}",
            summary="선택한 종목에 대한 분석 결과가 아직 없습니다.",
        )
        return

    status = model.status.value if row.status == "SUCCESS" else "Unavailable"
    evidence = " · ".join(
        value
        for value in (
            f"Snapshot movement: {row.snapshot_movement}" if row.snapshot_movement else None,
            f"Snapshot change: {row.snapshot_change_percent}%"
            if row.snapshot_change_percent is not None
            else None,
            f"Google Finance change: {row.google_finance_change_percent}%"
            if row.google_finance_change_percent is not None
            else None,
            f"News count: {row.news_count}" if row.news_count is not None else None,
            f"Data age: {model.age}" if model.age is not None else None,
        )
        if value is not None
    )
    render_insight_card(
        status=status,
        headline=f"LLM Stock Insight · {row.company_name or selected_symbol}",
        summary=row.summary or "선택한 종목의 분석 결과를 사용할 수 없습니다.",
        evidence=evidence or None,
        generated_at=row.analyzed_at_kst,
    )


def _render_price_hero(
    quote: LatestQuoteRow,
    delta: SnapshotDelta | None,
) -> None:
    """Render the selected symbol's primary price and status context."""
    movement = (
        "Available"
        if delta is not None
        else "Movement Unavailable"
    )
    data_state = freshness_state(
        quote.collected_at,
        threshold=GOOGLE_FRESHNESS_THRESHOLD,
    )
    price_delta = None if delta is None else format_signed_price(delta.price_delta, quote.currency)
    price_columns = st.columns([2, 1])
    with price_columns[0]:
        render_hero_metric(
            "Current Price",
            format_price(quote.current_price, quote.currency),
            detail=f"{quote.name} · {quote.symbol}",
            delta=price_delta,
        )
    with price_columns[1]:
        render_metadata_card(
            "Status Context",
            {
                "Data Status": data_state.label,
                "Change %": format_percent(quote.change_percent),
                "Last Collected": format_kst_datetime(quote.collected_at),
                "Movement": movement,
            },
        )
    if data_state.label in {"Stale", "No Data"}:
        render_attention_banner(
            "Google Finance",
            f"데이터 상태가 {data_state.label}입니다.",
            status=data_state.label,
        )
    elif delta is None:
        render_attention_banner(
            "Movement",
            "직전 Snapshot이 없어 변화량을 계산할 수 없습니다.",
            status="Movement Unavailable",
        )


def _render_price_chart(
    selected_symbol: str,
    selected_quote: LatestQuoteRow,
    history: list[PricePoint],
) -> None:
    """Render price history without smoothing, forecasting, or invented data."""
    if len(history) < 2:
        render_empty_state(
            "가격 추이를 표시하려면 선택 종목의 Snapshot이 두 개 이상 필요합니다."
        )
        return
    chart_frame = pd.DataFrame(
        {
            "Collected At": [point.collected_at for point in history],
            "Price": [float(point.current_price) for point in history],
        }
    )
    figure = px.line(chart_frame, x="Collected At", y="Price")
    figure.update_traces(
        hovertemplate="Time: %{x|%Y-%m-%d %H:%M KST}<br>Price: %{y}<extra></extra>"
    )
    render_chart_card(
        f"{selected_symbol} Price History ({selected_quote.currency})",
        figure,
        x_title="Collected At (KST)",
        y_title=selected_quote.currency,
        interpretation="저장된 가격 Snapshot을 오래된 순서로 표시합니다.",
    )


def main() -> None:
    """Render the Google Finance read-only snapshot view."""
    apply_dashboard_theme()
    render_sidebar_context()
    try:
        quotes = _filter_active_quotes(_load_latest_quotes(), _load_watchlist_symbols())
    except (DashboardConfigurationError, DashboardDatabaseError, ValueError):
        render_page_hero(
            "Google Finance",
            "현재 Watchlist와 저장된 가격 Snapshot을 조회하는 Read-only 화면입니다.",
            status="Unavailable",
        )
        render_empty_state("현재 Google Finance Watchlist 설정을 확인할 수 없습니다.")
        return

    if not quotes:
        render_page_hero(
            "Google Finance",
            "현재 Watchlist와 저장된 가격 Snapshot을 조회하는 Read-only 화면입니다.",
            status="No Data",
        )
        render_empty_state(
            "저장된 Google Finance Snapshot이 없습니다. 먼저 collect job 상태를 확인하세요."
        )
        return

    default_quote = max(quotes, key=lambda quote: quote.collected_at)
    default_state = freshness_state(
        default_quote.collected_at,
        threshold=GOOGLE_FRESHNESS_THRESHOLD,
    )
    render_page_hero(
        "Google Finance",
        "현재 Watchlist와 저장된 가격 Snapshot을 조회하는 Read-only 화면입니다.",
        primary_entity=f"{default_quote.name} ({default_quote.symbol})",
        status=default_state.label,
        last_updated=default_quote.collected_at,
    )
    selected_symbol = render_selection_panel(
        "Select symbol",
        [quote.symbol for quote in quotes],
        default_index=next(index for index, quote in enumerate(quotes) if quote == default_quote),
        format_func=lambda symbol: _selected_label(symbol, quotes),
    )
    if selected_symbol is None:
        render_empty_state("선택 가능한 종목이 없습니다.")
        return
    selected_quote = next(quote for quote in quotes if quote.symbol == selected_symbol)
    try:
        delta = _load_latest_delta(selected_symbol)
        history = _load_price_history(selected_symbol)
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_database_error()
        return

    render_section_title("Primary Price", "선택한 종목의 최신 저장 가격입니다.")
    _render_price_hero(selected_quote, delta)

    render_section_title("Price Visualization")
    _render_price_chart(selected_symbol, selected_quote, history)

    render_section_title("AI Insight")
    _render_insights(_load_insights(), selected_symbol)

    render_section_title("Snapshot History", "최신 수집 시각부터 표시합니다.")
    history_frame = pd.DataFrame(_history_table_rows(history))
    render_table_card(
        "History",
        history_frame,
        description="가격과 변화율은 저장된 Snapshot 값입니다.",
    )

    first_collected = history[-1].collected_at if history else selected_quote.collected_at
    render_section_title("Metadata")
    render_metadata_card(
        "Selected Instrument",
        {
            "Symbol": selected_quote.symbol,
            "Instrument": selected_quote.name,
            "Currency": selected_quote.currency,
            "Snapshot Count": str(selected_quote.snapshot_count),
            "First Collected": format_kst_datetime(first_collected),
            "Last Collected": format_kst_datetime(selected_quote.collected_at),
            "Movement": "Available" if delta is not None else "Unavailable",
            "Source": "Google Finance Snapshot",
        },
    )


if __name__ == "__main__":
    main()
