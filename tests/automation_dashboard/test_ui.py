"""Focused UI helper and page import contracts for the dashboard."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from importlib import import_module
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from automation_dashboard.ui.formatting import (
    MISSING_VALUE,
    format_duration,
    format_file_size,
    format_kst_date,
    format_kst_datetime,
    format_kst_time,
    format_percent,
    format_price,
    format_repository_location,
    format_signed_price,
)
from automation_dashboard.ui.states import availability_state, freshness_state


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("206.64000000"), "+206.64%"),
        (Decimal("-0.36000000"), "-0.36%"),
        (Decimal("0.00000000"), "0%"),
        (None, MISSING_VALUE),
    ],
)
def test_percentage_formatting_is_concise_and_textually_signed(
    value: Decimal | None,
    expected: str,
) -> None:
    """Percentages retain meaningful Decimal precision without trailing zero noise."""
    assert format_percent(value) == expected


def test_common_value_formatting_handles_kst_duration_size_and_missing_values() -> None:
    """The shared UI contract produces concise values without exposing local paths."""
    assert format_price(Decimal("231000.00000000"), "KRW") == "231,000 KRW"
    assert format_price(None, "USD") == MISSING_VALUE
    assert format_signed_price(Decimal("1.25000000"), "USD") == "+1.25 USD"
    assert format_signed_price(Decimal("-1.25000000"), "USD") == "-1.25 USD"
    assert format_kst_datetime(datetime(2026, 8, 4, 7, 17)) == "2026-08-04 16:17 KST"
    assert format_kst_date(datetime(2026, 8, 4, 7, 17)) == "2026-08-04"
    assert format_kst_time(datetime(2026, 8, 4, 7, 17)) == "16:17"
    assert format_duration(timedelta(seconds=72)) == "1분 12초"
    assert format_file_size(12_800) == "12.5 KB"
    assert format_file_size(None) == MISSING_VALUE
    assert format_repository_location(Path("/home/user/automation-hub")) == "automation-hub"


def test_freshness_state_uses_documented_threshold_boundaries() -> None:
    """A value at the threshold is healthy, while a later value is stale."""
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    healthy = freshness_state(
        now - timedelta(hours=2),
        threshold=timedelta(hours=2),
        now=now,
    )
    stale = freshness_state(
        now - timedelta(hours=2, seconds=1),
        threshold=timedelta(hours=2),
        now=now,
    )

    assert healthy.label == "Healthy"
    assert stale.label == "Stale"
    assert freshness_state(None, threshold=timedelta(hours=2), now=now).label == "No Data"


def test_availability_state_keeps_healthy_unavailable_and_unknown_as_text() -> None:
    """Status is understandable without relying on a color-only dashboard signal."""
    assert availability_state(True).label == "Healthy"
    assert availability_state(False).label == "Unavailable"
    assert availability_state(None).label == "Unknown"


@pytest.mark.parametrize(
    "module_name",
    [
        "automation_dashboard.pages.1_google_finance",
        "automation_dashboard.pages.2_namuwiki",
        "automation_dashboard.pages.3_operations",
    ],
)
def test_dashboard_pages_are_importable_without_running_database_queries(module_name: str) -> None:
    """Each page exposes a render entrypoint while preserving read-only test isolation."""
    module = import_module(module_name)
    assert callable(module.main)


@pytest.mark.parametrize(
    "script_path",
    [
        "automation_dashboard/app.py",
        "automation_dashboard/pages/1_google_finance.py",
        "automation_dashboard/pages/2_namuwiki.py",
        "automation_dashboard/pages/3_operations.py",
    ],
)
def test_dashboard_app_pages_render_without_database_or_external_llm(
    monkeypatch: pytest.MonkeyPatch,
    script_path: str,
) -> None:
    """AppTest covers the page shell with an isolated, empty SQLite configuration."""
    monkeypatch.setenv("DASHBOARD_DATABASE_URL", "sqlite+pysqlite:///:memory:")

    app = AppTest.from_file(script_path).run(timeout=20)

    assert not app.exception
