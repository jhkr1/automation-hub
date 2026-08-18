"""SQLAlchemy persistence models for append-only bus-monitor snapshots."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base

COORDINATE_NUMERIC = Numeric(17, 14)


class BusMonitoringTarget(Base):
    """A configured origin-to-destination route that bus monitoring collects."""

    __tablename__ = "bus_monitoring_targets"
    __table_args__ = (
        CheckConstraint(
            "CHAR_LENGTH(TRIM(name)) > 0",
            name="ck_bus_monitoring_targets_name_nonempty",
        ),
        CheckConstraint(
            "CHAR_LENGTH(TRIM(origin_name)) > 0",
            name="ck_bus_monitoring_targets_origin_name_nonempty",
        ),
        CheckConstraint(
            "CHAR_LENGTH(TRIM(destination_name)) > 0",
            name="ck_bus_monitoring_targets_destination_name_nonempty",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_name: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_latitude: Mapped[Decimal] = mapped_column(COORDINATE_NUMERIC, nullable=False)
    origin_longitude: Mapped[Decimal] = mapped_column(COORDINATE_NUMERIC, nullable=False)
    destination_name: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_latitude: Mapped[Decimal] = mapped_column(COORDINATE_NUMERIC, nullable=False)
    destination_longitude: Mapped[Decimal] = mapped_column(COORDINATE_NUMERIC, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    route_snapshots: Mapped[list[BusRouteSnapshot]] = relationship(
        back_populates="monitoring_target",
        passive_deletes=True,
    )


class BusRouteSnapshot(Base):
    """One persisted route-planning result, including partial and failed executions."""

    __tablename__ = "bus_route_snapshots"
    __table_args__ = (
        CheckConstraint(
            "route_status IN ('SUCCESS', 'FAILED')",
            name="ck_bus_route_snapshots_route_status",
        ),
        CheckConstraint(
            "realtime_status IN ('SUCCESS', 'UNAVAILABLE', 'NO_MATCHING_ARRIVAL', "
            "'NOT_REQUESTED')",
            name="ck_bus_route_snapshots_realtime_status",
        ),
        CheckConstraint(
            "route_status <> 'FAILED' OR realtime_status = 'NOT_REQUESTED'",
            name="ck_bus_route_snapshots_failed_realtime_not_requested",
        ),
        Index(
            "ix_bus_route_snapshots_target_collected_at",
            "monitoring_target_id",
            "collected_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    monitoring_target_id: Mapped[int] = mapped_column(
        ForeignKey("bus_monitoring_targets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    route_status: Mapped[str] = mapped_column(String(16), nullable=False)
    realtime_status: Mapped[str] = mapped_column(String(32), nullable=False)
    total_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    walk_distance_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transfer_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    boarding_station_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    boarding_station_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alighting_station_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alighting_station_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    monitoring_target: Mapped[BusMonitoringTarget] = relationship(back_populates="route_snapshots")
    lanes: Mapped[list[BusRouteSnapshotLane]] = relationship(
        back_populates="route_snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    realtime_snapshots: Mapped[list[BusRealtimeSnapshot]] = relationship(
        back_populates="route_snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class BusRouteSnapshotLane(Base):
    """One ordered ODsay lane candidate retained for a route snapshot."""

    __tablename__ = "bus_route_snapshot_lanes"
    __table_args__ = (
        UniqueConstraint(
            "route_snapshot_id",
            "lane_order",
            name="uq_bus_route_snapshot_lanes_snapshot_order",
        ),
        CheckConstraint("lane_order >= 0", name="ck_bus_route_snapshot_lanes_order_nonnegative"),
        CheckConstraint(
            "CHAR_LENGTH(TRIM(bus_number)) > 0",
            name="ck_bus_route_snapshot_lanes_bus_number_nonempty",
        ),
        CheckConstraint(
            "CHAR_LENGTH(TRIM(local_route_id)) > 0",
            name="ck_bus_route_snapshot_lanes_local_route_id_nonempty",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    route_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("bus_route_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    lane_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    bus_number: Mapped[str] = mapped_column(String(128), nullable=False)
    local_route_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    route_snapshot: Mapped[BusRouteSnapshot] = relationship(back_populates="lanes")


class BusRealtimeSnapshot(Base):
    """One approaching vehicle returned by Gyeonggi realtime information."""

    __tablename__ = "bus_realtime_snapshots"
    __table_args__ = (
        CheckConstraint(
            "arrival_seconds >= 0",
            name="ck_bus_realtime_snapshots_arrival_seconds_nonnegative",
        ),
        CheckConstraint(
            "remaining_stops >= 0",
            name="ck_bus_realtime_snapshots_remaining_stops_nonnegative",
        ),
        Index("ix_bus_realtime_snapshots_route_snapshot_id", "route_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    route_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("bus_route_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    station_id: Mapped[str] = mapped_column(String(64), nullable=False)
    route_id: Mapped[str] = mapped_column(String(64), nullable=False)
    route_number: Mapped[str] = mapped_column(String(128), nullable=False)
    vehicle_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    arrival_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_stops: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    plate_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remaining_seats: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    crowded: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    state_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    operating_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    route_snapshot: Mapped[BusRouteSnapshot] = relationship(back_populates="realtime_snapshots")
