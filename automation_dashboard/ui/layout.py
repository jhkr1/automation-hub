"""Small Streamlit layout helpers shared by all dashboard pages."""

from collections.abc import Sequence
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from automation_dashboard.ui.formatting import format_kst_datetime

CACHE_TTL_SECONDS = 60


def configure_chart(figure: go.Figure, *, x_title: str, y_title: str) -> go.Figure:
    """Apply a restrained Plotly layout that keeps Streamlit themes intact."""
    figure.update_layout(
        height=360,
        hovermode="x unified",
        margin={"l": 20, "r": 20, "t": 56, "b": 20},
        showlegend=False,
    )
    figure.update_xaxes(title_text=x_title)
    figure.update_yaxes(title_text=y_title)
    return figure


def render_page_header(
    title: str,
    description: str,
    *,
    last_updated: datetime | None = None,
) -> None:
    """Render a consistent page title, purpose, and optional data timestamp."""
    st.title(title)
    st.caption(description)
    if last_updated is not None:
        st.caption(f"마지막 데이터 갱신: {format_kst_datetime(last_updated)}")


def render_section_header(title: str, description: str | None = None) -> None:
    """Render a compact section heading with optional reader guidance."""
    st.subheader(title)
    if description:
        st.caption(description)


def render_information_card(
    title: str,
    *,
    primary: tuple[str, str] | None = None,
    details: Sequence[tuple[str, str]] = (),
) -> None:
    """Render long names and timestamps outside compact KPI components."""
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if primary is not None:
            st.caption(primary[0])
            st.write(primary[1])
        if details:
            for index in range(0, len(details), 2):
                row_details = details[index : index + 2]
                columns = st.columns(len(row_details))
                for column, (label, value) in zip(columns, row_details, strict=True):
                    column.caption(label)
                    column.write(value)


def render_sidebar_context() -> None:
    """Explain read-only behavior and offer an explicit cache-only refresh."""
    with st.sidebar:
        st.divider()
        st.caption("Automation Hub Dashboard")
        st.caption("Read-only · 조회 캐시 최대 60초")
        if st.button("조회 캐시 새로고침", width="stretch"):
            st.cache_data.clear()
            st.rerun()
