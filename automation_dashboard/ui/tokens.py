"""Design tokens for the read-only Automation Hub dashboard UI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardTokens:
    """Stable visual values shared by dashboard components."""

    container_max_width: int = 1_440
    page_padding: int = 32
    mobile_padding: int = 16
    grid_gap: int = 24
    card_gap: int = 16
    section_gap: int = 40
    card_padding: int = 16
    card_radius: int = 12
    card_min_height: int = 80
    primary_card_min_height: int = 144
    chart_height: int = 360
    mobile_chart_height: int = 280
    page_title_size: int = 32
    hero_value_size: int = 28
    section_title_size: int = 20
    body_size: int = 14
    caption_size: int = 12


TOKENS = DashboardTokens()

STATUS_COLORS: dict[str, str] = {
    "Healthy": "#188038",
    "Stale": "#B06000",
    "No Data": "#5F6368",
    "Unavailable": "#B3261E",
    "Invalid Artifact": "#B3261E",
    "Planned": "#5F6368",
    "Loading": "#5F6368",
}


DASHBOARD_CSS = f"""
<style>
:root {{
    --automation-card-radius: {TOKENS.card_radius}px;
    --automation-card-padding: {TOKENS.card_padding}px;
    --automation-section-gap: {TOKENS.section_gap}px;
}}

[data-testid="stMetric"] {{
    border: 1px solid #E5E7EB;
    border-radius: var(--automation-card-radius);
    padding: var(--automation-card-padding);
    background: #FFFFFF;
    min-height: {TOKENS.card_min_height}px;
}}

[data-testid="stMetricValue"] {{
    line-height: 1.2;
}}

[data-testid="stDataFrame"] {{
    border-radius: var(--automation-card-radius);
}}

[data-testid="stExpander"] {{
    border-radius: var(--automation-card-radius);
}}
</style>
"""
