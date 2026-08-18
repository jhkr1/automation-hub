"""Create bus-monitor targets and append-only route snapshots."""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_bus_monitor_snapshots"
down_revision: Union[str, None] = "0003_stock_quote_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Bus Monitor persistence tables in foreign-key dependency order."""
    op.create_table(
        "bus_monitoring_targets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("origin_name", sa.String(length=255), nullable=False),
        sa.Column("origin_latitude", sa.Numeric(precision=17, scale=14), nullable=False),
        sa.Column("origin_longitude", sa.Numeric(precision=17, scale=14), nullable=False),
        sa.Column("destination_name", sa.String(length=255), nullable=False),
        sa.Column("destination_latitude", sa.Numeric(precision=17, scale=14), nullable=False),
        sa.Column("destination_longitude", sa.Numeric(precision=17, scale=14), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(name)) > 0",
            name="ck_bus_monitoring_targets_name_nonempty",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(origin_name)) > 0",
            name="ck_bus_monitoring_targets_origin_name_nonempty",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(destination_name)) > 0",
            name="ck_bus_monitoring_targets_destination_name_nonempty",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bus_monitoring_targets"),
    )
    op.create_table(
        "bus_route_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("monitoring_target_id", sa.BigInteger(), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("route_status", sa.String(length=16), nullable=False),
        sa.Column("realtime_status", sa.String(length=32), nullable=False),
        sa.Column("total_time_minutes", sa.Integer(), nullable=True),
        sa.Column("walk_distance_meters", sa.Integer(), nullable=True),
        sa.Column("transfer_count", sa.SmallInteger(), nullable=True),
        sa.Column("boarding_station_name", sa.String(length=255), nullable=True),
        sa.Column("boarding_station_id", sa.String(length=64), nullable=True),
        sa.Column("alighting_station_name", sa.String(length=255), nullable=True),
        sa.Column("alighting_station_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "route_status IN ('SUCCESS', 'FAILED')",
            name="ck_bus_route_snapshots_route_status",
        ),
        sa.CheckConstraint(
            "realtime_status IN ('SUCCESS', 'UNAVAILABLE', 'NO_MATCHING_ARRIVAL', "
            "'NOT_REQUESTED')",
            name="ck_bus_route_snapshots_realtime_status",
        ),
        sa.CheckConstraint(
            "route_status <> 'FAILED' OR realtime_status = 'NOT_REQUESTED'",
            name="ck_bus_route_snapshots_failed_realtime_not_requested",
        ),
        sa.ForeignKeyConstraint(
            ["monitoring_target_id"],
            ["bus_monitoring_targets.id"],
            name="fk_bus_route_snapshots_monitoring_target_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bus_route_snapshots"),
    )
    op.create_index(
        "ix_bus_route_snapshots_target_collected_at",
        "bus_route_snapshots",
        ["monitoring_target_id", "collected_at"],
    )
    op.create_table(
        "bus_route_snapshot_lanes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("route_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("lane_order", sa.SmallInteger(), nullable=False),
        sa.Column("bus_number", sa.String(length=128), nullable=False),
        sa.Column("local_route_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("lane_order >= 0", name="ck_bus_route_snapshot_lanes_order_nonnegative"),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(bus_number)) > 0",
            name="ck_bus_route_snapshot_lanes_bus_number_nonempty",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(local_route_id)) > 0",
            name="ck_bus_route_snapshot_lanes_local_route_id_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["route_snapshot_id"],
            ["bus_route_snapshots.id"],
            name="fk_bus_route_snapshot_lanes_route_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bus_route_snapshot_lanes"),
        sa.UniqueConstraint(
            "route_snapshot_id",
            "lane_order",
            name="uq_bus_route_snapshot_lanes_snapshot_order",
        ),
    )
    op.create_table(
        "bus_realtime_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("route_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("station_id", sa.String(length=64), nullable=False),
        sa.Column("route_id", sa.String(length=64), nullable=False),
        sa.Column("route_number", sa.String(length=128), nullable=False),
        sa.Column("vehicle_type", sa.String(length=128), nullable=True),
        sa.Column("arrival_seconds", sa.Integer(), nullable=False),
        sa.Column("remaining_stops", sa.SmallInteger(), nullable=False),
        sa.Column("plate_number", sa.String(length=64), nullable=True),
        sa.Column("remaining_seats", sa.SmallInteger(), nullable=True),
        sa.Column("crowded", sa.SmallInteger(), nullable=True),
        sa.Column("state_code", sa.SmallInteger(), nullable=True),
        sa.Column("operating_status", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "arrival_seconds >= 0",
            name="ck_bus_realtime_snapshots_arrival_seconds_nonnegative",
        ),
        sa.CheckConstraint(
            "remaining_stops >= 0",
            name="ck_bus_realtime_snapshots_remaining_stops_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["route_snapshot_id"],
            ["bus_route_snapshots.id"],
            name="fk_bus_realtime_snapshots_route_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bus_realtime_snapshots"),
    )
    op.create_index(
        "ix_bus_realtime_snapshots_route_snapshot_id",
        "bus_realtime_snapshots",
        ["route_snapshot_id"],
    )


def downgrade() -> None:
    """Drop Bus Monitor tables in reverse foreign-key dependency order."""
    # MySQL uses each child FK's supporting index. Dropping the child table removes
    # that index safely, while dropping it first is rejected by the server.
    op.drop_table("bus_realtime_snapshots")
    op.drop_table("bus_route_snapshot_lanes")
    op.drop_table("bus_route_snapshots")
    op.drop_table("bus_monitoring_targets")
