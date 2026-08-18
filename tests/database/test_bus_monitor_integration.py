"""Optional MySQL integration tests for Bus Monitor persistence migrations."""

import os
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="set RUN_DB_INTEGRATION=1 to run against MySQL",
)


def _full_result():
    """Create a live-shape normalized result without an external provider call."""
    from bus_monitor.models import (
        BusLane,
        BusLeg,
        BusRouteResult,
        RealtimeArrival,
        RealtimeStatus,
        RouteStation,
        RouteStatus,
        TransitRoute,
    )

    bus_leg = BusLeg(
        start_station=RouteStation("삼평교", "206000542", 37.403789, 127.104252),
        end_station=RouteStation("도착정류장", "228000697", 37.271599, 127.108851),
        duration_minutes=29,
        station_count=4,
        lanes=(BusLane("5600", "228000184"), BusLane("9241", "228000442")),
    )
    route = TransitRoute(33, 243, 1, (bus_leg,))
    return BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=RealtimeStatus.SUCCESS,
        route=route,
        bus_leg=bus_leg,
        arrivals=(
            RealtimeArrival(
                "228000184",
                "5600",
                1228,
                18,
                "일반버스",
                remaining_seats=35,
            ),
            RealtimeArrival(
                "228000184",
                "5600",
                1536,
                19,
                "저상버스",
                remaining_seats=43,
            ),
        ),
    )


def test_bus_monitor_migrated_schema_and_snapshot_round_trip() -> None:
    """Verify tables, ordered children, UTC storage, and deterministic latest lookup."""
    from sqlalchemy import delete, inspect

    from bus_monitor.db_models import BusMonitoringTarget, BusRealtimeSnapshot, BusRouteSnapshot
    from bus_monitor.models import BusRouteResult, RealtimeStatus, RouteStatus
    from bus_monitor.storage import BusMonitorStorage
    from database.engine import engine
    from database.session import SessionLocal

    inspector = inspect(engine)
    assert {
        "bus_monitoring_targets",
        "bus_route_snapshots",
        "bus_route_snapshot_lanes",
        "bus_realtime_snapshots",
    }.issubset(inspector.get_table_names())
    assert "ix_bus_route_snapshots_target_collected_at" in {
        index["name"] for index in inspector.get_indexes("bus_route_snapshots")
    }
    assert "uq_bus_route_snapshot_lanes_snapshot_order" in {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("bus_route_snapshot_lanes")
    }

    storage = BusMonitorStorage()
    target = storage.create_target(
        name="Bus Monitor Integration",
        origin_name="Origin",
        origin_latitude="37.4043389599242",
        origin_longitude="127.102446246531",
        destination_name="Destination",
        destination_latitude="37.27220279535416",
        destination_longitude="127.10856729001851",
    )
    assert target.id is not None
    collected_at = datetime(2099, 1, 1, 1, tzinfo=timezone.utc)

    try:
        full_snapshot = storage.save_snapshot(target.id, _full_result(), collected_at=collected_at)
        partial = _full_result()
        partial = BusRouteResult(
            RouteStatus.SUCCESS,
            RealtimeStatus.NO_MATCHING_ARRIVAL,
            route=partial.route,
            bus_leg=partial.bus_leg,
        )
        partial_snapshot = storage.save_snapshot(target.id, partial, collected_at=collected_at)
        failed_snapshot = storage.save_snapshot(
            target.id,
            BusRouteResult(RouteStatus.FAILED, RealtimeStatus.NOT_REQUESTED),
            collected_at=collected_at,
        )

        with SessionLocal() as session:
            lanes = storage.list_snapshot_lanes(full_snapshot.id)
            realtime = storage.list_realtime_snapshots(full_snapshot.id)
            latest = storage.get_latest_snapshot(target.id)
            assert [lane.lane_order for lane in lanes] == [0, 1]
            assert [row.arrival_seconds for row in realtime] == [1228, 1536]
            assert all(row.collected_at.tzinfo is None for row in realtime)
            assert storage.list_snapshot_lanes(partial_snapshot.id)
            assert storage.list_realtime_snapshots(partial_snapshot.id) == []
            assert storage.list_snapshot_lanes(failed_snapshot.id) == []
            assert storage.list_realtime_snapshots(failed_snapshot.id) == []
            assert latest is not None
            assert latest.id == failed_snapshot.id
            assert session.get(BusRealtimeSnapshot, realtime[0].id) is not None
    finally:
        with SessionLocal.begin() as session:
            session.execute(
                delete(BusRouteSnapshot).where(BusRouteSnapshot.monitoring_target_id == target.id)
            )
            session.execute(delete(BusMonitoringTarget).where(BusMonitoringTarget.id == target.id))
