"""Fake-provider integration tests for the ODsay and Gyeonggi production pipeline."""

from bus_monitor.gyeonggi import GyeonggiProviderError
from bus_monitor.models import (
    BusLane,
    BusLeg,
    GyeonggiStationRoute,
    RealtimeArrival,
    RealtimeStatus,
    RouteStation,
    RouteStatus,
    TransitRoute,
)
from bus_monitor.odsay import OdsayProviderError
from bus_monitor.pipeline import BusMonitorPipeline


def _route() -> TransitRoute:
    bus_leg = BusLeg(
        start_station=RouteStation("삼평교", "206000542", 37.403789, 127.104252),
        end_station=RouteStation("도착정류장", "228000697", 37.271599, 127.108851),
        duration_minutes=29,
        station_count=4,
        lanes=(
            BusLane("5600", "228000184"),
            BusLane("9241", "228000442"),
        ),
    )
    return TransitRoute(33, 243, 1, (bus_leg,))


def _station_route(route_id: str = "228000184", route_number: str = "5600") -> GyeonggiStationRoute:
    return GyeonggiStationRoute(
        route_id=route_id,
        route_number=route_number,
        route_type_code=11,
        route_type_name="직행좌석형시내버스",
        station_order=90,
        region_name="용인",
    )


def _arrival(route_id: str = "228000184", route_number: str = "5600") -> RealtimeArrival:
    return RealtimeArrival(
        route_id=route_id,
        route_number=route_number,
        arrival_seconds=322,
        remaining_stops=4,
        vehicle_type="일반버스",
        plate_number="경기78아1127",
        remaining_seats=41,
        crowded=1,
        state_code=1,
        operating_status="PASS",
    )


class FakeRouteProvider:
    """Return one configured ODsay route or a controlled provider failure."""

    def __init__(self, route: TransitRoute | None = None, *, fail: bool = False) -> None:
        self._route = route or _route()
        self._fail = fail
        self.calls: list[tuple[float, float, float, float]] = []

    def search_route(
        self,
        origin_longitude: float,
        origin_latitude: float,
        destination_longitude: float,
        destination_latitude: float,
    ) -> TransitRoute:
        """Record coordinates and return the configured ODsay outcome."""
        self.calls.append(
            (origin_longitude, origin_latitude, destination_longitude, destination_latitude)
        )
        if self._fail:
            raise OdsayProviderError("route unavailable")
        return self._route


class FakeGyeonggiProvider:
    """Return configurable Gyeonggi route and arrival data without HTTP calls."""

    def __init__(
        self,
        *,
        station_routes: tuple[GyeonggiStationRoute, ...] = (_station_route(),),
        arrivals: tuple[RealtimeArrival, ...] = (_arrival(),),
        station_route_fail: bool = False,
        arrival_fail: bool = False,
    ) -> None:
        self._station_routes = station_routes
        self._arrivals = arrivals
        self._station_route_fail = station_route_fail
        self._arrival_fail = arrival_fail
        self.station_route_calls: list[str] = []
        self.arrival_calls: list[str] = []
        self.vehicle_location_calls: list[str] = []

    def get_station_routes(self, station_id: str) -> tuple[GyeonggiStationRoute, ...]:
        """Return configured authoritative routes or a controlled provider failure."""
        self.station_route_calls.append(station_id)
        if self._station_route_fail:
            raise GyeonggiProviderError("route lookup unavailable")
        return self._station_routes

    def get_arrivals(self, station_id: str) -> tuple[RealtimeArrival, ...]:
        """Return configured station arrivals or a controlled provider failure."""
        self.arrival_calls.append(station_id)
        if self._arrival_fail:
            raise GyeonggiProviderError("arrival unavailable")
        return self._arrivals

    def get_vehicle_locations(self, route_id: str) -> tuple[object, ...]:
        """Record unexpected vehicle-location calls; Pipeline MVP must not make them."""
        self.vehicle_location_calls.append(route_id)
        return ()


def _pipeline(
    route_provider: FakeRouteProvider | None = None,
    gyeonggi_provider: FakeGyeonggiProvider | None = None,
) -> tuple[BusMonitorPipeline, FakeRouteProvider, FakeGyeonggiProvider]:
    route_provider = route_provider or FakeRouteProvider()
    gyeonggi_provider = gyeonggi_provider or FakeGyeonggiProvider()
    return (
        BusMonitorPipeline(
            route_provider=route_provider,
            realtime_provider=gyeonggi_provider,
        ),
        route_provider,
        gyeonggi_provider,
    )


def _run(pipeline: BusMonitorPipeline):
    return pipeline.run(127.102446246531, 37.4043389599242, 127.10856729001851, 37.27220279535416)


def test_pipeline_returns_full_success_for_a_route_validated_5600_arrival() -> None:
    """A directly validated route ID preserves Gyeonggi realtime and seat details."""
    pipeline, _, gyeonggi = _pipeline()

    result = _run(pipeline)

    assert result.route_status is RouteStatus.SUCCESS
    assert result.realtime_status is RealtimeStatus.SUCCESS
    assert result.resolved_station is None
    assert result.arrivals == (_arrival(),)
    assert gyeonggi.station_route_calls == ["206000542"]
    assert gyeonggi.arrival_calls == ["206000542"]
    assert gyeonggi.vehicle_location_calls == []


def test_pipeline_keeps_only_arrivals_for_authoritative_odsay_lane_matches() -> None:
    """Multiple ODsay lanes may validate while only 5600 currently has an arrival."""
    pipeline, _, _ = _pipeline(
        gyeonggi_provider=FakeGyeonggiProvider(
            station_routes=(_station_route(), _station_route("228000442", "9241")),
            arrivals=(_arrival(), RealtimeArrival("228000999", "9999", 60, 1, None)),
        )
    )

    result = _run(pipeline)

    assert result.realtime_status is RealtimeStatus.SUCCESS
    assert result.arrivals == (_arrival(),)


def test_pipeline_marks_validated_routes_without_current_arrivals_as_normal_empty_state() -> None:
    """A supported 9241 route without a vehicle retains route success."""
    pipeline, _, _ = _pipeline(
        gyeonggi_provider=FakeGyeonggiProvider(
            station_routes=(_station_route("228000442", "9241"),),
            arrivals=(),
        )
    )

    result = _run(pipeline)

    assert result.route_status is RouteStatus.SUCCESS
    assert result.realtime_status is RealtimeStatus.NO_MATCHING_ARRIVAL
    assert result.arrivals == ()


def test_pipeline_returns_unavailable_when_gyeonggi_route_lookup_fails() -> None:
    """An authoritative route lookup failure preserves successful ODsay planning."""
    pipeline, _, gyeonggi = _pipeline(
        gyeonggi_provider=FakeGyeonggiProvider(station_route_fail=True)
    )

    result = _run(pipeline)

    assert result.route_status is RouteStatus.SUCCESS
    assert result.realtime_status is RealtimeStatus.UNAVAILABLE
    assert gyeonggi.arrival_calls == []


def test_pipeline_returns_unavailable_when_no_odsay_lane_is_authoritatively_supported() -> None:
    """A displayed route number never becomes a fallback when route IDs differ."""
    pipeline, _, gyeonggi = _pipeline(
        gyeonggi_provider=FakeGyeonggiProvider(
            station_routes=(_station_route("228000999", "5600"),),
        )
    )

    result = _run(pipeline)

    assert result.realtime_status is RealtimeStatus.UNAVAILABLE
    assert gyeonggi.arrival_calls == []


def test_pipeline_returns_unavailable_when_gyeonggi_arrival_lookup_fails() -> None:
    """Arrival API failures remain distinct from a normal no-current-arrival result."""
    pipeline, _, _ = _pipeline(
        gyeonggi_provider=FakeGyeonggiProvider(arrival_fail=True)
    )

    assert _run(pipeline).realtime_status is RealtimeStatus.UNAVAILABLE


def test_pipeline_short_circuits_gyeonggi_when_odsay_route_provider_fails() -> None:
    """An ODsay failure prevents every Gyeonggi call and leaves realtime unrequested."""
    pipeline, _, gyeonggi = _pipeline(route_provider=FakeRouteProvider(fail=True))

    result = _run(pipeline)

    assert result.route_status is RouteStatus.FAILED
    assert result.realtime_status is RealtimeStatus.NOT_REQUESTED
    assert gyeonggi.station_route_calls == []
    assert gyeonggi.arrival_calls == []
    assert gyeonggi.vehicle_location_calls == []
