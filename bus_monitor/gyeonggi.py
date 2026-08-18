"""Production provider for Gyeonggi's official bus information APIs."""

from __future__ import annotations

from typing import Any, Protocol

import requests

from bus_monitor.config import BusMonitorSettings
from bus_monitor.models import (
    GyeonggiStation,
    GyeonggiStationRoute,
    GyeonggiVehicleLocation,
    RealtimeArrival,
)

GYEONGGI_STATION_ENDPOINT = (
    "https://apis.data.go.kr/6410000/busstationservice/v2/busStationInfov2"
)
GYEONGGI_STATION_ROUTE_ENDPOINT = (
    "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationViaRouteListv2"
)
GYEONGGI_ARRIVAL_ENDPOINT = (
    "https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2"
)
GYEONGGI_VEHICLE_LOCATION_ENDPOINT = (
    "https://apis.data.go.kr/6410000/buslocationservice/v2/getBusLocationListv2"
)
SUCCESS_RESULT_CODE = "0"
DEFAULT_TIMEOUT_SECONDS = 10.0

_VEHICLE_TYPE_NAMES = {
    0: "일반버스",
    1: "저상버스",
    2: "2층버스",
    5: "전세버스",
    6: "예약버스",
    7: "트롤리버스",
}


class HttpResponse(Protocol):
    """Minimum response contract used by the Gyeonggi provider."""

    def json(self) -> object:
        """Return the decoded JSON response body."""

    def raise_for_status(self) -> None:
        """Raise an HTTP error for non-successful responses."""


class HttpClient(Protocol):
    """Minimum HTTP client contract used by the Gyeonggi provider."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> HttpResponse:
        """Fetch one URL with query parameters and a timeout."""


class GyeonggiProviderError(RuntimeError):
    """Base error for Gyeonggi production-provider failures."""


class GyeonggiConfigurationError(GyeonggiProviderError):
    """Raised when the Gyeonggi public-data service key is missing."""


class GyeonggiApiError(GyeonggiProviderError):
    """Raised when Gyeonggi returns a non-success API result code."""


class GyeonggiResponseError(GyeonggiProviderError):
    """Raised when a successful Gyeonggi response cannot be normalized safely."""


def _required_text(value: object, field_name: str) -> str:
    """Return required text or numeric identifier data as stripped text."""
    if value is None or not str(value).strip():
        raise GyeonggiResponseError(f"Gyeonggi response field {field_name} is missing or invalid")
    return str(value).strip()


def _optional_text(value: object) -> str | None:
    """Return stripped text or ``None`` for a documented blank response field."""
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _required_non_negative_int(value: object, field_name: str) -> int:
    """Return a required non-negative integer response field."""
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise GyeonggiResponseError(
            f"Gyeonggi response field {field_name} is missing or invalid"
        ) from exc
    if normalized < 0:
        raise GyeonggiResponseError(
            f"Gyeonggi response field {field_name} must not be negative"
        )
    return normalized


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    """Return an optional non-negative integer or ``None`` for a blank field."""
    if value is None or not str(value).strip():
        return None
    return _required_non_negative_int(value, field_name)


def _optional_seat_count(value: object, field_name: str) -> int | None:
    """Normalize the documented ``-1`` unavailable-seat sentinel to ``None``."""
    if value is None or not str(value).strip() or str(value).strip() == "-1":
        return None
    return _required_non_negative_int(value, field_name)


def _required_float(value: object, field_name: str) -> float:
    """Return a required numeric response field as a float."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise GyeonggiResponseError(
            f"Gyeonggi response field {field_name} is missing or invalid"
        ) from exc


class GyeonggiProvider:
    """Fetch normalized station, route, arrival, and vehicle data from Gyeonggi."""

    def __init__(
        self,
        http_client: HttpClient | None = None,
        *,
        service_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Create a provider with an injectable HTTP client and service key."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        configured_key = (
            service_key if service_key is not None else BusMonitorSettings().gyeonggi_service_key
        )
        if configured_key is None or not configured_key.strip():
            raise GyeonggiConfigurationError("GYEONGGI_SERVICE_KEY is not configured")

        self._http_client = http_client or requests.Session()
        self._service_key = configured_key.strip()
        self._timeout = timeout

    def get_station(self, station_id: str) -> GyeonggiStation | None:
        """Return one station detail or ``None`` for a normal empty result."""
        body = self._fetch_body(GYEONGGI_STATION_ENDPOINT, {"stationId": station_id})
        row = body.get("busStationInfo")
        if row is None or row == "":
            return None
        if not isinstance(row, dict):
            raise GyeonggiResponseError("Gyeonggi station detail is invalid")
        return self._station(row)

    def get_station_routes(self, station_id: str) -> tuple[GyeonggiStationRoute, ...]:
        """Return every route that officially serves one station."""
        body = self._fetch_body(GYEONGGI_STATION_ROUTE_ENDPOINT, {"stationId": station_id})
        return tuple(self._station_route(row) for row in self._item_rows(body, "busRouteList"))

    def get_arrivals(self, station_id: str) -> tuple[RealtimeArrival, ...]:
        """Flatten first and second approaching vehicles into normalized arrivals."""
        body = self._fetch_body(GYEONGGI_ARRIVAL_ENDPOINT, {"stationId": station_id})
        arrivals: list[RealtimeArrival] = []
        for row in self._item_rows(body, "busArrivalList"):
            arrivals.extend(self._arrivals_for_route(row))
        return tuple(arrivals)

    def get_vehicle_locations(self, route_id: str) -> tuple[GyeonggiVehicleLocation, ...]:
        """Return station-based current positions for all operating route vehicles."""
        body = self._fetch_body(GYEONGGI_VEHICLE_LOCATION_ENDPOINT, {"routeId": route_id})
        return tuple(
            self._vehicle_location(row) for row in self._item_rows(body, "busLocationList")
        )

    def _fetch_body(self, endpoint: str, parameters: dict[str, str]) -> dict[str, Any]:
        """Fetch one documented Gyeonggi JSON response and validate its envelope."""
        params = {"serviceKey": self._service_key, "format": "json", **parameters}
        try:
            response = self._http_client.get(endpoint, params=params, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GyeonggiProviderError(
                f"Gyeonggi HTTP request failed: {type(exc).__name__}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GyeonggiResponseError("Gyeonggi response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise GyeonggiResponseError("Gyeonggi response root must be an object")

        response_body = payload.get("response")
        if not isinstance(response_body, dict):
            raise GyeonggiResponseError("Gyeonggi response object is missing or invalid")
        header = response_body.get("msgHeader")
        if not isinstance(header, dict):
            raise GyeonggiResponseError("Gyeonggi response header is missing or invalid")
        if str(header.get("resultCode", "")) != SUCCESS_RESULT_CODE:
            code = str(header.get("resultCode", "missing"))
            raise GyeonggiApiError(f"Gyeonggi API returned resultCode {code}")

        body = response_body.get("msgBody")
        if not isinstance(body, dict):
            raise GyeonggiResponseError("Gyeonggi response body is missing or invalid")
        return body

    @staticmethod
    def _item_rows(body: dict[str, Any], item_name: str) -> tuple[dict[str, Any], ...]:
        """Normalize documented list, object, and empty item shapes to row tuples."""
        value = body.get(item_name)
        if value is None or value == "":
            return ()
        if isinstance(value, dict):
            return (value,)
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return tuple(value)
        raise GyeonggiResponseError(f"Gyeonggi response field {item_name} is invalid")

    @staticmethod
    def _station(row: dict[str, Any]) -> GyeonggiStation:
        """Normalize one station-detail response row."""
        return GyeonggiStation(
            station_id=_required_text(row.get("stationId"), "stationId"),
            name=_required_text(row.get("stationName"), "stationName"),
            mobile_number=_optional_text(row.get("mobileNo")),
            region_name=_required_text(row.get("regionName"), "regionName"),
            latitude=_required_float(row.get("y"), "y"),
            longitude=_required_float(row.get("x"), "x"),
        )

    @staticmethod
    def _station_route(row: dict[str, Any]) -> GyeonggiStationRoute:
        """Normalize one authoritative route-to-station lookup row."""
        return GyeonggiStationRoute(
            route_id=_required_text(row.get("routeId"), "routeId"),
            route_number=_required_text(row.get("routeName"), "routeName"),
            route_type_code=_required_non_negative_int(row.get("routeTypeCd"), "routeTypeCd"),
            route_type_name=_required_text(row.get("routeTypeName"), "routeTypeName"),
            station_order=_required_non_negative_int(row.get("staOrder"), "staOrder"),
            region_name=_required_text(row.get("regionName"), "regionName"),
        )

    @classmethod
    def _arrivals_for_route(cls, row: dict[str, Any]) -> tuple[RealtimeArrival, ...]:
        """Flatten up to two approaching-vehicle columns for one route row."""
        route_id = _required_text(row.get("routeId"), "routeId")
        route_number = _required_text(row.get("routeName"), "routeName")
        return tuple(
            arrival
            for index in (1, 2)
            if (
                arrival := cls._arrival_for_vehicle(
                    row,
                    index=index,
                    route_id=route_id,
                    route_number=route_number,
                )
            )
            is not None
        )

    @staticmethod
    def _arrival_for_vehicle(
        row: dict[str, Any],
        *,
        index: int,
        route_id: str,
        route_number: str,
    ) -> RealtimeArrival | None:
        """Normalize one arrival slot, treating blank ETA columns as no current vehicle."""
        seconds = _optional_non_negative_int(row.get(f"predictTimeSec{index}"), "predictTimeSec")
        minutes = _optional_non_negative_int(row.get(f"predictTime{index}"), "predictTime")
        if seconds is None and minutes is None:
            return None
        arrival_seconds = seconds if seconds is not None else minutes * 60
        remaining_stops = _required_non_negative_int(row.get(f"locationNo{index}"), "locationNo")
        vehicle_code = _optional_non_negative_int(row.get(f"lowPlate{index}"), "lowPlate")
        return RealtimeArrival(
            route_id=route_id,
            route_number=route_number,
            arrival_seconds=arrival_seconds,
            remaining_stops=remaining_stops,
            vehicle_type=_VEHICLE_TYPE_NAMES.get(vehicle_code),
            plate_number=_optional_text(row.get(f"plateNo{index}")),
            remaining_seats=_optional_seat_count(row.get(f"remainSeatCnt{index}"), "remainSeatCnt"),
            crowded=_optional_non_negative_int(row.get(f"crowded{index}"), "crowded"),
            state_code=_optional_non_negative_int(row.get(f"stateCd{index}"), "stateCd"),
            operating_status=_optional_text(row.get("flag")),
        )

    @staticmethod
    def _vehicle_location(row: dict[str, Any]) -> GyeonggiVehicleLocation:
        """Normalize one station-based vehicle-location response row."""
        return GyeonggiVehicleLocation(
            route_id=_required_text(row.get("routeId"), "routeId"),
            station_id=_required_text(row.get("stationId"), "stationId"),
            station_sequence=_required_non_negative_int(row.get("stationSeq"), "stationSeq"),
            vehicle_id=_required_text(row.get("vehId"), "vehId"),
            plate_number=_optional_text(row.get("plateNo")),
            remaining_seats=_optional_seat_count(row.get("remainSeatCnt"), "remainSeatCnt"),
            crowded=_optional_non_negative_int(row.get("crowded"), "crowded"),
            state_code=_optional_non_negative_int(row.get("stateCd"), "stateCd"),
        )
