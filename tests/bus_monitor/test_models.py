"""Unit tests for production bus-monitor domain contracts."""

from bus_monitor.models import (
    BusLane,
    BusLeg,
    BusRouteResult,
    RealtimeArrival,
    RealtimeStatus,
    ResolvedStation,
    RouteStation,
    RouteStatus,
    TransitRoute,
)


def _bus_leg() -> BusLeg:
    return BusLeg(
        start_station=RouteStation("삼평교", "206000542", 37.403789, 127.104252),
        end_station=RouteStation(
            "롯데캐슬스카이.이안두드림.백남준아트센터",
            "228000697",
            37.271599,
            127.108851,
        ),
        duration_minutes=29,
        station_count=4,
        lanes=(
            BusLane("5600", "228000184"),
            BusLane("9241", "228000442"),
            BusLane("5600(예약.평일운행)", "228000420"),
            BusLane("5600(급행하행)", "228000463"),
        ),
    )


def _route(bus_leg: BusLeg) -> TransitRoute:
    return TransitRoute(
        total_time_minutes=33,
        walk_distance_meters=243,
        transfer_count=1,
        bus_legs=(bus_leg,),
    )


def _resolved_station() -> ResolvedStation:
    return ResolvedStation(
        name="삼평교",
        node_id="GGB206000542",
        city_code="31020",
        latitude=37.4039167,
        longitude=127.1041667,
    )


def test_full_success_keeps_route_station_and_realtime_arrival() -> None:
    """A full success preserves all normalized route and realtime contracts."""
    bus_leg = _bus_leg()
    result = BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=RealtimeStatus.SUCCESS,
        route=_route(bus_leg),
        bus_leg=bus_leg,
        resolved_station=_resolved_station(),
        arrivals=(
            RealtimeArrival(
                route_id="GGB204000007",
                route_number="357",
                arrival_seconds=615,
                remaining_stops=8,
                vehicle_type="저상버스",
            ),
        ),
    )

    assert result.route is not None
    assert result.resolved_station is not None
    assert result.arrivals[0].arrival_seconds == 615
    assert result.arrivals[0].arrival_minutes == 10


def test_partial_success_keeps_route_when_realtime_is_unavailable() -> None:
    """A route remains usable when TAGO station or arrival lookup is unavailable."""
    bus_leg = _bus_leg()
    result = BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=RealtimeStatus.UNAVAILABLE,
        route=_route(bus_leg),
        bus_leg=bus_leg,
    )

    assert result.route is not None
    assert result.bus_leg is not None
    assert result.resolved_station is None
    assert result.arrivals == ()


def test_no_matching_arrival_keeps_the_resolved_station() -> None:
    """A station match can succeed even when no selected ODsay lane arrives there."""
    bus_leg = _bus_leg()
    result = BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=RealtimeStatus.NO_MATCHING_ARRIVAL,
        route=_route(bus_leg),
        bus_leg=bus_leg,
        resolved_station=_resolved_station(),
    )

    assert result.resolved_station is not None
    assert result.arrivals == ()


def test_route_failure_does_not_contain_realtime_data() -> None:
    """A failed ODsay route leaves realtime explicitly unrequested."""
    result = BusRouteResult(
        route_status=RouteStatus.FAILED,
        realtime_status=RealtimeStatus.NOT_REQUESTED,
    )

    assert result.route is None
    assert result.bus_leg is None
    assert result.resolved_station is None
    assert result.arrivals == ()


def test_bus_leg_retains_multiple_odsay_lane_candidates() -> None:
    """One bus leg preserves every ODsay lane candidate for later TAGO matching."""
    bus_leg = _bus_leg()

    assert [lane.bus_number for lane in bus_leg.lanes] == [
        "5600",
        "9241",
        "5600(예약.평일운행)",
        "5600(급행하행)",
    ]
    assert [lane.local_route_id for lane in bus_leg.lanes] == [
        "228000184",
        "228000442",
        "228000420",
        "228000463",
    ]
