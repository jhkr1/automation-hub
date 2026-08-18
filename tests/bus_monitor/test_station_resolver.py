"""Unit tests for the pure ODsay-to-TAGO station resolver."""

import pytest

from bus_monitor.models import RouteStation, StationCandidate
from bus_monitor.station_resolver import (
    AmbiguousStationMatchError,
    NoStationCandidateError,
    StationMatchNotFoundError,
    resolve_station,
)


def _route_station(
    *,
    name: str = "삼평교",
    local_station_id: str = "206000542",
    latitude: float = 37.403789,
    longitude: float = 127.104252,
) -> RouteStation:
    return RouteStation(name, local_station_id, latitude, longitude)


def _candidate(
    *,
    name: str = "삼평교",
    node_id: str = "GGB206000542",
    city_code: str = "31020",
    latitude: float = 37.4039167,
    longitude: float = 127.1041667,
) -> StationCandidate:
    return StationCandidate(name, node_id, city_code, latitude, longitude)


def test_resolve_station_returns_authoritative_tago_values_for_a_strong_match() -> None:
    """Near coordinates, matching name, and matching ID suffix resolve one station."""
    resolved = resolve_station(_route_station(), (_candidate(),))

    assert resolved.name == "삼평교"
    assert resolved.node_id == "GGB206000542"
    assert resolved.city_code == "31020"
    assert resolved.latitude == 37.4039167
    assert resolved.longitude == 127.1041667


def test_resolve_station_normalizes_simple_station_name_separators() -> None:
    """Slash and dot spelling differences remain equivalent station names."""
    route_station = _route_station(
        name="이노밸리/포스코DX",
        local_station_id="206000566",
    )
    candidate = _candidate(
        name="이노밸리.포스코DX",
        node_id="GGB206000566",
    )

    assert resolve_station(route_station, (candidate,)).node_id == "GGB206000566"


def test_resolve_station_uses_id_and_coordinates_to_choose_between_same_names() -> None:
    """Opposite-direction stations with equal names are not chosen by name alone."""
    route_station = _route_station()
    correct = _candidate()
    opposite_direction = _candidate(
        node_id="GGB206000543",
        latitude=37.403850,
        longitude=127.104100,
    )

    resolved = resolve_station(route_station, (opposite_direction, correct))

    assert resolved.node_id == "GGB206000542"


def test_resolve_station_accepts_close_id_pattern_match_with_a_name_difference() -> None:
    """A close, matching ID suffix is usable auxiliary evidence despite wording changes."""
    route_station = _route_station(name="판교테크노밸리", local_station_id="206000566")
    candidate = _candidate(
        name="이노밸리.포스코DX",
        node_id="GGB206000566",
        latitude=37.403800,
        longitude=127.104260,
    )

    assert resolve_station(route_station, (candidate,)).node_id == "GGB206000566"


def test_resolve_station_rejects_a_same_name_candidate_that_is_too_far_away() -> None:
    """Name equality alone cannot overcome the geographic match-distance limit."""
    too_far = _candidate(latitude=37.410000, longitude=127.1041667)

    with pytest.raises(StationMatchNotFoundError, match="No TAGO station candidate"):
        resolve_station(_route_station(), (too_far,))


def test_resolve_station_rejects_an_empty_candidate_list() -> None:
    """No TAGO candidates is distinct from candidates that fail matching rules."""
    with pytest.raises(NoStationCandidateError, match="no station candidates"):
        resolve_station(_route_station(), ())


def test_resolve_station_rejects_equally_supported_candidates_as_ambiguous() -> None:
    """Resolver refuses to select arbitrarily when two candidates tie on evidence."""
    first = _candidate(node_id="GGB206000542", latitude=37.403800, longitude=127.104250)
    second = _candidate(node_id="ALT206000542", latitude=37.403801, longitude=127.104251)

    with pytest.raises(AmbiguousStationMatchError, match="match equally"):
        resolve_station(_route_station(), (first, second))


def test_resolve_station_allows_strong_name_and_coordinate_evidence_without_id_pattern() -> None:
    """A prefix-pattern mismatch is not a hard failure when name and distance agree."""
    candidate = _candidate(node_id="GGB999999999")

    assert resolve_station(_route_station(), (candidate,)).node_id == "GGB999999999"
