"""Read-only Bus Monitor snapshot queries for the Streamlit dashboard."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from automation_dashboard.queries.google_finance import SEOUL_TZ, to_seoul_time
from bus_monitor.db_models import (
    BusMonitoringTarget,
    BusRealtimeSnapshot,
    BusRouteSnapshot,
    BusRouteSnapshotLane,
)


@dataclass(frozen=True)
class MonitoringTargetRow:
    """An enabled monitoring target available for dashboard selection."""

    id: int
    name: str
    origin_name: str
    destination_name: str


@dataclass(frozen=True)
class RouteSnapshotRow:
    """One route snapshot prepared for latest-state dashboard rendering."""

    id: int
    collected_at: datetime
    route_status: str
    realtime_status: str
    total_time_minutes: int | None
    walk_distance_meters: int | None
    transfer_count: int | None
    boarding_station_name: str | None
    alighting_station_name: str | None


@dataclass(frozen=True)
class LaneRow:
    """One ordered ODsay candidate retained with a route snapshot."""

    bus_number: str
    local_route_id: str


@dataclass(frozen=True)
class RealtimeRow:
    """One approaching vehicle prepared for presentation without raw provider data."""

    route_number: str
    arrival_seconds: int
    remaining_stops: int
    remaining_seats: int | None
    plate_number: str | None
    crowded: int | None
    operating_status: str | None


@dataclass(frozen=True)
class TodaySnapshotRow:
    """One KST-today route snapshot with its fastest recorded vehicle, if any."""

    snapshot: RouteSnapshotRow
    fastest_arrival: RealtimeRow | None


def list_enabled_targets(session: Session) -> list[MonitoringTargetRow]:
    """Return enabled targets in stable ID order for selection widgets."""
    statement = (
        select(
            BusMonitoringTarget.id,
            BusMonitoringTarget.name,
            BusMonitoringTarget.origin_name,
            BusMonitoringTarget.destination_name,
        )
        .where(BusMonitoringTarget.enabled.is_(True))
        .order_by(BusMonitoringTarget.id.asc())
    )
    return [
        MonitoringTargetRow(int(row.id), row.name, row.origin_name, row.destination_name)
        for row in session.execute(statement).all()
    ]


def load_latest_route_snapshot(session: Session, target_id: int) -> RouteSnapshotRow | None:
    """Return one deterministic latest snapshot for an enabled-target selection."""
    statement = (
        select(BusRouteSnapshot)
        .where(BusRouteSnapshot.monitoring_target_id == target_id)
        .order_by(BusRouteSnapshot.collected_at.desc(), BusRouteSnapshot.id.desc())
        .limit(1)
    )
    snapshot = session.scalar(statement)
    return None if snapshot is None else _route_row(snapshot)


def list_snapshot_lanes(session: Session, snapshot_id: int) -> list[LaneRow]:
    """Return one snapshot's ODsay lanes in their persisted provider order."""
    statement = (
        select(BusRouteSnapshotLane.bus_number, BusRouteSnapshotLane.local_route_id)
        .where(BusRouteSnapshotLane.route_snapshot_id == snapshot_id)
        .order_by(BusRouteSnapshotLane.lane_order.asc(), BusRouteSnapshotLane.id.asc())
    )
    return [LaneRow(row.bus_number, row.local_route_id) for row in session.execute(statement).all()]


def list_snapshot_realtime(session: Session, snapshot_id: int) -> list[RealtimeRow]:
    """Return approaching vehicles in fastest-arrival order for one snapshot."""
    statement = (
        select(BusRealtimeSnapshot)
        .where(BusRealtimeSnapshot.route_snapshot_id == snapshot_id)
        .order_by(BusRealtimeSnapshot.arrival_seconds.asc(), BusRealtimeSnapshot.id.asc())
    )
    return [_realtime_row(row) for row in session.scalars(statement)]


def list_today_snapshots(
    session: Session,
    target_id: int,
    *,
    today: date | None = None,
) -> list[TodaySnapshotRow]:
    """Return KST-today snapshots oldest-first with an optional fastest vehicle."""
    target_date = today or datetime.now(SEOUL_TZ).date()
    start_at, end_at = _seoul_day_bounds(target_date)
    snapshots = list(
        session.scalars(
            select(BusRouteSnapshot)
            .where(
                BusRouteSnapshot.monitoring_target_id == target_id,
                BusRouteSnapshot.collected_at >= start_at,
                BusRouteSnapshot.collected_at <= end_at,
            )
            .order_by(BusRouteSnapshot.collected_at.asc(), BusRouteSnapshot.id.asc())
        )
    )
    if not snapshots:
        return []
    snapshot_ids = [snapshot.id for snapshot in snapshots]
    realtime_by_snapshot: dict[int, RealtimeRow] = {}
    statement = (
        select(BusRealtimeSnapshot)
        .where(BusRealtimeSnapshot.route_snapshot_id.in_(snapshot_ids))
        .order_by(
            BusRealtimeSnapshot.route_snapshot_id.asc(),
            BusRealtimeSnapshot.arrival_seconds.asc(),
            BusRealtimeSnapshot.id.asc(),
        )
    )
    for arrival in session.scalars(statement):
        realtime_by_snapshot.setdefault(arrival.route_snapshot_id, _realtime_row(arrival))
    return [
        TodaySnapshotRow(_route_row(snapshot), realtime_by_snapshot.get(snapshot.id))
        for snapshot in snapshots
    ]


def _seoul_day_bounds(target_date: date) -> tuple[datetime, datetime]:
    """Return UTC-naive database bounds for a single Seoul calendar date."""
    return (
        datetime.combine(target_date, time.min, tzinfo=SEOUL_TZ)
        .astimezone(timezone.utc)
        .replace(tzinfo=None),
        datetime.combine(target_date, time.max, tzinfo=SEOUL_TZ)
        .astimezone(timezone.utc)
        .replace(tzinfo=None),
    )


def _route_row(snapshot: BusRouteSnapshot) -> RouteSnapshotRow:
    """Detach one ORM route row and localize its persisted UTC collection time."""
    return RouteSnapshotRow(
        snapshot.id,
        to_seoul_time(snapshot.collected_at),
        snapshot.route_status,
        snapshot.realtime_status,
        snapshot.total_time_minutes,
        snapshot.walk_distance_meters,
        snapshot.transfer_count,
        snapshot.boarding_station_name,
        snapshot.alighting_station_name,
    )


def _realtime_row(row: BusRealtimeSnapshot) -> RealtimeRow:
    """Detach one realtime ORM row for dashboard presentation."""
    return RealtimeRow(
        row.route_number,
        row.arrival_seconds,
        row.remaining_stops,
        row.remaining_seats,
        row.plate_number,
        row.crowded,
        row.operating_status,
    )
