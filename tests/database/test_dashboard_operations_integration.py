"""Optional MySQL read-only integration coverage for operations dashboard queries."""

import os

import pytest

from automation_dashboard.queries.operations import (
    load_alembic_status,
    load_database_summary,
    load_snapshot_summary,
)
from automation_dashboard.session import dashboard_session

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="set RUN_DB_INTEGRATION=1 to run against MySQL",
)


def test_operations_dashboard_queries_read_existing_mysql_metadata() -> None:
    """Read existing snapshot and Alembic data without inserting or changing records."""
    with dashboard_session() as session:
        database = load_database_summary(session)
        snapshots = load_snapshot_summary(session)
        alembic = load_alembic_status(session)

    assert database.status == "Connected"
    assert database.size_bytes is None or database.size_bytes >= 0
    assert snapshots.google_snapshot_count >= 0
    assert snapshots.namuwiki_snapshot_count >= 0
    assert alembic.current_head is not None
