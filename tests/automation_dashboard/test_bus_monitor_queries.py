"""Unit tests for detached Bus Monitor dashboard query contracts."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from automation_dashboard.queries.bus_monitor import (
    list_enabled_targets,
    list_snapshot_lanes,
    list_snapshot_realtime,
    list_today_snapshots,
    load_latest_route_snapshot,
)
from bus_monitor.db_models import (
    BusMonitoringTarget,
    BusRealtimeSnapshot,
    BusRouteSnapshot,
    BusRouteSnapshotLane,
)


@pytest.fixture
def session() -> Session:
    """Create isolated Bus Monitor dashboard tables without MySQL."""
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def register_mysql_compatibility_functions(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function("CHAR_LENGTH", 1, len)

    BusMonitoringTarget.__table__.create(engine)
    BusRouteSnapshot.__table__.create(engine)
    BusRouteSnapshotLane.__table__.create(engine)
    BusRealtimeSnapshot.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    active_session = factory()
    try:
        yield active_session
    finally:
        active_session.close()
        engine.dispose()


def _target(identifier: int, *, enabled: bool = True) -> BusMonitoringTarget:
    """Build one valid target with stable coordinates for query tests."""
    recorded_at = datetime(2026, 8, 1)
    return BusMonitoringTarget(
        id=identifier,
        name=f"Target {identifier}",
        origin_name="Origin",
        origin_latitude=Decimal("37.4043389599242"),
        origin_longitude=Decimal("127.1024462465310"),
        destination_name="Destination",
        destination_latitude=Decimal("37.2722027953542"),
        destination_longitude=Decimal("127.1085672900185"),
        enabled=enabled,
        created_at=recorded_at,
        updated_at=recorded_at,
    )


def _snapshot(
    identifier: int,
    *,
    target_id: int = 1,
    collected_at: datetime,
    route_status: str = "SUCCESS",
    realtime_status: str = "SUCCESS",
    total_time_minutes: int | None = 41,
) -> BusRouteSnapshot:
    """Build one persisted route snapshot with optional partial-state values."""
    return BusRouteSnapshot(
        id=identifier,
        monitoring_target_id=target_id,
        collected_at=collected_at,
        route_status=route_status,
        realtime_status=realtime_status,
        total_time_minutes=total_time_minutes,
        walk_distance_meters=800 if total_time_minutes is not None else None,
        transfer_count=1 if total_time_minutes is not None else None,
        boarding_station_name="삼평교" if total_time_minutes is not None else None,
        boarding_station_id="206000542" if total_time_minutes is not None else None,
        alighting_station_name="백남준아트센터" if total_time_minutes is not None else None,
        alighting_station_id="228000697" if total_time_minutes is not None else None,
        created_at=collected_at,
    )


def _arrival(
    identifier: int,
    *,
    snapshot_id: int,
    arrival_seconds: int,
    route_number: str,
) -> BusRealtimeSnapshot:
    """Build a deterministic realtime arrival row."""
    collected_at = datetime(2026, 8, 18, 8)
    return BusRealtimeSnapshot(
        id=identifier,
        route_snapshot_id=snapshot_id,
        collected_at=collected_at,
        station_id="206000542",
        route_id=f"route-{identifier}",
        route_number=route_number,
        vehicle_type=None,
        arrival_seconds=arrival_seconds,
        remaining_stops=2,
        plate_number=None,
        remaining_seats=44,
        crowded=None,
        state_code=None,
        operating_status="운행중",
        created_at=collected_at,
    )


def _save(session: Session, *rows: object) -> None:
    """Persist deterministic dashboard fixtures."""
    session.add_all(rows)
    session.commit()


def test_enabled_targets_and_latest_snapshot_are_stable_and_localized(session: Session) -> None:
    """Enabled choices exclude disabled targets; latest uses the ID tie-breaker."""
    same_time = datetime(2026, 8, 18, 8)
    _save(
        session,
        _target(1),
        _target(2, enabled=False),
        _snapshot(10, collected_at=same_time, total_time_minutes=40),
        _snapshot(11, collected_at=same_time, total_time_minutes=42),
    )

    targets = list_enabled_targets(session)
    latest = load_latest_route_snapshot(session, 1)

    assert [target.id for target in targets] == [1]
    assert latest is not None
    assert latest.id == 11
    assert latest.total_time_minutes == 42
    assert latest.collected_at == datetime(2026, 8, 18, 17, tzinfo=ZoneInfo("Asia/Seoul"))


def test_snapshot_children_preserve_lane_and_fastest_arrival_order(session: Session) -> None:
    """Lane provider order and realtime shortest ETA order are presentation-safe."""
    collected_at = datetime(2026, 8, 18, 8)
    _save(session, _target(1), _snapshot(10, collected_at=collected_at))
    _save(
        session,
        BusRouteSnapshotLane(
            id=1,
            route_snapshot_id=10,
            lane_order=1,
            bus_number="9241",
            local_route_id="228000442",
            created_at=collected_at,
        ),
        BusRouteSnapshotLane(
            id=2,
            route_snapshot_id=10,
            lane_order=0,
            bus_number="5600",
            local_route_id="228000184",
            created_at=collected_at,
        ),
        _arrival(1, snapshot_id=10, arrival_seconds=180, route_number="9241"),
        _arrival(2, snapshot_id=10, arrival_seconds=60, route_number="5600"),
    )

    lanes = list_snapshot_lanes(session, 10)
    arrivals = list_snapshot_realtime(session, 10)

    assert [lane.bus_number for lane in lanes] == ["5600", "9241"]
    assert [arrival.route_number for arrival in arrivals] == ["5600", "9241"]


def test_today_snapshots_use_kst_calendar_bounds_and_fastest_realtime(session: Session) -> None:
    """UTC persistence is filtered by Seoul date and does not leak into the next day."""
    _save(session, _target(1))
    _save(
        session,
        _snapshot(10, collected_at=datetime(2026, 8, 18, 8)),
        _snapshot(11, collected_at=datetime(2026, 8, 18, 15)),
        _snapshot(
            12,
            collected_at=datetime(2026, 8, 18, 9),
            realtime_status="UNAVAILABLE",
            total_time_minutes=39,
        ),
    )
    _save(
        session,
        _arrival(1, snapshot_id=10, arrival_seconds=240, route_number="9241"),
        _arrival(2, snapshot_id=10, arrival_seconds=90, route_number="5600"),
    )

    history = list_today_snapshots(session, 1, today=date(2026, 8, 18))

    assert [row.snapshot.id for row in history] == [10, 12]
    assert history[0].snapshot.collected_at.hour == 17
    assert history[0].fastest_arrival is not None
    assert history[0].fastest_arrival.route_number == "5600"
    assert history[1].fastest_arrival is None
    assert history[1].snapshot.realtime_status == "UNAVAILABLE"
