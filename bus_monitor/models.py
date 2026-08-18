"""Production domain contracts for the bus-monitor pipeline.

These models contain normalized provider results only. HTTP responses, API keys, and
provider-specific raw payloads remain outside this module.
"""

from dataclasses import dataclass
from enum import Enum


class RouteStatus(str, Enum):
    """Whether route planning produced a usable bus route."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RealtimeStatus(str, Enum):
    """Whether realtime information is available for a planned route."""

    SUCCESS = "SUCCESS"
    UNAVAILABLE = "UNAVAILABLE"
    NO_MATCHING_ARRIVAL = "NO_MATCHING_ARRIVAL"
    NOT_REQUESTED = "NOT_REQUESTED"


def _require_text(value: str, field_name: str) -> None:
    """Validate one required normalized text field."""
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_non_negative(value: int, field_name: str) -> None:
    """Validate one required non-negative integer field."""
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class RouteStation:
    """A bus stop as identified by ODsay within a selected route."""

    name: str
    local_station_id: str
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        """Validate the station data required by the Station Resolver."""
        _require_text(self.name, "name")
        _require_text(self.local_station_id, "local_station_id")
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be a valid WGS84 latitude")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be a valid WGS84 longitude")


@dataclass(frozen=True)
class BusLane:
    """One ODsay bus-lane candidate for a bus leg."""

    bus_number: str
    local_route_id: str

    def __post_init__(self) -> None:
        """Validate the ODsay fields retained for TAGO arrival matching."""
        _require_text(self.bus_number, "bus_number")
        _require_text(self.local_route_id, "local_route_id")


@dataclass(frozen=True)
class BusLeg:
    """One bus movement segment selected from an ODsay route option."""

    start_station: RouteStation
    end_station: RouteStation
    duration_minutes: int
    station_count: int
    lanes: tuple[BusLane, ...]

    def __post_init__(self) -> None:
        """Validate that the leg can be resolved and matched to an arrival."""
        _require_non_negative(self.duration_minutes, "duration_minutes")
        _require_non_negative(self.station_count, "station_count")
        if not self.lanes:
            raise ValueError("lanes must contain at least one bus candidate")


@dataclass(frozen=True)
class TransitRoute:
    """One ODsay route option retaining only its bus legs and summary metrics."""

    total_time_minutes: int
    walk_distance_meters: int
    transfer_count: int
    bus_legs: tuple[BusLeg, ...]

    def __post_init__(self) -> None:
        """Validate normalized route summary values."""
        _require_non_negative(self.total_time_minutes, "total_time_minutes")
        _require_non_negative(self.walk_distance_meters, "walk_distance_meters")
        _require_non_negative(self.transfer_count, "transfer_count")


@dataclass(frozen=True)
class ResolvedStation:
    """A TAGO station verified by the Station Resolver."""

    name: str
    node_id: str
    city_code: str
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        """Validate the TAGO identifiers needed by the Arrival Provider."""
        _require_text(self.name, "name")
        _require_text(self.node_id, "node_id")
        _require_text(self.city_code, "city_code")
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be a valid WGS84 latitude")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be a valid WGS84 longitude")


@dataclass(frozen=True)
class StationCandidate:
    """One TAGO station candidate awaiting Station Resolver verification."""

    name: str
    node_id: str
    city_code: str
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        """Validate identifiers and coordinates returned by TAGO Station API."""
        _require_text(self.name, "name")
        _require_text(self.node_id, "node_id")
        _require_text(self.city_code, "city_code")
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be a valid WGS84 latitude")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be a valid WGS84 longitude")


@dataclass(frozen=True)
class RealtimeArrival:
    """One normalized approaching vehicle for a bus route at a station."""

    route_id: str
    route_number: str
    arrival_seconds: int
    remaining_stops: int
    vehicle_type: str | None
    plate_number: str | None = None
    remaining_seats: int | None = None
    crowded: int | None = None
    state_code: int | None = None
    operating_status: str | None = None

    def __post_init__(self) -> None:
        """Keep provider seconds as the canonical arrival duration."""
        _require_text(self.route_id, "route_id")
        _require_text(self.route_number, "route_number")
        if self.vehicle_type is not None:
            _require_text(self.vehicle_type, "vehicle_type")
        if self.plate_number is not None:
            _require_text(self.plate_number, "plate_number")
        _require_non_negative(self.arrival_seconds, "arrival_seconds")
        _require_non_negative(self.remaining_stops, "remaining_stops")
        if self.remaining_seats is not None:
            _require_non_negative(self.remaining_seats, "remaining_seats")
        if self.crowded is not None:
            _require_non_negative(self.crowded, "crowded")
        if self.state_code is not None:
            _require_non_negative(self.state_code, "state_code")
        if self.operating_status is not None:
            _require_text(self.operating_status, "operating_status")

    @property
    def arrival_minutes(self) -> int:
        """Return a presentation-friendly whole-minute duration derived from seconds."""
        return self.arrival_seconds // 60


@dataclass(frozen=True)
class GyeonggiStation:
    """One Gyeonggi bus station returned by the official station API."""

    station_id: str
    name: str
    mobile_number: str | None
    region_name: str
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        """Validate a station identifier, display data, and WGS84 coordinates."""
        _require_text(self.station_id, "station_id")
        _require_text(self.name, "name")
        if self.mobile_number is not None:
            _require_text(self.mobile_number, "mobile_number")
        _require_text(self.region_name, "region_name")
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be a valid WGS84 latitude")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be a valid WGS84 longitude")


@dataclass(frozen=True)
class GyeonggiStationRoute:
    """One route that officially serves a Gyeonggi station."""

    route_id: str
    route_number: str
    route_type_code: int
    route_type_name: str
    station_order: int
    region_name: str

    def __post_init__(self) -> None:
        """Validate the authoritative route-to-station association."""
        _require_text(self.route_id, "route_id")
        _require_text(self.route_number, "route_number")
        _require_non_negative(self.route_type_code, "route_type_code")
        _require_text(self.route_type_name, "route_type_name")
        _require_non_negative(self.station_order, "station_order")
        _require_text(self.region_name, "region_name")


@dataclass(frozen=True)
class GyeonggiVehicleLocation:
    """One bus vehicle's current station-based position in Gyeonggi."""

    route_id: str
    station_id: str
    station_sequence: int
    vehicle_id: str
    plate_number: str | None = None
    remaining_seats: int | None = None
    crowded: int | None = None
    state_code: int | None = None

    def __post_init__(self) -> None:
        """Validate the station-based vehicle position contract."""
        _require_text(self.route_id, "route_id")
        _require_text(self.station_id, "station_id")
        _require_non_negative(self.station_sequence, "station_sequence")
        _require_text(self.vehicle_id, "vehicle_id")
        if self.plate_number is not None:
            _require_text(self.plate_number, "plate_number")
        if self.remaining_seats is not None:
            _require_non_negative(self.remaining_seats, "remaining_seats")
        if self.crowded is not None:
            _require_non_negative(self.crowded, "crowded")
        if self.state_code is not None:
            _require_non_negative(self.state_code, "state_code")


@dataclass(frozen=True)
class BusRouteResult:
    """Final pipeline result supporting both full and partial success."""

    route_status: RouteStatus
    realtime_status: RealtimeStatus
    route: TransitRoute | None = None
    bus_leg: BusLeg | None = None
    resolved_station: ResolvedStation | None = None
    arrivals: tuple[RealtimeArrival, ...] = ()

    def __post_init__(self) -> None:
        """Enforce valid state combinations without hiding partial route success."""
        if self.route_status is RouteStatus.FAILED:
            if self.realtime_status is not RealtimeStatus.NOT_REQUESTED:
                raise ValueError("a failed route must not request realtime information")
            if any((self.route, self.bus_leg, self.resolved_station, self.arrivals)):
                raise ValueError("a failed route result must not contain route or realtime data")
            return

        if self.route is None or self.bus_leg is None:
            raise ValueError("a successful route result requires route and bus_leg")
        if self.bus_leg not in self.route.bus_legs:
            raise ValueError("bus_leg must belong to route.bus_legs")
        if self.realtime_status is RealtimeStatus.NOT_REQUESTED:
            raise ValueError("a successful route must attempt realtime resolution")
        if self.realtime_status is RealtimeStatus.SUCCESS:
            if not self.arrivals:
                raise ValueError("successful realtime requires at least one arrival")
        elif self.realtime_status is RealtimeStatus.NO_MATCHING_ARRIVAL:
            if self.arrivals:
                raise ValueError("no matching arrival must not contain arrival rows")
        elif self.realtime_status is RealtimeStatus.UNAVAILABLE and self.arrivals:
            raise ValueError("unavailable realtime must not contain arrival rows")
