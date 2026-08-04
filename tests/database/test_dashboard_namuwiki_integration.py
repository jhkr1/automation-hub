"""Optional MySQL read-only integration coverage for Namuwiki dashboard queries."""

import os

import pytest

from automation_dashboard.queries.namuwiki import (
    list_keyword_history,
    list_keyword_statistics,
    list_latest_snapshot,
    load_snapshot_summary,
)
from automation_dashboard.session import dashboard_session

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="set RUN_DB_INTEGRATION=1 to run against MySQL",
)


def test_dashboard_namuwiki_queries_read_the_migrated_snapshot_table() -> None:
    """Run all dashboard reads against the existing MySQL schema without writing data."""
    with dashboard_session() as session:
        summary = load_snapshot_summary(session)
        latest_snapshot = list_latest_snapshot(session)
        statistics = list_keyword_statistics(session)

        assert summary.total_snapshot_count >= 0
        assert summary.today_snapshot_count >= 0
        assert summary.stored_keyword_count >= 0

        if latest_snapshot:
            assert [row.rank_position for row in latest_snapshot] == sorted(
                row.rank_position for row in latest_snapshot
            )
            assert summary.latest_collected_at == latest_snapshot[0].collected_at

        if statistics:
            history = list_keyword_history(session, statistics[0].keyword)
            assert history
            assert [point.collected_at for point in history] == sorted(
                point.collected_at for point in history
            )
