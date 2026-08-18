"""Pure resolver for matching ODsay stations to TAGO station candidates."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from bus_monitor.models import ResolvedStation, RouteStation, StationCandidate

EARTH_RADIUS_METERS = 6_371_000.0
MAX_MATCH_DISTANCE_METERS = 100.0
VERY_CLOSE_DISTANCE_METERS = 50.0
AMBIGUITY_DISTANCE_DELTA_METERS = 5.0
_NAME_SEPARATOR_PATTERN = re.compile(r"[\s./·()\[\]{}_-]+")
_NUMERIC_SUFFIX_PATTERN = re.compile(r"(\d+)$")


class StationResolverError(RuntimeError):
    """Base error for deterministic ODsay-to-TAGO station resolution failures."""


class NoStationCandidateError(StationResolverError):
    """Raised when TAGO returned no nearby station candidates."""


class StationMatchNotFoundError(StationResolverError):
    """Raised when no nearby candidate has sufficient matching evidence."""


class AmbiguousStationMatchError(StationResolverError):
    """Raised when multiple candidates have effectively equal match evidence."""


@dataclass(frozen=True)
class _Match:
    """Internal candidate evidence used only for deterministic selection."""

    candidate: StationCandidate
    distance_meters: float
    name_matches: bool
    id_matches: bool

    @property
    def rank(self) -> int | None:
        """Return a lower-is-stronger rank only for sufficiently safe matches."""
        if self.distance_meters <= VERY_CLOSE_DISTANCE_METERS:
            if self.name_matches and self.id_matches:
                return 0
            if self.name_matches:
                return 1
            if self.id_matches:
                return 2
        return None


def _distance_meters(first: RouteStation, second: StationCandidate) -> float:
    """Calculate Haversine distance between two WGS84 coordinates in meters."""
    latitude_delta = radians(second.latitude - first.latitude)
    longitude_delta = radians(second.longitude - first.longitude)
    first_latitude = radians(first.latitude)
    second_latitude = radians(second.latitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(first_latitude) * cos(second_latitude) * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(haversine))


def _normalize_name(value: str) -> str:
    """Normalize simple station-name separator differences without fuzzy matching."""
    return _NAME_SEPARATOR_PATTERN.sub("", unicodedata.normalize("NFKC", value).casefold())


def _numeric_suffix(value: str) -> str | None:
    """Return an identifier's terminal numeric part for auxiliary evidence only."""
    match = _NUMERIC_SUFFIX_PATTERN.search(value)
    return match.group(1) if match else None


def _id_pattern_matches(route_station: RouteStation, candidate: StationCandidate) -> bool:
    """Compare numeric ID suffixes without treating a provider prefix as a contract."""
    route_suffix = _numeric_suffix(route_station.local_station_id)
    candidate_suffix = _numeric_suffix(candidate.node_id)
    return route_suffix is not None and route_suffix == candidate_suffix


def _matched_candidates(
    route_station: RouteStation,
    candidates: tuple[StationCandidate, ...],
) -> list[_Match]:
    """Collect nearby candidates whose combined evidence satisfies resolver policy."""
    route_name = _normalize_name(route_station.name)
    matches: list[_Match] = []
    for candidate in candidates:
        distance_meters = _distance_meters(route_station, candidate)
        if distance_meters > MAX_MATCH_DISTANCE_METERS:
            continue
        match = _Match(
            candidate=candidate,
            distance_meters=distance_meters,
            name_matches=route_name == _normalize_name(candidate.name),
            id_matches=_id_pattern_matches(route_station, candidate),
        )
        if match.rank is not None:
            matches.append(match)
    return matches


def resolve_station(
    route_station: RouteStation,
    candidates: tuple[StationCandidate, ...],
) -> ResolvedStation:
    """Resolve one ODsay station using TAGO coordinates, name, and ID evidence.

    The TAGO node-id numeric suffix is a strong auxiliary signal, but a match always
    also requires geographic proximity and either matching name or ID evidence.
    """
    if not candidates:
        raise NoStationCandidateError("TAGO returned no station candidates")

    matches = _matched_candidates(route_station, candidates)
    if not matches:
        raise StationMatchNotFoundError("No TAGO station candidate matched the ODsay station")

    matches.sort(key=lambda match: (match.rank, match.distance_meters))
    best_match = matches[0]
    competing_matches = [
        match
        for match in matches[1:]
        if match.rank == best_match.rank
        and abs(match.distance_meters - best_match.distance_meters)
        <= AMBIGUITY_DISTANCE_DELTA_METERS
    ]
    if competing_matches:
        raise AmbiguousStationMatchError("Multiple TAGO station candidates match equally")

    candidate = best_match.candidate
    return ResolvedStation(
        name=candidate.name,
        node_id=candidate.node_id,
        city_code=candidate.city_code,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
    )
