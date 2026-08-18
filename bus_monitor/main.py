"""Coordinate-based production CLI for the bus-monitor pipeline."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from bus_monitor.config import BusMonitorSettings
from bus_monitor.db_models import BusMonitoringTarget, BusRouteSnapshot
from bus_monitor.gyeonggi import GyeonggiConfigurationError, GyeonggiProvider
from bus_monitor.models import BusRouteResult, RealtimeStatus, RouteStatus
from bus_monitor.odsay import OdsayConfigurationError, OdsayRouteProvider
from bus_monitor.pipeline import BusMonitorPipeline
from bus_monitor.storage import BusMonitorStorage


def _build_parser() -> argparse.ArgumentParser:
    """Build coordinate and persisted-target execution argument parsing."""
    parser = argparse.ArgumentParser(description="Run one bus-monitor route lookup.")
    parser.add_argument("--origin-longitude", type=float)
    parser.add_argument("--origin-latitude", type=float)
    parser.add_argument("--destination-longitude", type=float)
    parser.add_argument("--destination-latitude", type=float)
    parser.add_argument("--target-id", type=int)
    return parser


def build_pipeline(settings: BusMonitorSettings | None = None) -> BusMonitorPipeline:
    """Wire production ODsay and Gyeonggi providers into the production pipeline."""
    configured_settings = settings or BusMonitorSettings()
    return BusMonitorPipeline(
        route_provider=OdsayRouteProvider(api_key=configured_settings.odsay_api_key),
        realtime_provider=GyeonggiProvider(service_key=configured_settings.gyeonggi_service_key),
    )


def build_storage() -> BusMonitorStorage:
    """Create the package-specific storage used by persisted-target CLI runs."""
    return BusMonitorStorage()


def print_result(result: BusRouteResult) -> None:
    """Render one normalized pipeline result without exposing provider payloads."""
    print("=== Bus Monitor ===")
    print()
    print(f"Route Status: {result.route_status.value}")
    print(f"Realtime Status: {result.realtime_status.value}")

    if result.route is None or result.bus_leg is None:
        print()
        print("Route planning failed.")
        return

    route = result.route
    bus_leg = result.bus_leg
    print()
    print(f"Total Travel Time: {route.total_time_minutes} min")
    print(f"Walking Distance: {route.walk_distance_meters} m")
    print(f"Boarding Station: {bus_leg.start_station.name}")
    print(f"Alighting Station: {bus_leg.end_station.name}")
    print(f"Bus Candidates: {', '.join(lane.bus_number for lane in bus_leg.lanes)}")
    print(f"Gyeonggi Station ID: {bus_leg.start_station.local_station_id}")
    print()
    print("Realtime Arrivals:")

    if result.realtime_status is RealtimeStatus.UNAVAILABLE:
        print("Realtime information unavailable")
        return
    if result.realtime_status is RealtimeStatus.NO_MATCHING_ARRIVAL:
        print("No matching realtime arrivals for route candidates")
        return
    for arrival in result.arrivals:
        print(f"Bus: {arrival.route_number}")
        print(f"Arrival: {arrival.arrival_seconds} sec (about {arrival.arrival_minutes} min)")
        print(f"Remaining Stops: {arrival.remaining_stops}")
        if arrival.plate_number is not None:
            print(f"Vehicle: {arrival.plate_number}")
        if arrival.remaining_seats is not None:
            print(f"Remaining Seats: {arrival.remaining_seats}")
        if arrival.crowded is not None:
            print(f"Crowded: {arrival.crowded}")
        if arrival.operating_status is not None:
            print(f"Operating Status: {arrival.operating_status}")


def _validate_execution_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    """Return the requested mode after rejecting mixed or incomplete inputs."""
    coordinate_values = (
        args.origin_longitude,
        args.origin_latitude,
        args.destination_longitude,
        args.destination_latitude,
    )
    has_coordinates = any(value is not None for value in coordinate_values)
    has_complete_coordinates = all(value is not None for value in coordinate_values)
    if args.target_id is not None:
        if args.target_id <= 0:
            parser.error("--target-id must be positive")
        if has_coordinates:
            parser.error("--target-id cannot be combined with coordinate arguments")
        return "target"
    if not has_complete_coordinates:
        parser.error("all four coordinate arguments are required when --target-id is absent")
    return "coordinates"


def _run_target(target_id: int) -> int:
    """Run one enabled target, persist the result, and report its snapshot summary."""
    try:
        storage = build_storage()
        target = storage.get_target(target_id)
    except (SQLAlchemyError, ValidationError) as exc:
        print(f"Storage configuration error: {exc.__class__.__name__}", file=sys.stderr)
        return 1

    if target is None:
        print(f"Target not found: {target_id}", file=sys.stderr)
        return 1
    if not target.enabled:
        print(f"Target is disabled: {target.id}", file=sys.stderr)
        return 1

    try:
        pipeline = build_pipeline()
    except (GyeonggiConfigurationError, OdsayConfigurationError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    collected_at = datetime.now(timezone.utc)
    result = pipeline.run(
        float(target.origin_longitude),
        float(target.origin_latitude),
        float(target.destination_longitude),
        float(target.destination_latitude),
    )
    try:
        snapshot = storage.save_snapshot(target.id, result, collected_at=collected_at)
    except (SQLAlchemyError, ValueError) as exc:
        print(f"Storage error: {exc.__class__.__name__}", file=sys.stderr)
        return 1

    _print_snapshot_summary(target, result, snapshot)
    return 0


def _print_snapshot_summary(
    target: BusMonitoringTarget,
    result: BusRouteResult,
    snapshot: BusRouteSnapshot,
) -> None:
    """Render a safe persisted-target result summary without provider payloads."""
    lane_count = 0 if result.bus_leg is None else len(result.bus_leg.lanes)
    print("=== Bus Monitor Persisted Target ===")
    print(f"Target: {target.name} (ID: {target.id})")
    print(f"Route Status: {result.route_status.value}")
    print(f"Realtime Status: {result.realtime_status.value}")
    print(f"Snapshot ID: {snapshot.id}")
    print(f"Lane Count: {lane_count}")
    print(f"Realtime Row Count: {len(result.arrivals)}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the production pipeline once and return its process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    mode = _validate_execution_mode(args, parser)
    if mode == "target":
        assert args.target_id is not None
        return _run_target(args.target_id)

    try:
        pipeline = build_pipeline()
    except (GyeonggiConfigurationError, OdsayConfigurationError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    result = pipeline.run(
        args.origin_longitude,
        args.origin_latitude,
        args.destination_longitude,
        args.destination_latitude,
    )
    print_result(result)
    return 0 if result.route_status is RouteStatus.SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
