"""Minimal Streamlit entrypoint smoke contract."""

from datetime import datetime
from pathlib import Path

from automation_dashboard import app
from automation_dashboard.queries.operations import OperationsSnapshotSummary
from automation_dashboard.readers.llm_usage import LlmProfileUsage, LlmUsageReadModel
from automation_dashboard.readers.namuwiki_insights import InsightStatus


def test_dashboard_entrypoint_exposes_main() -> None:
    """The dashboard package exports an importable Streamlit entrypoint."""
    assert callable(app.main)


def test_home_attention_ignores_healthy_and_planned_states() -> None:
    """Home only promotes states that require operator attention."""
    assert app._attention_items("Healthy", "Healthy", "Healthy", "Planned") == []
    assert app._attention_items("Healthy", "Stale", "No Data", "Unavailable") == [
        ("Google Finance", "Stale"),
        ("Namuwiki", "No Data"),
        ("LLM Runtime", "Unavailable"),
    ]


def test_home_activity_preview_uses_existing_events_in_reverse_time_order() -> None:
    """Recent activity is built only from available snapshot and ledger timestamps."""
    snapshots = OperationsSnapshotSummary(
        google_snapshot_count=2,
        namuwiki_snapshot_count=1,
        google_today_snapshot_count=1,
        namuwiki_today_snapshot_count=1,
        latest_google_collected_at=datetime(2026, 8, 5, 9, 0),
        latest_google_symbol="NVDA:NASDAQ",
        latest_namuwiki_collected_at=datetime(2026, 8, 5, 8, 0),
        latest_namuwiki_keyword="Python",
    )
    usage = LlmUsageReadModel(
        status=InsightStatus.HEALTHY,
        path=Path("quota-ledger.json"),
        profiles=(LlmProfileUsage("production", 1),),
        retry_count=0,
        last_request_at_kst=datetime(2026, 8, 5, 10, 0),
    )

    events = app._activity_items(snapshots, usage)

    assert [event["label"] for event in events] == [
        "LLM Runtime request",
        "Google Finance collection",
        "Namuwiki snapshot",
    ]
