"""Unit tests for pure ODsay bus-lane to TAGO arrival matching."""

from bus_monitor.arrival_matcher import match_arrivals
from bus_monitor.models import BusLane, RealtimeArrival


def _lane(
    bus_number: str = "5600",
    local_route_id: str = "204000007",
) -> BusLane:
    return BusLane(bus_number, local_route_id)


def _arrival(
    route_number: str = "5600",
    route_id: str = "GGB204000007",
    arrival_seconds: int = 615,
) -> RealtimeArrival:
    return RealtimeArrival(
        route_id=route_id,
        route_number=route_number,
        arrival_seconds=arrival_seconds,
        remaining_stops=8,
        vehicle_type="저상버스",
    )


def test_match_arrivals_returns_a_strong_route_number_and_id_suffix_match() -> None:
    """Both display-number and route-ID evidence are required for a match."""
    assert match_arrivals((_lane(),), (_arrival(),)) == (_arrival(),)


def test_match_arrivals_preserves_multiple_matching_arrivals_in_tago_order() -> None:
    """Two approaching vehicles remain available without locally ranking them."""
    arrivals = (_arrival(arrival_seconds=2310), _arrival(arrival_seconds=615))

    assert match_arrivals((_lane(),), arrivals) == arrivals


def test_match_arrivals_rejects_a_route_number_match_with_a_different_id_suffix() -> None:
    """A shared display number alone is insufficient for an automatic match."""
    assert match_arrivals((_lane(),), (_arrival(route_id="GGB204000008"),)) == ()


def test_match_arrivals_rejects_an_id_suffix_match_with_a_different_route_number() -> None:
    """A shared ID suffix alone is insufficient for an automatic match."""
    assert match_arrivals((_lane(),), (_arrival(route_number="5600(급행)"),)) == ()


def test_match_arrivals_returns_empty_tuple_when_no_evidence_matches() -> None:
    """Unrelated lanes and arrivals do not create a guessed association."""
    assert match_arrivals((_lane(),), (_arrival("357", "GGB204000099"),)) == ()


def test_match_arrivals_matches_only_present_lanes_from_multiple_candidates() -> None:
    """All matching arrivals from any ODsay lane are retained in TAGO response order."""
    lanes = (_lane("5600", "204000007"), _lane("9241", "204000073"))
    matching_9241 = _arrival("9241", "GGB204000073", arrival_seconds=100)
    unrelated = _arrival("357", "GGB204000099", arrival_seconds=50)
    matching_5600 = _arrival("5600", "GGB204000007", arrival_seconds=300)

    assert match_arrivals(lanes, (matching_9241, unrelated, matching_5600)) == (
        matching_9241,
        matching_5600,
    )
