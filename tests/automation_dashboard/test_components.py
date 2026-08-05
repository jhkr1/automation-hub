"""Contracts for the shared Dashboard 2.0 presentation components."""

from inspect import signature

import pytest

from automation_dashboard.ui import components
from automation_dashboard.ui.tokens import DASHBOARD_CSS, STATUS_COLORS, TOKENS


def test_dashboard_tokens_define_shared_desktop_and_mobile_values() -> None:
    """Shared layout values are centralized instead of repeated in pages."""
    assert TOKENS.container_max_width == 1440
    assert TOKENS.grid_gap == 24
    assert TOKENS.section_gap == 40
    assert TOKENS.chart_height == 360
    assert TOKENS.mobile_chart_height == 280
    assert "stMetric" in DASHBOARD_CSS


def test_dashboard_css_uses_streamlit_theme_variables_for_surfaces_and_text() -> None:
    """Cards and metric text follow both Streamlit light and dark themes."""
    assert "var(--background-color" in DASHBOARD_CSS
    assert "var(--secondary-background-color" in DASHBOARD_CSS
    assert "var(--text-color" in DASHBOARD_CSS
    assert "background: #FFFFFF" not in DASHBOARD_CSS
    assert "background: #F8FAFC" not in DASHBOARD_CSS


def test_status_badge_uses_theme_text_and_status_border(monkeypatch: pytest.MonkeyPatch) -> None:
    """Status meaning remains colored while its text follows the active theme."""
    rendered: list[str] = []

    class Container:
        def markdown(self, value: str, **kwargs: object) -> None:
            rendered.append(value)

        def caption(self, value: str) -> None:
            rendered.append(value)

    components.render_status_badge("Healthy", container=Container())

    assert rendered
    assert "var(--text-color)" in rendered[0]
    assert "border:1px solid #188038" in rendered[0]


def test_status_colors_have_textual_state_contract() -> None:
    """Every supported state has a presentation color, while text remains primary."""
    assert set(STATUS_COLORS) >= {
        "Healthy",
        "Stale",
        "No Data",
        "Unavailable",
        "Invalid Artifact",
        "Planned",
        "Loading",
    }


@pytest.mark.parametrize(
    "component_name",
    [
        "render_page_hero",
        "render_hero_metric",
        "render_metric_card",
        "render_insight_card",
        "render_chart_card",
        "render_table_card",
        "render_status_badge",
        "render_section_title",
        "render_empty_state",
        "render_attention_banner",
        "render_overview_card",
        "render_metadata_card",
        "render_timeline_card",
        "render_selection_panel",
        "render_loading_placeholder",
    ],
)
def test_shared_components_expose_callable_renderers(component_name: str) -> None:
    """The shared UI surface is importable without starting a dashboard job."""
    renderer = getattr(components, component_name)
    assert callable(renderer)
    assert signature(renderer)


def test_selection_panel_returns_none_for_empty_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty selections do not create an invalid Streamlit selectbox."""
    called = False

    def selectbox(*args, **kwargs):
        nonlocal called
        called = True
        return "unexpected"

    monkeypatch.setattr(components.st, "selectbox", selectbox)

    assert components.render_selection_panel("Select", []) is None
    assert called is False
