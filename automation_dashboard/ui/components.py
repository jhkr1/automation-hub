"""Reusable, presentation-only Streamlit components."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from html import escape
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from automation_dashboard.ui.formatting import format_duration, format_kst_datetime
from automation_dashboard.ui.layout import configure_chart
from automation_dashboard.ui.states import status_presentation
from automation_dashboard.ui.tokens import DASHBOARD_CSS, STATUS_COLORS


def apply_dashboard_theme() -> None:
    """Inject the shared visual rules once per Streamlit script run."""
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)


def render_page_hero(
    title: str,
    description: str,
    *,
    primary_entity: str | None = None,
    status: str | None = None,
    last_updated: datetime | None = None,
) -> None:
    """Render the shared page title and optional primary context."""
    with st.container(border=True):
        st.title(title)
        st.caption(description)
        columns = st.columns(3)
        if primary_entity is not None:
            columns[0].caption("Primary Entity")
            columns[0].write(primary_entity)
        if status is not None:
            columns[1].caption("Status")
            render_status_badge(status, container=columns[1])
        if last_updated is not None:
            columns[2].caption("Last Updated")
            columns[2].write(format_kst_datetime(last_updated))


def render_hero_metric(
    label: str,
    value: str,
    *,
    detail: str | None = None,
    delta: str | None = None,
) -> None:
    """Render a prominent value for the page's primary entity."""
    with st.container(border=True):
        st.caption(label)
        st.metric(label, value, delta=delta, delta_color="off")
        if detail:
            st.caption(detail)


def render_metric_card(
    label: str,
    value: str,
    *,
    detail: str | None = None,
) -> None:
    """Render a compact numeric or short-status card."""
    with st.container(border=True):
        st.metric(label, value, delta_color="off")
        if detail:
            st.caption(detail)


def render_insight_card(
    *,
    status: str,
    summary: str | None = None,
    headline: str | None = None,
    evidence: str | None = None,
    generated_at: datetime | None = None,
    confidence: str | None = None,
) -> None:
    """Render an insight without inventing unavailable fields."""
    with st.container(border=True):
        render_status_badge(status)
        if headline:
            st.subheader(headline)
        if summary:
            st.write(summary)
        if evidence or confidence or generated_at:
            details: list[str] = []
            if evidence:
                details.append(f"Evidence: {evidence}")
            if confidence:
                details.append(f"Confidence: {confidence}")
            if generated_at:
                details.append(f"Generated: {format_kst_datetime(generated_at)}")
            st.caption(" · ".join(details))


def render_chart_card(
    title: str,
    figure: go.Figure,
    *,
    x_title: str,
    y_title: str,
    interpretation: str | None = None,
) -> None:
    """Render a chart with the shared height and restrained layout."""
    with st.container(border=True):
        st.subheader(title)
        st.plotly_chart(
            configure_chart(figure, x_title=x_title, y_title=y_title),
            width="stretch",
        )
        if interpretation:
            st.caption(interpretation)


def render_table_card(
    title: str,
    data: Any,
    *,
    description: str | None = None,
) -> None:
    """Render a detailed table as a secondary information surface."""
    with st.container(border=True):
        st.subheader(title)
        if description:
            st.caption(description)
        st.dataframe(data, width="stretch", hide_index=True)


def render_status_badge(
    status: str,
    *,
    detail: str | None = None,
    container: Any = st,
) -> None:
    """Render status text with a non-color fallback for accessibility."""
    presentation = status_presentation(status)
    color = STATUS_COLORS[presentation.tone]
    safe_status = escape(presentation.label)
    container.markdown(
        (
            '<span '
            'style="'
            'color:var(--text-color);'
            'background-color:var(--secondary-background-color);'
            f"border:1px solid {color};"
            'border-radius:999px;'
            'display:inline-block;'
            'font-weight:600;'
            'padding:2px 8px;'
            '">'
            f"{safe_status}</span>"
        ),
        unsafe_allow_html=True,
    )
    if detail:
        container.caption(detail)


def render_section_title(title: str, description: str | None = None) -> None:
    """Render a consistent section heading."""
    st.subheader(title)
    if description:
        st.caption(description)


def render_empty_state(
    message: str,
    *,
    status: str = "No Data",
    next_action: str | None = None,
) -> None:
    """Render a text-first empty or planned state."""
    with st.container(border=True):
        render_status_badge(status)
        st.info(message)
        if next_action:
            st.caption(next_action)


def render_attention_banner(
    title: str,
    message: str,
    *,
    status: str = "Unavailable",
) -> None:
    """Render a prominent issue without exposing raw exceptions."""
    with st.container(border=True):
        render_status_badge(status)
        st.warning(f"{title}: {message}")


def render_overview_card(
    title: str,
    headline: str,
    *,
    status: str,
    detail: str | None = None,
    link_label: str | None = None,
    link_target: str | None = None,
) -> None:
    """Render a Home page package summary."""
    with st.container(border=True):
        st.subheader(title)
        render_status_badge(status)
        st.write(headline)
        if detail:
            st.caption(detail)
        if link_label and link_target:
            st.page_link(link_target, label=link_label, width="stretch")


def render_metadata_card(
    title: str,
    items: Mapping[str, str],
) -> None:
    """Render secondary metadata in a consistent two-column card."""
    with st.container(border=True):
        st.subheader(title)
        values = list(items.items())
        for index in range(0, len(values), 2):
            row = values[index : index + 2]
            columns = st.columns(len(row))
            for column, (label, value) in zip(columns, row, strict=True):
                column.caption(label)
                column.write(value)


def render_timeline_card(
    title: str,
    items: Sequence[Mapping[str, str]],
    *,
    empty_message: str = "최근 활동이 없습니다.",
) -> None:
    """Render recent activity as a compact chronological list."""
    with st.container(border=True):
        st.subheader(title)
        if not items:
            render_empty_state(empty_message)
            return
        for item in items:
            timestamp = item.get("timestamp", "—")
            label = item.get("label", "Activity")
            detail = item.get("detail")
            st.markdown(f"**{timestamp}**  {label}")
            if detail:
                st.caption(detail)


def render_selection_panel(
    label: str,
    options: Sequence[str],
    *,
    default_index: int = 0,
    format_func: Any = str,
    key: str | None = None,
) -> str | None:
    """Render a safe selector and return None when no option exists."""
    if not options:
        return None
    index = min(max(default_index, 0), len(options) - 1)
    return st.selectbox(
        label,
        options=list(options),
        index=index,
        format_func=format_func,
        key=key,
    )


def render_loading_placeholder(message: str = "Loading dashboard data...") -> None:
    """Render a lightweight loading state using native Streamlit primitives."""
    with st.container(border=True):
        render_status_badge("Loading")
        st.info(message)


def format_data_age(age: timedelta | None) -> str:
    """Format an optional age for shared cards."""
    return format_duration(age)
