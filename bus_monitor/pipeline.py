"""Production orchestration for one ODsay route and Gyeonggi realtime lookup."""

from __future__ import annotations

from typing import Protocol

from bus_monitor.gyeonggi import GyeonggiProviderError
from bus_monitor.models import (
    BusLane,
    BusLeg,
    BusRouteResult,
    GyeonggiStationRoute,
    RealtimeArrival,
    RealtimeStatus,
    RouteStatus,
    TransitRoute,
)
from bus_monitor.odsay import OdsayProviderError


class RouteProvider(Protocol):
    """Minimum route-planning contract required by the bus-monitor pipeline."""

    def search_route(
        self,
        origin_longitude: float,
        origin_latitude: float,
        destination_longitude: float,
        destination_latitude: float,
    ) -> TransitRoute:
        """Return one normalized transit route."""


class RealtimeProvider(Protocol):
    """Minimum Gyeonggi route-validation and arrival contract for the pipeline."""

    def get_station_routes(
        self,
        station_id: str,
    ) -> tuple[GyeonggiStationRoute, ...]:
        """Return authoritative Gyeonggi routes that serve one station."""

    def get_arrivals(self, station_id: str) -> tuple[RealtimeArrival, ...]:
        """Return Gyeonggi realtime arrivals for one station."""


class BusMonitorPipeline:
    """Compose ODsay route planning with Gyeonggi route-validated realtime arrivals."""

    def __init__(
        self,
        *,
        route_provider: RouteProvider,
        realtime_provider: RealtimeProvider,
    ) -> None:
        """Create a pipeline with injected provider dependencies."""
        self._route_provider = route_provider
        self._realtime_provider = realtime_provider

    def run(
        self,
        origin_longitude: float,
        origin_latitude: float,
        destination_longitude: float,
        destination_latitude: float,
    ) -> BusRouteResult:
        """Return one full or partial bus-monitor result for coordinate inputs."""
        try:
            route = self._route_provider.search_route(
                origin_longitude,
                origin_latitude,
                destination_longitude,
                destination_latitude,
            )
        except OdsayProviderError:
            return BusRouteResult(
                route_status=RouteStatus.FAILED,
                realtime_status=RealtimeStatus.NOT_REQUESTED,
            )

        bus_leg = route.bus_legs[0]
        try:
            station_routes = self._realtime_provider.get_station_routes(
                bus_leg.start_station.local_station_id
            )
        except GyeonggiProviderError:
            return self._unavailable_result(route, bus_leg)

        route_ids = _matched_route_ids(bus_leg.lanes, station_routes)
        if not route_ids:
            return self._unavailable_result(route, bus_leg)

        try:
            arrivals = self._realtime_provider.get_arrivals(bus_leg.start_station.local_station_id)
        except GyeonggiProviderError:
            return self._unavailable_result(route, bus_leg)

        matching_arrivals = tuple(arrival for arrival in arrivals if arrival.route_id in route_ids)
        if not matching_arrivals:
            return BusRouteResult(
                route_status=RouteStatus.SUCCESS,
                realtime_status=RealtimeStatus.NO_MATCHING_ARRIVAL,
                route=route,
                bus_leg=bus_leg,
            )
        return BusRouteResult(
            route_status=RouteStatus.SUCCESS,
            realtime_status=RealtimeStatus.SUCCESS,
            route=route,
            bus_leg=bus_leg,
            arrivals=matching_arrivals,
        )

    @staticmethod
    def _unavailable_result(
        route: TransitRoute,
        bus_leg: BusLeg,
    ) -> BusRouteResult:
        """Return route partial success after Gyeonggi lookup unavailability."""
        return BusRouteResult(
            route_status=RouteStatus.SUCCESS,
            realtime_status=RealtimeStatus.UNAVAILABLE,
            route=route,
            bus_leg=bus_leg,
        )


def _matched_route_ids(
    lanes: tuple[BusLane, ...],
    station_routes: tuple[GyeonggiStationRoute, ...],
) -> frozenset[str]:
    """Return Gyeonggi route IDs directly verified for the selected ODsay lanes.

    ``local_route_id`` is compared only with the authoritative Gyeonggi ``route_id``.
    Display route numbers are intentionally not used as a fallback because equal route
    numbers with different IDs are not a safe automatic association.
    """
    route_ids = {route.route_id for route in station_routes}
    return frozenset(lane.local_route_id for lane in lanes if lane.local_route_id in route_ids)
