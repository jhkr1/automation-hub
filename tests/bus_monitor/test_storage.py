"""Unit tests for Bus Monitor target and snapshot persistence boundaries."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from bus_monitor.db_models import (
    BusMonitoringTarget,
    BusRealtimeSnapshot,
    BusRouteSnapshot,
    BusRouteSnapshotLane,
)
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
from bus_monitor.storage import BusMonitorStorage


def _bus_leg() -> BusLeg:
    """Create the normalized first bus leg used by persistence cases."""
    return BusLeg(
        start_station=RouteStation("삼평교", "206000542", 37.403789, 127.104252),
        end_station=RouteStation("도착정류장", "228000697", 37.271599, 127.108851),
        duration_minutes=29,
        station_count=4,
        lanes=(
            BusLane("5600", "228000184"),
            BusLane("9241", "228000442"),
        ),
    )


def _route(bus_leg: BusLeg) -> TransitRoute:
    """Create a route containing the selected first bus leg."""
    return TransitRoute(33, 243, 1, (bus_leg,))


def _full_success() -> BusRouteResult:
    """Create a full route and two approaching vehicle rows."""
    bus_leg = _bus_leg()
    return BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=RealtimeStatus.SUCCESS,
        route=_route(bus_leg),
        bus_leg=bus_leg,
        arrivals=(
            RealtimeArrival(
                route_id="228000184",
                route_number="5600",
                arrival_seconds=1228,
                remaining_stops=18,
                vehicle_type="일반버스",
                plate_number="경기78아1111",
                remaining_seats=35,
                crowded=1,
                state_code=1,
                operating_status="PASS",
            ),
            RealtimeArrival(
                route_id="228000184",
                route_number="5600",
                arrival_seconds=1536,
                remaining_stops=19,
                vehicle_type="저상버스",
                plate_number="경기78아2222",
                remaining_seats=43,
                crowded=0,
                state_code=1,
                operating_status="PASS",
            ),
        ),
    )


def _partial_success(status: RealtimeStatus = RealtimeStatus.UNAVAILABLE) -> BusRouteResult:
    """Create a usable route whose realtime rows are absent by contract."""
    bus_leg = _bus_leg()
    return BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=status,
        route=_route(bus_leg),
        bus_leg=bus_leg,
    )


class FakeSession:
    """Minimal session fake that exposes transaction behavior and recorded ORM rows."""

    def __init__(self, *, fail_on_add: int | None = None) -> None:
        self.added: list[object] = []
        self.fail_on_add = fail_on_add
        self._add_count = 0
        self.target: BusMonitoringTarget | None = None
        self.scalar_result: BusRouteSnapshot | None = None
        self.scalar_rows: list[object] = []

    def add(self, row: object) -> None:
        """Record an insert or simulate a database failure at one insert boundary."""
        self._add_count += 1
        if self.fail_on_add == self._add_count:
            raise IntegrityError("insert failed", {}, ValueError("forced failure"))
        self.added.append(row)

    def get(self, model: type[object], target_id: int) -> BusMonitoringTarget | None:
        """Return the configured target only for its stored identifier."""
        if model is BusMonitoringTarget and self.target is not None and target_id == self.target.id:
            return self.target
        return None

    def scalar(self, statement: object) -> BusRouteSnapshot | None:
        """Return a configured latest snapshot result."""
        return self.scalar_result

    def scalars(self, statement: object) -> FakeScalarResult:
        """Return configured ORM rows for list query helpers."""
        return FakeScalarResult(self.scalar_rows)

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None


class FakeTransaction:
    """Record whether the storage operation committed or rolled back."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeSession:
        return self.session

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True


class FakeScalarResult:
    """Minimal iterable stand-in for SQLAlchemy's ScalarResult."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def __iter__(self):
        """Iterate configured scalar rows."""
        return iter(self._rows)


class FakeSessionFactory:
    """Provide the two Session factory access patterns used by BusMonitorStorage."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.transaction = FakeTransaction(session)

    def begin(self) -> FakeTransaction:
        """Return the transaction context used for create and save operations."""
        return self.transaction

    def __call__(self) -> FakeSession:
        return self.session


def _storage(session: FakeSession) -> BusMonitorStorage:
    """Build storage with a stable aware UTC clock."""
    return BusMonitorStorage(
        FakeSessionFactory(session),
        clock=lambda: datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc),
    )


def test_create_target_normalizes_coordinates_and_commits() -> None:
    """A target is configurable without hardcoding the current commute route."""
    session = FakeSession()

    factory = FakeSessionFactory(session)
    target = BusMonitorStorage(
        factory,
        clock=lambda: datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc),
    ).create_target(
        name=" 퇴근길 ",
        origin_name=" 지식시스템 ",
        origin_latitude="37.4043389599242",
        origin_longitude="127.102446246531",
        destination_name=" 롯데마트 신갈점 ",
        destination_latitude="37.27220279535416",
        destination_longitude="127.10856729001851",
    )

    assert session.added == [target]
    assert target.name == "퇴근길"
    assert str(target.origin_latitude) == "37.4043389599242"
    assert target.created_at == datetime(2026, 8, 18, 9, 0)
    assert target.updated_at == datetime(2026, 8, 18, 9, 0)
    assert factory.transaction.committed is True


def test_target_query_helpers_return_target_and_enabled_rows() -> None:
    """Target reads are limited to get-by-ID and enabled-list MVP operations."""
    session = FakeSession()
    target = BusMonitoringTarget(id=7, enabled=True)
    session.target = target
    session.scalar_rows = [target]
    storage = _storage(session)

    assert storage.get_target(7) is target
    assert storage.get_target(8) is None
    assert storage.list_enabled_targets() == [target]


def test_full_success_persists_one_route_lanes_and_each_realtime_vehicle() -> None:
    """A full result maps every ODsay candidate and every approaching vehicle row."""
    session = FakeSession()
    collected_at = datetime(2026, 8, 18, 10, 15, tzinfo=timezone.utc)

    snapshot = _storage(session).save_snapshot(1, _full_success(), collected_at=collected_at)

    lanes = [row for row in session.added if isinstance(row, BusRouteSnapshotLane)]
    realtime_rows = [row for row in session.added if isinstance(row, BusRealtimeSnapshot)]
    assert isinstance(session.added[0], BusRouteSnapshot)
    assert snapshot.route_status == "SUCCESS"
    assert snapshot.realtime_status == "SUCCESS"
    assert snapshot.collected_at == datetime(2026, 8, 18, 10, 15)
    assert snapshot.boarding_station_id == "206000542"
    assert [(row.lane_order, row.bus_number) for row in lanes] == [(0, "5600"), (1, "9241")]
    assert [row.arrival_seconds for row in realtime_rows] == [1228, 1536]
    assert [row.remaining_seats for row in realtime_rows] == [35, 43]


@pytest.mark.parametrize("status", [RealtimeStatus.UNAVAILABLE, RealtimeStatus.NO_MATCHING_ARRIVAL])
def test_partial_success_persists_route_and_lanes_without_realtime(
    status: RealtimeStatus,
) -> None:
    """Realtime absence does not discard usable planned route and lane evidence."""
    session = FakeSession()

    snapshot = _storage(session).save_snapshot(1, _partial_success(status))

    assert snapshot.route_status == "SUCCESS"
    assert snapshot.realtime_status == status.value
    assert len([row for row in session.added if isinstance(row, BusRouteSnapshotLane)]) == 2
    assert not [row for row in session.added if isinstance(row, BusRealtimeSnapshot)]


def test_route_failure_persists_only_a_status_snapshot() -> None:
    """A failed route remains observable without lanes, realtime, or route summary values."""
    session = FakeSession()
    result = BusRouteResult(RouteStatus.FAILED, RealtimeStatus.NOT_REQUESTED)

    snapshot = _storage(session).save_snapshot(1, result)

    assert session.added == [snapshot]
    assert snapshot.route_status == "FAILED"
    assert snapshot.realtime_status == "NOT_REQUESTED"
    assert snapshot.total_time_minutes is None
    assert snapshot.boarding_station_id is None


def test_snapshot_save_rolls_back_when_child_insert_fails() -> None:
    """A child-row insert failure exits the one snapshot transaction with rollback."""
    session = FakeSession(fail_on_add=3)
    factory = FakeSessionFactory(session)
    storage = BusMonitorStorage(factory, clock=lambda: datetime(2026, 8, 18, tzinfo=timezone.utc))

    with pytest.raises(IntegrityError):
        storage.save_snapshot(1, _full_success())

    assert factory.transaction.committed is False
    assert factory.transaction.rolled_back is True


def test_models_define_the_lane_order_unique_constraint_and_status_invariant() -> None:
    """Schema metadata preserves ordered candidates and failed-route state safety."""
    lane_constraints = {
        constraint.name for constraint in BusRouteSnapshotLane.__table__.constraints
    }
    route_constraints = {constraint.name for constraint in BusRouteSnapshot.__table__.constraints}

    assert "uq_bus_route_snapshot_lanes_snapshot_order" in lane_constraints
    assert "ck_bus_route_snapshots_failed_realtime_not_requested" in route_constraints


def test_latest_snapshot_query_uses_timestamp_and_id_descending_order() -> None:
    """Latest lookup retains the repository's deterministic same-timestamp ordering rule."""
    session = FakeSession()
    expected = BusRouteSnapshot(id=3, monitoring_target_id=1)
    session.scalar_result = expected

    assert _storage(session).get_latest_snapshot(1) is expected
