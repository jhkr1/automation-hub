"""MySQL-backed persistence for bus-monitor targets and snapshots."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from bus_monitor.db_models import (
    BusMonitoringTarget,
    BusRealtimeSnapshot,
    BusRouteSnapshot,
    BusRouteSnapshotLane,
)
from bus_monitor.models import BusRouteResult, RouteStatus


def _as_utc_naive(value: datetime, field_name: str) -> datetime:
    """Convert an aware datetime to the project's naive UTC database representation."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _required_text(value: str, field_name: str) -> str:
    """Normalize a required short text input before persistence."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _coordinate(
    value: Decimal | float | str,
    field_name: str,
    minimum: Decimal,
    maximum: Decimal,
) -> Decimal:
    """Convert a coordinate without introducing binary float rounding into storage."""
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a decimal coordinate") from exc
    if not minimum <= normalized <= maximum:
        raise ValueError(f"{field_name} is outside the valid WGS84 range")
    return normalized


class BusMonitorStorage:
    """Persist bus-monitor configuration and complete pipeline snapshots."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize with the shared session factory and an injectable UTC clock."""
        if session_factory is None:
            from database.session import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def create_target(
        self,
        *,
        name: str,
        origin_name: str,
        origin_latitude: Decimal | float | str,
        origin_longitude: Decimal | float | str,
        destination_name: str,
        destination_latitude: Decimal | float | str,
        destination_longitude: Decimal | float | str,
        enabled: bool = True,
    ) -> BusMonitoringTarget:
        """Create one independently configurable monitoring target in a transaction."""
        now = _as_utc_naive(self._clock(), "clock")
        target = BusMonitoringTarget(
            name=_required_text(name, "name"),
            origin_name=_required_text(origin_name, "origin_name"),
            origin_latitude=_coordinate(
                origin_latitude,
                "origin_latitude",
                Decimal("-90"),
                Decimal("90"),
            ),
            origin_longitude=_coordinate(
                origin_longitude,
                "origin_longitude",
                Decimal("-180"),
                Decimal("180"),
            ),
            destination_name=_required_text(destination_name, "destination_name"),
            destination_latitude=_coordinate(
                destination_latitude,
                "destination_latitude",
                Decimal("-90"),
                Decimal("90"),
            ),
            destination_longitude=_coordinate(
                destination_longitude,
                "destination_longitude",
                Decimal("-180"),
                Decimal("180"),
            ),
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory.begin() as session:
            session.add(target)
        return target

    def get_target(self, target_id: int) -> BusMonitoringTarget | None:
        """Return one configured target or ``None`` if its identifier is absent."""
        with self._session_factory() as session:
            return session.get(BusMonitoringTarget, target_id)

    def list_enabled_targets(self) -> list[BusMonitoringTarget]:
        """Return enabled targets in stable primary-key order."""
        statement = (
            select(BusMonitoringTarget)
            .where(BusMonitoringTarget.enabled.is_(True))
            .order_by(BusMonitoringTarget.id.asc())
        )
        with self._session_factory() as session:
            return list(session.scalars(statement))

    def save_snapshot(
        self,
        monitoring_target_id: int,
        result: BusRouteResult,
        *,
        collected_at: datetime | None = None,
    ) -> BusRouteSnapshot:
        """Persist one complete pipeline result atomically without provider raw payloads."""
        if monitoring_target_id <= 0:
            raise ValueError("monitoring_target_id must be positive")
        if not isinstance(result, BusRouteResult):
            raise TypeError("result must be a BusRouteResult")

        collected_at_utc = _as_utc_naive(
            collected_at if collected_at is not None else self._clock(),
            "collected_at",
        )
        created_at = _as_utc_naive(self._clock(), "clock")
        snapshot = self._route_snapshot(
            monitoring_target_id,
            result,
            collected_at=collected_at_utc,
            created_at=created_at,
        )

        with self._session_factory.begin() as session:
            session.add(snapshot)
            if result.route_status is RouteStatus.SUCCESS:
                assert result.bus_leg is not None
                for lane_order, lane in enumerate(result.bus_leg.lanes):
                    session.add(
                        BusRouteSnapshotLane(
                            route_snapshot=snapshot,
                            lane_order=lane_order,
                            bus_number=lane.bus_number,
                            local_route_id=lane.local_route_id,
                            created_at=created_at,
                        )
                    )
                for arrival in result.arrivals:
                    session.add(
                        BusRealtimeSnapshot(
                            route_snapshot=snapshot,
                            collected_at=collected_at_utc,
                            station_id=result.bus_leg.start_station.local_station_id,
                            route_id=arrival.route_id,
                            route_number=arrival.route_number,
                            vehicle_type=arrival.vehicle_type,
                            arrival_seconds=arrival.arrival_seconds,
                            remaining_stops=arrival.remaining_stops,
                            plate_number=arrival.plate_number,
                            remaining_seats=arrival.remaining_seats,
                            crowded=arrival.crowded,
                            state_code=arrival.state_code,
                            operating_status=arrival.operating_status,
                            created_at=created_at,
                        )
                    )
        return snapshot

    def get_latest_snapshot(self, monitoring_target_id: int) -> BusRouteSnapshot | None:
        """Return the latest snapshot for a target using deterministic timestamp ordering."""
        statement = (
            select(BusRouteSnapshot)
            .where(BusRouteSnapshot.monitoring_target_id == monitoring_target_id)
            .order_by(BusRouteSnapshot.collected_at.desc(), BusRouteSnapshot.id.desc())
            .limit(1)
        )
        with self._session_factory() as session:
            return session.scalar(statement)

    def list_route_snapshots(
        self,
        monitoring_target_id: int,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[BusRouteSnapshot]:
        """Return target snapshots newest-first, optionally within a UTC-aware time range."""
        filters = [BusRouteSnapshot.monitoring_target_id == monitoring_target_id]
        if start_at is not None:
            filters.append(BusRouteSnapshot.collected_at >= _as_utc_naive(start_at, "start_at"))
        if end_at is not None:
            filters.append(BusRouteSnapshot.collected_at <= _as_utc_naive(end_at, "end_at"))
        statement = (
            select(BusRouteSnapshot)
            .where(*filters)
            .order_by(BusRouteSnapshot.collected_at.desc(), BusRouteSnapshot.id.desc())
        )
        with self._session_factory() as session:
            return list(session.scalars(statement))

    def list_snapshot_lanes(self, route_snapshot_id: int) -> list[BusRouteSnapshotLane]:
        """Return persisted ODsay lane candidates in their provider-returned order."""
        statement = (
            select(BusRouteSnapshotLane)
            .where(BusRouteSnapshotLane.route_snapshot_id == route_snapshot_id)
            .order_by(BusRouteSnapshotLane.lane_order.asc(), BusRouteSnapshotLane.id.asc())
        )
        with self._session_factory() as session:
            return list(session.scalars(statement))

    def list_realtime_snapshots(self, route_snapshot_id: int) -> list[BusRealtimeSnapshot]:
        """Return approaching vehicles ordered by their canonical ETA and identity."""
        statement = (
            select(BusRealtimeSnapshot)
            .where(BusRealtimeSnapshot.route_snapshot_id == route_snapshot_id)
            .order_by(BusRealtimeSnapshot.arrival_seconds.asc(), BusRealtimeSnapshot.id.asc())
        )
        with self._session_factory() as session:
            return list(session.scalars(statement))

    @staticmethod
    def _route_snapshot(
        monitoring_target_id: int,
        result: BusRouteResult,
        *,
        collected_at: datetime,
        created_at: datetime,
    ) -> BusRouteSnapshot:
        """Map normalized domain data to its parent persistence row."""
        if result.route_status is RouteStatus.FAILED:
            return BusRouteSnapshot(
                monitoring_target_id=monitoring_target_id,
                collected_at=collected_at,
                route_status=result.route_status.value,
                realtime_status=result.realtime_status.value,
                created_at=created_at,
            )

        assert result.route is not None
        assert result.bus_leg is not None
        return BusRouteSnapshot(
            monitoring_target_id=monitoring_target_id,
            collected_at=collected_at,
            route_status=result.route_status.value,
            realtime_status=result.realtime_status.value,
            total_time_minutes=result.route.total_time_minutes,
            walk_distance_meters=result.route.walk_distance_meters,
            transfer_count=result.route.transfer_count,
            boarding_station_name=result.bus_leg.start_station.name,
            boarding_station_id=result.bus_leg.start_station.local_station_id,
            alighting_station_name=result.bus_leg.end_station.name,
            alighting_station_id=result.bus_leg.end_station.local_station_id,
            created_at=created_at,
        )
